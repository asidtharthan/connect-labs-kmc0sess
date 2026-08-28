#!/usr/bin/env python3
"""preflight.py - run everything CI runs, the way CI runs it, BEFORE pushing.

WHY THIS EXISTS
---------------
On 2026-08-25 the publish job failed seven times in one day. Not one of those failures was
unforeseeable; every one was reproducible on this machine in under two minutes. They happened because
"the gates pass locally" was never the same statement as "the gates pass in CI":

  1. A SyntaxError in refresh_interviews_dashboard.py. No gate imports the orchestrator - it is the
     thing that runs them - so it had never been compiled. The job pulled every source, then died.
  2. Gate G flagged the one OPEN cohort. I had only reasoned about closed ones.
  3. Gate G again: the exemption matched substrings, so ".line_status.NPS[0]" slipped past.
  4. Gate G a third time: making the drop-off view deadline-aware meant an ended cohort could gain
     drop-outs as the calendar advanced.
  5. A check-count floor set to 26 when CI legitimately runs 23, because two reference files are not
     in git and their sections skip.
  6. A cross-view allowance too tight for a seven-week-old snapshot.

Two of those (2 and 6) were the gates working correctly on data my stale local build did not contain.
The rest were me not running what CI runs.

Then on 2026-08-26 it failed three more times, and preflight caught NONE of them, because they were
a different question. Removing one cohort lowered cumulative counters and the regression guard
blocked it, correctly. preflight answers "will this CODE pass CI?"; it did not answer "will this
CHANGE trip the guard?". For anything that REMOVES data only the second question matters. Step 2c
now answers it by measurement - see impact_diff.py - and REFUSES to pass if a counter falls that
has not been deliberately waived, or if a count-changing file was touched with no baseline taken.

WHAT IT DOES
------------
Everything, in the order the daily job does it, plus the checks that only exist here:

  0. compile every script the orchestrator invokes, and validate the workflow YAML
  1. the unit fixtures for the reading rules
  2. rebuild in the CORRECT ORDER - build_payload_agg BEFORE build_dashboard_data. They are separate
     programs and the second does NOT re-run the first; running them the other way round compares a
     fresh dashboard against a stale aggregate and produces phantom mismatches.
  2c. REGRESSION-GUARD IMPACT: diff this build's counters against a before-snapshot and print the
     exact allow_regression list. Fails if a counter falls unwaived, or if a count-changing file
     was touched without a baseline. This is the step that would have saved 2026-08-26.
  3. the four gate suites, including the render harness that is easy to forget
  4. CI SIMULATION: hide the files that are not in git, re-run the gates, and confirm they still pass.
     This is the step that would have caught failure 5 on its own.
  5. formatting, in check mode, with the pinned hooks rather than whatever npx resolves

    python preflight.py              # everything
    python preflight.py --fast       # skip the rebuild and the CI simulation (gates on existing data)

Exit code 0 means it is safe to push. Anything else means CI would have failed.
"""

import fnmatch
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
FAST = "--fast" in sys.argv

# Present here, absent on the runner. Sections that depend on them skip in CI, which changes the
# check COUNT - the thing that broke the publish once already.
NOT_IN_CI = [
    "master_v7_2026-06-10.csv",
    "screenshots/Latest files/GW Tables - 11th June 2026.xlsx",
]

# CI (refresh-interviews.yml) sets this at JOB level, so every build AND every audit in the run reads
# the Connect leg from connect_user_data_snapshot.csv. Preflight read it from the *_audit folders, which
# hold 63 cohorts against the snapshot's 72: the regression guard reported 36 phantom drops on a change
# that never touched Connect, and setting it for the build steps alone then desynced the audits from the
# payload they check. Reproducing CI is the point of this script, so it is set once, here, for everything.
os.environ.setdefault("INTERVIEWS_CONNECT_SNAPSHOT", "1")

results = []


def step(label, cmd, *, cwd=ROOT, env=None, timeout=2400, must_contain=None, forbid=None):
    t0 = time.time()
    print(f"\n=== {label} ===", flush=True)
    try:
        # CI runs UTF-8 on Linux; this console is cp1252, so a gate printing a Sigma in a check
        # name died with UnicodeEncodeError and preflight announced "CI would fail too. Do not
        # push." That is the worst false alarm available: it blames the code for a console limit.
        env = dict(env or os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        results.append((label, False, f"TIMEOUT after {timeout}s"))
        print(f"  TIMEOUT after {timeout}s")
        return False
    out = (r.stdout or "") + (r.stderr or "")
    ok = r.returncode == 0
    detail = f"rc={r.returncode} ({time.time() - t0:.0f}s)"
    if ok and must_contain and must_contain not in out:
        ok, detail = False, f"expected text missing: {must_contain!r}"
    if ok and forbid and forbid in out:
        ok, detail = False, f"forbidden text present: {forbid!r}"
    for line in out.splitlines():
        if any(
            k in line
            for k in ("TOTAL:", "[FAIL]", "ONLY ", "ABORT", "Traceback", "[render]", "fixtures pass", "checks pass")
        ):
            print("  " + line.strip()[:160])
    results.append((label, ok, detail))
    print(f"  -> {'OK' if ok else 'FAILED'}  {detail}")
    return ok


def pipeline_scripts():
    """The orchestrator plus every script it invokes, derived from the file so a new step is covered."""
    import re

    src = open(os.path.join(ROOT, "refresh_interviews_dashboard.py"), encoding="utf-8").read()
    return ["refresh_interviews_dashboard.py"] + sorted(set(re.findall(r'"([a-z_0-9]+\.py)"', src)))


# brutal_verify compares the payload against RAW sources. This machine holds a stale Connect snapshot
# and a partial HQ tree, so a fixed set of families fail here and pass on the runner. Muting them would
# hide a regression, so instead: count them, and fail if the count rises or an unknown family appears.
BRUTAL_LOCAL_FAMILIES = (
    "raw snapshot",  # Connect snapshot is older here than the live pull in CI
    "topicStatus 7-state counts",  # depends on the same snapshot for its universe
    "flwMatrix rows ==",  # same
    "substring present verbatim",  # compares against a render built from the fuller CI payload
    "no day-over-day regression",  # _run_history.json lives in the CI cache, not here
)
BRUTAL_LOCAL_BUDGET = 39  # measured 2026-08-25; raise ONLY with a reason


def brutal_baseline():
    """Fail on a RISE in local failures, or on any failure outside the known local-only families."""
    print("\n=== 3c. brutal_verify (7b), against the known local-only baseline ===", flush=True)
    r = subprocess.run([PY, "brutal_verify.py"], cwd=ROOT, capture_output=True, text=True, timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    fails = [ln.split("[FAIL]", 1)[1].strip() for ln in out.splitlines() if "[FAIL]" in ln]
    unknown = [f for f in fails if not any(k in f for k in BRUTAL_LOCAL_FAMILIES)]
    ok = len(fails) <= BRUTAL_LOCAL_BUDGET and not unknown
    detail = f"{len(fails)} local failures (budget {BRUTAL_LOCAL_BUDGET}), {len(unknown)} unknown"
    if unknown:
        detail += " -> " + unknown[0][:90]
    for f in unknown[:3]:
        print("  UNKNOWN FAILURE: " + f[:150])
    results.append(("3c. brutal_verify (local baseline)", ok, detail))
    print(f"  -> {'OK' if ok else 'FAILED'}  {detail}")
    return ok


# Four hooks cannot execute under this machine's Application Control policy (WinError 4551). They run
# in CI. Run everything else, and name what was skipped rather than silently passing.
# Hooks Application Control refuses that ARE runnable as plain modules. Checked directly so a genuine
# failure cannot hide behind the block. Anything not listed here is reported as blocked and left to CI.
DIRECT_FALLBACK = {
    "black": ["black", "--check"],
    "flake8": ["flake8"],
    "isort": ["isort", "--check-only"],
}


def changed_python():
    """The .py files this push would actually change - staged, plus anything differing from main.

    NOT the whole tree: `black --check .` sweeps 93 untracked scratch scripts that CI has never linted,
    so it could never pass and the check would become noise. CI lints the tracked tree and main is
    green, so what matters before a push is what this change touches.
    """
    out = set()
    for args in (["diff", "--name-only", "--cached"], ["diff", "--name-only", "origin/main..."]):
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        out.update(f for f in r.stdout.split() if f.endswith(".py") and os.path.exists(f))
    return sorted(out)


PRECOMMIT_BLOCKED = ("check-yaml", "trailing-whitespace", "end-of-file-fixer", "check-case-conflict")


def precommit_runnable():
    print("\n=== 5. pre-commit, hooks this machine can actually run ===", flush=True)
    ids = []
    try:
        import yaml

        cfg = yaml.safe_load(io_open_text(".pre-commit-config.yaml"))
        for repo in cfg.get("repos", []):
            for h in repo.get("hooks", []):
                if h.get("id") and h["id"] not in PRECOMMIT_BLOCKED:
                    ids.append(h["id"])
    except Exception as e:  # noqa: BLE001 - config shape varies
        results.append(("5. pre-commit", False, f"could not read config: {e}"))
        return False
    bad = []
    # pre-commit --all-files means "every file in the git INDEX". A new file is invisible to it until
    # it is staged - which is how preflight.py itself shipped unformatted and failed the CI linter on
    # the commit that added it. `git add` your new files BEFORE running preflight and they are covered;
    # preflight warns below if it sees new source files that are not staged.
    #
    # It deliberately does NOT lint every untracked file: there are 93 abandoned scratch scripts in
    # this tree that CI has never linted and never will, and failing on them would make preflight
    # useless.
    unstaged_new = [
        f
        for f in subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.split()
        if f.endswith((".py", ".js")) and "/" not in f and not f.startswith("_")
    ]
    bad = []
    blocked = []
    for hid in ids:
        r = subprocess.run(
            [PY, "-m", "pre_commit", "run", hid, "--all-files"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=900,
        )
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            # Detect the block DYNAMICALLY. Which hooks Application Control refuses varies between
            # machines and over time - black and django-upgrade started being blocked partway through
            # 2026-08-25 - so a hardcoded list silently turns into a hardcoded lie. A blocked hook is
            # reported as blocked and still runs in CI; only a genuine failure counts.
            if "WinError 4551" in out or "Application Control" in out:
                # Blocked as a pre-commit hook - but several of these are plain Python tools that run
                # fine when invoked directly, so FALL BACK rather than shrug. Reporting "blocked" and
                # moving on is how a real black failure hid behind an environment quirk and reached CI
                # anyway: false confidence is worse than no check.
                direct = DIRECT_FALLBACK.get(hid)
                if direct:
                    targets = changed_python()
                    if not targets:
                        print(f"  ok, nothing changed for: {hid}")
                        continue
                    r2 = subprocess.run(
                        [PY, "-m", *direct, *targets],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        timeout=900,
                    )
                    if r2.returncode != 0:
                        bad.append(hid)
                        print(f"  FAILED (hook blocked, ran directly): {hid}")
                    else:
                        print(f"  ok via direct run (hook itself is blocked): {hid}")
                    continue
                blocked.append(hid)
                print(f"  BLOCKED by this machine, no direct fallback (runs in CI): {hid}")
            else:
                bad.append(hid)
                print(f"  FAILED hook: {hid}")
    if unstaged_new:
        print(
            f"  NOTE: {len(unstaged_new)} new source file(s) are NOT staged, so the hooks did not "
            f"see them: {', '.join(unstaged_new[:6])}"
        )
        print("        `git add` them and re-run, or CI will lint what preflight did not.")
    ok = not bad
    detail = (
        f"{len(ids) - len(blocked)} hooks ran, {len(bad)} failed"
        + (f" ({', '.join(bad)})" if bad else "")
        + f"; blocked by this machine (run in CI): {', '.join(sorted(set(blocked))) or 'none'}"
    )
    results.append(("5. pre-commit (runnable hooks)", ok, detail))
    print(f"  -> {'OK' if ok else 'FAILED'}  {detail}")
    return ok


def io_open_text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# Touching any of these can change what the pipeline COUNTS, not just how it runs - which is the
# only class of change the regression guard can block. Every 2026-08-26 failure was in this class.
SHAPE_FILES = (
    "build_payload_agg.py",
    "build_dashboard_data.py",
    "topic_status_lib.py",
    "audit_e2e.py",
    "brutal_verify.py",
    "regression_guard.py",
    "build_render_data.py",
)
SNAP = os.path.join(ROOT, ".impact_snapshots", "before.json")


def changed_files():
    """Staged, UNSTAGED, and anything differing from main.

    The plain `git diff --name-only` is not optional here: an edit sitting in the working tree is
    exactly the state you are in when you run preflight, and leaving it out made this check blind to
    the change it exists to catch.
    """
    out = set()
    for args in (
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
        ["diff", "--name-only", "origin/main..."],
    ):
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        out.update(r.stdout.split())
    return out


def impact_check():
    """Answer "will this CHANGE trip the regression guard?" - the question preflight used to skip.

    preflight validates the CODE. It has never validated the CONSEQUENCES, so on 2026-08-26 a
    single cohort removal failed CI three times in a row while the exact list of counters that had
    dropped was discovered one run at a time. That list is computable here in seconds.
    """
    print("\n=== 2c. regression-guard impact ===", flush=True)
    touched = sorted(f for f in changed_files() if os.path.basename(f) in SHAPE_FILES)

    if not os.path.exists(SNAP):
        if not touched:
            results.append(
                ("2c. regression-guard impact", True, "no shape-changing files touched; no baseline needed")
            )
            print("  -> OK  no shape-changing files touched")
            return True
        detail = f"NO BASELINE SNAPSHOT, but {', '.join(os.path.basename(t) for t in touched)} changed"
        results.append(("2c. regression-guard impact", False, detail))
        print(f"  -> FAILED  {detail}")
        print("  These files can change what the pipeline COUNTS. Without a before/after you are")
        print("  guessing at the waiver list, and CI will enumerate it for you one failure at a time.")
        print("  Fix: `git stash`, `python build_payload_agg.py && python build_dashboard_data.py`,")
        print("       `python impact_diff.py --snapshot before`, `git stash pop`, rebuild, re-run.")
        return False

    r = subprocess.run([PY, "impact_diff.py"], cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = (r.stdout or "") + (r.stderr or "")
    print("  " + "\n  ".join(out.splitlines()[-24:]))
    if r.returncode == 0:
        results.append(("2c. regression-guard impact", True, "no metric falls; guard will not object"))
        print("  -> OK  nothing falls")
        return True
    if r.returncode != 2:
        results.append(("2c. regression-guard impact", False, f"impact_diff failed rc={r.returncode}"))
        return False

    # Something fell. That is allowed ONLY if it was deliberate and is already waived here.
    dropped = []
    for i, ln in enumerate(out.splitlines()):
        if "VERBATIM" in ln:
            nxt = [x.strip() for x in out.splitlines()[i:] if x.strip() and "," in x]
            dropped = nxt[1].split(",") if len(nxt) > 1 else []
            break
    allow = [p.strip() for p in os.environ.get("INTERVIEWS_ALLOW_REGRESSION", "").split(",") if p.strip()]
    unwaived = [m for m in dropped if not any(p == "all" or p == m or fnmatch.fnmatch(m, p) for p in allow)]
    if allow and not unwaived:
        detail = f"{len(dropped)} drop(s), ALL waived by your INTERVIEWS_ALLOW_REGRESSION - pass the same value to CI"
        results.append(("2c. regression-guard impact", True, detail))
        print(f"  -> OK  {detail}")
        return True
    detail = f"{len(unwaived)} of {len(dropped)} drop(s) NOT waived"
    results.append(("2c. regression-guard impact", False, detail))
    print(f"  -> FAILED  {detail}")
    print("  Either they are a BUG (fix the code), or they are INTENDED - in which case export the")
    print("  printed list as INTERVIEWS_ALLOW_REGRESSION, re-run preflight, and pass the SAME string")
    print("  to the workflow_dispatch `allow_regression` input. Do not discover this list in CI.")
    return False


def main():
    # ---- 0. syntax and config -----------------------------------------------------------------
    step("0a. compile every pipeline script", [PY, "-m", "py_compile", *pipeline_scripts()])
    step(
        "0b. workflow YAML parses",
        [
            PY,
            "-c",
            "import yaml,io;y=yaml.safe_load(io.open('.github/workflows/refresh-interviews.yml',"
            "encoding='utf-8'));assert y['jobs']['refresh']['steps'];print('steps',"
            "len(y['jobs']['refresh']['steps']))",
        ],
    )

    # ---- 1. unit fixtures ---------------------------------------------------------------------
    step("1. reading-rule fixtures", [PY, "test_topic_status_lib.py"], must_contain="fixtures pass")

    # ---- 2. rebuild, IN ORDER -----------------------------------------------------------------
    if not FAST:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        env.pop("INTERVIEWS_TODAY", None)
        if step("2a. build_payload_agg (MUST run before build_dashboard_data)", [PY, "build_payload_agg.py"], env=env):
            step("2b. build_dashboard_data", [PY, "build_dashboard_data.py"], env=env)

    # ---- 2c. REGRESSION-GUARD IMPACT ----------------------------------------------------------
    impact_check()

    # ---- 3. the four gate suites --------------------------------------------------------------
    step("3a. audit_e2e (6a)", [PY, "audit_e2e.py"], forbid="CHECKS RAN")
    step("3b. dashboard_data audit (6b)", [PY, "build_dashboard_data_audit.py"], forbid="CHECKS RAN")
    brutal_baseline()
    step(
        "3d. render harness (7c) - the one that is easy to forget",
        ["node", "verify_render_dropoff.js"],
        must_contain="ALL PASS",
    )

    # ---- 4. CI SIMULATION ---------------------------------------------------------------------
    # The runner does not have these files. Sections that need them skip, which changes the check
    # count - and a floor tuned to the local count blocks every CI run. Hide them and re-run.
    if not FAST:
        print("\n=== 4. CI simulation: hiding files that are not in git ===", flush=True)
        stash = os.path.join(ROOT, "_preflight_stash")
        os.makedirs(stash, exist_ok=True)
        moved = []
        for rel in NOT_IN_CI:
            src = os.path.join(ROOT, rel)
            if os.path.exists(src):
                dst = os.path.join(stash, os.path.basename(rel))
                shutil.move(src, dst)
                moved.append((src, dst))
                print(f"  hidden: {rel}")
        try:
            step("4a. audit_e2e AS CI SEES IT", [PY, "audit_e2e.py"], forbid="CHECKS RAN")
            step("4b. dashboard_data audit AS CI SEES IT", [PY, "build_dashboard_data_audit.py"], forbid="CHECKS RAN")
        finally:
            for src, dst in moved:
                os.makedirs(os.path.dirname(src), exist_ok=True)
                shutil.move(dst, src)
                print(f"  restored: {os.path.relpath(src, ROOT)}")
            if os.path.isdir(stash) and not os.listdir(stash):
                os.rmdir(stash)

    # ---- 5. formatting, with the PINNED hooks -------------------------------------------------
    # npx prettier and the pre-commit prettier disagree about YAML quote style. CI runs the pinned
    # one, so that is the only one whose opinion counts.
    precommit_runnable()

    # ---- verdict ------------------------------------------------------------------------------
    print("\n" + "=" * 78)
    print("PREFLIGHT")
    print("=" * 78)
    bad = [r for r in results if not r[1]]
    for label, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label:52} {detail}")
    if bad:
        print(f"\n  {len(bad)} FAILED - CI would fail too. Do not push.")
        return 1
    print(f"\n  all {len(results)} checks pass - safe to push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
