"""topic_status_lib.py — the single definition of "what state is this FLW × cohort × topic slot in?".

This logic used to be copy-pasted in build_payload_agg.py and build_dashboard_data.py, which is exactly
how two consumers of the "same" metric drift apart. Both now import from here. (The audit gates keep
their OWN independent implementations on purpose — a gate that imports the code under test proves
nothing.)

TWO CORRECTIONS LIVE HERE, both from the 2026-08-07 audit:

1. `not-triggered` is now its own state. The old model had no way to say "the bot never sent this
   interview", so a slot whose scheduled window had passed was painted `available-missed-overdue`,
   labelled "the FLW missed this topic's window". On 2026-08-07 at least 2,094 of the 2,614 red cells
   (80%) had no trigger form at all — the interview was never sent. Those cells were blaming FLWs for
   the pipeline's own gap. `available-*` now means "we asked and got no session"; `not-triggered`
   means "we never asked".

2. The universe is claimed ∪ has-master-rows, not claimed alone. It used to be exactly the FLWs with a
   Connect `date_claimed`, which dropped 210 started and 182 completed interviews (2.2%) belonging to
   FLWs who interviewed in a cohort the Connect snapshot has no claim record for (ABT1 mostly, where
   `initiated` exceeds `claimed`). An interview that happened must appear in the matrix that counts it.

STATE INDEX ORDER IS APPEND-ONLY. flwMatrix ships these as bare integers, so `completed` must stay 5
and `started-not-completed` must stay 4 — renderers, CSV exports and gates all index on those. New
states go on the END. Display order is a separate concern (see BAR_ORDER in the render).
"""
from datetime import timedelta

# index order == wire format. APPEND ONLY — never reorder.
STATES = [
    "not-applicable",  # 0 topic isn't part of this cohort's design
    "not-available-yet",  # 1 not due yet per the schedule, and not triggered early
    "available-not-started",  # 2 triggered, no session yet, window still open
    "available-missed-overdue",  # 3 triggered, no session, window has passed
    "started-not-completed",  # 4 FLW replied but didn't finish
    "completed",  # 5 done
    "not-triggered",  # 6 due per the schedule but no trigger form exists — never sent
]
STATE_IDX = {s: i for i, s in enumerate(STATES)}
# the 5 "real" states for a topic that IS in the cohort's design, plus not-triggered
STATES_APPLICABLE = [s for s in STATES if s != "not-applicable"]


def status_for(topic, topics, master_row, training_date, cadence, today):
    """State of one (FLW, cohort, topic) slot.

    `master_row` is the FLW's master row for this topic in this cohort, or None. A master row exists
    only where a trigger form does, so `master_row is None` IS the signal that nothing was ever sent.
    """
    if topic not in topics:
        return "not-applicable"
    n = topics.index(topic) + 1
    m = master_row
    if m and m["is_completed"] == "Y":
        return "completed"
    if m and m["is_started"] == "Y":
        return "started-not-completed"
    if m:
        # triggered, but no session: the FLW was actually asked, so the window language is fair
        if training_date and cadence and n < len(topics) and today >= training_date + timedelta(days=n * cadence):
            return "available-missed-overdue"
        return "available-not-started"
    # no trigger form for this slot
    if not training_date or not cadence:
        # We don't know this cohort's schedule (it exists in CommCare but not in the Connect snapshot,
        # so training_date is None — the documented 2026-08-04 case). Without a schedule we cannot say
        # the interview was DUE, so we must not accuse the pipeline of missing it either.
        return "available-not-started"
    if today < training_date + timedelta(days=(n - 1) * cadence):
        return "not-available-yet"  # not due yet — nothing has gone wrong
    return "not-triggered"  # due per the schedule and never sent


def status_idx(topic, topics, master_row, training_date, cadence, today):
    return STATE_IDX[status_for(topic, topics, master_row, training_date, cadence, today)]


def universe_for(cohort, cohort_flws, cohort_flw_meta, interviewed_by_cohort):
    """The FLWs whose slots this cohort's matrix should cover.

    Connect-claimed FLWs, PLUS anyone with a master row in the cohort. The second half matters because
    `initiated` exceeds `claimed` in several subgroups (a Welcome form with no claim record), and
    without it their real, completed interviews are missing from topicStatus and the FLW × Topic matrix
    while still being counted in table1/table2 — the same number two different ways.
    """
    claimed = {f for f in cohort_flws.get(cohort, ()) if cohort_flw_meta.get((cohort, f), {}).get("date_claimed")}
    return claimed | set(interviewed_by_cohort.get(cohort, ()))


def interviewed_index(rows):
    """cohort -> set of FLWs holding a master row there (i.e. the bot triggered something)."""
    out = {}
    for r in rows:
        out.setdefault(r["cohort_id"], set()).add(r["connect_id"])
    return out
