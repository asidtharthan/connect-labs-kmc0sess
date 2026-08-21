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


def _visit(visit_id, username, visit_date):
    return {"id": visit_id, "username": username, "visit_date": visit_date}


def _selection(filtered, unfiltered=None):
    """A get_visit_ids_for_audit stand-in.

    Returns (ids, visits) for the return_visits=True selection call and a bare id list
    for the probe _capped_flw_visit_ids makes when the filtered selection came back
    empty, matching the real method's two shapes.
    """

    def fake(opportunity_ids, criteria=None, return_visits=False, **kwargs):
        if return_visits:
            return [v["id"] for v in filtered], list(filtered)
        return list(unfiltered or [])

    return fake


@pytest.fixture
def patched():
    """Substitute the three collaborators and hand back the recorded calls.

    AuditDataAccess is only constructed when a cap is configured, so its presence here
    is what lets an uncapped test assert it was never touched.
    """
    created = {}
    with mock.patch("connect_labs.workflow.data_access.WorkflowDataAccess") as wda_cls, mock.patch(
        "connect_labs.audit.tasks.run_audit_creation"
    ) as task, mock.patch("connect_labs.audit.data_access.AuditDataAccess") as ada_cls:
        wda_cls.return_value.create_run.return_value = SimpleNamespace(id=4242)
        task.apply.return_value = _EagerResult()
        ada_cls.return_value.get_visit_ids_for_audit.side_effect = _selection([])
        created["wda"] = wda_cls
        created["task"] = task
        created["ada"] = ada_cls
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
    definition = _definition(schedule_defaults={"opportunity_ids": [DIAL_OPP, DIGITAL_OPP], "sample_percentage": 30})
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
    run_default(definition=definition, access_token="t", cadence="daily", window=("2026-01-01", "2026-01-31"))
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


# ── The per-worker cap ────────────────────────────────────────────────────────
#
# The cap cannot be expressed in AuditCriteria, so run_default selects the visits
# itself. What matters is that it caps PHOTOS: related_fields/filter_by_image is applied
# at image extraction, never at visit selection, so a cap laid over a raw selection would
# slice visits of every type — on opp 1487, 40% of visits carry no weight photo at all.


def _capped(**extra):
    defaults = {"opportunity_ids": [DIGITAL_OPP], "max_per_flw": 2}
    defaults.update(extra)
    return _definition(schedule_defaults=defaults)


def test_no_cap_configured_leaves_visit_selection_to_the_task(patched):
    """The uncapped path must stay exactly as it shipped — no preselection at all."""
    definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP]})
    run_default(definition=definition, access_token="t", cadence="daily")

    patched["ada"].assert_not_called()
    kwargs = patched["task"].apply.call_args.kwargs["kwargs"]
    assert "flw_visit_ids" not in kwargs
    assert "visit_ids" not in kwargs
    assert "selected_flw_user_ids" not in kwargs["criteria"]


@pytest.mark.parametrize("cap", [0, None, "", "not-a-number"])
def test_unusable_cap_values_mean_no_cap(patched, cap):
    """A blank or malformed cap must degrade to uncapped rather than raise or cap at 0."""
    run_default(definition=_capped(max_per_flw=cap), access_token="t", cadence="daily")

    patched["ada"].assert_not_called()
    assert "flw_visit_ids" not in patched["task"].apply.call_args.kwargs["kwargs"]


def test_cap_slices_each_worker_independently(patched):
    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection(
        [
            _visit(1, "alice", "2026-08-01"),
            _visit(2, "alice", "2026-08-02"),
            _visit(3, "alice", "2026-08-03"),
            _visit(4, "bob", "2026-08-01"),
        ]
    )
    run_default(definition=_capped(), access_token="t", cadence="daily")

    kwargs = patched["task"].apply.call_args.kwargs["kwargs"]
    assert len(kwargs["flw_visit_ids"]["alice"]) == 2, "three visits must be cut to the cap"
    assert kwargs["flw_visit_ids"]["bob"] == [4], "a worker under the cap keeps everything"
    # The flat union lets the creation task skip re-selecting visits.
    assert kwargs["visit_ids"] == sorted(set(kwargs["flw_visit_ids"]["alice"] + [4]))


def test_cap_keeps_the_most_recent_visits(patched):
    """Otherwise the cap keeps an arbitrary slice of whatever order the backend returned."""
    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection(
        [
            _visit(1, "alice", "2026-08-01"),
            _visit(9, "alice", "2026-08-09"),
            _visit(5, "alice", "2026-08-05"),
        ]
    )
    run_default(definition=_capped(), access_token="t", cadence="daily")

    assert patched["task"].apply.call_args.kwargs["kwargs"]["flw_visit_ids"]["alice"] == [9, 5]


def test_cap_selects_only_the_photo_bearing_form(patched):
    """The whole point of the cap fix: cap photos, not visits."""
    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection([_visit(1, "alice", "2026-08-01")])
    run_default(definition=_capped(), access_token="t", cadence="daily")

    selection = patched["ada"].return_value.get_visit_ids_for_audit.call_args.kwargs["criteria"]
    assert selection["deliver_unit_types"] == ["Record Visit Details"]
    # related_fields does nothing at selection time; carrying it here would imply it does.
    assert "related_fields" not in selection


def test_photo_form_name_is_overridable_from_config(patched):
    """A form rename upstream must be absorbable with a definition patch, not a release."""
    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection([_visit(1, "alice", "2026-08-01")])
    definition = _capped()
    definition.data["config"]["photo_form_names"] = ["Renamed Visit Form"]
    run_default(definition=definition, access_token="t", cadence="daily")

    selection = patched["ada"].return_value.get_visit_ids_for_audit.call_args.kwargs["criteria"]
    assert selection["deliver_unit_types"] == ["Renamed Visit Form"]


def test_cap_sends_selected_flw_user_ids_with_the_mapping(patched):
    """run_audit_creation ignores flw_visit_ids unless selected_flw_user_ids is set too,
    so omitting it would silently produce an uncapped run."""
    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection(
        [_visit(1, "alice", "2026-08-01"), _visit(2, "bob", "2026-08-01")]
    )
    run_default(definition=_capped(), access_token="t", cadence="daily")

    kwargs = patched["task"].apply.call_args.kwargs["kwargs"]
    assert kwargs["criteria"]["selected_flw_user_ids"] == ["alice", "bob"]
    assert set(kwargs["flw_visit_ids"]) == {"alice", "bob"}


def test_renamed_photo_form_is_reported_not_passed_off_as_a_quiet_window(patched):
    """Nothing matching the form while the window HOLDS visits is a fault. Reporting it
    as "empty" would hide a schedule that silently audits nothing every night."""
    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection([], unfiltered=[7, 8, 9])
    result = run_default(definition=_capped(), access_token="t", cadence="daily")

    assert result["status"] == "failed"
    assert result["empty_opportunities"] == []
    assert "photo_form_names" in result["errors"][0]
    patched["task"].apply.assert_not_called()


def test_genuinely_quiet_window_with_a_cap_is_empty_not_a_failure(patched):
    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection([], unfiltered=[])
    result = run_default(definition=_capped(), access_token="t", cadence="daily")

    assert result["status"] == "empty"
    assert result["empty_opportunities"] == [DIGITAL_OPP]
    assert result["errors"] == []
    patched["task"].apply.assert_not_called()


def test_one_opportunitys_rename_does_not_cost_the_others_their_audits(patched):
    def per_opp(opportunity_ids, criteria=None, return_visits=False, **kwargs):
        if opportunity_ids == [DIAL_OPP]:
            return ([], []) if return_visits else [7]
        if return_visits:
            return [1], [_visit(1, "alice", "2026-08-01")]
        return []

    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = per_opp
    definition = _capped(opportunity_ids=[DIAL_OPP, DIGITAL_OPP])
    result = run_default(definition=definition, access_token="t", cadence="daily")

    assert result["status"] == "ready"
    assert result["sessions_created"] == 1
    assert len(result["errors"]) == 1 and str(DIAL_OPP) in result["errors"][0]
    assert patched["task"].apply.call_count == 1


def test_cap_is_recorded_on_the_run_so_the_ui_reads_it_back(patched):
    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection([_visit(1, "alice", "2026-08-01")])
    run_default(definition=_capped(max_per_flw=7), access_token="t", cadence="daily")

    state = patched["wda"].return_value.create_run.call_args.kwargs["initial_state"]
    assert state["max_per_flw"] == 7


def test_uncapped_run_records_no_cap_on_the_run(patched):
    definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP]})
    run_default(definition=definition, access_token="t", cadence="daily")

    state = patched["wda"].return_value.create_run.call_args.kwargs["initial_state"]
    assert state["max_per_flw"] is None


def test_cap_closes_the_data_access_it_opens(patched):
    """These run in a Celery worker; a leaked httpx client per opportunity accumulates."""
    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection([_visit(1, "alice", "2026-08-01")])
    run_default(definition=_capped(), access_token="t", cadence="daily")

    patched["ada"].return_value.close.assert_called_once()


def test_the_cap_filter_survives_the_real_criteria_parser():
    """The bug this cap fix exists to avoid was setting a key the backend ignores, so
    pin the whole hop: the criteria dict run_default builds must still carry
    deliver_unit_types after AuditCriteria.from_dict, and filter_visits_for_audit must
    actually accept that parameter. Mocked selection tests cannot see either.
    """
    import inspect

    from connect_labs.audit.data_access import AuditCriteria
    from connect_labs.labs.analysis.pipeline import AnalysisPipeline
    from connect_labs.workflow.templates.kmc_image_audit import PHOTO_FORM_NAMES, _scheduled_criteria

    criteria = _scheduled_criteria(
        opp_id=DIGITAL_OPP,
        opp_meta={str(DIGITAL_OPP): {"llo": "PIPN"}},
        window_start="2026-08-01",
        window_end="2026-08-07",
        sample_percentage=30,
        image_path="anthropometric/upload_weight_image",
        field_path="child_weight_visit",
    )
    criteria["deliver_unit_types"] = list(PHOTO_FORM_NAMES)

    parsed = AuditCriteria.from_dict(criteria)
    assert parsed.deliver_unit_types == PHOTO_FORM_NAMES, "the form filter was dropped in parsing"
    assert parsed.sample_percentage == 30, "sampling must still compose with the cap"
    assert parsed.audit_type == "date_range"

    # The selection layer must really take it. related_fields is the counter-example:
    # it is a valid AuditCriteria field that this signature has no parameter for, which
    # is exactly why filter_by_image never narrowed visit selection.
    params = inspect.signature(AnalysisPipeline.filter_visits_for_audit).parameters
    assert "deliver_unit_types" in params
    assert "related_fields" not in params


# ── The schedule dialog's settings ────────────────────────────────────────────


def test_schedule_defaults_key_agrees_with_the_registry():
    """The template names the config key as a literal to avoid a circular import, so
    nothing but a test stops the two drifting and the dialog writing where run_default
    does not read."""
    from connect_labs.workflow.templates import SCHEDULE_DEFAULTS_CONFIG_KEY
    from connect_labs.workflow.templates.kmc_image_audit import SCHEDULE_DEFAULTS_KEY

    assert SCHEDULE_DEFAULTS_KEY == SCHEDULE_DEFAULTS_CONFIG_KEY


def test_declared_options_are_well_formed():
    from connect_labs.workflow.templates import SCHEDULE_OPTION_TYPES, template_schedule_options

    options = template_schedule_options(TEMPLATE_KEY)
    assert options, "the dialog would offer nothing"
    for opt in options:
        assert opt["type"] in SCHEDULE_OPTION_TYPES
        assert opt["label"] and opt["label"] != opt["key"], "every option needs a human label"
        assert opt["help"], "an unexplained scheduling knob invites a wrong setting"


def test_option_choices_come_from_the_workflows_own_config():
    """Frozen choices would go stale the moment a workflow's opportunity set changed."""
    from connect_labs.workflow.templates import schedule_options_for_definition

    definition = SimpleNamespace(
        template_type=TEMPLATE_KEY,
        data={
            "config": {
                "opp_names": {"1487": "PIPN (V3)", "1236": "EHA (V2+)"},
                "schedule_defaults": {"opportunity_ids": [1487], "max_per_flw": 12},
            }
        },
    )
    by_key = {o["key"]: o for o in schedule_options_for_definition(definition)}

    # Sorted by id so the dialog's order does not depend on dict ordering.
    assert by_key["opportunity_ids"]["choices"] == [
        {"value": 1236, "label": "EHA (V2+)"},
        {"value": 1487, "label": "PIPN (V3)"},
    ]
    # Current values come back so the dialog opens on what the schedule would really use.
    assert by_key["opportunity_ids"]["selected"] == [1487]
    assert by_key["max_per_flw"]["value"] == 12


def test_options_are_empty_for_a_template_that_cannot_be_scheduled():
    from connect_labs.workflow.templates import template_schedule_options

    assert template_schedule_options("performance_review") == []
    assert template_schedule_options(None) == []


@pytest.mark.parametrize("option_key", ["opportunity_ids", "max_per_flw", "sample_percentage"])
def test_every_offered_setting_actually_changes_a_run(patched, option_key):
    """The dialog must not offer a setting run_default ignores — that is precisely the
    lie this surface was built to remove (a cap set on screen, a run without it)."""
    from connect_labs.workflow.templates import template_schedule_options

    assert option_key in {o["key"] for o in template_schedule_options(TEMPLATE_KEY)}

    patched["ada"].return_value.get_visit_ids_for_audit.side_effect = _selection(
        [_visit(1, "alice", "2026-08-01"), _visit(2, "alice", "2026-08-02")]
    )

    if option_key == "opportunity_ids":
        definition = _definition(schedule_defaults={"opportunity_ids": [DIAL_OPP]})
        run_default(definition=definition, access_token="t", cadence="daily")
        audited = [c.kwargs["kwargs"]["opportunities"][0]["id"] for c in patched["task"].apply.call_args_list]
        assert audited == [DIAL_OPP]
        return

    if option_key == "max_per_flw":
        definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP], "max_per_flw": 1})
        run_default(definition=definition, access_token="t", cadence="daily")
        kwargs = patched["task"].apply.call_args.kwargs["kwargs"]
        assert len(kwargs["flw_visit_ids"]["alice"]) == 1
        return

    definition = _definition(schedule_defaults={"opportunity_ids": [DIGITAL_OPP], "sample_percentage": 45})
    run_default(definition=definition, access_token="t", cadence="daily")
    assert patched["task"].apply.call_args.kwargs["kwargs"]["criteria"]["sample_percentage"] == 45
