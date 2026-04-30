"""
Unit tests for ``flag_logic.py``.

These tests run without Django setup — they exercise pure-Python flag
computation against synthetic fixtures. The fixtures intentionally hit
threshold boundaries to catch off-by-one regressions when porting from
the JS source at ``workflow/templates/kmc_flw_flags.py``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from commcare_connect.custom_analysis.kmc_audit import flag_logic
from commcare_connect.custom_analysis.kmc_audit.flag_logic import (
    ALL_FLAGS,
    FLWFlagResult,
    MIN_CASES,
    PRIORITY_FLAGS,
    SECONDARY_FLAGS,
    THRESHOLDS,
    compute_case_metrics,
    compute_enrollment_metrics,
    compute_round_weight_pct,
    compute_weight_metrics,
    derive_flags,
    visit_flag_sources,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def make_visit(case_id: str, day_offset: int, weight: float | None = None,
               kmc_status: str | None = None, reg_date: date | None = None,
               discharge_date: date | None = None, **extra) -> dict:
    base = date(2026, 1, 1)
    return {
        "username": extra.get("username", "flw1"),
        "beneficiary_case_id": case_id,
        "visit_date": (base + timedelta(days=day_offset)).isoformat(),
        "weight": weight,
        "kmc_status": kmc_status,
        "reg_date": reg_date.isoformat() if reg_date else None,
        "discharge_date": discharge_date.isoformat() if discharge_date else None,
        **{k: v for k, v in extra.items() if k != "username"},
    }


def make_aggregated_row(**kwargs) -> dict:
    """Match the AGGREGATED pipeline output shape (minimal fields)."""
    return {
        "username": "flw1",
        "total_cases": 0,
        "deaths": 0,
        "total_visits": 0,
        "danger_visit_count": 0,
        "danger_positive_count": 0,
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Tier mapping sanity
# ---------------------------------------------------------------------------


def test_priority_tier_has_six_flags():
    assert len(PRIORITY_FLAGS) == 6


def test_secondary_tier_plus_priority_covers_all_real_flags():
    # flag_mort is synthetic; everything else in PRIORITY + SECONDARY should be in ALL_FLAGS.
    real_priority = [f for f in PRIORITY_FLAGS if f != "flag_mort"]
    real_secondary = list(SECONDARY_FLAGS)
    union = set(real_priority) | set(real_secondary)
    assert union <= set(ALL_FLAGS)
    assert len(ALL_FLAGS) == 16


def test_thresholds_cover_all_real_flags():
    # Each non-synthetic flag must have a threshold and min-cases entry.
    for flag in ALL_FLAGS:
        key = flag.replace("flag_", "")
        # Combined mort uses mort_low/mort_high keys; danger flags use sub-keys
        if key.startswith("mort_"):
            continue
        if key in ("hr_copycat", "round_weight", "temp_copycat", "spo2_implausible",
                   "ga_fullterm", "gps_same_case_far", "ds_no_referral",
                   "wt_loss", "wt_gain", "wt_zero", "danger_high", "danger_zero",
                   "enroll", "visits"):
            assert key in THRESHOLDS, f"{flag}: missing THRESHOLD"


# ---------------------------------------------------------------------------
# compute_weight_metrics
# ---------------------------------------------------------------------------


def test_weight_metrics_empty():
    out = compute_weight_metrics([])
    assert out == {"pct_wt_loss": None, "mean_daily_gain": None,
                   "pct_wt_zero": None, "weight_pairs": 0}


def test_weight_metrics_pair_outside_window_is_skipped():
    # 35-day gap exceeds the 30-day pair-eligibility window.
    visits = [
        make_visit("case1", 0, weight=2000.0),
        make_visit("case1", 35, weight=2200.0),
    ]
    out = compute_weight_metrics(visits)
    assert out["weight_pairs"] == 0


def test_weight_metrics_zero_change_pair():
    visits = [
        make_visit("case1", 0, weight=2000.0),
        make_visit("case1", 5, weight=2000.0),
    ]
    out = compute_weight_metrics(visits)
    assert out["weight_pairs"] == 1
    assert out["pct_wt_zero"] == pytest.approx(1.0)
    assert out["pct_wt_loss"] == pytest.approx(0.0)
    assert out["mean_daily_gain"] == pytest.approx(0.0)


def test_weight_metrics_loss_pair_counts_correctly():
    visits = [
        make_visit("case1", 0, weight=2000.0),
        make_visit("case1", 5, weight=1900.0),
    ]
    out = compute_weight_metrics(visits)
    assert out["pct_wt_loss"] == pytest.approx(1.0)
    assert out["mean_daily_gain"] == pytest.approx(-20.0)


def test_weight_metrics_extreme_weight_filtered_out():
    # 6000g exceeds the 500-5000g eligibility band — both readings should be ignored.
    visits = [
        make_visit("case1", 0, weight=6000.0),
        make_visit("case1", 5, weight=2000.0),
    ]
    out = compute_weight_metrics(visits)
    assert out["weight_pairs"] == 0


def test_weight_metrics_twins_segregated_by_case_id():
    # Two distinct beneficiary_case_ids must be paired independently.
    visits = [
        make_visit("twin_a", 0, weight=2000.0),
        make_visit("twin_b", 1, weight=1500.0),
        make_visit("twin_a", 5, weight=2100.0),  # only this pair is valid
    ]
    out = compute_weight_metrics(visits)
    assert out["weight_pairs"] == 1


# ---------------------------------------------------------------------------
# compute_enrollment_metrics
# ---------------------------------------------------------------------------


def test_enrollment_late_when_reg_more_than_8_days_after_discharge():
    cases = []
    # 12 cases: 5 late, 7 on-time. Min 10 needed for the rate to be returned.
    for i in range(5):
        cases.append(make_visit(
            f"late_{i}", 0,
            reg_date=date(2026, 1, 20),
            discharge_date=date(2026, 1, 1),  # 19-day gap = late
        ))
    for i in range(7):
        cases.append(make_visit(
            f"ontime_{i}", 0,
            reg_date=date(2026, 1, 5),
            discharge_date=date(2026, 1, 1),  # 4-day gap = on time
        ))
    out = compute_enrollment_metrics(cases)
    assert out["cases_with_dates"] == 12
    assert out["pct_late_enroll"] == pytest.approx(5 / 12)


def test_enrollment_returns_none_when_below_min_cases():
    # Only 9 cases with both dates — below MIN_CASES["enroll"] (10).
    cases = [
        make_visit(f"case_{i}", 0,
                   reg_date=date(2026, 1, 20),
                   discharge_date=date(2026, 1, 1))
        for i in range(9)
    ]
    out = compute_enrollment_metrics(cases)
    assert out["pct_late_enroll"] is None


# ---------------------------------------------------------------------------
# compute_case_metrics
# ---------------------------------------------------------------------------


def test_case_metrics_only_latest_status_counted():
    # Two visits for the same case: earlier shows discharged, later shows deceased.
    visits = [
        make_visit("case1", 0, kmc_status="discharged"),
        make_visit("case1", 10, kmc_status="deceased"),
    ]
    out = compute_case_metrics(visits)
    assert out["closed_cases"] == 1
    assert out["non_mort_closed"] == 0  # final status was deceased


def test_case_metrics_open_cases_not_counted_as_closed():
    visits = [make_visit("case1", 0, kmc_status="active")]
    out = compute_case_metrics(visits)
    assert out["closed_cases"] == 0


# ---------------------------------------------------------------------------
# compute_round_weight_pct
# ---------------------------------------------------------------------------


def test_round_weight_pct_below_min_data():
    visits = [make_visit("case1", i, weight=2000.0) for i in range(MIN_CASES["round_weight"] - 1)]
    pct, n = compute_round_weight_pct(visits)
    assert pct is None
    assert n == MIN_CASES["round_weight"] - 1


def test_round_weight_pct_all_rounded():
    # 25 weights, all multiples of 100g.
    visits = [make_visit(f"case_{i}", i, weight=1500.0 + (i * 100)) for i in range(25)]
    pct, n = compute_round_weight_pct(visits)
    assert pct == pytest.approx(1.0)
    assert n == 25


def test_round_weight_pct_mixed():
    # 20 weights: 16 round (= 80%), 4 non-round.
    weights = [1500.0] * 16 + [1523.0, 1547.0, 1612.0, 1689.0]
    visits = [make_visit(f"case_{i}", i, weight=w) for i, w in enumerate(weights)]
    pct, n = compute_round_weight_pct(visits)
    assert pct == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# derive_flags — integration of the above
# ---------------------------------------------------------------------------


def test_derive_flags_excludes_low_volume_flw():
    aggregated = make_aggregated_row(total_cases=MIN_CASES["exclude"] - 1)
    result = derive_flags(aggregated, [])
    assert result.excluded is True
    # All flags including synthetic are None (not False) when excluded
    for f in ALL_FLAGS:
        assert result.flags[f] is None
    assert result.flags["flag_mort"] is None


def test_derive_flags_low_visits_fires():
    aggregated = make_aggregated_row(total_cases=30, total_visits=20)
    # Build 10 distinct closed non-mortality cases, but only 20 total visits
    # → avg visits per non-mort closed = 2.0, below the 3.0 threshold.
    visits = []
    for i in range(10):
        cid = f"c{i}"
        visits.append(make_visit(cid, 0, weight=2000.0, kmc_status="discharged"))
        visits.append(make_visit(cid, 5, weight=2050.0, kmc_status="discharged"))
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_visits"] is True


def test_derive_flags_high_mortality_fires():
    aggregated = make_aggregated_row(total_cases=20, deaths=5)  # 25%
    result = derive_flags(aggregated, [])
    assert result.flags["flag_mort_high"] is True
    assert result.flags["flag_mort"] is True  # synthetic — fires when either component fires


def test_derive_flags_low_mortality_fires():
    aggregated = make_aggregated_row(total_cases=200, deaths=1)  # 0.5% < 2%
    result = derive_flags(aggregated, [])
    assert result.flags["flag_mort_low"] is True
    assert result.flags["flag_mort"] is True


def test_derive_flags_zero_danger_fires():
    aggregated = make_aggregated_row(
        total_cases=50, danger_visit_count=40, danger_positive_count=0,
    )
    result = derive_flags(aggregated, [])
    assert result.flags["flag_danger_zero"] is True


def test_derive_flags_high_danger_fires():
    aggregated = make_aggregated_row(
        total_cases=50, danger_visit_count=40, danger_positive_count=20,  # 50%
    )
    result = derive_flags(aggregated, [])
    assert result.flags["flag_danger_high"] is True


def test_derive_flags_unknown_secondary_flags_are_none_not_false():
    aggregated = make_aggregated_row(total_cases=50)
    # No heart_rate / temperature / etc. fields in visits → those flags should be None.
    visits = [make_visit(f"c{i}", 0, weight=2000.0, kmc_status="discharged") for i in range(15)]
    result = derive_flags(aggregated, visits)
    # flag_round_weight: 15 weights all = 2000 (round) → fires, not None
    # But the other 6 secondary flags (HR, temp, SpO2, GA, GPS, referral) should be None
    # since their underlying fields are missing from the visits.
    assert result.flags["flag_hr_copycat"] is None
    assert result.flags["flag_temp_copycat"] is None
    assert result.flags["flag_spo2_implausible"] is None
    assert result.flags["flag_ga_fullterm"] is None
    assert result.flags["flag_gps_same_case_far"] is None
    assert result.flags["flag_ds_no_referral"] is None


def test_derive_flags_round_weight_works_with_visit_data_only():
    # 25 visits, all weights are exact 100g multiples → flag_round_weight fires.
    aggregated = make_aggregated_row(total_cases=50)
    visits = [make_visit(f"c{i}", i, weight=1800.0) for i in range(25)]
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_round_weight"] is True


def test_priority_flag_count_uses_synthetic_mort():
    aggregated = make_aggregated_row(total_cases=20, deaths=5)
    result = derive_flags(aggregated, [])
    # flag_mort is a priority flag; both flag_mort_low and flag_mort_high are secondary.
    # flag_mort fires (because high) but is counted ONCE in priority count.
    assert result.flags["flag_mort"] is True
    assert result.priority_flag_count >= 1


# ---------------------------------------------------------------------------
# visit_flag_sources
# ---------------------------------------------------------------------------


def test_visit_flag_sources_marks_round_weight_visits():
    visits = [make_visit(f"c{i}", i, weight=1800.0) for i in range(25)]
    result = FLWFlagResult(
        username="flw1",
        excluded=False,
        flags={f: False for f in ALL_FLAGS} | {"flag_round_weight": True, "flag_mort": False},
    )
    annotated = visit_flag_sources(visits, result)
    # Every annotated visit should mention flag_round_weight (all weights are 1800g multiples of 100).
    for row in annotated:
        assert "flag_round_weight" in row["flag_sources"]


def test_visit_flag_sources_returns_empty_sources_when_no_flag_fires():
    visits = [make_visit(f"c{i}", i, weight=2000.0) for i in range(5)]
    result = FLWFlagResult(
        username="flw1",
        excluded=False,
        flags={f: False for f in ALL_FLAGS} | {"flag_mort": False},
    )
    annotated = visit_flag_sources(visits, result)
    for row in annotated:
        assert row["flag_sources"] == []
