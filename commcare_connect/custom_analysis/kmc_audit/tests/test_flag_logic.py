"""
Unit tests for ``flag_logic.py``.

These tests exercise pure-Python flag computation against synthetic
fixtures; no Django setup required. Fixtures intentionally hit
threshold boundaries to catch off-by-one regressions when porting
from the JS source at ``workflow/templates/kmc_flw_flags.py``.

Source of truth for thresholds and rules: the
"Overview of KMC flags [March 2026]" doc.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from commcare_connect.custom_analysis.kmc_audit.flag_logic import (
    ALL_FLAGS,
    MIN_CASES,
    PRIORITY_FLAGS,
    SECONDARY_FLAGS,
    FLWFlagResult,
    compute_avg_visits_top_50,
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


def make_visit(
    case_id: str,
    day_offset: int,
    weight: float | None = None,
    kmc_status: str | None = None,
    child_alive: str | None = None,
    reg_date: date | None = None,
    discharge_date: date | None = None,
    **extra,
) -> dict:
    base = date(2026, 1, 1)
    return {
        "username": extra.get("username", "flw1"),
        "beneficiary_case_id": case_id,
        "visit_date": (base + timedelta(days=day_offset)).isoformat(),
        "weight": weight,
        "kmc_status": kmc_status,
        "child_alive": child_alive,
        "reg_date": reg_date.isoformat() if reg_date else None,
        "discharge_date": discharge_date.isoformat() if discharge_date else None,
        **{k: v for k, v in extra.items() if k != "username"},
    }


def make_aggregated_row(**kwargs) -> dict:
    """Match the AGGREGATED pipeline output shape (minimal fields)."""
    return {
        "username": "flw1",
        "total_cases": 0,
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
    # Synthetics (flag_mort, flag_data_quality) are NOT in ALL_FLAGS — they're
    # derived from the base 16 computed flags. Priority + secondary should cover
    # all base flags once synthetics are excluded.
    synthetics = {"flag_mort", "flag_data_quality"}
    real_priority = [f for f in PRIORITY_FLAGS if f not in synthetics]
    real_secondary = list(SECONDARY_FLAGS)
    union = set(real_priority) | set(real_secondary)
    assert union <= set(ALL_FLAGS)
    assert len(ALL_FLAGS) == 16


# ---------------------------------------------------------------------------
# compute_weight_metrics
# ---------------------------------------------------------------------------


def test_weight_metrics_empty():
    out = compute_weight_metrics([])
    assert out == {"pct_wt_loss": None, "mean_daily_gain": None, "pct_wt_zero": None, "weight_pairs": 0}


def test_weight_metrics_pair_outside_window_is_skipped():
    visits = [
        make_visit("case1", 0, weight=2000.0),
        make_visit("case1", 35, weight=2200.0),
    ]
    assert compute_weight_metrics(visits)["weight_pairs"] == 0


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
    visits = [
        make_visit("case1", 0, weight=6000.0),
        make_visit("case1", 5, weight=2000.0),
    ]
    assert compute_weight_metrics(visits)["weight_pairs"] == 0


def test_weight_metrics_twins_segregated_by_case_id():
    visits = [
        make_visit("twin_a", 0, weight=2000.0),
        make_visit("twin_b", 1, weight=1500.0),
        make_visit("twin_a", 5, weight=2100.0),
    ]
    assert compute_weight_metrics(visits)["weight_pairs"] == 1


# ---------------------------------------------------------------------------
# compute_enrollment_metrics
# ---------------------------------------------------------------------------


def test_enrollment_late_when_reg_more_than_8_days_after_discharge():
    cases = []
    for i in range(5):
        cases.append(
            make_visit(
                f"late_{i}",
                0,
                reg_date=date(2026, 1, 20),
                discharge_date=date(2026, 1, 1),
            )
        )
    for i in range(7):
        cases.append(
            make_visit(
                f"ontime_{i}",
                0,
                reg_date=date(2026, 1, 5),
                discharge_date=date(2026, 1, 1),
            )
        )
    out = compute_enrollment_metrics(cases)
    assert out["cases_with_dates"] == 12
    assert out["pct_late_enroll"] == pytest.approx(5 / 12)


def test_enrollment_returns_none_when_below_min_cases():
    cases = [make_visit(f"case_{i}", 0, reg_date=date(2026, 1, 20), discharge_date=date(2026, 1, 1)) for i in range(9)]
    assert compute_enrollment_metrics(cases)["pct_late_enroll"] is None


# ---------------------------------------------------------------------------
# compute_case_metrics — latest-visit child_alive rule (March-2026 doc)
# ---------------------------------------------------------------------------


def test_case_metrics_mortality_uses_latest_visit_child_alive():
    """Case with earlier child_alive='no' but latest 'yes' should NOT be mortality."""
    visits = [
        make_visit("case1", 0, child_alive="no"),  # earlier visit
        make_visit("case1", 10, child_alive="yes"),  # latest visit (corrected)
    ]
    cm = compute_case_metrics(visits)
    assert cm["deaths"] == 0


def test_case_metrics_mortality_when_latest_child_alive_no():
    visits = [
        make_visit("case1", 0, child_alive="yes"),
        make_visit("case1", 10, child_alive="no"),  # latest
    ]
    cm = compute_case_metrics(visits)
    assert cm["deaths"] == 1


def test_case_metrics_falls_back_to_status_deceased_when_no_child_alive_field():
    visits = [
        make_visit("case1", 0, kmc_status="deceased"),
    ]
    cm = compute_case_metrics(visits)
    assert cm["deaths"] == 1


def test_case_metrics_only_latest_status_for_closed_check():
    visits = [
        make_visit("case1", 0, kmc_status="discharged"),
        make_visit("case1", 10, kmc_status="active"),  # latest — re-opened
    ]
    cm = compute_case_metrics(visits)
    assert cm["closed_cases"] == 0


def test_case_metrics_open_cases_not_counted_as_closed():
    visits = [make_visit("case1", 0, kmc_status="active")]
    assert compute_case_metrics(visits)["closed_cases"] == 0


def test_case_metrics_visit_counts_per_case():
    visits = [
        make_visit("c1", 0, kmc_status="discharged"),
        make_visit("c1", 5, kmc_status="discharged"),
        make_visit("c1", 10, kmc_status="discharged"),
        make_visit("c2", 0, kmc_status="discharged"),
    ]
    cm = compute_case_metrics(visits)
    cases_by_id = {c["case_id"]: c for c in cm["cases"]}
    assert cases_by_id["c1"]["visit_count"] == 3
    assert cases_by_id["c2"]["visit_count"] == 1


# ---------------------------------------------------------------------------
# compute_avg_visits_top_50 — March-2026 doc 50-case window
# ---------------------------------------------------------------------------


def test_avg_visits_top_50_uses_recent_cases_only():
    """50 most recently closed cases drive the average; older closed cases
    are ignored. Build 60 closed cases — first 10 (oldest) have 1 visit,
    last 50 have 5 visits each. Average should be 5.0, not (10*1 + 50*5)/60."""
    visits = []
    for i in range(60):
        cid = f"c{i:03d}"  # noqa: E231
        # First 10 cases: 1 visit each, very old dates (day 0..9)
        # Last 50 cases: 5 visits each, recent dates (day 100..149 + offsets)
        if i < 10:
            visits.append(make_visit(cid, i, kmc_status="discharged"))
        else:
            base_day = 100 + (i - 10)
            for k in range(5):
                visits.append(make_visit(cid, base_day + k * 0.0 + k, kmc_status="discharged"))
    cm = compute_case_metrics(visits)
    avg, n = compute_avg_visits_top_50(cm)
    assert n == 50
    assert avg == pytest.approx(5.0)


def test_avg_visits_top_50_returns_none_below_min_cases():
    visits = [make_visit(f"c{i}", i, kmc_status="discharged") for i in range(MIN_CASES["visits"] - 1)]
    cm = compute_case_metrics(visits)
    avg, n = compute_avg_visits_top_50(cm)
    assert avg is None


def test_avg_visits_top_50_excludes_mortality_cases():
    """Closed mortality cases should be filtered out of the average."""
    visits = []
    # 10 non-mortality closed cases, 1 visit each
    for i in range(10):
        visits.append(make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes"))
    # 5 mortality closed cases, lots of visits each (would inflate avg if included)
    for i in range(5):
        for k in range(10):
            visits.append(make_visit(f"dead_{i}", 50 + i + k, kmc_status="deceased", child_alive="no"))
    cm = compute_case_metrics(visits)
    avg, n = compute_avg_visits_top_50(cm)
    assert n == 10
    assert avg == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# compute_round_weight_pct
# ---------------------------------------------------------------------------


def test_round_weight_pct_below_min_data():
    visits = [make_visit("case1", i, weight=2000.0) for i in range(MIN_CASES["round_weight"] - 1)]
    pct, n = compute_round_weight_pct(visits)
    assert pct is None


def test_round_weight_pct_all_rounded():
    visits = [make_visit(f"case_{i}", i, weight=1500.0 + (i * 100)) for i in range(25)]
    pct, _n = compute_round_weight_pct(visits)
    assert pct == pytest.approx(1.0)


def test_round_weight_pct_mixed():
    weights = [1500.0] * 16 + [1523.0, 1547.0, 1612.0, 1689.0]
    visits = [make_visit(f"case_{i}", i, weight=w) for i, w in enumerate(weights)]
    pct, _n = compute_round_weight_pct(visits)
    assert pct == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# derive_flags — integration of the above (doc-faithful)
# ---------------------------------------------------------------------------


def test_derive_flags_excludes_low_volume_flw():
    aggregated = make_aggregated_row(total_cases=MIN_CASES["exclude"] - 1)
    result = derive_flags(aggregated, [])
    assert result.excluded is True
    for f in ALL_FLAGS:
        assert result.flags[f] is None
    assert result.flags["flag_mort"] is None
    assert result.flags["flag_data_quality"] is None


def test_derive_flags_low_visits_fires_with_doc_50_case_window():
    """20 closed non-mort cases × 1 visit each → avg 1.0 < 3.0 → flag fires."""
    aggregated = make_aggregated_row(total_cases=20)
    visits = [make_visit(f"c{i}", i, kmc_status="discharged", child_alive="yes") for i in range(20)]
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_visits"] is True


def test_derive_flags_high_mortality_fires_via_latest_child_alive():
    """20 cases, 5 with latest child_alive='no' (25%)."""
    aggregated = make_aggregated_row(total_cases=20)
    visits = []
    for i in range(15):
        visits.append(make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes"))
    for i in range(5):
        visits.append(make_visit(f"dead_{i}", 30 + i, kmc_status="discharged", child_alive="no"))
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_mort_high"] is True
    assert result.flags["flag_mort"] is True


def test_derive_flags_low_mortality_fires_via_latest_child_alive():
    """200 cases, 1 with latest child_alive='no' (0.5% < 2%)."""
    aggregated = make_aggregated_row(total_cases=200)
    visits = [make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes") for i in range(199)]
    visits.append(make_visit("dead_0", 250, kmc_status="discharged", child_alive="no"))
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_mort_low"] is True


def test_derive_flags_zero_danger_fires():
    aggregated = make_aggregated_row(
        total_cases=50,
        danger_visit_count=40,
        danger_positive_count=0,
    )
    result = derive_flags(aggregated, [])
    assert result.flags["flag_danger_zero"] is True


def test_derive_flags_high_danger_fires():
    aggregated = make_aggregated_row(
        total_cases=50,
        danger_visit_count=40,
        danger_positive_count=20,
    )
    result = derive_flags(aggregated, [])
    assert result.flags["flag_danger_high"] is True


def test_derive_flags_unknown_secondary_flags_are_none_not_false():
    aggregated = make_aggregated_row(total_cases=50)
    visits = [make_visit(f"c{i}", i, weight=2000.0, kmc_status="discharged", child_alive="yes") for i in range(15)]
    result = derive_flags(aggregated, visits)
    # Vital-sign flags whose underlying fields aren't captured: stay None.
    assert result.flags["flag_hr_copycat"] is None
    assert result.flags["flag_temp_copycat"] is None
    assert result.flags["flag_spo2_implausible"] is None
    assert result.flags["flag_ga_fullterm"] is None
    assert result.flags["flag_gps_same_case_far"] is None


def test_derive_flags_round_weight_works_with_visit_data_only():
    aggregated = make_aggregated_row(total_cases=50)
    visits = [make_visit(f"c{i}", i, weight=1800.0, kmc_status="discharged", child_alive="yes") for i in range(25)]
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_round_weight"] is True


def test_priority_flag_count_uses_synthetic_mort():
    aggregated = make_aggregated_row(total_cases=20)
    visits = []
    for i in range(15):
        visits.append(make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes"))
    for i in range(5):
        visits.append(make_visit(f"dead_{i}", 30 + i, kmc_status="discharged", child_alive="no"))
    result = derive_flags(aggregated, visits)
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
    for row in annotated:
        assert "flag_round_weight" in row["flag_sources"]


def test_visit_flag_sources_returns_empty_sources_when_no_flag_fires():
    visits = [make_visit(f"c{i}", i, weight=2000.0) for i in range(5)]
    result = FLWFlagResult(
        username="flw1",
        excluded=False,
        flags={f: False for f in ALL_FLAGS} | {"flag_mort": False, "flag_data_quality": False},
    )
    annotated = visit_flag_sources(visits, result)
    for row in annotated:
        assert row["flag_sources"] == []


# ---------------------------------------------------------------------------
# flag_data_quality — composite synthetic flag
# ---------------------------------------------------------------------------


def test_data_quality_fires_when_round_weight_fires():
    """flag_data_quality should be True if flag_round_weight fires (sub-flag)."""
    aggregated = make_aggregated_row(total_cases=50)
    visits = [make_visit(f"c{i}", i, weight=1800.0, kmc_status="discharged", child_alive="yes") for i in range(25)]
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_round_weight"] is True
    assert result.flags["flag_data_quality"] is True


def test_data_quality_false_when_all_sub_flags_pass():
    """flag_data_quality should be False if all sub-flags are False."""
    aggregated = make_aggregated_row(total_cases=50)
    # Weights NOT rounded to 100g (e.g. 1501, 1602, 1703, ...)
    visits = [
        make_visit(f"c{i}", i, weight=1501.0 + i * 100 + 1, kmc_status="discharged", child_alive="yes")
        for i in range(25)
    ]
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_round_weight"] is False
    # HR/temp/spo2 all have no data → None
    # DQ fires if ANY is True, is False if ALL are False (and at least one is computed),
    # but here only round_weight is computed (False), rest are None.
    # Since at least one sub-flag computed False and none are True, result depends on
    # whether we treat "mix of False and None" as False.
    # By design: True if any True, None if ALL None, False otherwise.
    assert result.flags["flag_data_quality"] is False


def test_data_quality_none_when_all_sub_flags_none():
    """flag_data_quality should be None if ALL sub-flags lack data."""
    aggregated = make_aggregated_row(total_cases=50)
    # No weight data at all → round_weight gets None. HR/temp/spo2 also None.
    visits = [make_visit(f"c{i}", i, kmc_status="discharged", child_alive="yes") for i in range(25)]
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_round_weight"] is None
    assert result.flags["flag_data_quality"] is None


def test_temp_copycat_returns_value_when_temperature_present():
    """When temperature data is in visits, compute_temp_copycat_pct computes a real value."""
    from commcare_connect.custom_analysis.kmc_audit.flag_logic import compute_temp_copycat_pct

    visits = [make_visit(f"c{i}", i, temperature=36.5) for i in range(25)]
    pct, n = compute_temp_copycat_pct(visits)
    assert n == 25
    assert pct == pytest.approx(1.0)  # All same value → 100% copycat


def test_temp_copycat_none_when_no_temperature_field():
    """Without temperature in visit rows, compute returns None."""
    from commcare_connect.custom_analysis.kmc_audit.flag_logic import compute_temp_copycat_pct

    visits = [make_visit(f"c{i}", i, weight=2000.0) for i in range(25)]
    pct, n = compute_temp_copycat_pct(visits)
    assert pct is None
    assert n == 0


def test_total_cases_from_visits_matches_distinct_case_ids():
    """total_cases_from_visits should count distinct case IDs from visit rows."""
    aggregated = make_aggregated_row(total_cases=3)
    visits = [
        make_visit("case_a", 0),
        make_visit("case_a", 5),
        make_visit("case_b", 1),
        make_visit("case_c", 2),
    ]
    result = derive_flags(aggregated, visits)
    assert result.total_cases_from_visits == 3


def test_metric_fields_populated_on_result():
    """Secondary metric fields should be populated on the FLWFlagResult."""
    aggregated = make_aggregated_row(total_cases=50)
    visits = [make_visit(f"c{i}", i, weight=1800.0, kmc_status="discharged", child_alive="yes") for i in range(25)]
    result = derive_flags(aggregated, visits)
    assert result.round_weight_pct is not None
    assert result.round_weight_pct == pytest.approx(1.0)
    # HR/SpO2/GA/GPS should be None since no data
    assert result.hr_copycat_pct is None
    assert result.spo2_implausible_pct is None
    assert result.ga_fullterm_pct is None
    assert result.gps_same_case_far_pct is None
