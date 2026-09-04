"""Day-over-day REGRESSION GUARD for the Connect Interviews dashboard.

WHY THIS EXISTS
---------------
Every other gate in this pipeline (audit_e2e.py, build_dashboard_data_audit.py, brutal_verify.py)
is *relative*: each one re-derives the expected value from the same source files the dashboard was
built from. That makes them excellent at catching build-layer bugs and useless at catching source
degradation. If an HQ domain 401s, an OCS pull truncates, or the Connect snapshot reassembles
empty, every number on the dashboard shrinks — and every gate still passes, because the gates
recompute from the degraded source and match it perfectly. The run publishes a silently smaller
dashboard to stakeholders.

This module is the only *absolute* gate: it compares today's run against a persisted history of
prior runs (`_run_history.json`) and against hard floors that hold with no history at all.

THREE TIERS
-----------
  Tier 1  hard monotonic (tolerance 0) — cumulative counters that can never legitimately shrink:
          counts.*, per-ROLL-subgroup + Overall table1.{flws,ist,icmp},
          connectFunnel[sg].{invited,accepted,learn_completed,claimed},
          the A/B arm-PAIR SUMS of table3, and the raw source counts.
  Tier 2  oscillation-tolerant — the per-ARM rows of table3 (ABT1-A/B, ABT2-A/B, ABT3-A/B). One FLW
          can hold membership in BOTH arms of a pair, so an arm figure legitimately wobbles by a few
          FLWs run to run (root-caused 2026-07-28: cross-arm double counting at the per-ARM level;
          the subgroup and overall totals were proven monotonic, the arm splits were not).
          Fail only on a drop greater than max(3, 2%). The arm-pair SUM is in Tier 1, which is
          where the real signal lives anyway.
  Tier 3  stall detection — a live programme always adds interviews. If counts.started is
          byte-identical across 3 consecutive runs, a source is frozen. Also asserts the two
          structural "nothing fell off the map" invariants: unmappedCohorts and
          connectPendingSubgroups must both be empty.

ABSOLUTE FLOORS (always enforced, even with no history)
-------------------------------------------------------
Floors are the backstop for the very first run, for a lost/evicted history cache, and for the
"everything went to zero" collapse. They are deliberately set at ~55% of the values measured on
the real 2026-08-07 build, so:
  * they can never be tripped by growth (a floor is a minimum; growth only moves values away);
  * a legitimate downward correction (e.g. excluding a batch of test accounts, which has happened
    twice on this project and moved counts by low single-digit percent) cannot trip them either;
  * a real collapse — a dead domain, a truncated OCS pull, an empty Connect snapshot — halves or
    zeroes the number and always trips them.
Once history exists, Tier 1 catches ANY decrease at tolerance 0, so the floors only have to catch
catastrophes, not drift. That is why they are slack rather than tight.

  metric                       2026-08-07 actual   floor    floor as % of actual
  counts.master_rows                       6221     3400                    55%
  counts.started                           5683     3100                    55%
  counts.claimed_pairs                     3326     1800                    54%
  sum(connectFunnel.invited)               3955     2100                    53%
  len(flwMatrix)                           3326     1800                    54%
  sources.ocs_sessions                    18265    10000                    55%

STRICTNESS
----------
History-based checks (Tier 1/2/3) are enforced only when INTERVIEWS_STRICT_FRESHNESS=1 — the same
switch brutal_verify.py uses, and the one the daily CI sets. A local no-credential build runs on
intentionally-static source files and must not fail. Absolute floors and the structural invariants
are enforced ALWAYS. A missing or empty history file is never a failure: the run records and passes.

ESCAPE HATCH
------------
INTERVIEWS_ALLOW_REGRESSION=<comma-separated metric names, glob patterns, or "all">
waives specific metrics for one reviewed run (e.g. shipping a test-account exclusion that
legitimately lowers counts). Every use is logged loudly and echoed into the GitHub step summary.

USAGE
-----
  python regression_guard.py check     # gate: read dashboard_data.json + _run_history.json
  python regression_guard.py record    # append today's entry (call ONLY after a successful publish)
  python regression_guard.py show      # dump the recorded history compactly

  from regression_guard import record, check, load_history
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
HISTORY_JSON = ROOT / "_run_history.json"
DASHBOARD_JSON = ROOT / "dashboard_data.json"
OCS_STATE_CACHE = ROOT / "_ocs_state_cache.json"
CONNECT_SNAPSHOT = ROOT / "connect_user_data_snapshot.csv"
HQ_PULL_DIR = ROOT / "hq_pull_full"

MAX_HISTORY = 30

# Rollup subgroups that appear as table1 rows (mirrors ROLL in build_payload_agg.py) + "Overall".
# Read from the data rather than hardcoded, so onboarding a new subgroup needs no edit here.
ARM_PAIRS = {"ABT1": ("ABT1-A", "ABT1-B"), "ABT2": ("ABT2-A", "ABT2-B"), "ABT3": ("ABT3-A", "ABT3-B")}

COUNT_KEYS = ("cohorts", "flws", "master_rows", "started", "completed", "claimed_pairs")
T1_FIELDS = ("flws", "ist", "icmp")
CF_FIELDS = ("invited", "accepted", "learn_completed", "claimed")
SOURCE_KEYS = ("ocs_sessions", "trigger_rows", "connect_snapshot_rows", "trigger_files", "ocs_newest_age_days")
# Not every source figure is a cumulative counter, and Tier 1 assumes they all are. An AGE falls when
# fresh data arrives, which is the HEALTHY direction, so holding it to monotonicity would fail the
# publish at the exact moment a stuck pull recovered. It stays in the metrics so Tier 3 and the run
# history can both read it; it is only excluded from the monotonic comparison.
NON_CUMULATIVE_SOURCES = frozenset({"ocs_newest_age_days"})

# Tier 2 tolerance: a per-arm figure may fall by up to max(ARM_ABS, ARM_PCT * prior) without failing.
ARM_DROP_ABS = 3
ARM_DROP_PCT = 0.02

# Absolute floors ≈ 55% of the LIVE 2026-08-07 build (render v140: master_rows 9909, started 9372,
# flwMatrix 3327, Σinvited 3956, ocs_sessions ~18.3k).
#
# ⚠️ These were first calibrated against a LOCAL build that turned out to be 39% smaller than live,
# because hq_pull_full/ held stale per-domain pulls (PANEL from 26-Jun, ABT3/2WT from 06-Jul, EXT from
# 27-Jul) — and all 196 gate checks passed on it, which is precisely the blind spot this module exists
# to cover. Always calibrate floors against the LIVE payload, never a local tree.
FLOORS = {
    "counts.master_rows": 5400,
    "counts.started": 5100,
    "counts.claimed_pairs": 1800,
    "connectFunnel.TOTAL.invited": 2150,
    "flwMatrix.rows": 1800,
    "sources.ocs_sessions": 10000,
}
# A static floor goes stale as the programme grows. Once there is history, the effective floor is the
# larger of the static value and this fraction of the best figure ever recorded, so the bar rises with
# the data and a 60% collapse can never sit "above the floor" just because the floor was set years ago.
FLOOR_FRACTION_OF_HISTORY = 0.55

STALL_RUNS = 3  # counts.started identical across this many consecutive runs => frozen source
# How stale OCS's newest session must be before a frozen count reads as a quiet programme rather than
# a stuck pull. Two days: the pull runs daily, so a genuinely stuck one still has yesterday's session
# sitting in the cache, while a wound-down programme leaves nothing new for days. Measured on the
# 2026-09-04 block, OCS's newest session was 2 days old and falling - 16 sessions on 28 Aug, 2 on 2 Sep.
# It MUST exceed STALL_RUNS. Flatness takes STALL_RUNS days to establish, and while sources are
# frozen the newest session ages exactly one day per run, so a threshold at or below STALL_RUNS can
# never be met while the stall is still detectable - the fail branch becomes unreachable and the
# check silently does nothing. Proven vacuous at 2; +2 leaves a real stuck pull two runs to shout.
STALL_QUIET_DAYS = STALL_RUNS + 2

# The last day the programme collected interviews, declared rather than inferred.
#
# A finished programme and a stuck pull are byte-identical in the data: both show a frozen interview
# count beside a frozen source, and both leave the newest session ageing a day at a time. No amount
# of arithmetic separates them, so one of them has to be declared. Past this date a frozen count is
# the expected steady state and Tier 3 stops asking.
#
# Tier 1 stays live throughout - a FALL in any counter still fails, which is the signal that
# actually matters once collection has stopped.
#
# The bot was deactivated after 2026-09-02 (last session 04:34, against 16 on 28 Aug). If the
# programme RESUMES, set this back to None or the stall check stays switched off for the new run.
PROGRAMME_ENDED = "2026-09-02"


# --------------------------------------------------------------------------------------- helpers
def _strict() -> bool:
    return bool(os.environ.get("INTERVIEWS_STRICT_FRESHNESS"))


def _programme_ended() -> tuple[bool, str]:
    """(has the declared programme end passed, the date it was declared for).

    INTERVIEWS_PROGRAMME_ENDED overrides the constant; set it empty to switch the exemption off.
    """
    raw = os.environ.get("INTERVIEWS_PROGRAMME_ENDED", PROGRAMME_ENDED)
    if not raw:
        return False, ""
    try:
        return date.today() > date.fromisoformat(raw), raw
    except ValueError:
        return False, ""


def _allowlist() -> list[str]:
    raw = os.environ.get("INTERVIEWS_ALLOW_REGRESSION", "").strip()
    return [p.strip() for p in raw.split(",") if p.strip()] if raw else []


def _is_waived(metric: str, allow: list[str]) -> bool:
    return any(p.lower() == "all" or p == metric or fnmatch.fnmatch(metric, p) for p in allow)


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=15
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def _load_json(path: Path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# ------------------------------------------------------------------------------- source counting
def source_counts(extra_sources: dict | None = None) -> dict:
    """Cheap row/file counts straight off the raw source artifacts.

    A source that is ABSENT records None and is skipped by check() — absence means "this run did
    not stage that artifact" (e.g. the CI deletes connect_user_data_snapshot.csv after publishing),
    not "the source collapsed". A source that is PRESENT BUT EMPTY records 0, which is a decrease
    and therefore a Tier 1 failure — that is exactly the "snapshot reassembled empty" case.
    """
    out: dict[str, int | None] = {k: None for k in SOURCE_KEYS}

    if OCS_STATE_CACHE.exists():
        cache = _load_json(OCS_STATE_CACHE)
        rows: list = []
        if isinstance(cache, list):
            rows = cache
        elif isinstance(cache, dict):
            # tolerate a future dict-shaped cache ({sid: state} or {"sessions": [...]})
            sess = cache.get("sessions")
            rows = sess if isinstance(sess, list) else list(cache.values())
        out["ocs_sessions"] = len(rows)
        # AGE of the newest session, not just how many there are. The stall check needs to tell a
        # stuck pull from a quiet programme, and it cannot do that on the count alone: when interviews
        # genuinely stop, the count freezes too and an idle programme looks identical to a broken one.
        # A frozen count beside a session from this morning is a stuck pull; a frozen count beside a
        # session from a week ago is simply nobody interviewing.
        newest = ""
        for r in rows:
            if not isinstance(r, dict):
                continue
            t = (r.get("updated_at") or r.get("created_at") or "")[:10]
            if t > newest:
                newest = t
        if newest:
            try:
                out["ocs_newest_age_days"] = (date.today() - date.fromisoformat(newest)).days
            except ValueError:
                pass

    if HQ_PULL_DIR.is_dir():
        trig_files = sorted(HQ_PULL_DIR.glob("*trigger_bot.jsonl"))
        out["trigger_files"] = len(trig_files)
        rows = 0
        for fp in trig_files:
            with open(fp, encoding="utf-8") as fh:
                rows += sum(1 for ln in fh if ln.strip())
        out["trigger_rows"] = rows

    if CONNECT_SNAPSHOT.exists():
        with open(CONNECT_SNAPSHOT, encoding="utf-8", newline="") as fh:
            rdr = csv.reader(fh)
            try:
                next(rdr)  # header
                out["connect_snapshot_rows"] = sum(1 for r in rdr if any(c.strip() for c in r))
            except StopIteration:
                out["connect_snapshot_rows"] = 0  # present but empty -> a real regression

    if extra_sources:
        out.update({k: v for k, v in extra_sources.items()})
    return out


# ------------------------------------------------------------------------------ entry extraction
def _claimed_pairs(dd: dict) -> int | None:
    cp = (dd.get("counts") or {}).get("claimed_pairs")
    if isinstance(cp, int):
        return cp
    fm = dd.get("flwMatrix")
    if isinstance(fm, list):
        return len(fm)  # brutal_verify proves flwMatrix rows == claimed (FLW,cohort) pairs
    pay = _load_json(ROOT / "payload_agg.json") or {}
    return (pay.get("counts") or {}).get("claimed_pairs")


def make_entry(dd: dict, extra_sources: dict | None = None) -> dict:
    counts = dict(dd.get("counts") or {})
    entry = {
        "date": dd.get("today") or date.today().isoformat(),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "built_at": dd.get("built_at"),
        "git_sha": _git_sha(),
        "counts": {k: counts.get(k) for k in COUNT_KEYS if k != "claimed_pairs"},
        "table1": {r["key"]: {f: r.get(f) for f in T1_FIELDS} for r in dd.get("table1") or [] if r.get("key")},
        "table3": {r["key"]: {f: r.get(f) for f in T1_FIELDS} for r in dd.get("table3") or [] if r.get("key")},
        "connectFunnel": {
            r["sg"]: {f: r.get(f) for f in CF_FIELDS} for r in dd.get("connectFunnel") or [] if r.get("sg")
        },
        "flwMatrix_rows": len(dd.get("flwMatrix") or []),
        "sources": source_counts(extra_sources),
    }
    entry["counts"]["claimed_pairs"] = _claimed_pairs(dd)
    return entry


def _metrics(entry: dict) -> dict[str, int]:
    """Flatten one history entry into {metric_name: value} for the TIER 1 comparison."""
    m: dict[str, int] = {}
    for k, v in (entry.get("counts") or {}).items():
        if isinstance(v, int):
            m[f"counts.{k}"] = v
    for key, row in (entry.get("table1") or {}).items():
        for f in T1_FIELDS:
            if isinstance(row.get(f), int):
                m[f"table1.{key}.{f}"] = row[f]
    for sg, row in (entry.get("connectFunnel") or {}).items():
        for f in CF_FIELDS:
            if isinstance(row.get(f), int):
                m[f"connectFunnel.{sg}.{f}"] = row[f]
    # A/B arm-PAIR SUMS are monotonic even though the individual arms are not (an FLW in both arms
    # of a pair moves between the two arm rows but never leaves the pair).
    t3 = entry.get("table3") or {}
    for pair, (a, b) in ARM_PAIRS.items():
        if a in t3 and b in t3:
            for f in T1_FIELDS:
                va, vb = t3[a].get(f), t3[b].get(f)
                if isinstance(va, int) and isinstance(vb, int):
                    m[f"table3pair.{pair}.{f}"] = va + vb
    if isinstance(t3.get("Overall"), dict):
        for f in T1_FIELDS:
            if isinstance(t3["Overall"].get(f), int):
                m[f"table3.Overall.{f}"] = t3["Overall"][f]
    for k, v in (entry.get("sources") or {}).items():
        if isinstance(v, int):
            m[f"sources.{k}"] = v
    if isinstance(entry.get("flwMatrix_rows"), int):
        m["flwMatrix.rows"] = entry["flwMatrix_rows"]
    return m


def _arm_metrics(entry: dict) -> dict[str, int]:
    """Flatten the per-ARM table3 rows — the TIER 2 (oscillation-tolerant) set."""
    m: dict[str, int] = {}
    for pair, arms in ARM_PAIRS.items():
        for arm in arms:
            row = (entry.get("table3") or {}).get(arm) or {}
            for f in T1_FIELDS:
                if isinstance(row.get(f), int):
                    m[f"table3.{arm}.{f}"] = row[f]
    return m


# --------------------------------------------------------------------------------------- history
def load_history(path: Path | str = HISTORY_JSON) -> list[dict]:
    data = _load_json(Path(path))
    return data if isinstance(data, list) else []


def record(dashboard_data: dict, extra_sources: dict | None = None, path: Path | str = HISTORY_JSON) -> dict:
    """Append one compact entry for this run. Newest last, capped at MAX_HISTORY entries.

    Call this ONLY after a successful publish — see docs/REGRESSION_GUARD_WIRING.md.
    """
    path = Path(path)
    hist = load_history(path)
    entry = make_entry(dashboard_data, extra_sources)
    # One entry per (date, built_at): a same-day re-run replaces its predecessor rather than
    # stacking, so the 3-run stall detector counts distinct builds, not retries of one build.
    hist = [h for h in hist if not (h.get("date") == entry["date"] and h.get("built_at") == entry["built_at"])]
    hist.append(entry)
    hist = hist[-MAX_HISTORY:]
    path.write_text(json.dumps(hist, indent=1) + "\n", encoding="utf-8")
    print(
        f"[regression_guard] recorded run {entry['date']} ({entry.get('git_sha')}) -> "
        f"{path.name} ({len(hist)} entries kept)"
    )
    return entry


# ----------------------------------------------------------------------------------------- check
def check(
    dashboard_data: dict,
    history: list[dict] | None = None,
    *,
    strict: bool | None = None,
    allow: list[str] | None = None,
    extra_sources: dict | None = None,
    verbose: bool = True,
) -> list[str]:
    """Return a list of failure strings (empty == pass)."""
    strict = _strict() if strict is None else strict
    allow = _allowlist() if allow is None else allow
    history = load_history() if history is None else history

    fails: list[str] = []
    waived: list[str] = []
    cur = make_entry(dashboard_data, extra_sources)

    def fail(metric: str, msg: str):
        if _is_waived(metric, allow):
            waived.append(f"{metric}: {msg}")
        else:
            fails.append(f"[{metric}] {msg}")

    if allow and verbose:
        print("!" * 90)
        print(f"!! REGRESSION WAIVER ACTIVE — INTERVIEWS_ALLOW_REGRESSION={','.join(allow)}")
        print("!! Regressions matching these patterns will NOT fail this run. This must be a one-off,")
        print("!! deliberately-reviewed change (e.g. a new test-account exclusion). Unset it after.")
        print("!" * 90)

    # ---------- absolute floors (ALWAYS enforced, no history needed) ----------
    cm = _metrics(cur)
    cm["connectFunnel.TOTAL.invited"] = sum(
        v for k, v in cm.items() if k.startswith("connectFunnel.") and k.endswith(".invited")
    )
    for metric, static_floor in FLOORS.items():
        val = cm.get(metric)
        if val is None:
            if verbose:
                print(f"  [skip] floor {metric} — not present in this build")
            continue
        # ratchet the floor up with the data: a static number set today is a weak collapse detector
        # once the programme has doubled
        best = max((_metrics(h).get(metric) or 0) for h in history) if history else 0
        floor = max(static_floor, int(FLOOR_FRACTION_OF_HISTORY * best))
        src = "static" if floor == static_floor else f"{FLOOR_FRACTION_OF_HISTORY:.0%} of best-ever {best}"
        if val <= floor:
            fail(
                metric,
                f"ABSOLUTE FLOOR breached: {val} <= {floor} ({src}) — a value this low means a source collapsed",
            )
        elif verbose:
            print(f"  [PASS] floor {metric} = {val} > {floor} ({src})")

    # ---------- structural invariants (ALWAYS enforced) ----------
    for key in ("unmappedCohorts", "connectPendingSubgroups"):
        val = dashboard_data.get(key)
        if val is None:
            continue
        if val:
            fail(f"structural.{key}", f"expected [] but got {val!r} — cohorts/subgroups fell off the map")
        elif verbose:
            print(f"  [PASS] structural {key} == []")

    # ---------- history-based tiers ----------
    if not history:
        if verbose:
            print("  [info] no history yet — Tier 1/2/3 skipped (this run seeds the history)")
    elif not strict:
        if verbose:
            print(
                "  [info] INTERVIEWS_STRICT_FRESHNESS unset — Tier 1/2/3 are advisory only "
                "(local no-credential builds run on static source)"
            )
        _report_history_deltas(cur, history, verbose)
    else:
        prev = history[-1]
        pm = _metrics(prev)

        # Tier 1 — hard monotonic, tolerance 0.
        for metric, old in sorted(pm.items()):
            if metric.startswith("sources.") and metric.split(".", 1)[1] in NON_CUMULATIVE_SOURCES:
                continue  # an age is not a counter; see NON_CUMULATIVE_SOURCES
            new = cm.get(metric)
            if new is None:
                fail(
                    metric,
                    f"TIER 1: metric present in the previous run ({old}) but MISSING now — "
                    f"a subgroup/source disappeared from the build",
                )
            elif new < old:
                fail(
                    metric,
                    f"TIER 1 MONOTONIC VIOLATION: {old} -> {new} "
                    f"({new - old}, {100.0 * (new - old) / old:+.1f}%) — cumulative counters cannot decrease",
                )

        # Tier 2 — per-ARM table3, oscillation-tolerant.
        pa, ca = _arm_metrics(prev), _arm_metrics(cur)
        for metric, old in sorted(pa.items()):
            new = ca.get(metric)
            if new is None:
                fail(metric, f"TIER 2: arm row present in the previous run ({old}) but MISSING now")
                continue
            drop = old - new
            tol = max(ARM_DROP_ABS, ARM_DROP_PCT * old)
            if drop > tol:
                fail(
                    metric,
                    f"TIER 2 ARM DROP: {old} -> {new} (-{drop}, {100.0 * drop / old:.1f}%) "
                    f"exceeds tolerance max({ARM_DROP_ABS}, {ARM_DROP_PCT:.0%}) = {tol:.1f}",
                )
            elif drop > 0 and verbose:
                print(f"  [ok]   arm wobble {metric}: {old} -> {new} (-{drop}, within tolerance {tol:.1f})")

        # Tier 3 — stall detection on counts.started.
        #
        # Two corrections over the naive version:
        #  * count distinct DATES, not entries. Republishing three times in one day is not a stall.
        #  * only FAIL when the SOURCES are frozen too. A flat interview count with sources still
        #    growing is a programme winding down, which is real and must not block publishing.
        #    Blocking it would also deadlock: the gate runs before the push, and history is only
        #    recorded after a successful push, so a hard stall failure can never clear itself.
        started_now = cm.get("counts.started")
        by_date = {}
        for h in history:
            by_date[h.get("date")] = h  # last entry wins per date
        recent = [by_date[d] for d in sorted(by_date)][-(STALL_RUNS - 1) :]
        prior = [h.get("counts", {}).get("started") for h in recent]
        flat = started_now is not None and len(prior) >= STALL_RUNS - 1 and all(p == started_now for p in prior)
        if flat:
            # Four states reach here, and only ONE of them is a fault. They must be told apart by
            # something other than the counters, because a finished programme and a broken pull look
            # identical on those. Getting it wrong deadlocks the daily job: this gate runs before the
            # push and history is only written after a successful one, so a wrong FAIL can never
            # clear itself on its own.
            #
            #   sources still growing  -> a programme winding down. Real, must publish.
            #   past PROGRAMME_ENDED   -> collection has stopped by declaration. Expected steady state.
            #   newest session is old  -> nobody is interviewing. Quiet, not broken.
            #   newest session is FRESH-> OCS has data we are not turning into interviews. A stuck pull.
            age_now = cm.get("sources.ocs_newest_age_days")
            src_now = cm.get("sources.ocs_sessions")
            src_prior = [_metrics(h).get("sources.ocs_sessions") for h in recent]
            sources_frozen = src_now is not None and all(s == src_now for s in src_prior)
            dates = ", ".join(str(h.get("date")) for h in recent)
            ended, ended_on = _programme_ended()
            quiet = age_now is not None and age_now >= STALL_QUIET_DAYS
            flat_for = f"counts.started flat at {started_now} for {STALL_RUNS} days ({dates} and today)"

            if not sources_frozen:
                if verbose:
                    print(
                        f"  [warn] {flat_for}, but sources are still moving "
                        f"(ocs_sessions {src_prior} -> {src_now}) - reads as a quiet programme, "
                        f"not a frozen pull. Not failing."
                    )
            elif ended:
                if verbose:
                    print(
                        f"  [warn] {flat_for} and ocs_sessions frozen at {src_now}, but the programme is "
                        f"declared finished as of {ended_on} - a frozen count is the expected steady "
                        f"state, not a stuck pull. Not failing. Tier 1 still fails on any FALL."
                    )
            elif quiet:
                if verbose:
                    print(
                        f"  [warn] {flat_for} and ocs_sessions frozen at {src_now}, but OCS's newest "
                        f"session is {age_now} days old - the programme has gone quiet, not the pull. "
                        f"Not failing."
                    )
            else:
                fail(
                    "counts.started",
                    f"TIER 3 STALL: counts.started == {started_now} AND sources.ocs_sessions == {src_now} "
                    f"across {STALL_RUNS} distinct days ({dates} and today) while OCS's newest session is "
                    f"only {'unknown' if age_now is None else age_now} day(s) old, so OCS has data we are "
                    f"not turning into interviews - a pull is stuck rather than the programme being quiet",
                )
        elif verbose and started_now is not None:
            print(f"  [PASS] stall: counts.started {prior} -> {started_now}")

    if waived and verbose:
        print("\n" + "!" * 90)
        print(f"!! {len(waived)} REGRESSION(S) WAIVED by INTERVIEWS_ALLOW_REGRESSION — review each:")
        for w in waived:
            print(f"!!   {w}")
        print("!" * 90)
    return fails


def _report_history_deltas(cur: dict, history: list[dict], verbose: bool):
    """Non-strict mode: print what WOULD have failed, without failing."""
    if not verbose:
        return
    prev, cm, pm = history[-1], _metrics(cur), _metrics(history[-1])
    drops = [(k, pm[k], cm[k]) for k in sorted(pm) if k in cm and cm[k] < pm[k]]
    if drops:
        print(
            f"  [warn] {len(drops)} metric(s) decreased vs {prev.get('date')} "
            f"(advisory — set INTERVIEWS_STRICT_FRESHNESS=1 to enforce):"
        )
        for k, o, n in drops[:20]:
            print(f"           {k}: {o} -> {n}")
    else:
        print(f"  [info] no metric decreased vs {prev.get('date')}")


# ------------------------------------------------------------------------------------------- CLI
def _summary_append(text: str):
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        try:
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except Exception:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("action", nargs="?", default="check", choices=["check", "record", "show"])
    ap.add_argument("--data", default=str(DASHBOARD_JSON), help="dashboard_data.json to read")
    ap.add_argument("--history", default=str(HISTORY_JSON), help="_run_history.json to read/write")
    args = ap.parse_args(argv)

    if args.action == "show":
        for h in load_history(args.history):
            print(
                f"{h.get('date')}  sha={h.get('git_sha')}  "
                f"cohorts={h.get('counts', {}).get('cohorts')} "
                f"started={h.get('counts', {}).get('started')} "
                f"completed={h.get('counts', {}).get('completed')} "
                f"master_rows={h.get('counts', {}).get('master_rows')} "
                f"sources={h.get('sources')}"
            )
        return 0

    dd = _load_json(Path(args.data))
    if not isinstance(dd, dict):
        print(f"ABORT: cannot read {args.data}")
        return 1

    if args.action == "record":
        record(dd, path=args.history)
        return 0

    print("=" * 90)
    print("REGRESSION GUARD — absolute day-over-day checks (the only NON-relative gate)")
    print("=" * 90)
    hist = load_history(args.history)
    print(
        f"  history: {len(hist)} prior run(s) in {Path(args.history).name}"
        f"{'  (last: ' + str(hist[-1].get('date')) + ')' if hist else '  (none — seeding)'}"
    )
    print(f"  strict:  {'ON (INTERVIEWS_STRICT_FRESHNESS=1)' if _strict() else 'off — floors only'}")
    fails = check(dd, hist)
    print("\n" + "=" * 90)
    if fails:
        print(f"  REGRESSION GUARD: {len(fails)} FAILURE(S) ❌")
        for f in fails:
            print(f"    {f}")
        print("=" * 90)
        _summary_append("### ❌ Regression guard failed\n" + "\n".join(f"- `{f}`" for f in fails))
        return 1
    print("  REGRESSION GUARD: ALL PASS ✅")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
