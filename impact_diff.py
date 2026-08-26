#!/usr/bin/env python3
"""impact_diff.py - answer "what will this change do to the regression guard?" BEFORE pushing.

WHY THIS EXISTS
---------------
On 2026-08-26 the publish job failed three avoidable times in a row while removing one cohort
(1NPS1) from the dashboard. Every failure was the SAME failure: a cumulative counter that had
included the removed cohort went down, and the guard blocked it, as designed.

I knew that would happen. I wrote it down before starting. Then I still discovered WHICH counters
one failed CI run at a time:

  attempt 2  the waiver said `connectFunnel`, but metric names are dotted -
             `connectFunnel.2WT.accepted` - and the matcher takes globs, not prefixes.
  attempt 3  brutal_verify keeps its OWN copy of the cohort mapping and still knew about NPS.
  attempt 4  five more counters nobody had listed: flwMatrix.rows, sources.*, table1.Overall.*

preflight.py could not have caught any of these. It answers "will this CODE pass CI?". It does not
answer "will this CHANGE trip the regression guard?". For anything that REMOVES data those are
different questions, and only the second one mattered.

This module answers the second one, by measurement rather than by reasoning:

    # 1. BEFORE touching anything, off the current build:
    python impact_diff.py --snapshot before

    # 2. make the change, then rebuild in the correct order:
    python build_payload_agg.py && python build_dashboard_data.py

    # 3. read off the exact damage:
    python impact_diff.py

It prints every metric that fell or vanished, and the exact, ready-to-paste value for the
`allow_regression` input on the workflow_dispatch. One pass, no CI round-trips.

WHY BEFORE/AFTER AND NOT AGAINST LIVE
-------------------------------------
The local build is chronically smaller than live (~6.2k master rows against ~10.5k) because
hq_pull_full/ is a patchwork of per-domain pulls. Diffing local against live would drown the real
signal in staleness. Diffing local-before against local-after cancels the staleness exactly: both
sides are equally stale, so every remaining difference is the change itself.

`--baseline live` and `--baseline history` exist for the cases where you want them, and both say
loudly what they are comparing.

EXIT CODES
    0  nothing fell; the guard will not object
    2  something fell; the waiver line is printed - review every entry before using it
    1  could not run (missing build, missing snapshot)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import regression_guard as rg

ROOT = Path(__file__).parent
SNAP_DIR = ROOT / ".impact_snapshots"
DASHBOARD_JSON = ROOT / "dashboard_data.json"
LIVE_JSON = ROOT / "_live_full.json"


# ----------------------------------------------------------------------------------- collection
def _metrics_of(dd: dict) -> dict:
    """Every metric the guard actually compares, in one flat dict.

    Tier 1 (hard monotonic) and Tier 2 (per-arm, tolerance) are collected separately because they
    fail on different rules, and a change that is fine under Tier 2 tolerance must not be waived.
    """
    entry = rg.make_entry(dd)
    tier1 = rg._metrics(entry)
    # the guard synthesises this one at check time; mirror it or it is invisible here
    tier1["connectFunnel.TOTAL.invited"] = sum(
        v for k, v in tier1.items() if k.startswith("connectFunnel.") and k.endswith(".invited")
    )
    return {
        "tier1": tier1,
        "tier2": rg._arm_metrics(entry),
        "structural": {k: dd.get(k) for k in ("unmappedCohorts", "connectPendingSubgroups") if dd.get(k) is not None},
        "built_at": dd.get("built_at"),
        "today": dd.get("today"),
    }


def _load_dd(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"impact_diff: {path.name} not found - build first (build_payload_agg then build_dashboard_data)")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# -------------------------------------------------------------------------------------- reporting
def _tier1_drops(before: dict, after: dict) -> list[tuple]:
    """Tier 1 tolerance is ZERO, and a VANISHED metric fails too (guard: `if new is None`)."""
    out = []
    for metric, old in sorted(before.items()):
        new = after.get(metric)
        if new is None:
            out.append((metric, old, None, "VANISHED"))
        elif isinstance(old, int) and isinstance(new, int) and new < old:
            out.append((metric, old, new, f"-{old - new}"))
    return out


def _tier2_drops(before: dict, after: dict) -> list[tuple]:
    """Tier 2 allows max(ARM_DROP_ABS, ARM_DROP_PCT * prior). Only report breaches of that."""
    out = []
    for metric, old in sorted(before.items()):
        new = after.get(metric)
        if new is None:
            out.append((metric, old, None, "VANISHED"))
            continue
        if not (isinstance(old, int) and isinstance(new, int)) or new >= old:
            continue
        allowed = max(rg.ARM_DROP_ABS, int(rg.ARM_DROP_PCT * old))
        if (old - new) > allowed:
            out.append((metric, old, new, f"-{old - new} (tolerance {allowed})"))
    return out


def _floor_breaches(after_tier1: dict, history: list) -> list[tuple]:
    """The floors are enforced with or without history, so a big removal can breach one directly."""
    out = []
    for metric, static_floor in rg.FLOORS.items():
        val = after_tier1.get(metric)
        if val is None:
            continue
        best = max((rg._metrics(h).get(metric) or 0) for h in history) if history else 0
        floor = max(static_floor, int(rg.FLOOR_FRACTION_OF_HISTORY * best))
        if val <= floor:
            out.append((metric, val, floor))
    return out


def _print_table(title: str, rows: list[tuple], headers: tuple) -> None:
    print(f"\n{title}")
    if not rows:
        print("  none")
        return
    w = max(len(str(r[0])) for r in rows)
    print(f"  {headers[0]:<{w}}  {headers[1]:>9}  {headers[2]:>9}  {headers[3]}")
    for metric, old, new, delta in rows:
        print(f"  {metric:<{w}}  {old!s:>9}  {'-' if new is None else new:>9}  {delta}")


# ------------------------------------------------------------------------------------------ modes
def do_snapshot(label: str) -> int:
    SNAP_DIR.mkdir(exist_ok=True)
    dd = _load_dd(DASHBOARD_JSON)
    snap = _metrics_of(dd)
    path = SNAP_DIR / f"{label}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=1, sort_keys=True)
    print(f"snapshot '{label}' -> {path.relative_to(ROOT)}")
    print(f"  built_at {snap['built_at']}  |  {len(snap['tier1'])} tier-1 + {len(snap['tier2'])} tier-2 metrics")
    print(
        f"  counts.master_rows {snap['tier1'].get('counts.master_rows')}  "
        f"started {snap['tier1'].get('counts.started')}  "
        f"cohorts {snap['tier1'].get('counts.cohorts')}"
    )
    return 0


def do_compare(before_label: str, baseline: str) -> int:
    after = _metrics_of(_load_dd(DASHBOARD_JSON))

    if baseline == "snapshot":
        path = SNAP_DIR / f"{before_label}.json"
        if not path.exists():
            sys.exit(
                f"impact_diff: no snapshot '{before_label}'.\n"
                f"  Take one BEFORE the change:  python impact_diff.py --snapshot {before_label}\n"
                f"  Or compare against live:     python impact_diff.py --baseline live"
            )
        with open(path, encoding="utf-8") as fh:
            before = json.load(fh)
        src = f"snapshot '{before_label}' (built_at {before.get('built_at')})"
    elif baseline == "live":
        if not LIVE_JSON.exists():
            sys.exit("impact_diff: _live_full.json not found - run `python _pull_full_live.py` first")
        before = _metrics_of(_load_dd(LIVE_JSON))
        src = "LIVE published render"
        print("!" * 92)
        print("!! BASELINE = LIVE. The local build is chronically SMALLER than live (stale hq_pull_full/),")
        print("!! so most of what follows will be staleness, not your change. Prefer --snapshot before.")
        print("!" * 92)
    else:  # history
        hist = rg.load_history()
        if not hist:
            sys.exit("impact_diff: _run_history.json is empty or absent (it is carried in the CI cache, not git)")
        before = {
            "tier1": rg._metrics(hist[-1]),
            "tier2": rg._arm_metrics(hist[-1]),
            "structural": {},
            "built_at": hist[-1].get("built_at"),
        }
        src = f"run history, last entry ({hist[-1].get('date')})"

    print(f"\nBASELINE : {src}")
    print(f"CURRENT  : local dashboard_data.json (built_at {after['built_at']})")

    t1 = _tier1_drops(before.get("tier1") or {}, after["tier1"])
    t2 = _tier2_drops(before.get("tier2") or {}, after["tier2"])
    floors = _floor_breaches(after["tier1"], rg.load_history())

    _print_table(
        "TIER 1 - hard monotonic, tolerance ZERO. Every row here FAILS the guard:",
        t1,
        ("metric", "before", "after", "delta"),
    )
    _print_table(
        "TIER 2 - per-arm, tolerance max(3, 2%). Only breaches shown:", t2, ("metric", "before", "after", "delta")
    )

    print("\nABSOLUTE FLOORS (enforced with or without history):")
    if floors:
        for metric, val, floor in floors:
            print(f"  BREACHED  {metric} = {val} <= {floor}")
        print("  A floor breach is NOT waivable by allow_regression. Do not push this build.")
    else:
        print("  none breached")

    # connectPendingSubgroups is non-empty on almost every LOCAL build, because the Connect snapshot
    # here is stale and those subgroups have no enrolment leg yet (see the 2026-08-04 undercount).
    # That is a local artefact, not the failure this tool is looking for. CI pulls Connect live.
    local_only = {"connectPendingSubgroups"} if not os.environ.get("INTERVIEWS_STRICT_FRESHNESS") else set()
    struct = {k: v for k, v in (after.get("structural") or {}).items() if v}
    real_struct = {k: v for k, v in struct.items() if k not in local_only}
    print("\nSTRUCTURAL INVARIANTS (must be empty lists):")
    if real_struct:
        for k, v in real_struct.items():
            print(f"  NON-EMPTY  {k} = {v!r}")
        print("  Also not waivable. Cohorts have fallen off the map - fix the mapping, not the guard.")
    else:
        print("  clean")
    for k, v in struct.items():
        if k in local_only:
            print(f"  [local]    {k} = {v!r} - expected on a local build (stale Connect snapshot), CI pulls live")
    struct = real_struct

    dropped = [r[0] for r in t1] + [r[0] for r in t2]
    if not dropped:
        print("\nRESULT: nothing fell. The regression guard will not object. No waiver needed.")
        return 0

    print(f"\nRESULT: {len(dropped)} metric(s) will fail the guard.")
    print("\nPaste this into the workflow_dispatch `allow_regression` input, VERBATIM:")
    print("\n  " + ",".join(dropped))
    print("\n  Exact names, not prefixes. `connectFunnel` does NOT match `connectFunnel.2WT.accepted`;")
    print("  the matcher is fnmatch, so a prefix needs a trailing `.*` to work.")
    print("\n  Check every name above is a drop you INTENDED. A waiver is a one-off for a deliberate")
    print("  change; anything in that list you cannot explain is a bug you are about to publish.")
    if floors or struct:
        print("\n  WARNING: a floor breach or structural failure is listed above and CANNOT be waived.")
    return 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--snapshot",
        metavar="LABEL",
        nargs="?",
        const="before",
        help="record the CURRENT build's metrics under LABEL (default 'before')",
    )
    p.add_argument("--before", default="before", metavar="LABEL", help="snapshot to compare against")
    p.add_argument(
        "--baseline",
        choices=("snapshot", "live", "history"),
        default="snapshot",
        help="what to diff against (default: snapshot)",
    )
    a = p.parse_args(argv)
    if a.snapshot is not None:
        return do_snapshot(a.snapshot)
    return do_compare(a.before, a.baseline)


if __name__ == "__main__":
    sys.exit(main())
