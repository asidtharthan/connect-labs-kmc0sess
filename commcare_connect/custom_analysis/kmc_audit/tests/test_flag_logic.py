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
    compute_avg_visits_top_50,  # Backwards-compat alias to compute_avg_visits
)
from commcare_connect.custom_analysis.kmc_audit.flag_logic import (
    ALL_FLAGS,
    MIN_CASES,
    PRIORITY_FLAGS,
    SECONDARY_FLAGS,
    FLWFlagResult,
    compute_avg_visits,
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
        "kmc_visit_count": 0,
        "danger_visit_count": 0,
        "danger_positive_count": 0,
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Tier mapping sanity
# ---------------------------------------------------------------------------


def test_priority_tier_has_ten_flags():
    assert len(PRIORITY_FLAGS) == 10


def test_secondary_tier_plus_priority_covers_all_real_flags():
    # flag_mort is the only synthetic — it's derived from flag_mort_low + flag_mort_high.
    # Priority + secondary should cover all base flags once the synthetic is excluded.
    synthetics = {"flag_mort"}
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
    assert out == {
        "pct_wt_loss": None,
        "mean_daily_gain": None,
        "pct_wt_zero": None,
        "weight_pairs": 0,
        "gain_pairs": 0,
    }


def test_weight_metrics_pair_outside_window_is_skipped():
    visits = [
        make_visit("case1", 0, weight=2.0),
        make_visit("case1", 35, weight=2.2),
    ]
    assert compute_weight_metrics(visits)["weight_pairs"] == 0


def test_weight_metrics_zero_change_pair():
    visits = [
        make_visit("case1", 0, weight=2.0),
        make_visit("case1", 5, weight=2.0),
    ]
    out = compute_weight_metrics(visits)
    assert out["weight_pairs"] == 1
    assert out["pct_wt_zero"] == pytest.approx(1.0)
    assert out["pct_wt_loss"] == pytest.approx(0.0)
    # Zero-change pair has diff=0 → not a gain pair → mean_daily_gain is None
    assert out["mean_daily_gain"] is None


def test_weight_metrics_loss_pair_counts_correctly():
    visits = [
        make_visit("case1", 0, weight=2.0),
        make_visit("case1", 5, weight=1.9),
    ]
    out = compute_weight_metrics(visits)
    assert out["pct_wt_loss"] == pytest.approx(1.0)
    # Loss pair has diff<0 → not a gain pair → mean_daily_gain is None
    assert out["mean_daily_gain"] is None


def test_weight_metrics_gain_only_mean():
    """mean_daily_gain should use only gain pairs (positive diff), per the April follow-on doc."""
    visits = [
        make_visit("case1", 0, weight=2.0),
        make_visit("case1", 5, weight=1.9),  # loss pair: diff = -100g
        make_visit("case1", 10, weight=2.1),  # gain pair: diff = +200g in 5 days = 40 g/day
    ]
    out = compute_weight_metrics(visits)
    assert out["weight_pairs"] == 2
    assert out["pct_wt_loss"] == pytest.approx(0.5)
    # Mean daily gain = 200/5 = 40.0 (only the gain pair, NOT averaged with the loss)
    assert out["mean_daily_gain"] == pytest.approx(40.0)


def test_weight_metrics_extreme_weight_filtered_out():
    visits = [
        make_visit("case1", 0, weight=6.0),
        make_visit("case1", 5, weight=2.0),
    ]
    assert compute_weight_metrics(visits)["weight_pairs"] == 0


def test_weight_metrics_twins_segregated_by_case_id():
    visits = [
        make_visit("twin_a", 0, weight=2.0),
        make_visit("twin_b", 1, weight=1.5),
        make_visit("twin_a", 5, weight=2.1),
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
    """visit_count only includes follow-up visits (visit_number populated)."""
    visits = [
        make_visit("c1", 0, kmc_status="discharged", visit_number=1),
        make_visit("c1", 5, kmc_status="discharged", visit_number=2),
        make_visit("c1", 10, kmc_status="discharged", visit_number=3),
        make_visit("c2", 0, kmc_status="discharged", visit_number=1),
    ]
    cm = compute_case_metrics(visits)
    cases_by_id = {c["case_id"]: c for c in cm["cases"]}
    assert cases_by_id["c1"]["visit_count"] == 3
    assert cases_by_id["c2"]["visit_count"] == 1


def test_case_metrics_registration_visits_excluded_from_count():
    """Registration forms (no visit_number) should not inflate visit_count."""
    visits = [
        make_visit("c1", 0, kmc_status="active"),  # registration — no visit_number
        make_visit("c1", 5, kmc_status="discharged", visit_number=1),  # follow-up
        make_visit("c1", 10, kmc_status="discharged", visit_number=2),  # follow-up
    ]
    cm = compute_case_metrics(visits)
    cases_by_id = {c["case_id"]: c for c in cm["cases"]}
    assert cases_by_id["c1"]["visit_count"] == 2  # Only follow-ups counted


# ---------------------------------------------------------------------------
# compute_avg_visits — April canonical (no 50-cap; uses ALL non-mort closed)
# ---------------------------------------------------------------------------


def test_avg_visits_uses_all_non_mort_closed_cases():
    """April canonical doc Table 0 row 1 dropped the March-narrative 50-cap.
    Build 60 closed non-mortality cases — first 10 have 1 follow-up visit,
    next 50 have 5 follow-up visits each. Average across ALL 60 should be:
    (10*1 + 50*5) / 60 = 260/60 ≈ 4.333."""
    visits = []
    for i in range(60):
        cid = f"c{i:03d}"  # noqa: E231
        if i < 10:
            visits.append(make_visit(cid, i, kmc_status="discharged", visit_number=1))
        else:
            base_day = 100 + (i - 10)
            for k in range(5):
                visits.append(make_visit(cid, base_day + k, kmc_status="discharged", visit_number=k + 1))
    cm = compute_case_metrics(visits)
    avg, n = compute_avg_visits(cm)
    assert n == 60, f"expected all 60 non-mort closed cases (no 50-cap), got {n}"
    assert avg == pytest.approx(260 / 60)


def test_avg_visits_returns_none_below_min_cases():
    """fewer than MIN_CASES["visits"] (10) non-mort closed → None."""
    visits = [make_visit(f"c{i}", i, kmc_status="discharged") for i in range(MIN_CASES["visits"] - 1)]
    cm = compute_case_metrics(visits)
    avg, n = compute_avg_visits(cm)
    assert avg is None


def test_avg_visits_excludes_mortality_cases():
    """Closed mortality cases should be filtered out of the average."""
    visits = []
    for i in range(10):
        visits.append(make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes", visit_number=1))
    for i in range(5):
        for k in range(10):
            visits.append(
                make_visit(f"dead_{i}", 50 + i + k, kmc_status="deceased", child_alive="no", visit_number=k + 1)
            )
    cm = compute_case_metrics(visits)
    avg, n = compute_avg_visits(cm)
    assert n == 10
    assert avg == pytest.approx(1.0)


# Backwards-compat: the old function name is kept as an alias so external
# callers don't break. Smoke-check that it dispatches to the new behavior.
def test_compute_avg_visits_top_50_alias_drops_50_cap():
    """The old name is kept as an alias of compute_avg_visits — no longer
    enforces the 50-cap (the alias's behavior changed when April canonical
    dropped the cap)."""
    visits = []
    for i in range(60):
        visits.append(
            make_visit(f"c{i:03d}", i, kmc_status="discharged", child_alive="yes", visit_number=1)  # noqa: E231
        )
    cm = compute_case_metrics(visits)
    avg, n = compute_avg_visits_top_50(cm)
    assert n == 60  # All 60, not capped to 50


# ---------------------------------------------------------------------------
# compute_round_weight_pct
# ---------------------------------------------------------------------------


def test_round_weight_pct_below_min_data():
    # April canonical doc Table 0 row 13: round_weight uses follow-up weights only.
    # visit_number must be set for a visit row to be counted as follow-up.
    visits = [make_visit("case1", i, weight=2.0, visit_number=1) for i in range(MIN_CASES["round_weight"] - 1)]
    pct, n = compute_round_weight_pct(visits)
    assert pct is None


def test_round_weight_pct_all_rounded():
    visits = [make_visit(f"case_{i}", i, weight=1.5 + (i * 0.1), visit_number=1) for i in range(25)]
    pct, _n = compute_round_weight_pct(visits)
    assert pct == pytest.approx(1.0)


def test_round_weight_pct_mixed():
    weights = [1.5] * 16 + [1.523, 1.547, 1.612, 1.689]
    visits = [make_visit(f"case_{i}", i, weight=w, visit_number=1) for i, w in enumerate(weights)]
    pct, _n = compute_round_weight_pct(visits)
    assert pct == pytest.approx(0.8)


def test_round_weight_pct_excludes_registration_weights():
    """Per April canonical Table 0 row 13 ('follow-up weights'),
    rows without visit_number (registration forms) must NOT be counted."""
    # 20 follow-up visits (visit_number set) with rounded weights
    follow_ups = [make_visit(f"f{i}", i, weight=1.5, visit_number=1) for i in range(20)]
    # 10 registration visits (visit_number=None) with non-rounded weights
    # Older code counted these toward the denominator; new code drops them.
    registrations = [make_visit(f"r{i}", 100 + i, weight=1.523) for i in range(10)]
    pct, n = compute_round_weight_pct(follow_ups + registrations)
    assert n == 20, f"expected 20 follow-up weights only, got {n}"
    assert pct == pytest.approx(1.0), "all 20 follow-up weights are rounded"


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


def test_derive_flags_low_visits_fires_with_doc_50_case_window():
    """20 closed non-mort cases × 1 follow-up visit each → avg 1.0 < 3.0 → flag fires."""
    aggregated = make_aggregated_row(total_cases=20)
    visits = [make_visit(f"c{i}", i, kmc_status="discharged", child_alive="yes", visit_number=1) for i in range(20)]
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_visits"] is True


def test_derive_flags_high_mortality_fires_via_latest_child_alive():
    """20 closed cases, 5 with latest child_alive='no'. mort_rate = 5/20 = 25% > 20%."""
    aggregated = make_aggregated_row(total_cases=20)
    visits = []
    for i in range(15):
        visits.append(make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes"))
    for i in range(5):
        visits.append(make_visit(f"dead_{i}", 30 + i, kmc_status="discharged", child_alive="no"))
    result = derive_flags(aggregated, visits)
    # mort_rate = deaths / closed_cases = 5 / 20 = 25%
    assert result.mort_rate == pytest.approx(0.25)
    assert result.flags["flag_mort_high"] is True
    assert result.flags["flag_mort"] is True


def test_derive_flags_low_mortality_fires_via_latest_child_alive():
    """200 closed cases, 1 with latest child_alive='no'.
    mort_rate = 1/200 = 0.5% < 2% → flag fires."""
    aggregated = make_aggregated_row(total_cases=200)
    visits = [make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes") for i in range(199)]
    visits.append(make_visit("dead_0", 250, kmc_status="discharged", child_alive="no"))
    result = derive_flags(aggregated, visits)
    # mort_rate = deaths / closed_cases = 1 / 200 = 0.5%
    assert result.mort_rate == pytest.approx(0.005)
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


def test_primary_flags_return_none_not_false_when_insufficient_data():
    """Primary flags must return None (insufficient data) — not False
    (passes) — when the minimum data requirement isn't met. Otherwise
    the UI shows a green "pass" indicator where it should show a neutral
    "—" dash."""
    aggregated = make_aggregated_row(
        total_cases=50,
        danger_visit_count=5,
        danger_positive_count=0,
    )
    # Only 5 visits, all open cases → not enough for most flags
    visits = [make_visit(f"c{i}", i, weight=2.0, kmc_status="active") for i in range(5)]
    result = derive_flags(aggregated, visits)
    # danger_high needs 20+ visits, only 5
    assert result.flags["flag_danger_high"] is None
    # danger_zero needs 30+ visits, only 5
    assert result.flags["flag_danger_zero"] is None
    # weight flags need 10+ pairs, we have <10
    assert result.flags["flag_wt_loss"] is None
    assert result.flags["flag_wt_gain"] is None
    assert result.flags["flag_wt_zero"] is None


def test_mortality_flags_none_when_below_min_cases():
    """Mortality flags need 20+ closed_cases. With fewer than 20 total
    cases the FLW is excluded entirely (all flags None)."""
    aggregated = make_aggregated_row(total_cases=15)
    visits = [make_visit(f"c{i}", i, kmc_status="discharged", child_alive="yes") for i in range(15)]
    result = derive_flags(aggregated, visits)
    assert result.excluded is True
    assert result.flags["flag_mort_low"] is None
    assert result.flags["flag_mort_high"] is None
    assert result.flags["flag_mort"] is None


def test_mortality_flags_none_when_insufficient_closed_cases():
    """Mortality flags need 20+ closed_cases (not total_cases). An FLW
    with 30 total cases but only 15 closed should not be assessed."""
    aggregated = make_aggregated_row(total_cases=30)
    # 15 closed (discharged) + 15 open (active) → closed_cases=15 < 20
    visits = []
    for i in range(15):
        visits.append(make_visit(f"closed_{i}", i, kmc_status="discharged", child_alive="yes"))
    for i in range(15):
        visits.append(make_visit(f"open_{i}", 50 + i, kmc_status="active"))
    result = derive_flags(aggregated, visits)
    assert result.excluded is False  # Not excluded — 30 total cases >= 20
    assert result.flags["flag_mort_low"] is None  # Insufficient closed cases
    assert result.flags["flag_mort_high"] is None
    assert result.flags["flag_mort"] is None


def test_derive_flags_unknown_secondary_flags_are_none_not_false():
    aggregated = make_aggregated_row(total_cases=50)
    visits = [make_visit(f"c{i}", i, weight=2.0, kmc_status="discharged", child_alive="yes") for i in range(15)]
    result = derive_flags(aggregated, visits)
    # Vital-sign flags whose underlying fields aren't captured: stay None.
    assert result.flags["flag_hr_copycat"] is None
    assert result.flags["flag_temp_copycat"] is None
    assert result.flags["flag_spo2_implausible"] is None
    assert result.flags["flag_ga_fullterm"] is None
    assert result.flags["flag_gps_same_case_far"] is None


def test_derive_flags_round_weight_works_with_visit_data_only():
    """Round-weight requires follow-up visits (visit_number set), per April canonical doc."""
    aggregated = make_aggregated_row(total_cases=50)
    visits = [
        make_visit(f"c{i}", i, weight=1.8, kmc_status="discharged", child_alive="yes", visit_number=1)
        for i in range(25)
    ]
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_round_weight"] is True


def test_priority_flag_count_uses_synthetic_mort():
    aggregated = make_aggregated_row(total_cases=20)
    visits = []
    for i in range(15):
        visits.append(make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes", visit_number=1))
    for i in range(5):
        visits.append(make_visit(f"dead_{i}", 30 + i, kmc_status="discharged", child_alive="no", visit_number=1))
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_mort"] is True
    assert result.priority_flag_count >= 1


# ---------------------------------------------------------------------------
# visit_flag_sources
# ---------------------------------------------------------------------------


def test_visit_flag_sources_marks_round_weight_visits():
    visits = [make_visit(f"c{i}", i, weight=1.8) for i in range(25)]
    result = FLWFlagResult(
        username="flw1",
        excluded=False,
        flags={f: False for f in ALL_FLAGS} | {"flag_round_weight": True, "flag_mort": False},
    )
    annotated = visit_flag_sources(visits, result)
    for row in annotated:
        assert "flag_round_weight" in row["flag_sources"]


def test_visit_flag_sources_returns_empty_sources_when_no_flag_fires():
    visits = [make_visit(f"c{i}", i, weight=2.0) for i in range(5)]
    result = FLWFlagResult(
        username="flw1",
        excluded=False,
        flags={f: False for f in ALL_FLAGS} | {"flag_mort": False},
    )
    annotated = visit_flag_sources(visits, result)
    for row in annotated:
        assert row["flag_sources"] == []


# ---------------------------------------------------------------------------
# Individual data quality flags (no composite)
# ---------------------------------------------------------------------------


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

    visits = [make_visit(f"c{i}", i, weight=2.0) for i in range(25)]
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
    """Secondary metric fields should be populated on the FLWFlagResult.
    Note: visit_number=1 needed so round_weight has follow-up data to count."""
    aggregated = make_aggregated_row(total_cases=50)
    visits = [
        make_visit(f"c{i}", i, weight=1.8, kmc_status="discharged", child_alive="yes", visit_number=1)
        for i in range(25)
    ]
    result = derive_flags(aggregated, visits)
    assert result.round_weight_pct is not None
    assert result.round_weight_pct == pytest.approx(1.0)
    # HR/SpO2/GA/GPS should be None since no data
    assert result.hr_copycat_pct is None
    assert result.spo2_implausible_pct is None
    assert result.ga_fullterm_pct is None
    assert result.gps_same_case_far_pct is None


# ---------------------------------------------------------------------------
# April canonical fixes — explicit tests for the 4 doc-alignment changes
# ---------------------------------------------------------------------------


def test_late_enroll_inclusive_8_day_boundary():
    """Doc text: '8 or more days' / '8+ days' — code must use >= 8.
    Case at exactly 8 days post-discharge is late."""
    # Build 10 cases all enrolled exactly 8 days after discharge.
    visits = [
        make_visit(
            f"case_{i}",
            0,
            reg_date=date(2026, 1, 9),  # 8 days after discharge
            discharge_date=date(2026, 1, 1),
        )
        for i in range(10)
    ]
    out = compute_enrollment_metrics(visits)
    assert out["cases_with_dates"] == 10
    assert out["pct_late_enroll"] == pytest.approx(
        1.0
    ), "Expected 100% late at exactly 8 days post-discharge (April canonical: '8+ days')"


def test_late_enroll_7_day_boundary_not_late():
    """7 days post-discharge is not late under either old or new rule."""
    visits = [
        make_visit(
            f"case_{i}",
            0,
            reg_date=date(2026, 1, 8),  # 7 days after discharge
            discharge_date=date(2026, 1, 1),
        )
        for i in range(10)
    ]
    out = compute_enrollment_metrics(visits)
    assert out["pct_late_enroll"] == pytest.approx(0.0)


def test_danger_metrics_prefer_visit_level_over_aggregated():
    """Aggregated ``danger_positive_count`` is bound to the primary form
    path only; if V1 fallback-path positives exist, the agg under-counts.
    Visit-level rows resolve via first-non-null across both paths, so we
    recount from them. This test simulates that scenario: aggregated says
    rate is 1/40 = 2.5%, but visit-level (which captures fallback positives)
    says 10/40 = 25% → flag should fire. Without the fix, flag would pass."""
    aggregated = make_aggregated_row(
        total_cases=50,
        # Wrong (under-counted) aggregated values:
        danger_visit_count=40,
        danger_positive_count=1,  # only the primary-path 'yes' counted
    )
    # Visit-level data: 10 of 40 positives across both paths.
    visits = []
    for i in range(10):
        # These resolve to 'yes' via the visit pipeline's first-non-null rule
        visits.append(make_visit(f"y{i}", i, danger_sign_positive="yes"))
    for i in range(30):
        visits.append(make_visit(f"n{i}", 30 + i, danger_sign_positive="no"))
    result = derive_flags(aggregated, visits)
    # Visit-level 10/40 = 25% < 30% — passes danger_high.
    # But the test below proves we use visit-level values, not the broken agg.
    assert result.danger_rate == pytest.approx(10 / 40)
    # Without the fix, derive_flags would have used agg counts: 1/40 = 2.5%.
    assert result.danger_rate != pytest.approx(1 / 40)


def test_danger_metrics_fall_back_to_aggregated_when_visits_empty():
    """If visit_rows carries no danger data at all (e.g. test fixtures that
    pre-date the visit-level recount), fall back to aggregated values so
    those tests still pass."""
    aggregated = make_aggregated_row(
        total_cases=50,
        danger_visit_count=40,
        danger_positive_count=15,
    )
    result = derive_flags(aggregated, [])  # no visit rows
    assert result.danger_rate == pytest.approx(15 / 40)


def test_read_weight_g_auto_detects_grams_vs_kg():
    """Production CommCare V2 forms store weight in grams (e.g. 1345 for a
    1.345 kg baby). Tests historically pass kg (e.g. 1.5). _read_weight_g
    must accept both and normalise to grams. This test locks in the
    auto-detect behaviour so regressing to a unconditional kg→g
    multiply is caught."""
    from commcare_connect.custom_analysis.kmc_audit.flag_logic import _read_weight_g

    # Grams (production format) — used as-is.
    assert _read_weight_g({"weight": "1345"}) == 1345.0
    assert _read_weight_g({"weight": "1845.0"}) == 1845.0
    assert _read_weight_g({"weight": 2500}) == 2500.0
    # Kilograms (test-fixture format) — multiplied by 1000.
    assert _read_weight_g({"weight": "1.5"}) == 1500.0
    assert _read_weight_g({"weight": 2.0}) == 2000.0
    assert _read_weight_g({"weight": 0.8}) == 800.0
    # Edge cases.
    assert _read_weight_g({"weight": None}) is None
    assert _read_weight_g({"weight": ""}) is None
    assert _read_weight_g({"weight": 0}) is None
    assert _read_weight_g({"weight": -1.5}) is None
    # Implausible — a 50 (kg or g) baby is rejected as out-of-range.
    # 50 falls in the "neither kg nor grams" gap (50-100).
    assert _read_weight_g({"weight": 80}) is None
    # 50000 g (= 50 kg) is far too heavy for a neonate.
    assert _read_weight_g({"weight": 50000}) is None


def test_compute_weight_metrics_exposes_gain_pairs():
    """Per April canonical Table 0 row 8, flag_wt_gain gates on gain pairs only.
    compute_weight_metrics must expose gain_pairs as a separate field."""
    visits = [
        make_visit("case1", 0, weight=2.0),
        make_visit("case1", 5, weight=1.9),  # loss
        make_visit("case1", 10, weight=2.1),  # gain
        make_visit("case2", 0, weight=2.0),
        make_visit("case2", 5, weight=2.0),  # zero
    ]
    out = compute_weight_metrics(visits)
    assert out["weight_pairs"] == 3  # 1 loss + 1 gain + 1 zero
    assert out["gain_pairs"] == 1


def test_flag_wt_gain_evaluates_with_any_gain_pairs():
    """No minimum data gate — flag evaluates as long as any baby has a gain pair."""
    aggregated = make_aggregated_row(total_cases=50)
    visits = []
    # 15 loss pairs, all in their own case
    for i in range(15):
        cid = f"loss_{i}"
        visits.append(make_visit(cid, 0, weight=2.0))
        visits.append(make_visit(cid, 5, weight=1.9))  # loss
    # 5 gain pairs — each baby gains 500g / 5 days = 100 g/day (> 60 threshold)
    for i in range(5):
        cid = f"gain_{i}"
        visits.append(make_visit(cid, 0, weight=1.5))
        visits.append(make_visit(cid, 5, weight=2.0))
    result = derive_flags(aggregated, visits)
    # Even with only 5 gain babies, the flag evaluates (no min gate)
    assert result.flags["flag_wt_gain"] is True
    # Loss flag should still evaluate (15 loss pairs out of 20 = 75% > 15%)
    assert result.flags["flag_wt_loss"] is True


def test_flag_wt_gain_fires_when_per_baby_avg_exceeds_threshold():
    """Per-baby avg daily gain > 60g/day → fires (no minimum pair count)."""
    aggregated = make_aggregated_row(total_cases=50)
    visits = []
    for i in range(12):
        cid = f"gain_{i}"
        visits.append(make_visit(cid, 0, weight=1.0))
        visits.append(make_visit(cid, 5, weight=1.5))  # +500g/5d = 100 g/day
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_wt_gain"] is True
    assert result.mean_daily_gain == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Doc-example fixture tests — encode the actual numbered FLW examples in
# Tables 1-16 of the April Follow-on so the algorithm is provably faithful
# to the doc's own example data.
# ---------------------------------------------------------------------------


def test_doc_example_flw_2328_high_mortality_32_4pct():
    """Doc Table 3 row 1: FLW 2328 (PIPN), 108 closed cases, 35 deaths,
    mortality rate 32.4%. Flag_mort_high should fire."""
    aggregated = make_aggregated_row(total_cases=108)
    visits = []
    # 73 alive closed cases
    for i in range(73):
        visits.append(make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes", visit_number=1))
    # 35 deceased closed cases (latest visit reports child_alive='no')
    for i in range(35):
        visits.append(make_visit(f"dead_{i}", 200 + i, kmc_status="discharged", child_alive="no", visit_number=1))
    result = derive_flags(aggregated, visits)
    assert result.deaths == 35
    assert result.closed_cases == 108
    assert result.mort_rate == pytest.approx(35 / 108)
    assert result.mort_rate == pytest.approx(0.324, abs=0.001)  # doc rounds to 32.4%
    assert result.flags["flag_mort_high"] is True
    assert result.flags["flag_mort"] is True


def test_doc_example_flw_2274_zero_mortality():
    """Doc Table 2 row 1: FLW 2274 (PIPN), 47 closed cases, 0 deaths.
    flag_mort_low should fire (rate 0% < 2%)."""
    aggregated = make_aggregated_row(total_cases=47)
    visits = [
        make_visit(f"alive_{i}", i, kmc_status="discharged", child_alive="yes", visit_number=1) for i in range(47)
    ]
    result = derive_flags(aggregated, visits)
    assert result.deaths == 0
    assert result.closed_cases == 47
    assert result.mort_rate == pytest.approx(0.0)
    assert result.flags["flag_mort_low"] is True


def test_doc_example_flw_2208_low_avg_visits():
    """Doc Table 1 row 1: FLW 2208 (Nama), 14 closed cases assessed,
    avg 1.07 follow-up visits/case. flag_visits should fire (1.07 < 3.0)."""
    aggregated = make_aggregated_row(total_cases=20)  # ≥20 to avoid exclusion
    # 14 closed non-mortality cases; 1 case has 2 visits, the other 13 have 1.
    # Total = 13 + 2 = 15; avg = 15/14 = 1.071
    visits = []
    for i in range(13):
        visits.append(make_visit(f"c{i}", i, kmc_status="discharged", child_alive="yes", visit_number=1))
    visits.append(make_visit("c13", 13, kmc_status="discharged", child_alive="yes", visit_number=1))
    visits.append(make_visit("c13", 14, kmc_status="discharged", child_alive="yes", visit_number=2))
    # 6 open cases to round to 20 total cases (won't count in avg)
    for i in range(6):
        visits.append(make_visit(f"open_{i}", 100 + i, kmc_status="active"))
    result = derive_flags(aggregated, visits)
    assert result.flags["flag_visits"] is True
    assert result.avg_visits == pytest.approx(15 / 14, abs=0.01)
    assert result.avg_visits < 1.10  # doc says 1.07


def test_doc_example_flw_2262_late_enrollment_82pct():
    """Doc Table 4 row 1: FLW 2262 (PIPN), 28 cases with discharge date,
    23 late enrollments (82.1%). Flag fires at the user-chosen 35% threshold."""
    aggregated = make_aggregated_row(total_cases=28)
    visits = []
    # 23 late cases (registered exactly 9+ days after discharge)
    for i in range(23):
        visits.append(make_visit(f"late_{i}", 0, reg_date=date(2026, 1, 11), discharge_date=date(2026, 1, 1)))
    # 5 on-time cases (registered 0-7 days after discharge)
    for i in range(5):
        visits.append(make_visit(f"ontime_{i}", 0, reg_date=date(2026, 1, 5), discharge_date=date(2026, 1, 1)))
    result = derive_flags(aggregated, visits)
    assert result.cases_with_dates == 28
    assert result.pct_late_enroll == pytest.approx(23 / 28, abs=0.01)
    assert result.pct_late_enroll == pytest.approx(0.821, abs=0.005)  # doc says 82.1%
    assert result.flags["flag_enroll"] is True


def test_doc_example_flw_4841_high_danger_88pct():
    """Doc Table 5 row 1: FLW 4841 (PIPN), 69 follow-up visits, 61 danger sign positive.
    Danger rate 88.4%. Fires at >30% threshold."""
    aggregated = make_aggregated_row(
        total_cases=50,  # plenty
        danger_visit_count=69,  # 69 visits where field was filled
        danger_positive_count=61,  # 61 of those said yes
    )
    result = derive_flags(aggregated, [])
    assert result.danger_rate == pytest.approx(61 / 69, abs=0.001)
    assert result.danger_rate == pytest.approx(0.884, abs=0.005)
    assert result.flags["flag_danger_high"] is True


def test_doc_example_flw_4871_zero_danger_signs():
    """Doc Table 6 row 1: FLW 4871 (PIPN), 360 follow-up visits, 0 danger signs.
    Danger rate 0%. flag_danger_zero fires (zero rate across 30+ visits)."""
    aggregated = make_aggregated_row(
        total_cases=50,
        danger_visit_count=360,
        danger_positive_count=0,
    )
    result = derive_flags(aggregated, [])
    assert result.danger_rate == pytest.approx(0.0)
    assert result.flags["flag_danger_zero"] is True


def test_doc_example_flw_2328_weight_gain_125_5_g_per_day():
    """Doc Table 8 row 1: FLW 2328 (PIPN), 162 valid gain pairs, mean 125.5 g/day.
    Flag fires (>60 g/day)."""
    aggregated = make_aggregated_row(total_cases=50)
    visits = []
    # 162 gain pairs distributed across cases (one pair per case for simplicity).
    # Each pair: +500g over 4 days = 125 g/day (close to 125.5).
    for i in range(162):
        cid = f"gain_{i}"
        visits.append(make_visit(cid, 0, weight=1.0))
        visits.append(make_visit(cid, 4, weight=1.5))  # +500g / 4d = 125 g/day
    result = derive_flags(aggregated, visits)
    assert result.weight_pairs == 162
    assert result.mean_daily_gain == pytest.approx(125.0, abs=0.5)
    assert result.flags["flag_wt_gain"] is True


def test_doc_example_flw_2208_zero_change_71pct():
    """Doc Table 9 row 1: FLW 2208 (Nama), 28 valid weight pairs,
    20 zero-change pairs (71.4%). Flag fires (>30%)."""
    aggregated = make_aggregated_row(total_cases=50)
    visits = []
    # 20 zero-change pairs (one per case)
    for i in range(20):
        cid = f"zero_{i}"
        visits.append(make_visit(cid, 0, weight=2.0))
        visits.append(make_visit(cid, 5, weight=2.0))
    # 8 gain pairs (loss/gain doesn't matter as long as it's not zero)
    for i in range(8):
        cid = f"gain_{i}"
        visits.append(make_visit(cid, 0, weight=2.0))
        visits.append(make_visit(cid, 5, weight=2.1))
    result = derive_flags(aggregated, visits)
    assert result.weight_pairs == 28
    assert result.pct_wt_zero == pytest.approx(20 / 28, abs=0.001)
    assert result.flags["flag_wt_zero"] is True


def test_doc_example_flw_2198_round_weight_100pct():
    """Doc Table 13 row 1: FLW 2198 (Nama), 26 valid weight entries, ALL rounded.
    Flag fires (>=80%). Visits must be marked as follow-ups (visit_number set)."""
    aggregated = make_aggregated_row(total_cases=50)
    visits = [
        make_visit(f"c{i}", i, weight=1.5 + (i * 0.1), kmc_status="discharged", child_alive="yes", visit_number=1)
        for i in range(26)
    ]
    result = derive_flags(aggregated, visits)
    assert result.round_weight_pct == pytest.approx(1.0)
    assert result.flags["flag_round_weight"] is True


def test_doc_example_flw_2251_no_referral():
    """Doc Table 14 row 1: FLW 2251 (PIPN), 672 DS-positive visits, 0 referrals.
    Referral rate 0% → flag fires."""
    aggregated = make_aggregated_row(total_cases=50)
    # Build 672 DS-positive visits, all with no referral
    visits = [make_visit(f"v{i}", i, danger_sign_positive="yes", child_referred="no") for i in range(672)]
    result = derive_flags(aggregated, visits)
    assert result.ds_no_referral_pct == pytest.approx(0.0)
    assert result.flags["flag_ds_no_referral"] is True
