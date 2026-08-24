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

# ---- per-cohort grace override -------------------------------------------------------------------
# How long after an interview is released does an FLW have to do it before it counts as missed?
# The DEFAULT is one gap - that cohort's own interview spacing - which is why nothing is listed here:
# a 3-day-gap cohort gets 3 days and a 14-day-gap cohort gets 14, automatically, with no tuning.
#
# Add an entry only when a cohort's owners want a different allowance, e.g. {"1PC1": 28} to give PANEL
# cohort 1PC1 28 days instead of its usual 4. Keyed by cohort id, so cohorts of one design can differ.
# Lives HERE rather than in one builder so that every consumer of the definition reads the same
# overrides - a shared function with unshared inputs is not a shared definition.
GRACE_DAYS = {}

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


def release_for(n, training_date, cadence):
    """The date interview `n` becomes available: the cohort start plus its position in the schedule."""
    return training_date + timedelta(days=(n - 1) * cadence)


def deadline_for(n, training_date, cadence, grace=None):
    """The date interview `n` stops being open.

    Released at (n-1) x cadence, then one further cadence to actually do it - i.e. the deadline is the
    moment the NEXT interview would have fallen due. `grace` overrides that one-cadence allowance for a
    cohort whose owners want it longer or shorter; with grace=cadence (the default) this reproduces the
    original rule exactly.
    """
    return training_date + timedelta(days=(n - 1) * cadence + (cadence if grace is None else grace))


def cohort_end(topics, training_date, cadence, grace=None):
    """When a cohort is over: the deadline of its LAST interview.

    Used to score each cohort at its own end date. Cohorts of one design start weeks apart, so a single
    date shared across the design scores early cohorts against a calendar they never ran in.
    """
    return deadline_for(len(topics), training_date, cadence, grace)


def status_for(topic, topics, master_row, training_date, cadence, today, grace=None):
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
        # Triggered, but no session: the FLW was actually asked, so the window language is fair.
        #
        # The FINAL interview used to be exempt here (`n < len(topics)`), a leftover from the upstream
        # scheduling bug where a terminal frequency_days=9999 left the last interview with no next date.
        # The exemption meant nobody could ever be marked as having skipped their last interview: a
        # 13-of-13 PANEL worker who dropped the last one read as still-open forever, and 2WT - a
        # single-interview design - could never register a miss at all, showing an impossible 0%
        # drop-off. The deadline is a property of THIS interview (released, plus one gap to do it), so
        # it applies to the last one exactly like every other.
        if training_date and cadence and today >= deadline_for(n, training_date, cadence, grace):
            return "available-missed-overdue"
        return "available-not-started"
    # no trigger form for this slot
    if not training_date or not cadence:
        # We don't know this cohort's schedule (it exists in CommCare but not in the Connect snapshot,
        # so training_date is None — the documented 2026-08-04 case). Without a schedule we cannot say
        # the interview was DUE, so we must not accuse the pipeline of missing it either.
        return "available-not-started"
    if today < release_for(n, training_date, cadence):
        return "not-available-yet"  # not due yet — nothing has gone wrong
    return "not-triggered"  # due per the schedule and never sent


def status_idx(topic, topics, master_row, training_date, cadence, today, grace=None):
    return STATE_IDX[status_for(topic, topics, master_row, training_date, cadence, today, grace)]


# States that mean "an interview was put to this FLW and its window has since closed without a finished
# session". This is the shared definition of disengagement: the retention graphs used to run their own
# flat 14-day silence rule instead, which meant a 14-day-gap cohort called an on-schedule worker a
# drop-out while a 3-day-gap cohort gave them nearly five missed turns of slack.
OVERDUE_STATES = frozenset({"available-missed-overdue"})


def progress_at(deadlines, asof, finished_date=None):
    """Where does this FLW stand as of `asof`? One of four states.

    `deadlines` is an iterable of (deadline_date, completed_date_or_None) covering the interviews
    ACTUALLY SENT to this FLW - never slots the bot skipped.

      finished     completed their whole design. Outranks everything.
      dropped      an interview they were sent went past its deadline unfinished.
      in-progress  they have a live interview whose deadline has not arrived yet.
      waiting      they completed everything sent to them, but their design is not complete -
                   nothing further was ever sent, so there is nothing for them to do.

    `waiting` exists because folding it into `dropped` blames FLWs for a schedule that stopped, and
    folding it into steady/inconsistent reads as "they are fine" when they never finished. On live data
    it is 491 FLW-cohort pairs, 15% of starters and 69% of TRE, so it is far too large to mislabel.

    Dropped is recoverable on purpose: complete the interview late and the FLW stops counting as
    dropped, matching how the old silence rule behaved.
    """
    if finished_date is not None and finished_date <= asof:
        return "finished"
    overdue = live = False
    for dl, done in deadlines:
        if done is not None and done <= asof:
            continue  # done by now, nothing outstanding for this slot
        if dl <= asof:
            overdue = True
        else:
            live = True
    if overdue:
        return "dropped"
    return "in-progress" if live else "waiting"


def dropped_at(deadlines, asof, finished_date=None):
    """Thin wrapper kept for callers that only need the boolean."""
    return progress_at(deadlines, asof, finished_date) == "dropped"


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
