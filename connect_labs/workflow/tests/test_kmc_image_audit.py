"""Tests for the kmc_image_audit template's headless default-run hook.

The hook is the only way these audits can run unattended, so the things worth
pinning are: it is registered as schedulable, it derives the same window every
other schedulable template derives, it routes each opportunity to the agent its
scale hardware requires, and a single bad opportunity does not cost the others
their audits.

No network or DB: WorkflowDataAccess and the audit-creation task are both
substituted, so what is asserted is the CALLS the hook makes.
"""

from types import SimpleNamespace
from unittest import mock

import pytest

from connect_labs.workflow.templates import TEMPLATES, template_supports_default_run
from connect_labs.workflow.templates.kmc_image_audit import run_default

TEMPLATE_KEY = "kmc_image_audit"
# 1236 EHA is dial, 1487 PIPN is digital — the pair that proves per-opportunity routing.
DIAL_OPP, DIGITAL_OPP = 1236, 1487


def _definition(**config_overrides):
    config = {
        "opp_meta": {
            str(DIAL_OPP): {"llo": "EHA", "scale": "dial"},
            str(DIGITAL_OPP): {"llo": "PIPN", "scale": "digital"},
        },
        "agent_for_scale": {"digital": "scale_validation", "dial": "scale_dial_read"},
        "weight_image_path": "anthropometric/upload_weight_image",
        "weight_field_path": "child_weight_visit",
    }
    config.update(config_overrides)
    return SimpleNamespace(id=99, opportunity_id=DIGITAL_OPP, opportunity_ids=[DIGITAL_OPP], data={"config": config})


class _EagerResult:
    def __init__(self, sessions=1, ok=True, payload=None):
        self._ok = ok
        if not ok:
            self.result = "boom"
        elif payload is not None:
            self.result = payload
        else:
            self.result = {"sessions": [{"id": i} for i in range(sessions)]}

    def successful(self):
        return self._ok


@pytest.fixture
def patched():
    """Substitute the two collaborators and hand back the recorded calls."""
    created = {}
    with mock.patch("connect_labs.workflow.data_access.WorkflowDataAccess") as wda_cls, mock.patch(
        "connect_labs.audit.tasks.run_audit_creation"
    ) as task:
        wda_cls.return_value.create_run.return_value = SimpleNamespace(id=4242)
        task.apply.return_value = _EagerResult()
        created["wda"] = wda_cls
        created["task"] = task
        yield created


def test_template_is_registered_and_schedulable():
    assert TEMPLATE_KEY in TEMPLATES
    assert template_supports_default_run(TEMPLATE_KEY) is True


def test_does_not_declare_saved_runs():
    """Declaring it would re-point run completion at a snapshot contract this
    workflow has never used, changing what "Mark run complete" does."""
    template = TEMPLATES[TEMPLATE_KEY]
    assert template.get("supports_saved_runs") is False
    assert template.get("build_snapshot") is None


def test_empty_opportunity_list_fails_loudly(patched):
    """A schedule that silently audits nothing every night is the worst outcome."""
    result = run_default(definition=_definition(), access_token="t", cadence="daily")
    assert result["status"] == "failed"
    assert result["sessions_created"] == 0
    assert "opportunity_ids is empty" in result["error"]
    patched["task"].apply.assert_not_called()


def test_one_audit_per_opportunity_with_hardware_specific_agent(patched):
    definition = _definition(
        schedule_defaults={"opportunity_ids": [DIAL_OPP, DIGITAL_OPP], "sample_percentage": 30}
    )
    result = run_default(definition=definition, access_token="t", cadence="daily")

    assert result["status"] == "ready"
    assert result["run_id"] == 4242
    assert result["sessions_created"] == 2
    assert patched["task"].apply.call_count == 2

    by_opp = {
        call.kwargs["kwargs"]["opportunities"][0]["id"]: call.kwargs["kwargs"]
        for call in patched["task"].apply.call_args_list
    }
    assert by_opp[DIAL_OPP]["ai_agent_id"] == "scale_dial_read"
    assert by_opp[DIGITAL_OPP]["ai_agent_id"] == "scale_validation"
    # Every session must be linked to the run, or the results page cannot find them.
    assert {c["workflow_run_id"] for c in by_opp.values()} == {4242}
    assert {c["criteria"]["sample_percentage"] for c in by_opp.values()} == {30}
    assert {c["criteria"]["tag"] for c in by_opp.values()} == {"kmc_weight_photo"}


def test_agent_override_wins_over_scale_hardware(patched):
    """The override is how a mis-recorded scale is corrected without a deploy."""
    definition = _definition(
        schedule_defaults={
            "opportunity_ids": [DIGITAL_OPP],
            "agent_override": {str(DIGITAL_OPP): "scale_dial_read"},
        }
    )
    run_default(definition=definition, access_token="t", cadence="daily")
    kwargs = patched["task"].apply.call_args.kwargs["kwargs"]
    assert kwargs["ai_agent_id"] == "scale_dial_read"


@pytest.mark.parametrize(
    "cadence,expect_same_day",
    [("daily", False), ("weekly", False), ("monthly", False)],
)
def test_window_comes_from_cadence(patched, cadence, expect_same_day):
    """Windows must match what every other schedulable template resolves, so a
    scheduled run audits the period the cadence implies rather than 'today'."""
    from datetime import date

    from connect_labs.workflow.audit_generation import resolve_window, window_preset_for_cadence

    expected = resolve_window(window_preset_for_cadence(cadence), date.today())
    definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP]})
    run_default(definition=definition, access_token="t", cadence=cadence)

    criteria = patched["task"].apply.call_args.kwargs["kwargs"]["criteria"]
    assert (criteria["start_date"], criteria["end_date"]) == expected
    assert criteria["start_date"] <= criteria["end_date"]
    if not expect_same_day:
        assert criteria["start_date"] != date.today().isoformat() or cadence == "daily"


def test_explicit_window_overrides_cadence(patched):
    """The workflow_run_default tool passes a window for backfills."""
    definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP]})
    run_default(
        definition=definition, access_token="t", cadence="daily", window=("2026-01-01", "2026-01-31")
    )
    criteria = patched["task"].apply.call_args.kwargs["kwargs"]["criteria"]
    assert criteria["start_date"] == "2026-01-01"
    assert criteria["end_date"] == "2026-01-31"


def test_one_failing_opportunity_does_not_stop_the_batch(patched):
    """A single unreachable opportunity must not cost the others their audits."""
    patched["task"].apply.side_effect = [RuntimeError("upstream 500"), _EagerResult(sessions=3)]
    definition = _definition(schedule_defaults={"opportunity_ids": [DIAL_OPP, DIGITAL_OPP]})
    result = run_default(definition=definition, access_token="t", cadence="daily")

    assert patched["task"].apply.call_count == 2
    assert result["sessions_created"] == 3
    assert result["status"] == "ready"
    assert any("upstream 500" in e for e in result["errors"])


def test_all_opportunities_failing_reports_failed(patched):
    patched["task"].apply.side_effect = [RuntimeError("nope"), RuntimeError("nope")]
    definition = _definition(schedule_defaults={"opportunity_ids": [DIAL_OPP, DIGITAL_OPP]})
    result = run_default(definition=definition, access_token="t", cadence="daily")
    assert result["status"] == "failed"
    assert result["sessions_created"] == 0
    assert len(result["errors"]) == 2


def test_run_state_carries_llo_summary_for_the_history_table(patched):
    """The run-history LLO column reads state.llo_summary; a scheduled run must
    populate it the same way a hand-triggered run does."""
    definition = _definition(schedule_defaults={"opportunity_ids": [DIAL_OPP, DIGITAL_OPP]})
    run_default(definition=definition, access_token="t", cadence="daily")
    state = patched["wda"].return_value.create_run.call_args.kwargs["initial_state"]
    assert state["llo_summary"] == "EHA / PIPN"
    assert state["selected_opps"] == [DIAL_OPP, DIGITAL_OPP]


def test_empty_window_is_not_reported_as_failure(patched):
    """A quiet week audits nothing, and that is correct. Reporting it as failed would have a weekly
    schedule cry wolf until nobody reads it. Observed live: 10% of a two-day window rounded to zero
    photos and the hook said status=failed with errors=[] — nothing to act on, and wrong."""
    patched["task"].apply.return_value = _EagerResult(sessions=0)
    definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP]})
    result = run_default(definition=definition, access_token="t", cadence="daily")
    assert result["status"] == "empty"
    assert result["sessions_created"] == 0
    assert result["errors"] == []
    assert result["empty_opportunities"] == [DIGITAL_OPP]


def test_failure_inside_a_successful_task_is_recorded(patched):
    """run_audit_creation can return success-shaped but carry an error — a live HTTP 500 from the
    record-creation API did exactly that, and it vanished into an empty errors list."""
    patched["task"].apply.return_value = _EagerResult(
        sessions=0, payload={"success": False, "error": "500 from /export/labs_record/"}
    )
    definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP]})
    result = run_default(definition=definition, access_token="t", cadence="daily")
    assert result["status"] == "failed"
    assert any("500" in e for e in result["errors"])
    assert result["empty_opportunities"] == []


def test_partial_batch_reports_ready_and_names_the_empty_one(patched):
    """One opportunity with data and one without is a success, not a failure - but the empty one
    must still be named so nobody assumes it was audited."""
    patched["task"].apply.side_effect = [_EagerResult(sessions=2), _EagerResult(sessions=0)]
    definition = _definition(schedule_defaults={"opportunity_ids": [DIAL_OPP, DIGITAL_OPP]})
    result = run_default(definition=definition, access_token="t", cadence="daily")
    assert result["status"] == "ready"
    assert result["sessions_created"] == 2
    assert result["empty_opportunities"] == [DIGITAL_OPP]
    assert result["errors"] == []


def test_never_sends_a_synthetic_username(patched):
    """Regression: create_record puts username straight into the payload it POSTs to
    /export/labs_record/. A literal "scheduler" matched no upstream user and made EVERY session
    creation fail with HTTP 500, while the identical criteria succeeded from the UI. An empty
    username works (the key is omitted); an invented one does not. Verified live: run 15253 created
    5 sessions once this stopped fabricating a name."""
    definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP]})
    run_default(definition=definition, access_token="t", cadence="daily")
    sent = patched["task"].apply.call_args.kwargs["kwargs"]["username"]
    assert sent == "", "expected an empty username, got %r" % sent
    assert sent != "scheduler"


def test_uses_the_definitions_username_when_it_has_one(patched):
    """When the workflow record does carry a username, attribute the audit to it rather than
    dropping it — the UI attributes sessions to the person who triggered them."""
    definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP]})
    definition.username = "real_person"
    run_default(definition=definition, access_token="t", cadence="daily")
    assert patched["task"].apply.call_args.kwargs["kwargs"]["username"] == "real_person"
