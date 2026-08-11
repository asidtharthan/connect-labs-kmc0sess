"""Gate: the KMC Audit Dashboard's on-screen counts must agree with the rows they filter to.

The flag engine has its own parity harness. That harness proves the *numbers* are right and says
nothing about whether the UI's summary counts describe the rows the UI actually shows. A shipped
build had the indicator chip tally reading an unfiltered cohort while the table also applied the
quick filter, so a chip reading "15 Green" could return 8 rows. Counts on screen that disagree with
each other are a reporting defect regardless of engine correctness, so they get their own gate.

kmc_audit_ui_invariants.js extracts the real filter/tally bodies out of the template source and
runs them over a synthetic cohort. It never re-implements them — a hand-written second copy is the
exact failure mode being guarded against.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "kmc_audit_ui_invariants.js"
MUTATE = (
    '? baseFiltered : baseFiltered.filter(function(d){ return condsPass(d, others); });',
    '? analyzed : analyzed.filter(function(d){ return condsPass(d, others); });',
)


def _node():
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node is not on PATH")
    return exe


def _run(env_tpl=None):
    env = None
    if env_tpl is not None:
        import os

        env = dict(os.environ, KMC_UI_TPL=str(env_tpl))
    return subprocess.run(
        [_node(), str(SCRIPT)], capture_output=True, text=True, env=env, cwd=str(HERE)
    )


def test_ui_counts_match_the_rows_they_filter_to():
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UI INVARIANTS PASS" in result.stdout


def test_the_gate_actually_fails_when_the_invariant_is_broken(tmp_path):
    """Mutation test. A gate nobody has watched fail is not a gate.

    Re-introduces the defect that shipped — the chip tally reading the unfiltered cohort — into a
    throwaway copy of the template and asserts the gate rejects it.
    """
    src = (HERE.parent / "templates" / "kmc_audit_dashboard.py").read_text(encoding="utf-8")
    assert src.count(MUTATE[0]) == 1, "mutation anchor moved; update MUTATE"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(src.replace(*MUTATE), encoding="utf-8")

    result = _run(env_tpl=mutant)
    assert result.returncode != 0, "the gate passed a template it should have rejected"
    assert "UI INVARIANTS FAIL" in result.stderr
