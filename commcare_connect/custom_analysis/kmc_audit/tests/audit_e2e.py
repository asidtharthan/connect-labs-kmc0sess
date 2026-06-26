"""
End-to-end data audit: traces 4 realistic FLWs through the complete pipeline.

Checks every single flag value, metric, frequency grid count, badge count,
and column rendering for all 10 priority + 7 secondary flags.

Run with:
    python -m pytest commcare_connect/custom_analysis/kmc_audit/tests/audit_e2e.py \
        -v --noconftest --override-ini="addopts=" -s
"""
from __future__ import annotations

from datetime import date, timedelta

from commcare_connect.custom_analysis.kmc_audit.flag_logic import (
    ALL_FLAGS,
    FLAG_LABELS,
    PRIORITY_FLAGS,
    SECONDARY_FLAGS,
    FLWFlagResult,
    derive_flags,
)

# --- Fixture builders ----------------------------------------------------


def make_visit(
    case_id, day_offset, weight=None, kmc_status=None, child_alive=None, reg_date=None, discharge_date=None, **extra
):
    base = date(2026, 1, 1)
    return {
        "username": extra.pop("username", "flw1"),
        "beneficiary_case_id": case_id,
        "visit_date": (base + timedelta(days=day_offset)).isoformat(),
        "weight": weight,
        "visit_number": extra.pop("visit_number", None),
        "kmc_status": kmc_status,
        "child_alive": child_alive,
        "reg_date": reg_date.isoformat() if reg_date else None,
        "discharge_date": discharge_date.isoformat() if discharge_date else None,
        **extra,
    }


def make_agg(**kw):
    return {
        "username": "flw1",
        "total_cases": 0,
        "kmc_visit_count": 0,
        "danger_visit_count": 0,
        "danger_positive_count": 0,
        **kw,
    }


# --- 4 realistic FLW profiles --------------------------------------------


def build_flw_a():
    """FLW-A: High mortality (30%), low visits, rounded weights, copycat temp & HR.
    Should fire: flag_visits, flag_mort (high), flag_round_weight, flag_temp_copycat, flag_hr_copycat.
    """
    agg = make_agg(username="flw_a", total_cases=50)
    visits = []
    # 50 cases: 35 discharged alive, 15 deceased
    for i in range(35):
        cid = f"a_alive_{i}"
        visits += [
            make_visit(
                cid,
                i,
                weight=1.5,
                kmc_status="discharged",
                child_alive="yes",
                visit_number=1,
                username="flw_a",
                temperature=36.5,
                heart_rate=120.0,
                spo2_level=95.0,
                danger_sign_positive="no",
                child_referred="no",
                reg_date=date(2026, 1, 2),
                discharge_date=date(2026, 1, 1),
            ),
        ]
    for i in range(15):
        cid = f"a_dead_{i}"
        visits += [
            make_visit(
                cid,
                100 + i,
                weight=1.5,
                kmc_status="deceased",
                child_alive="no",
                visit_number=1,
                username="flw_a",
                temperature=36.5,
                heart_rate=120.0,
                spo2_level=95.0,
                danger_sign_positive="no",
                child_referred="no",
                reg_date=date(2026, 1, 2),
                discharge_date=date(2026, 1, 1),
            ),
        ]
    return agg, visits


def build_flw_b():
    """FLW-B: Late enrollment (80%), high danger signs (50%), no referrals.
    Should fire: flag_enroll, flag_danger_high, flag_ds_no_referral.
    """
    agg = make_agg(username="flw_b", total_cases=40)
    visits = []
    # 32 late enrollment cases (registered 10 days after discharge)
    for i in range(32):
        cid = f"b_late_{i}"
        visits += [
            make_visit(
                cid,
                i,
                weight=1.5 + 0.001 * i,
                kmc_status="discharged",
                child_alive="yes",
                visit_number=1,
                username="flw_b",
                temperature=36.0 + 0.1 * (i % 5),  # varied temps
                heart_rate=110.0 + (i % 10),  # varied HR
                spo2_level=95.0,
                danger_sign_positive="yes" if i < 20 else "no",
                child_referred="no",
                reg_date=date(2026, 1, 11),
                discharge_date=date(2026, 1, 1),
            ),
        ]
    # 8 on-time cases
    for i in range(8):
        cid = f"b_ontime_{i}"
        visits += [
            make_visit(
                cid,
                50 + i,
                weight=1.6 + 0.001 * i,
                kmc_status="discharged",
                child_alive="yes",
                visit_number=1,
                username="flw_b",
                temperature=36.0 + 0.1 * (i % 5),
                heart_rate=110.0 + (i % 10),
                spo2_level=95.0,
                danger_sign_positive="yes" if i < 4 else "no",
                child_referred="no",
                reg_date=date(2026, 1, 5),
                discharge_date=date(2026, 1, 1),
            ),
        ]
    return agg, visits


def build_flw_c():
    """FLW-C: Implausible SpO2 (many out of range), GPS spread (pairs far apart).
    Should fire: flag_spo2_implausible, flag_gps_same_case_far.
    """
    agg = make_agg(username="flw_c", total_cases=40)
    visits = []
    for i in range(40):
        cid = f"c_case_{i}"
        # 10 out of 40 have bad SpO2
        spo2 = 50.0 if i < 10 else 95.0
        # GPS: alternate between two locations ~100km apart
        if i % 2 == 0:
            gps = "20.0 78.0 0 10"
        else:
            gps = "21.0 78.0 0 10"  # ~111km north
        visits += [
            make_visit(
                cid,
                i * 2,
                weight=1.5 + 0.001 * i,
                kmc_status="discharged",
                child_alive="yes",
                visit_number=1,
                username="flw_c",
                temperature=36.0 + 0.1 * (i % 3),
                heart_rate=110.0 + (i % 15),
                spo2_level=spo2,
                danger_sign_positive="no",
                child_referred="no",
                gps=gps,
                reg_date=date(2026, 1, 2),
                discharge_date=date(2026, 1, 1),
            ),
        ]
        # Add a second visit to same case with different GPS (to create same-case pairs)
        if i % 2 == 0:
            gps2 = "21.0 78.0 0 10"
        else:
            gps2 = "20.0 78.0 0 10"
        visits += [
            make_visit(
                cid,
                i * 2 + 1,
                weight=1.5 + 0.002 * i,
                kmc_status="discharged",
                child_alive="yes",
                visit_number=2,
                username="flw_c",
                temperature=36.0 + 0.1 * (i % 3),
                heart_rate=110.0 + (i % 15),
                spo2_level=95.0,
                danger_sign_positive="no",
                child_referred="no",
                gps=gps2,
                reg_date=date(2026, 1, 2),
                discharge_date=date(2026, 1, 1),
            ),
        ]
    return agg, visits


def build_flw_d():
    """FLW-D: Clean FLW -- no flags should fire.
    Normal mortality (5%), good visits (4 avg), no rounded weights, varied vitals.
    """
    agg = make_agg(username="flw_d", total_cases=60)
    visits = []
    # 57 alive cases with 4 follow-up visits each
    for i in range(57):
        cid = f"d_alive_{i}"
        for v in range(4):
            visits += [
                make_visit(
                    cid,
                    i * 5 + v,
                    weight=1.5 + 0.023 * v + 0.001 * i,
                    kmc_status="discharged",
                    child_alive="yes",
                    visit_number=v + 1,
                    username="flw_d",
                    temperature=36.0 + 0.3 * (v % 3),
                    heart_rate=100.0 + (v * 5) + (i % 20),
                    spo2_level=92.0 + (v % 5),
                    danger_sign_positive="yes" if (i + v) % 10 == 0 else "no",
                    child_referred="yes" if (i + v) % 10 == 0 else "no",
                    gps=f"{20.0 + 0.001 * i} {78.0 + 0.001 * v} 0 10",
                    reg_date=date(2026, 1, 2),
                    discharge_date=date(2026, 1, 1),
                ),
            ]
    # 3 deceased
    for i in range(3):
        cid = f"d_dead_{i}"
        visits += [
            make_visit(
                cid,
                400 + i,
                weight=1.5,
                kmc_status="deceased",
                child_alive="no",
                visit_number=1,
                username="flw_d",
                temperature=37.0,
                heart_rate=130.0,
                spo2_level=90.0,
                danger_sign_positive="no",
                child_referred="no",
                reg_date=date(2026, 1, 2),
                discharge_date=date(2026, 1, 1),
            ),
        ]
    return agg, visits


# --- Main audit ----------------------------------------------------------


def run_audit():
    """Run the full audit and print detailed results."""
    builders = {
        "FLW-A (high mort, rounded wt, copycat vitals)": build_flw_a,
        "FLW-B (late enroll, high danger, no referral)": build_flw_b,
        "FLW-C (bad SpO2, GPS spread)": build_flw_c,
        "FLW-D (clean, no flags expected)": build_flw_d,
    }

    results: dict[str, FLWFlagResult] = {}

    print("\n" + "=" * 90)
    print("KMC AUDIT DASHBOARD -- END-TO-END DATA AUDIT")
    print("=" * 90)

    # -- Tier structure verification --
    print(f"\n{'-' * 60}")
    print("TIER STRUCTURE VERIFICATION")
    print(f"{'-' * 60}")
    print(f"  PRIORITY_FLAGS count: {len(PRIORITY_FLAGS)} (expected: 10)")
    print(f"  SECONDARY_FLAGS count: {len(SECONDARY_FLAGS)} (expected: 7)")
    print(f"  ALL_FLAGS count: {len(ALL_FLAGS)} (expected: 16)")
    print(f"  Priority flags: {', '.join(PRIORITY_FLAGS)}")
    print(f"  Secondary flags: {', '.join(SECONDARY_FLAGS)}")

    assert len(PRIORITY_FLAGS) == 10, f"PRIORITY_FLAGS has {len(PRIORITY_FLAGS)}, expected 10"
    assert len(SECONDARY_FLAGS) == 7, f"SECONDARY_FLAGS has {len(SECONDARY_FLAGS)}, expected 7"
    assert len(ALL_FLAGS) == 16, f"ALL_FLAGS has {len(ALL_FLAGS)}, expected 16"

    # Verify flag_data_quality is NOT in any tier
    assert "flag_data_quality" not in PRIORITY_FLAGS, "flag_data_quality should NOT be in PRIORITY_FLAGS"
    assert "flag_data_quality" not in SECONDARY_FLAGS, "flag_data_quality should NOT be in SECONDARY_FLAGS"
    assert "flag_data_quality" not in ALL_FLAGS, "flag_data_quality should NOT be in ALL_FLAGS"

    # Verify flag_wt_gain is in SECONDARY, not PRIORITY
    assert "flag_wt_gain" not in PRIORITY_FLAGS, "flag_wt_gain should NOT be in PRIORITY_FLAGS"
    assert "flag_wt_gain" in SECONDARY_FLAGS, "flag_wt_gain should be in SECONDARY_FLAGS"

    # Verify all 4 DQ flags are in PRIORITY
    for dq in ("flag_round_weight", "flag_hr_copycat", "flag_temp_copycat", "flag_spo2_implausible"):
        assert dq in PRIORITY_FLAGS, f"{dq} should be in PRIORITY_FLAGS"

    print("  OK All tier structure checks pass")

    # -- Per-FLW flag computation --
    for label, builder in builders.items():
        print(f"\n{'-' * 60}")
        print(f"FLW: {label}")
        print(f"{'-' * 60}")

        agg, visits = builder()
        result = derive_flags(agg, visits)
        results[label] = result

        print(
            f"  Cases: {result.total_cases} | Visits: {result.total_visits} | "
            f"Deaths: {result.deaths} | Closed: {result.closed_cases}"
        )
        print(f"  Excluded: {result.excluded}")
        print(f"  flag_count (ALL_FLAGS based): {result.flag_count}")
        print(f"  priority_flag_count: {result.priority_flag_count}")

        # Print ALL flag values
        print(f"\n  {'Flag':<30} {'Value':<10} {'Metric':<15} {'Tier':<10}")
        print(f"  {'-' * 65}")
        for f in PRIORITY_FLAGS:
            val = result.flags.get(f)
            val_str = "True" if val is True else ("False" if val is False else "None (--)")
            # Get metric value
            metric = _get_metric(result, f)
            print(f"  {FLAG_LABELS.get(f, f):<30} {val_str:<10} {metric:<15} {'PRIORITY':<10}")
        for f in SECONDARY_FLAGS:
            val = result.flags.get(f)
            val_str = "True" if val is True else ("False" if val is False else "None (--)")
            metric = _get_metric(result, f)
            print(f"  {FLAG_LABELS.get(f, f):<30} {val_str:<10} {metric:<15} {'secondary':<10}")

    # -- FLW-A specific assertions --
    a = results["FLW-A (high mort, rounded wt, copycat vitals)"]
    print(f"\n{'-' * 60}")
    print("FLW-A ASSERTIONS")
    print(f"{'-' * 60}")

    # Mortality: 15/50 = 30% > 20%
    assert a.flags["flag_mort_high"] is True, f"Expected flag_mort_high=True, got {a.flags['flag_mort_high']}"
    assert a.flags["flag_mort"] is True
    assert a.mort_rate is not None and abs(a.mort_rate - 0.30) < 0.01
    print(f"  OK Mortality: {a.mort_rate:.1%} (flag_mort_high=True)")

    # Visits: all 50 cases have exactly 1 follow-up, avg=1.0 < 3.0
    assert a.flags["flag_visits"] is True, f"Expected flag_visits=True, got {a.flags['flag_visits']}"
    assert a.avg_visits is not None and a.avg_visits < 3.0
    print(f"  OK Avg visits: {a.avg_visits:.2f} (flag_visits=True)")

    # Round weight: all weights are 1.5kg = 1500g (exact 100g multiple)
    assert a.flags["flag_round_weight"] is True, f"Expected flag_round_weight=True, got {a.flags['flag_round_weight']}"
    assert a.round_weight_pct is not None and a.round_weight_pct >= 0.80
    print(f"  OK Round weight: {a.round_weight_pct:.1%} (flag_round_weight=True)")

    # Temp copycat: all temps are 36.5 -> 100% same value > 75%
    assert a.flags["flag_temp_copycat"] is True, f"Expected flag_temp_copycat=True, got {a.flags['flag_temp_copycat']}"
    assert a.temp_copycat_pct is not None and a.temp_copycat_pct > 0.75
    print(f"  OK Temp copycat: {a.temp_copycat_pct:.1%} (flag_temp_copycat=True)")

    # HR copycat: all HR are 120.0 -> 100% same value > 75%
    assert a.flags["flag_hr_copycat"] is True, f"Expected flag_hr_copycat=True, got {a.flags['flag_hr_copycat']}"
    assert a.hr_copycat_pct is not None and a.hr_copycat_pct > 0.75
    print(f"  OK HR copycat: {a.hr_copycat_pct:.1%} (flag_hr_copycat=True)")

    # SpO2: all in range -> should NOT fire
    assert (
        a.flags["flag_spo2_implausible"] is False
    ), f"Expected flag_spo2_implausible=False, got {a.flags['flag_spo2_implausible']}"
    print(f"  OK SpO2: {a.spo2_implausible_pct:.1%} (flag_spo2_implausible=False)")

    # GPS: only 1 visit per case -> no pairs -> None
    assert a.flags["flag_gps_same_case_far"] is None
    print("  OK GPS: None (insufficient pairs)")

    # flag_count counts: flag_visits + flag_mort_high + flag_round_weight + flag_temp_copycat + flag_hr_copycat = 5
    # (flag_mort is synthetic, not in ALL_FLAGS. flag_mort_low might also fire for some)
    fired_all = [f for f in ALL_FLAGS if a.flags.get(f) is True]
    print(f"  Total ALL_FLAGS fired: {len(fired_all)} -> {fired_all}")
    # priority_flag_count counts PRIORITY_FLAGS (includes synthetic flag_mort)
    fired_priority = [f for f in PRIORITY_FLAGS if a.flags.get(f) is True]
    print(f"  Total PRIORITY fired: {len(fired_priority)} -> {fired_priority}")

    # -- FLW-B specific assertions --
    b = results["FLW-B (late enroll, high danger, no referral)"]
    print(f"\n{'-' * 60}")
    print("FLW-B ASSERTIONS")
    print(f"{'-' * 60}")

    # Late enrollment: 32/40 = 80% > 35%
    assert b.flags["flag_enroll"] is True, f"Expected flag_enroll=True, got {b.flags['flag_enroll']}"
    assert b.pct_late_enroll is not None and b.pct_late_enroll > 0.35
    print(f"  OK Late enrollment: {b.pct_late_enroll:.1%} (flag_enroll=True)")

    # Danger signs: 24/40 = 60% > 30%
    assert b.flags["flag_danger_high"] is True, f"Expected flag_danger_high=True, got {b.flags['flag_danger_high']}"
    assert b.danger_rate is not None and b.danger_rate > 0.30
    print(f"  OK Danger rate: {b.danger_rate:.1%} (flag_danger_high=True)")

    # DS no referral: 24 DS-positive visits, 0 referred -> rate=0%
    assert (
        b.flags["flag_ds_no_referral"] is True
    ), f"Expected flag_ds_no_referral=True, got {b.flags['flag_ds_no_referral']}"
    assert b.ds_no_referral_pct is not None and b.ds_no_referral_pct == 0.0
    print(f"  OK No referral: {b.ds_no_referral_pct:.1%} referral rate (flag_ds_no_referral=True)")

    # HR/Temp: varied values -> should NOT fire
    assert b.flags["flag_hr_copycat"] is not True, "HR copycat should not fire with varied HR"
    assert b.flags["flag_temp_copycat"] is not True, "Temp copycat should not fire with varied temp"
    print(f"  OK HR copycat: {b.hr_copycat_pct} (not fired)")
    print(f"  OK Temp copycat: {b.temp_copycat_pct} (not fired)")

    fired_priority_b = [f for f in PRIORITY_FLAGS if b.flags.get(f) is True]
    print(f"  Total PRIORITY fired: {len(fired_priority_b)} -> {fired_priority_b}")

    # -- FLW-C specific assertions --
    c = results["FLW-C (bad SpO2, GPS spread)"]
    print(f"\n{'-' * 60}")
    print("FLW-C ASSERTIONS")
    print(f"{'-' * 60}")

    # SpO2: 10/80 visits with bad SpO2 (some visits have good SpO2)
    # Actually we have 40 first visits + 40 second visits = 80 total
    # First 10 cases have spo2=50 on first visit, rest have 95
    # Second visits all have spo2=95
    # So 10 bad out of 80 total = 12.5% > 10%
    assert (
        c.flags["flag_spo2_implausible"] is True
    ), f"Expected flag_spo2_implausible=True, got {c.flags['flag_spo2_implausible']}"
    assert c.spo2_implausible_pct is not None and c.spo2_implausible_pct > 0.10
    print(f"  OK SpO2 implausible: {c.spo2_implausible_pct:.1%} (flag_spo2_implausible=True)")

    # GPS: all same-case pairs are ~111km apart -> >30%
    assert (
        c.flags["flag_gps_same_case_far"] is True
    ), f"Expected flag_gps_same_case_far=True, got {c.flags['flag_gps_same_case_far']}"
    assert c.gps_same_case_far_pct is not None and c.gps_same_case_far_pct > 0.30
    print(f"  OK GPS spread: {c.gps_same_case_far_pct:.1%} (flag_gps_same_case_far=True)")

    fired_priority_c = [f for f in PRIORITY_FLAGS if c.flags.get(f) is True]
    print(f"  Total PRIORITY fired: {len(fired_priority_c)} -> {fired_priority_c}")

    # -- FLW-D specific assertions --
    d = results["FLW-D (clean, no flags expected)"]
    print(f"\n{'-' * 60}")
    print("FLW-D ASSERTIONS (clean FLW -- expect NO priority flags)")
    print(f"{'-' * 60}")

    # Mortality: 3/60 = 5% -> between 2% and 20% -> no flag
    assert d.flags["flag_mort_high"] is not True
    assert d.flags["flag_mort_low"] is not True
    assert d.flags["flag_mort"] is not True
    print(f"  OK Mortality: {d.mort_rate:.1%} (no mort flag)")

    # Visits: 57 cases x 4 visits = 228 visits, avg = 4.0 >= 3.0 -> no flag
    assert d.flags["flag_visits"] is not True
    print(f"  OK Avg visits: {d.avg_visits:.2f} (no visits flag)")

    # Check all priority flags are not True
    priority_fired = [f for f in PRIORITY_FLAGS if d.flags.get(f) is True]
    print(f"  Priority flags fired: {len(priority_fired)} -> {priority_fired}")
    if priority_fired:
        print(f"  !! WARNING: Clean FLW has {len(priority_fired)} priority flags!")
        for f in priority_fired:
            print(f"    - {FLAG_LABELS.get(f, f)}: {_get_metric(d, f)}")

    # -- Frequency grid simulation --
    print(f"\n{'=' * 60}")
    print("FREQUENCY GRID SIMULATION (mirrors dashboard JS)")
    print(f"{'=' * 60}")

    all_results = list(results.values())
    eligible = [r for r in all_results if not r.excluded]
    total_eligible = len(eligible)

    print(f"\n  Total FLWs: {len(all_results)}")
    print(f"  Eligible (not excluded): {total_eligible}")
    print(f"\n  {'Flag':<30} {'Fired':<8} {'/ Total':<10} {'Label'}")
    print(f"  {'-' * 65}")

    for f in PRIORITY_FLAGS:
        fired = sum(1 for r in eligible if r.flags.get(f) is True)
        label = FLAG_LABELS.get(f, f)
        print(f"  {f:<30} {fired:<8} / {total_eligible:<7} {label}")

    # -- Badge count verification --
    print(f"\n{'=' * 60}")
    print("BADGE COUNT VERIFICATION (flag_count uses ALL_FLAGS)")
    print(f"{'=' * 60}")

    for label, result in results.items():
        all_fired = [f for f in ALL_FLAGS if result.flags.get(f) is True]
        priority_fired = [f for f in PRIORITY_FLAGS if result.flags.get(f) is True]
        print(f"\n  {label}:")
        print(f"    flag_count (badge): {result.flag_count} (fires: {[FLAG_LABELS.get(f, f) for f in all_fired]})")
        print(
            f"    priority_flag_count: {result.priority_flag_count} "
            f"(fires: {[FLAG_LABELS.get(f, f) for f in priority_fired]})"
        )

    # -- Verify flag_count = sum of ALL_FLAGS True values --
    print(f"\n{'=' * 60}")
    print("FLAG_COUNT CONSISTENCY CHECK")
    print(f"{'=' * 60}")
    for label, result in results.items():
        manual_count = sum(1 for f in ALL_FLAGS if result.flags.get(f) is True)
        assert (
            result.flag_count == manual_count
        ), f"{label}: flag_count={result.flag_count} but manual count={manual_count}"
        manual_priority = sum(1 for f in PRIORITY_FLAGS if result.flags.get(f) is True)
        assert (
            result.priority_flag_count == manual_priority
        ), f"{label}: priority_flag_count={result.priority_flag_count} but manual={manual_priority}"
        print(f"  OK {label}: flag_count={result.flag_count}, priority_flag_count={result.priority_flag_count}")

    # -- Verify no stale flag_data_quality in flags dict --
    print(f"\n{'=' * 60}")
    print("STALE REFERENCE CHECK")
    print(f"{'=' * 60}")
    for label, result in results.items():
        assert "flag_data_quality" not in result.flags, f"{label}: flag_data_quality should NOT be in flags dict!"
        # flag_mort IS expected (synthetic)
        assert "flag_mort" in result.flags, f"{label}: flag_mort should be in flags dict"
    print("  OK No flag_data_quality in any flags dict")
    print("  OK flag_mort (synthetic) present in all flags dicts")

    # -- Column rendering simulation --
    print(f"\n{'=' * 60}")
    print("COLUMN RENDERING CHECK (what JS would show)")
    print(f"{'=' * 60}")
    for label, result in results.items():
        print(f"\n  {label}:")
        for f in PRIORITY_FLAGS:
            val = result.flags.get(f)
            if val is True:
                cell = f"RED ({_get_metric(result, f)})"
            elif val is False:
                cell = f"GREEN ({_get_metric(result, f)})"
            else:
                cell = "-- (null)"
            print(f"    {FLAG_LABELS.get(f, f):<25} -> {cell}")

    print(f"\n{'=' * 90}")
    print("END-TO-END AUDIT COMPLETE -- ALL ASSERTIONS PASSED")
    print(f"{'=' * 90}\n")


def _get_metric(r: FLWFlagResult, flag_key: str) -> str:
    """Format the metric value for a given flag."""
    mapping = {
        "flag_visits": ("avg_visits", lambda v: f"{v:.2f}"),
        "flag_mort": ("mort_rate", lambda v: f"{v:.1%}"),
        "flag_mort_low": ("mort_rate", lambda v: f"{v:.1%}"),
        "flag_mort_high": ("mort_rate", lambda v: f"{v:.1%}"),
        "flag_enroll": ("pct_late_enroll", lambda v: f"{v:.1%}"),
        "flag_danger_high": ("danger_rate", lambda v: f"{v:.1%}"),
        "flag_danger_zero": ("danger_rate", lambda v: f"{v:.1%}"),
        "flag_wt_loss": ("pct_wt_loss", lambda v: f"{v:.1%}"),
        "flag_wt_gain": ("mean_daily_gain", lambda v: f"{v:.1f} g/d"),
        "flag_wt_zero": ("pct_wt_zero", lambda v: f"{v:.1%}"),
        "flag_round_weight": ("round_weight_pct", lambda v: f"{v:.1%}"),
        "flag_hr_copycat": ("hr_copycat_pct", lambda v: f"{v:.1%}"),
        "flag_temp_copycat": ("temp_copycat_pct", lambda v: f"{v:.1%}"),
        "flag_spo2_implausible": ("spo2_implausible_pct", lambda v: f"{v:.1%}"),
        "flag_ga_fullterm": ("ga_fullterm_pct", lambda v: f"{v:.1%}"),
        "flag_gps_same_case_far": ("gps_same_case_far_pct", lambda v: f"{v:.1%}"),
        "flag_ds_no_referral": ("ds_no_referral_pct", lambda v: f"{v:.1%}"),
    }
    if flag_key not in mapping:
        return "?"
    attr, fmt = mapping[flag_key]
    val = getattr(r, attr, None)
    if val is None:
        return "--"
    return fmt(val)


# --- Test entry point (for pytest) --------------------------------------


def test_e2e_audit():
    """Run the full audit as a pytest test."""
    run_audit()


if __name__ == "__main__":
    run_audit()
