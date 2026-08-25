"""Unit fixtures for the reading rules. There was no test file for topic_status_lib at all.

That absence is what let the PANEL defect run: `progress_at_reading` silently degrades to a different
reading when its input is the wrong shape, and nothing anywhere exercised the degraded path. An agent
later forced that fallback deliberately and all four gate suites stayed green while the published
drop-off headline moved by 46%.

These are hand-built deadline lists where A, B and C must give three DIFFERENT, asserted answers - so a
reading collapsing into another one fails here rather than on the dashboard.

Run with pytest; it is also importable as a script.
"""

from datetime import date

import topic_status_lib as tsl

TODAY = date(2026, 8, 25)


def d(day, month=8):
    return date(2026, month, day)


# (deadline, completed_or_None, interview_n)
FINISHED_ALL = [(d(1), d(1), 1), (d(5), d(5), 2)]
TAIL_OVERDUE = [(d(1), d(1), 1), (d(5), d(5), 2), (d(10), None, 3)]
TAIL_NOT_DUE = [(d(1), d(1), 1), (d(5), d(5), 2), (d(29), None, 3)]
SKIPPED_RETURNED = [(d(1), d(1), 1), (d(5), None, 2), (d(10), d(10), 3)]
NEVER_REPLIED = [(d(10), None, 1)]
ALL_SENT_DONE = [(d(1), d(1), 1), (d(5), d(5), 2)]


def test_deadline_in_the_future_is_never_a_dropout():
    """The PANEL defect in one line: someone mid-interview is not a drop-out, under ANY reading."""
    for reading in ("B", "C"):
        assert tsl.progress_at_reading(TAIL_NOT_DUE, TODAY, None, reading) == "in-progress", reading


def test_overdue_tail_is_dropped_under_both_b_and_c():
    assert tsl.progress_at_reading(TAIL_OVERDUE, TODAY, None, "B") == "dropped"
    assert tsl.progress_at_reading(TAIL_OVERDUE, TODAY, None, "C") == "dropped"


def test_skip_then_return_separates_b_from_c():
    """This is the whole reason C exists. If these two ever agree, C has collapsed into B."""
    assert tsl.progress_at_reading(SKIPPED_RETURNED, TODAY, None, "B") == "dropped"
    assert tsl.progress_at_reading(SKIPPED_RETURNED, TODAY, None, "C") != "dropped"


def test_never_replied_is_dropped_under_both():
    """The purest drop-out. Reading A cannot see these people at all, which is A's flaw, not theirs."""
    assert tsl.progress_at_reading(NEVER_REPLIED, TODAY, None, "B") == "dropped"
    assert tsl.progress_at_reading(NEVER_REPLIED, TODAY, None, "C") == "dropped"


def test_finished_outranks_everything():
    assert tsl.progress_at_reading(TAIL_OVERDUE, TODAY, d(20), "C") == "finished"
    assert tsl.progress_at_reading(TAIL_OVERDUE, TODAY, d(20), "B") == "finished"


def test_did_everything_sent_is_waiting_not_dropped():
    """Blaming an FLW for a schedule that stopped is the error this whole bucket exists to prevent."""
    assert tsl.progress_at_reading(ALL_SENT_DONE, TODAY, None, "B") == "waiting"
    assert tsl.progress_at_reading(ALL_SENT_DONE, TODAY, None, "C") == "waiting"


def test_reading_a_is_silence_and_ignores_the_schedule():
    """A says dropped on pure silence even where B and C say the person is fine."""
    assert tsl.progress_at_reading(ALL_SENT_DONE, TODAY, None, "A", silence_days=True) == "dropped"
    assert tsl.progress_at_reading(ALL_SENT_DONE, TODAY, None, "A", silence_days=False) == "waiting"


def test_the_three_readings_are_not_the_same_rule():
    """One fixture where all three disagree. If any two agree here, one has silently degraded."""
    b = tsl.progress_at_reading(SKIPPED_RETURNED, TODAY, None, "B")
    c = tsl.progress_at_reading(SKIPPED_RETURNED, TODAY, None, "C")
    a = tsl.progress_at_reading(SKIPPED_RETURNED, TODAY, None, "A", silence_days=True)
    assert b == "dropped" and c != "dropped" and a == "dropped"
    assert not (b == c), "C has collapsed into B"


def test_two_tuple_input_degrades_to_reading_b():
    """The exact defect. Documented, deliberate - and now pinned, so it cannot change unnoticed.

    A 2-tuple carries no interview number, so C cannot tell a skip from a stop and falls back to B.
    The fix was to stop FEEDING it 2-tuples; this test exists so that if anyone changes the fallback
    (to raise, say) it is a visible decision rather than a silent one.
    """
    two = [(d(1), d(1)), (d(5), None)]
    assert tsl.progress_at_reading(two, TODAY, None, "C") == tsl.progress_at_reading(two, TODAY, None, "B")


def test_reading_a_without_silence_days_degrades_to_b():
    """Second undocumented fallback, one branch up from the known one. Pinned for the same reason."""
    assert tsl.progress_at_reading(TAIL_OVERDUE, TODAY, None, "A", silence_days=None) == tsl.progress_at_reading(
        TAIL_OVERDUE, TODAY, None, "B"
    )


def test_deadline_is_one_gap_after_release():
    """A 3-day design gets 3 days; a 14-day design gets 14. The flat-14 rule is what this replaced."""
    start = date(2026, 6, 1)
    assert tsl.deadline_for(1, start, 3) == date(2026, 6, 4)
    assert tsl.deadline_for(1, start, 14) == date(2026, 6, 15)
    assert tsl.deadline_for(3, start, 4) == date(2026, 6, 13)


def test_r1_rounds_half_up_like_the_browser():
    """Python's round() is banker's rounding; the page uses Math.round. They must not disagree."""
    assert tsl.r1(0.05) == 0.1
    assert tsl.r1(0.15) == 0.2
    assert tsl.r1(2.25) == 2.3


if __name__ == "__main__":
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            bad += 1
            print(f"  FAIL  {fn.__name__}  {e}")
    print(f"\n[tsl] {len(fns) - bad}/{len(fns)} fixtures pass")
    sys.exit(1 if bad else 0)
