"""The stall check must tell a STUCK PULL from a programme that has stopped, in every direction.

On 2026-09-04 the daily publish was blocked by TIER 3 STALL: counts.started and sources.ocs_sessions
were both frozen for three days. Nothing was stuck - the bot had been deactivated, last session
2026-09-02 04:34 against 16 on 28 Aug. The check could not tell the two apart, because when a
programme genuinely stops its source freezes too and idle looks exactly like broken.

Two things are pinned here.

FIRST, both verdicts, because a wrong one deadlocks the daily job: this gate runs before the push and
history is only written after a successful push, so a wrong FAIL can never clear itself.

SECOND, that the FAIL branch is REACHABLE. The first attempt at this fix set the quiet threshold to 2
days while flatness takes 3 days to establish. Since a frozen source ages a day per run, the newest
session was always >= 3 days old by the time the check could fire, so the fail branch was unreachable
and the gate silently did nothing. A green suite proved nothing. Hence test_reachable below.

    python test_regression_stall.py     (exits non-zero on any wrong verdict)
"""

import datetime
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ.setdefault("INTERVIEWS_STRICT_FRESHNESS", "1")  # Tier 3 is advisory without it

import regression_guard as g  # noqa: E402  (must follow the env default above)

TODAY = datetime.date.today()
COUNTS = {"started": 9933, "cohorts": 72, "flws": 1451, "completed": 9431, "master_rows": 10533}
SOURCES = {"ocs_sessions": 22367, "trigger_rows": 5000, "connect_snapshot_rows": 3900, "trigger_files": 12}
# The absolute-floor tier reads the funnel and the matrix. Without them every verdict below reads
# FAIL for reasons that have nothing to do with the stall, which would make this suite meaningless.
CF = {"invited": 4200, "accepted": 3800, "learn_completed": 3500, "claimed": 3400}
MATRIX_ROWS = 2400

fails_seen = []


def dashboard(started):
    """The CURRENT run, in raw dashboard shape - check() converts this itself."""
    return {
        "today": str(TODAY),
        "counts": dict(COUNTS, started=started),
        "connectFunnel": [dict(CF, sg="TOTAL")],
        "flwMatrix": [{"i": i} for i in range(MATRIX_ROWS)],
    }


def recorded(started, age):
    """A HISTORY row, in the already-converted shape make_entry() writes."""
    return {
        "counts": dict(COUNTS, started=started, claimed_pairs=MATRIX_ROWS),
        "connectFunnel": {"TOTAL": dict(CF)},
        "flwMatrix_rows": MATRIX_ROWS,
        "sources": dict(SOURCES, ocs_newest_age_days=age),
    }


def verdict(label, age, ended=None, src_growing=False, started_now=None, want=None):
    """Run the guard and report PASS/FAIL. `ended` is the declared end date, None = a live programme."""
    os.environ["INTERVIEWS_PROGRAMME_ENDED"] = "" if ended is None else ended

    started = COUNTS["started"] if started_now is None else started_now
    hist = []
    for i in range(g.STALL_RUNS, 0, -1):
        # The same newest session was i days YOUNGER i days ago, so age falls going back in time.
        e = recorded(COUNTS["started"], None if age is None else max(0, age - i))
        if src_growing:
            e["sources"]["ocs_sessions"] = SOURCES["ocs_sessions"] - (i * 40)
        e["date"] = str(TODAY - datetime.timedelta(days=i))
        hist.append(e)

    got = g.check(
        dashboard(started),
        hist,
        allow=[],
        extra_sources=dict(SOURCES, ocs_newest_age_days=age),
        verbose=False,
    )
    outcome = "FAIL" if got else "PASS"
    ok = outcome == want
    print("  %-58s -> %-4s  %s" % (label, outcome, "ok" if ok else "WRONG, wanted " + want))
    if not ok:
        fails_seen.append(f"{label}: got {outcome} wanted {want}  {got}")
    return ok


print(
    "Tier 3 constants: STALL_RUNS=%d STALL_QUIET_DAYS=%d PROGRAMME_ENDED=%r"
    % (g.STALL_RUNS, g.STALL_QUIET_DAYS, g.PROGRAMME_ENDED)
)
print()

print("A live programme. counts.started and ocs_sessions frozen in every case:")
verdict("newest session 3 days old (earliest a stall can fire)", 3, want="FAIL")
verdict("newest session 4 days old (pull still stuck)", 4, want="FAIL")
verdict("age unknown, older cache shape (be conservative)", None, want="FAIL")
verdict("newest session %d days old (programme quiet)" % g.STALL_QUIET_DAYS, g.STALL_QUIET_DAYS, want="PASS")
verdict("newest session 30 days old (long quiet spell)", 30, want="PASS")
verdict("sources still GROWING (winding down)", 3, src_growing=True, want="PASS")
print()

print("The programme is declared finished (this is the 2026-09-04 block):")
verdict("2 days old, past the declared end date", 2, ended="2026-09-02", want="PASS")
verdict("0 days old, past the declared end date", 0, ended="2026-09-02", want="PASS")
verdict("declared end is in the FUTURE, so still live", 3, ended=str(TODAY + datetime.timedelta(days=5)), want="FAIL")
verdict("unparseable end date falls back to live", 3, ended="not-a-date", want="FAIL")
print()

print("Tier 1 must survive the exemption. A FALL still fails after the programme ends:")
verdict("started FALLS 9933 -> 9800 past the declared end", 9, ended="2026-09-02", started_now=9800, want="FAIL")
print()

print("An age is not a cumulative counter, so a RECOVERING pull must not trip Tier 1:")
verdict("newest session goes 9 days old -> 0 (pull recovers)", 0, ended="2026-09-02", want="PASS")
print()

# ---------------------------------------------------------------- the anti-vacuity guard
print("Is the FAIL branch reachable for a realistic stuck pull?")
os.environ["INTERVIEWS_PROGRAMME_ENDED"] = ""
structural = g.STALL_QUIET_DAYS > g.STALL_RUNS
reachable = False
for outage in range(g.STALL_RUNS, 40):
    hist = []
    for i in range(g.STALL_RUNS, 0, -1):
        e = recorded(COUNTS["started"], max(0, outage - i))
        e["date"] = str(TODAY - datetime.timedelta(days=i))
        hist.append(e)
    got = g.check(
        dashboard(COUNTS["started"]),
        hist,
        allow=[],
        extra_sources=dict(SOURCES, ocs_newest_age_days=outage),
        verbose=False,
    )
    if [f for f in got if "STALL" in str(f)]:
        reachable = True
        break
print(
    "  STALL_QUIET_DAYS > STALL_RUNS                              -> %s"
    % ("ok" if structural else "NO, the fail branch is UNREACHABLE")
)
print(
    "  a real outage trips it (at %s days)                        -> %s"
    % (outage if reachable else "no", "ok" if reachable else "NO, the check is VACUOUS")
)
if not structural:
    fails_seen.append("STALL_QUIET_DAYS <= STALL_RUNS makes the fail branch unreachable")
if not reachable:
    fails_seen.append("no outage length trips the stall check")

print()
if fails_seen:
    print("[stall] WRONG VERDICTS:")
    for f in fails_seen:
        print("   -", f)
    raise SystemExit(1)
print("[stall] all verdicts correct, and the fail branch is reachable")
raise SystemExit(0)
