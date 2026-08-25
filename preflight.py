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

WHAT IT DOES
------------
Everything, in the order the daily job does it, plus the checks that only exist here:

  0. compile every script the orchestrator invokes, and validate the workflow YAML
  1. the unit fixtures for the reading rules
  2. rebuild in the CORRECT ORDER - build_payload_agg BEFORE build_dashboard_data. They are separate
     programs and the second does NOT re-run the first; running them the other way round compares a
     fresh dashboard against a stale aggregate and produces phantom mismatches.
  3. the four gate suites, including the render harness that is easy to forget
  4. CI SIMULATION: hide the files that are not in git, re-run the gates, and confirm they still pass.
     This is the step that would have caught failure 5 on its own.
  5. formatting, in check mode, with the pinned hooks rather than whatever npx resolves

    python preflight.py              # everything
    python preflight.py --fast       # skip the rebuild and the CI simulation (gates on existing data)

Exit code 0 means it is safe to push. Anything else means CI would have failed.
"""
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

results = []


def step(label, cmd, *, cwd=ROOT, env=None, timeout=2400, must_contain=None, forbid=None):
    t0 = time.time()
    print(f"\n=== {label} ===", flush=True)
    try:
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
        if any(k in line for k in ("TOTAL:", "[FAIL]", "ONLY ", "ABORT", "Traceback",
                                   "[render]", "fixtures pass", "checks pass")):
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
    "raw snapshot",                 # Connect snapshot is older here than the live pull in CI
    "topicStatus 7-state counts",   # depends on the same snapshot for its universe
    "flwMatrix rows ==",            #   "
    "substring present verbatim",   # compares against a render built from the fuller CI payload
    "no day-over-day regression",   # _run_history.json lives in the CI cache, not here
)
BRUTAL_LOCAL_BUDGET = 39            # measured 2026-08-25; raise ONLY with a reason


def brutal_baseline():
    """Fail on a RISE in local failures, or on any failure outside the known local-only families."""
    print("\n=== 3c. brutal_verify (7b), against the known local-only baseline ===", flush=True)
    r = subprocess.run([PY, "brutal_verify.py"], cwd=ROOT, capture_output=True, text=True,
                       timeout=1800)
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
    except Exception as e:                                    # noqa: BLE001 - config shape varies
        results.append(("5. pre-commit", False, f"could not read config: {e}"))
        return False
    bad = []
    for hid in ids:
        r = subprocess.run([PY, "-m", "pre_commit", "run", hid, "--all-files"], cwd=ROOT,
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            bad.append(hid)
            print(f"  FAILED hook: {hid}")
    ok = not bad
    detail = (f"{len(ids)} hooks run, {len(bad)} failed"
              + (f" ({', '.join(bad)})" if bad else "")
              + f"; skipped (blocked by Application Control): {', '.join(PRECOMMIT_BLOCKED)}")
    results.append(("5. pre-commit (runnable hooks)", ok, detail))
    print(f"  -> {'OK' if ok else 'FAILED'}  {detail}")
    return ok


def io_open_text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def main():
    # ---- 0. syntax and config -----------------------------------------------------------------
    step("0a. compile every pipeline script", [PY, "-m", "py_compile", *pipeline_scripts()])
    step("0b. workflow YAML parses", [PY, "-c",
         "import yaml,io;y=yaml.safe_load(io.open('.github/workflows/refresh-interviews.yml',"
         "encoding='utf-8'));assert y['jobs']['refresh']['steps'];print('steps',"
         "len(y['jobs']['refresh']['steps']))"])

    # ---- 1. unit fixtures ---------------------------------------------------------------------
    step("1. reading-rule fixtures", [PY, "test_topic_status_lib.py"], must_contain="fixtures pass")

    # ---- 2. rebuild, IN ORDER -----------------------------------------------------------------
    if not FAST:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        env.pop("INTERVIEWS_TODAY", None)
        if step("2a. build_payload_agg (MUST run before build_dashboard_data)",
                [PY, "build_payload_agg.py"], env=env):
            step("2b. build_dashboard_data", [PY, "build_dashboard_data.py"], env=env)

    # ---- 3. the four gate suites --------------------------------------------------------------
    step("3a. audit_e2e (6a)", [PY, "audit_e2e.py"], forbid="CHECKS RAN")
    step("3b. dashboard_data audit (6b)", [PY, "build_dashboard_data_audit.py"], forbid="CHECKS RAN")
    brutal_baseline()
    step("3d. render harness (7c) - the one that is easy to forget",
         ["node", "verify_render_dropoff.js"], must_contain="ALL PASS")

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
            step("4b. dashboard_data audit AS CI SEES IT", [PY, "build_dashboard_data_audit.py"],
                 forbid="CHECKS RAN")
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
