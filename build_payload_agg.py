"""Build the AGGREGATES payload (tiny, render-ready) from the validated master + status.
Funnel + Tables 1-3 + topic/subgroup status distributions + %Started line series.
No per-row data (those need the server-side phase). Emits payload_agg.json + size.
"""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import build_master_4src as bm
import topic_status_lib as tsl

# Drives status time-gating; dynamic so the daily job gates against the real date. INTERVIEWS_TODAY
# overrides it for one purpose: proving that a CLOSED cohort's numbers do not move as the calendar
# does. If a finished cohort gains drop-outs simply because time passed, the daily refresh is counting
# silence rather than behaviour, and that is a bug. audit_e2e runs the build twice and diffs.
import os as _os

TODAY = date.fromisoformat(_os.environ["INTERVIEWS_TODAY"]) if _os.environ.get("INTERVIEWS_TODAY") else date.today()
# Canonical topic order; include every topic ANY subgroup design uses (auto-picks up 12/13/C from the
# CCHQ-derived schedule) so topic-completion never silently drops a topic the bot actually runs.
_CANON_TOPICS = [
    "A",
    "B",
    "C",
    "D",
    "E",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "8S",
    "8L",
    "10S",
    "10L",
    "11S",
    "11L",
    "13L",
    "99",
    "101",
    "F",
    "G",
]
TOPICS = [t for t in _CANON_TOPICS if any(t in bm.SUBGROUP_DESIGN[sg]["topics"] for sg in bm.SUBGROUP_DESIGN)]
SG_ORDER = ["TRS", "TRE", "ABT1-A", "ABT1-B", "ABT2-A", "ABT2-B", "PANEL", "ABT3-A", "ABT3-B", "2WT", "EXT"]
ROLL = {
    "TRS": "TRS",
    "TRE": "TRE",
    "ABT1-A": "ABT1",
    "ABT1-B": "ABT1",
    "ABT2-A": "ABT2",
    "ABT2-B": "ABT2",
    "PANEL": "PANEL",
    "ABT3-A": "ABT3",
    "ABT3-B": "ABT3",
    "2WT": "2WT",
    "EXT": "EXT",
}

# ---- cells: unique (flw,cohort,interview_n) ----
cell = {}
for r in bm.rows:
    k = (r["connect_id"], r["cohort_id"], int(r["interview_n"]))
    c = cell.setdefault(
        k,
        {
            "sg": r["subgroup"],
            "n": int(r["interview_n"]),
            "flw": r["connect_id"],
            "t": False,
            "s": False,
            "c": False,
            "hw": 0,
            "hm": 0,
        },
    )
    c["t"] = True
    if r["is_started"] == "Y":
        c["s"] = True
        # FLW message words/msgs for this started session (per-session; matched_session unique per row)
        c["hw"] += int(r.get("session_human_words", 0) or 0)
        c["hm"] += int(r.get("session_human_msgs", 0) or 0)
    if r["is_completed"] == "Y":
        c["c"] = True
cells = list(cell.values())

# ---- present subgroups (auto-load: a subgroup appears only once it has data, so PANEL/ABT3 stay
#      hidden until their first cohort launches; SG_ORDER only fixes display order of those present) ----
_present = {c["sg"] for c in cells}
for _cohort, _info in bm.cohort_info.items():
    if bm.cohort_flws.get(_cohort):
        _present.add(_info["subgroup"])
SG_PRESENT = [sg for sg in SG_ORDER if sg in _present]
# topics applicable to >=1 present subgroup (hides topics 10/11 etc. until a subgroup using them is live)
APPLICABLE = [t for t in TOPICS if any(t in bm.SUBGROUP_DESIGN[sg]["topics"] for sg in SG_PRESENT)]

# ---- eligible per subgroup ----
elig_sg = defaultdict(set)
for (cohort, topic), flws in bm.welcome_flws_by_key.items():
    sg = bm.cohort_to_sg(cohort)
    if sg:
        elig_sg[sg] |= flws

# ---- funnel + line series ----
fset = defaultdict(lambda: {"t": set(), "s": set(), "c": set()})
for c in cells:
    f = fset[(c["sg"], c["n"])]
    if c["t"]:
        f["t"].add(c["flw"])
    if c["s"]:
        f["s"].add(c["flw"])
    if c["c"]:
        f["c"].add(c["flw"])

# ---- penult/last back-to-back artifact: "did-last-only" de-impacted starts (item 8) ----
# Some subgroups trigger the last two interviews back-to-back (~0-day gap); a set of FLWs engage
# ONLY the last (skipping the penultimate), inflating the last interview's %Started and masking the
# true decline. did_last_only = started(last) − started(penult); the de-impacted series removes those
# from the LAST interview's STARTED numerator (eligible base unchanged). Gated by the median
# penult→last TRIGGER gap (<1 day) so it auto-applies to PANEL/ABT3 only if they're back-to-back.


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


DEIMPACT_GAP_DAYS = 1.0
deimpact = {}  # sg -> {"last_n": int, "count": int}
for sg in SG_PRESENT:
    topics = bm.SUBGROUP_DESIGN[sg]["topics"]
    if len(topics) < 3:  # 2-interview subgroups: normal-cadence non-sequential takers, not artifacts
        continue
    last_n, pen_n = len(topics), len(topics) - 1
    last_top, pen_top = topics[-1], topics[-2]
    started_last, started_pen = fset[(sg, last_n)]["s"], fset[(sg, pen_n)]["s"]
    did_last_only = started_last - started_pen
    if not did_last_only:
        continue
    gaps = []
    for flw in started_last | started_pen:
        pt = bm.triggers_by_flw_iv.get((flw, pen_top))
        lt = bm.triggers_by_flw_iv.get((flw, last_top))
        if pt and lt:
            gaps.append(abs((lt[0]["received_on"] - pt[0]["received_on"]).total_seconds()) / 86400.0)
    med = _median(gaps)
    if med is not None and med < DEIMPACT_GAP_DAYS:
        # count_c = how many of them COMPLETED it. Removing people from Started without removing
        # their completions is what made Completed exceed Started in seven rows.
        deimpact[sg] = {
            "last_n": last_n,
            "count": len(did_last_only),
            "count_c": len(did_last_only & fset[(sg, last_n)]["c"]),
        }
print(
    f"[8] de-impact (penult/last artifact): {sum(d['count'] for d in deimpact.values())} FLWs across {sorted(deimpact)}"
)

# ---- per-(subgroup, interview) release status (items A1/A2): not-available / in-progress / settled ----
# Uses per-cohort training dates + the CCHQ schedule offsets so "not yet offered" interviews (e.g. the
# later PANEL ones) are distinguished from genuine drop-off. Aggregated across a subgroup's cohorts:
#   not-available = no cohort has reached this interview's release date yet (don't plot — avoids a false 0%)
#   in-progress   = released for some, but the NEXT interview isn't released for all (still accumulating)
#   settled       = the next interview is released for all cohorts (this interview's window has closed)
_subgroup_cohorts = defaultdict(list)
for _c, _inf in bm.cohort_info.items():
    _subgroup_cohorts[_inf["subgroup"]].append(_c)


def _offset(cohort, k, sg):
    sched = bm.cohort_schedule.get(cohort)
    if sched and 0 <= k - 1 < len(sched):
        return sched[k - 1]["offset_days"]
    return (k - 1) * bm.SUBGROUP_DESIGN[sg]["cadence"]


def _release_status(sg, n):
    topics = bm.SUBGROUP_DESIGN[sg]["topics"]
    cad = bm.SUBGROUP_DESIGN[sg]["cadence"]
    rel_now, rel_next = [], []
    for c in _subgroup_cohorts.get(sg, []):
        td = bm.cohort_info[c].get("training_date")
        if not td:
            continue
        rel_now.append(TODAY >= td + timedelta(days=_offset(c, n, sg)))
        nxt = _offset(c, n + 1, sg) if n < len(topics) else _offset(c, n, sg) + cad
        rel_next.append(TODAY >= td + timedelta(days=nxt))
    if not rel_now or not any(rel_now):
        return "not-available"
    return "settled" if all(rel_next) else "in-progress"


funnel = []
line = {}
line_di = {}
line_prev = (
    {}
)  # per-subgroup: %Started with denominator = FLWs who STARTED the PREVIOUS interview (item: retention-prev)
line_status = {}
line_days = {}  # per-subgroup: median days from the FLW's interview-1 trigger to interview-N trigger
for sg in SG_PRESENT:
    elig = len(elig_sg[sg]) or 1
    di = deimpact.get(sg)
    topic1 = bm.SUBGROUP_DESIGN[sg]["topics"][0]
    series = []
    series_di = []
    series_prev = []
    statuses = []
    days_series = []
    for i, tc in enumerate(bm.SUBGROUP_DESIGN[sg]["topics"]):
        n = i + 1
        f = fset[(sg, n)]
        t, s, cc = len(f["t"]), len(f["s"]), len(f["c"])
        s_di = s - di["count"] if (di and n == di["last_n"]) else s
        c_di = cc - di.get("count_c", 0) if (di and n == di["last_n"]) else cc
        st = _release_status(sg, n)
        # "reached-previous-interview" retention: of the FLWs who STARTED interview n-1, what fraction
        # ALSO started interview n. Numerator = |started(n) ∩ started(n-1)| (NOT raw started(n) — an FLW
        # can start n without n-1, which would push the ratio >100% and off the chart). Denominator =
        # |started(n-1)|. This is bounded ≤100% and is the true conditional retention (later interviews
        # aren't diluted by FLWs who haven't reached that stage). n=1 uses the initiated base (no previous);
        # null when the previous interview has 0 starters.
        if n > 1:
            prev_set = fset[(sg, n - 1)]["s"]
            prev_started = len(prev_set)
            prev_num = len(f["s"] & prev_set)  # started n AND started n-1
        else:
            prev_started, prev_num = elig, s
        pct_started_prev = tsl.r1(100 * prev_num / prev_started) if prev_started else None
        funnel.append(
            {
                "sg": sg,
                "n": n,
                "topic": tc,
                "name": bm.TOPIC_NAMES[tc],
                "elig": elig,
                "trig": t,
                "started": s,
                "completed": cc,
                "pct_trig": tsl.r1(100 * t / elig),
                "pct_started": tsl.r1(100 * s / elig),
                "pct_completed": tsl.r1(100 * cc / s) if s else None,
                # completion as a share of the INITIATED base (retention), not of this interview's
                # starters — for the "pay per interview" / full retention table (Screenshot 104).
                "pct_completed_base": tsl.r1(100 * cc / elig),
                # de-impacted started (penult/last artifact removed from the LAST interview only)
                "started_di": s_di,
                "completed_di": c_di,
                "pct_completed_di": tsl.r1(100 * c_di / s_di) if s_di else None,
                "pct_started_di": tsl.r1(100 * s_di / elig),
                # %Started vs FLWs who started the previous interview (reached-prev denominator)
                "prev_started": prev_started,  # denominator = |started(n-1)| (n=1 -> elig)
                "prev_num": prev_num,  # numerator = |started(n) ∩ started(n-1)| (n=1 -> started)
                "pct_started_prev": pct_started_prev,
                # release status (not-available / in-progress / settled) for funnel display
                "status": st,
            }
        )
        series.append(tsl.r1(100 * s / elig))
        series_di.append(tsl.r1(100 * s_di / elig))
        series_prev.append(pct_started_prev)
        statuses.append(st)
        # median days from when the FLW DID interview 1 (session start) to when they DID interview n.
        # Anchored on the actual OCS session start (not the trigger), so day 0 = "the day they did their
        # first interview". Population = FLWs who STARTED interview n and have an interview-1 session. n=1 -> 0.
        day_vals = []
        for flw in f["s"]:
            s1 = bm.session_start_by_flw_iv.get((flw, topic1))
            sn = bm.session_start_by_flw_iv.get((flw, tc))
            if s1 and sn:
                day_vals.append((sn - s1).total_seconds() / 86400.0)
        med_days = _median(day_vals)
        days_series.append(tsl.r1(med_days) if med_days is not None else None)
    line[sg] = series
    line_di[sg] = series_di
    line_prev[sg] = series_prev
    line_status[sg] = statuses
    line_days[sg] = days_series

# ---- per-subgroup "still rolling out" flag (drives the dotted funnel line) ----
# Option A (data-driven, no hardcoded dates): a subgroup is "active" (-> dotted) while it is still
# releasing interviews, i.e. TODAY is on/before the projected release of its LAST interview for its
# latest-launching cohort; SOLID once every cohort's last interview has been released. Projected from
# signals the pipeline already holds: each cohort's invitation/training date + the CCHQ schedule's
# cumulative offset to the last interview (`_offset`), plus a fixed lag for FLWs to finish Learn before
# interview 1 fires. (training_date = earliest invited_date, which for re-draw cohorts precedes the
# real interview start by ~a week — the lag absorbs that skew.) Falls back to the cohort's FIRST real
# interview trigger + offset when the invitation date isn't available yet, and marks a present-but-
# date-less cohort active. Additive: does not touch line_status, funnel numbers, or the nulling.
LINE_LAG_DAYS = 7  # invitation/training date -> interview-1 release lag (FLWs complete Learn first)
_cohort_first_trig = {}
for r in bm.rows:
    _td = bm.parse_dt(r.get("trigger_received_on"))
    _c = r["cohort_id"]
    if _td and (_c not in _cohort_first_trig or _td < _cohort_first_trig[_c]):
        _cohort_first_trig[_c] = _td
# ONE cohort-end date for the whole payload. Every consumer that needs to know whether a cohort is
# still running reads this map, so the funnel line, the engagement panel and the drop-off view cannot
# disagree about it. tsl.cohort_end IS the function the drop-off scoring uses, which is the point.
# (cohort_info only holds the older cohorts, so the union below keeps the newer subgroups in.)
COHORT_END = {}
for _c in set(_cohort_first_trig) | set(bm.cohort_info):
    _sg = bm.cohort_to_sg(_c)
    if _sg not in bm.SUBGROUP_DESIGN:
        continue
    _cad = bm.SUBGROUP_DESIGN[_sg]["cadence"]
    # Start date, in the order build_master_4src resolved it: invitation, else the first trigger. A
    # cohort with neither cannot be dated and stays out of the map.
    _st = bm.cohort_info.get(_c, {}).get("start_date")
    if not _st and _c in _cohort_first_trig:
        _st = _cohort_first_trig[_c].date()
    if not _st or not _cad:
        continue
    COHORT_END[_c] = tsl.cohort_end(bm.SUBGROUP_DESIGN[_sg]["topics"], _st, _cad, tsl.GRACE_DAYS.get(_c))

# A subgroup's funnel line stays dotted while ANY of its cohorts is still inside its schedule. A cohort
# with no invitation and no trigger yet cannot be dated, so it counts as still rolling out, as before.
line_active = {sg: False for sg in SG_PRESENT}
for _c in set(_cohort_first_trig) | set(bm.cohort_info):
    _sg = bm.cohort_to_sg(_c)
    if _sg not in line_active:
        continue
    _end = COHORT_END.get(_c)
    if _end is None or TODAY <= _end:
        line_active[_sg] = True

# Authoritative dotted->solid dates from the program rollout schedule (per the cohort tracker /
# program owners). These OVERRIDE the derived projection above for named subgroups whose real rollout
# can't be inferred from the schedule alone — PANEL is behind its 13-interview schedule (would project
# into mid-Aug) and EXT is still ramping (a derived estimate undershoots). Any subgroup NOT listed here
# keeps the data-driven estimate above, so new subgroups still auto-derive. Update when the rollout
# schedule changes; drop an entry once its date has passed to hand the subgroup back to the estimate.
LINE_DOTTED_UNTIL = {
    # Empty: the PANEL (Jul 31) and EXT (Aug 9) pins have both expired, so every subgroup now falls back
    # to the data-driven estimate above. Both consumers iterate .items(), so an empty dict is a no-op.
    # Add {"<SG>": date(Y, M, D)} again when a rollout schedule needs to override the estimate.
}
for _sg, _until in LINE_DOTTED_UNTIL.items():
    if _sg in line_active:
        line_active[_sg] = TODAY <= _until


# ---- Tables 1-3 ----
def agg(keyfn, keys):
    a = defaultdict(lambda: {"flw": set(), "ist": 0, "icmp": 0, "hw": 0, "hm": 0})
    for c in cells:
        for k in set(keyfn(c)):
            if c["s"]:
                a[k]["flw"].add(c["flw"])
                a[k]["ist"] += 1
                a[k]["hw"] += c["hw"]
                a[k]["hm"] += c["hm"]
            if c["c"]:
                a[k]["icmp"] += 1
    return [
        {
            "key": k,
            "flws": len(a[k]["flw"]),
            "ist": a[k]["ist"],
            "icmp": a[k]["icmp"],
            "pct": tsl.r1(100 * a[k]["icmp"] / a[k]["ist"]) if a[k]["ist"] else None,
            "avg_words": tsl.r1(a[k]["hw"] / a[k]["hm"]) if a[k]["hm"] else None,
        }
        for k in keys
        if k in a
    ]


# rollup keys (Table 1) and A/B keys (Table 3) follow the present subgroups, so PANEL/ABT3 fold in
# automatically once they have data and stay absent otherwise.
_roll_keys = list(dict.fromkeys(ROLL[sg] for sg in SG_PRESENT)) + ["Overall"]
_abt_keys = [sg for sg in SG_PRESENT if sg.startswith(("ABT1", "ABT2", "ABT3"))] + ["Overall"]
t1 = agg(lambda c: [ROLL[c["sg"]], "Overall"], _roll_keys)
t3 = agg(
    lambda c: ([c["sg"], "Overall"] if c["sg"].startswith(("ABT1", "ABT2", "ABT3")) else []),
    _abt_keys,
)
# Table 2 by topic
t2a = defaultdict(lambda: {"flw": set(), "ist": 0, "icmp": 0, "hw": 0, "hm": 0})
for c in cells:
    tc = bm.SUBGROUP_DESIGN[c["sg"]]["topics"][c["n"] - 1]
    if c["s"]:
        t2a[tc]["flw"].add(c["flw"])
        t2a[tc]["ist"] += 1
        t2a[tc]["hw"] += c["hw"]
        t2a[tc]["hm"] += c["hm"]
    if c["c"]:
        t2a[tc]["icmp"] += 1
t2 = [
    {
        "code": tc,
        "name": bm.TOPIC_NAMES[tc],
        "flws": len(t2a[tc]["flw"]),
        "ist": t2a[tc]["ist"],
        "icmp": t2a[tc]["icmp"],
        "pct": tsl.r1(100 * t2a[tc]["icmp"] / t2a[tc]["ist"]) if t2a[tc]["ist"] else None,
        "avg_words": tsl.r1(t2a[tc]["hw"] / t2a[tc]["hm"]) if t2a[tc]["hm"] else None,
    }
    # all applicable topics (not just those with started data) so the By-Topic breakdown shows the
    # full roster incl. not-yet-started ones (10/11/12/13) — zero-activity rows get 0 / None metrics.
    for tc in APPLICABLE
]

# ---- topic-status distribution (per topic + per subgroup) for stacked bars ----
# STATES + the status rule live in topic_status_lib so build_dashboard_data.py cannot drift from this.
STATES = tsl.STATES
mlook = {}


def rank(r):
    return (1 if r["is_completed"] == "Y" else 0) * 2 + (1 if r["is_started"] == "Y" else 0)


for r in bm.rows:
    k = (r["connect_id"], r["cohort_id"], r["topic_code"])
    if k not in mlook or rank(r) > rank(mlook[k]):
        mlook[k] = r


def status_for(flw, cohort, topic):
    sg = bm.cohort_to_sg(cohort)
    return tsl.status_for(
        topic,
        bm.SUBGROUP_DESIGN[sg]["topics"],
        mlook.get((flw, cohort, topic)),
        bm.cohort_info.get(cohort, {}).get("start_date"),  # one shared source, see build_master
        bm.SUBGROUP_DESIGN[sg]["cadence"],
        TODAY,
        tsl.GRACE_DAYS.get(cohort),
    )


topic_status = defaultdict(lambda: defaultdict(int))
sg_status = defaultdict(lambda: defaultdict(int))
topic_status_cohort = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # topic -> cohort -> state -> n
_interviewed = tsl.interviewed_index(bm.rows)
for cohort, info in bm.cohort_info.items():
    sg = info["subgroup"]
    # claimed ∪ anyone with a master row here — see topic_status_lib.universe_for
    claimed = sorted(tsl.universe_for(cohort, bm.cohort_flws, bm.cohort_flw_meta, _interviewed))
    for flw in claimed:
        for topic in TOPICS:
            st = status_for(flw, cohort, topic)
            topic_status[topic][st] += 1
            if st != "not-applicable":
                sg_status[sg][st] += 1
                topic_status_cohort[topic][cohort][st] += 1
topic_status_out = [
    {"code": tc, "name": bm.TOPIC_NAMES[tc], **{s: topic_status[tc][s] for s in STATES}} for tc in APPLICABLE
]
# per-cohort topic status (for the by-cohort drilldown); the applicable states (topic IS in the cohort)
STATES5 = [
    "completed",
    "started-not-completed",
    "available-missed-overdue",
    "available-not-started",
    "not-available-yet",
    "not-triggered",
]
topic_status_cohort_out = {}
for tc in APPLICABLE:
    rows_c = []
    for cohort in sorted(topic_status_cohort.get(tc, {})):
        d = topic_status_cohort[tc][cohort]
        rows_c.append({"cohort": cohort, "total": sum(d[s] for s in STATES5), **{s: d[s] for s in STATES5}})
    if rows_c:
        topic_status_cohort_out[tc] = rows_c

# ---- Retention Drop-off matrix (GW parity): Connect funnel + per-interview blocks ----
# Eligible = # FLWs Initiated (constant per group), so %Started/%Triggered are retention rates.
coh_init = defaultdict(set)  # cohort -> set of FLWs with any welcome form
for (cohort, _topic), flws in bm.welcome_flws_by_key.items():
    coh_init[cohort] |= flws
coh_fset = defaultdict(lambda: {"t": set(), "s": set(), "c": set()})  # (cohort,n) -> unique-FLW sets
for r in bm.rows:
    key = (r["cohort_id"], int(r["interview_n"]))
    coh_fset[key]["t"].add(r["connect_id"])
    if r["is_started"] == "Y":
        coh_fset[key]["s"].add(r["connect_id"])
    if r["is_completed"] == "Y":
        coh_fset[key]["c"].add(r["connect_id"])


def _iv_blocks(topics, init_set, fget, di_n=None, di_ct=0, di_cc=0):
    base = len(init_set) or 1
    out = []
    for i, tc in enumerate(topics):
        n = i + 1
        f = fget(n)
        t, s, c = len(f["t"]), len(f["s"]), len(f["c"])
        s_di = s - di_ct if (di_n is not None and n == di_n and di_ct) else s
        c_di = c - di_cc if (di_n is not None and n == di_n and di_cc) else c
        out.append(
            {
                "n": n,
                "topic": tc,
                "name": bm.TOPIC_NAMES[tc],
                "eligible": len(init_set),
                "triggered": t,
                "pct_trig": tsl.r1(100 * t / base),
                "started": s,
                "pct_started": tsl.r1(100 * s / base),
                "completed": c,
                "pct_completed": tsl.r1(100 * c / s) if s else None,
                "pct_completed_base": tsl.r1(100 * c / base),  # completed / initiated base (retention)
                "started_di": s_di,
                "pct_started_di": tsl.r1(100 * s_di / base),  # de-impacted (item 8)
                # Completed is de-impacted by the SAME people, so the row cannot report more completions
                # than starts. Without this, seven rows did exactly that.
                "completed_di": c_di,
                "pct_completed_di": tsl.r1(100 * c_di / s_di) if s_di else None,
            }
        )
    return out


dropoff_sg = []
for sg in SG_PRESENT:
    u = bm.sg_unique[sg]
    claimed = u["claimed"]
    init = elig_sg.get(sg, set())
    connect = {
        "invited": len(u["invited"]),
        "accepted": len(u["accepted"]),
        "learn_started": len(u["learn_started"]),
        "learn_completed": len(u["learn_completed"]),
        "claimed": len(claimed),
        "flw_reg": len(claimed & bm.flw_registered),
        "initiated": len(init),
    }
    cohorts_n = sum(1 for c in bm.cohort_info if bm.cohort_info[c]["subgroup"] == sg)
    dropoff_sg.append(
        {
            "sg": sg,
            "cohorts_n": cohorts_n,
            "connect": connect,
            "interviews": _iv_blocks(
                bm.SUBGROUP_DESIGN[sg]["topics"],
                init,
                lambda n, _sg=sg: fset[(_sg, n)],
                di_n=deimpact.get(sg, {}).get("last_n"),
                di_ct=deimpact.get(sg, {}).get("count", 0),
                di_cc=deimpact.get(sg, {}).get("count_c", 0),
            ),
        }
    )

dropoff_cohorts = defaultdict(list)
for cohort in sorted(bm.cohort_info):
    sg = bm.cohort_info[cohort]["subgroup"]
    flws = bm.cohort_flws[cohort]
    inv = acc = ls = lc = 0
    claimed_set = set()
    for u in flws:
        m = bm.cohort_flw_meta.get((cohort, u), {})
        inv += 1 if m.get("invited_date") else 0
        acc += 1 if m.get("accepted") else 0
        ls += 1 if m.get("learn_started") else 0
        lc += 1 if m.get("learn_completed") else 0
        if m.get("date_claimed"):
            claimed_set.add(u)
    init = coh_init.get(cohort, set())
    connect = {
        "invited": inv,
        "accepted": acc,
        "learn_started": ls,
        "learn_completed": lc,
        "claimed": len(claimed_set),
        "flw_reg": len(claimed_set & bm.flw_registered),
        "initiated": len(init),
    }
    dropoff_cohorts[sg].append(
        {
            "cohort": cohort,
            "connect": connect,
            "interviews": _iv_blocks(
                bm.SUBGROUP_DESIGN[sg]["topics"],
                init,
                lambda n, _c=cohort: coh_fset.get((_c, n), {"t": set(), "s": set(), "c": set()}),
            ),
        }
    )

dropoff = {"subgroups": dropoff_sg, "cohorts": dict(dropoff_cohorts)}

# Subgroups whose Connect funnel (Invited/Accepted/Learn/Claimed) is PENDING: they have interview
# data but their cohorts are missing from the Connect snapshot (a stale/failed Connect pull). The
# render flags these so Invited=0 reads as "not pulled yet", not "nobody invited".
connect_pending_sgs = sorted(
    {
        bm.cohort_info[c]["subgroup"]
        for c in getattr(bm, "CONNECT_PENDING_COHORTS", set())
        if c in bm.cohort_info and bm.cohort_info[c]["subgroup"] in SG_PRESENT
    }
)
if connect_pending_sgs:
    print(f"[eng] connect-funnel PENDING subgroups: {connect_pending_sgs}")


# ---- Cohort Engagement (3-panel: recruitment / engagement-quality / current-status) ----
# Neal's spec: separate what the single retention curve conflates — (1) how many FLWs have STARTED
# interviewing, (2) how consistently starters keep going, (3) where each starter stands now. All
# backward-looking (computable each week, never future-dependent), from interview SESSION records only.
# We use the pipeline's canonical started rows (one matched OCS session per interview slot) so the
# starter counts tie out exactly with table1[sg].flws / connectFunnel[sg].started. Session DATE is the
# OCS session start (created_at, UTC), joined via matched_session_id. Collapsed to one row per (flw,day).
def _pcts_to_100(counts, base):
    """Round a set of counts to whole percentages that sum to EXACTLY 100.

    Rounding each share independently made the four outcome bars land on 99 or 101 at 36 of 156
    week-points, while the legend promised they sum to 100. Largest-remainder (Hare quota) assigns the
    leftover points to whichever shares were cut hardest, so the stack always closes.
    """
    if not base:
        return [0] * len(counts)
    exact = [100 * c / base for c in counts]
    out = [int(x) for x in exact]
    short = 100 - sum(out)
    if short > 0:
        order = sorted(range(len(counts)), key=lambda i: (exact[i] - out[i], counts[i]), reverse=True)
        for i in order[:short]:
            out[i] += 1
    return out


def _slot_deadline(n, start, cad, cohort, trig_iso):
    """When this interview stops being open FOR THIS WORKER.

    The design deadline is start + (n-1)*gap + grace. But 22.1% of sent slots were triggered AFTER
    their own design deadline had already passed (ABT1-A 52.9%, worst case 98 days late), so scoring
    against the design alone blames the FLW for a window the pipeline had already closed before sending.
    A worker cannot be late for something that had not arrived, so the deadline is whichever is LATER:
    the design's, or one gap after it actually reached them.

    Measured effect on the counts: none - those slots were never completed at any later date either.
    This is an attribution fix, not a numbers fix, and it protects future cohorts where a late trigger
    might still be completed in time.
    """
    dl = tsl.deadline_for(n, start, cad, tsl.GRACE_DAYS.get(cohort))
    td = bm.parse_dt(trig_iso) if trig_iso else None
    if td:
        from_trigger = td.date() + timedelta(days=tsl.GRACE_DAYS.get(cohort) or cad)
        if from_trigger > dl:
            return from_trigger
    return dl


_sid2date = {e["sid"]: e["first"].date() for _lst in bm.ocs_by_key.values() for e in _lst}
_eng_flw_dates = defaultdict(lambda: defaultdict(set))  # sg -> flw -> {started session dates}
_eng_comp_topic_dt = defaultdict(lambda: defaultdict(dict))  # sg -> flw -> {topic: earliest completed date}
_eng_flw_llo = {}  # flw -> LLO (COWACDI / EHA), for the by-LLO split
# sg -> flw -> [(deadline_date, completed_date_or_None)] for the interviews ACTUALLY PUT TO THAT FLW.
# This is what replaced the flat 14-day silence rule: an FLW counts as dropped when one of their own
# scheduled interviews went past its deadline unfinished. Only triggered slots appear here, so an FLW
# who did everything that was sent to them is never blamed for interviews the bot never sent (the
# `not-triggered` distinction the 2026-08-07 audit introduced for the matrix).
_eng_deadlines = defaultdict(lambda: defaultdict(list))
# sg -> flw -> {(cohort, interview_n): (deadline, done, n)} - the collapsed form, flattened below
_eng_dl_by_key = defaultdict(lambda: defaultdict(dict))
_eng_flw_cad = {}  # flw -> a gap, first-wins; ALL view only
# Per-SUBGROUP cadence. The global map above is first-wins, so TRS (earliest, 1,298 FLWs) claimed most
# shared workers and PANEL's Active/Slow/Quiet bands were computed on a 7-day gap instead of its real 4
# for 99% of its FLWs. A subgroup's own series must use its own cadence.
_eng_sg_cad = defaultdict(dict)
_cohort_llo = getattr(bm, "cohort_llo", {})
for r in bm.rows:
    _llo = _cohort_llo.get(r["cohort_id"])
    if _llo and r["connect_id"] not in _eng_flw_llo:
        _eng_flw_llo[r["connect_id"]] = _llo
    _d = _sid2date.get(r.get("matched_session_id"))
    _rsg, _rflw = r["subgroup"], r["connect_id"]
    _rcad = bm.SUBGROUP_DESIGN[_rsg]["cadence"] if _rsg in bm.SUBGROUP_DESIGN else None
    # start_date, not training_date - the same shared source the matrix and drop-off view use, so the
    # engagement chart cannot judge a cohort against a different calendar than the other two views.
    _rtrain = bm.cohort_info.get(r["cohort_id"], {}).get("start_date")
    if _rcad:
        _eng_flw_cad.setdefault(_rflw, _rcad)  # first-wins, used ONLY by the pooled ALL view
        _eng_sg_cad[_rsg][_rflw] = _rcad  # per-subgroup: always that subgroup's own cadence
        if _rtrain and r.get("interview_n"):
            # Keyed by (cohort, interview) and collapsed, NOT appended. A duplicate bot trigger
            # produces two rows for one interview; appending both left a worker carrying an unfinished
            # tuple for an interview they had completed, so the engagement chart reported MORE
            # drop-outs than the drop-off view despite seeing fewer workers. Same collapse rule
            # _coh_slot uses: completed beats not-completed, earliest completion wins.
            _ek = (r["cohort_id"], int(r["interview_n"]))
            _edone = _d if r.get("is_completed") == "Y" else None
            _eprev = _eng_dl_by_key[_rsg][_rflw].get(_ek)
            if _eprev is None or (_edone is not None and (_eprev[1] is None or _edone < _eprev[1])):
                _eng_dl_by_key[_rsg][_rflw][_ek] = (
                    _slot_deadline(
                        int(r["interview_n"]), _rtrain, _rcad, r["cohort_id"], r.get("trigger_received_on")
                    ),
                    _edone,
                    int(r["interview_n"]),  # reading C needs the slot number: a gap BEFORE their last
                )  # completed interview is a skip, a gap after it is a stop
    if r.get("is_started") == "Y" and _d:
        _eng_flw_dates[r["subgroup"]][r["connect_id"]].add(_d)
    if r.get("is_completed") == "Y" and _d:
        _tc = r["topic_code"]
        _cur = _eng_comp_topic_dt[r["subgroup"]][r["connect_id"]].get(_tc)
        if _cur is None or _d < _cur:
            _eng_comp_topic_dt[r["subgroup"]][r["connect_id"]][_tc] = _d


def _eng_filter_llo(flw_dates, finished_dates, llo):
    """Restrict a subgroup's (flw_dates, finished_dates) to FLWs of one LLO."""
    fd = {f: d for f, d in flw_dates.items() if _eng_flw_llo.get(f) == llo}
    fn = {f: d for f, d in finished_dates.items() if _eng_flw_llo.get(f) == llo}
    return fd, fn


def _eng_finished_dates(sg, design_len):
    """{flw: date they completed all `design_len` interviews} — a "Finished" FLW's silence is not dropout."""
    out = {}
    if design_len <= 0:
        return out
    for _flw, _tdates in _eng_comp_topic_dt.get(sg, {}).items():
        if len(_tdates) >= design_len:
            out[_flw] = sorted(_tdates.values())[design_len - 1]  # date the Nth distinct topic was done
    return out


# Per-subgroup scheduled rollout-end (same signals as the dotted funnel line) so we can mark a cohort
# "ended" — a started FLW who never finished but whose cohort's window has closed isn't a live dropout.
# Flatten the collapsed map into the list shape the series builder expects.
for _fsg, _fm in _eng_dl_by_key.items():
    for _fflw, _fslots in _fm.items():
        _eng_deadlines[_fsg][_fflw] = list(_fslots.values())

_eng_end = {}
for _c, _ee in COHORT_END.items():  # the same map the funnel line and the drop-off view use
    _esg = bm.cohort_to_sg(_c)
    if _esg not in SG_PRESENT:
        continue
    if _esg not in _eng_end or _ee > _eng_end[_esg]:
        _eng_end[_esg] = _ee
for _esg, _eu in LINE_DOTTED_UNTIL.items():  # authoritative overrides win
    if _esg in _eng_end:
        _eng_end[_esg] = _eu


def _eng_maxgap(ds):
    return max((b - a).days for a, b in zip(ds, ds[1:])) if len(ds) > 1 else 0


def _eng_compute(flw_dates, finished_dates, gap_thresh, end_date, deadlines=None, cad_of=None, gap_of=None):
    """Per-week series for one subgroup (or None if no sessions).

    Adds a FINISHED bucket (completed all scheduled interviews) that outranks the silence buckets, so a
    completer's inactivity reads as "done", not "dropped" (Neal's cross-cohort fix). The grid ends at the
    last actual session date, so an ended cohort naturally freezes there rather than trailing to today.

    DROPPED is not a silence rule. It asks whether one of the FLW's own scheduled interviews went past
    its deadline unfinished (`deadlines`, see topic_status_lib.dropped_at). The old rule was a flat 14
    days for every cohort, which meant an ABT2-A worker waiting exactly on schedule (14-day gap) was
    called a drop-out while a TRE worker (3-day gap) got nearly five missed turns of slack. It also
    swept in FLWs who did everything that was ever sent to them, because the schedule stalled rather
    than the person.

    `cad_of` / `gap_of` map an FLW to their own cohort's gap and gap-threshold, so the ALL view stops
    applying one 8-day number to eleven differently-paced designs. `gap_thresh` remains the fallback.

    TWO INDEPENDENT READINGS, not one stack:

      OUTCOME  finished / dropped / waiting / in-progress - mutually exclusive, sums to 100.
      RHYTHM   steady / inconsistent - computed for EVERY starter with 2+ interviews, sums to 100.

    Rhythm used to be the residual of the outcome stack, which meant it only ever described FLWs who
    were in none of the other buckets. Once every cohort closed, that residual emptied and the KPI
    tiles showed 0% steady. Rhythm is not an outcome, it is a property of how someone worked, and a
    finisher has a rhythm just as much as a dropout does.

    Rhythm uses the largest gap BETWEEN interviews, not current silence. Silence keeps growing after
    someone stops, so a finisher would drift into "inconsistent" purely because the calendar moved.
    """
    all_dates = [d for ds in flw_dates.values() for d in ds]
    if not all_dates:
        return None
    first, last = min(all_dates), max(all_dates)
    Ws, w = [], first + timedelta(days=6)  # week-ending dates every 7 days from first session
    while w < last:
        Ws.append(w)
        w += timedelta(days=7)
    Ws.append(last)  # final point = data's last date (freezes ended cohorts)
    weeks, started_s = [], []
    steady_p, incons_p, drop_p, fin_p, wait_p, inprog_p = [], [], [], [], [], []
    new_s, active_s, slow_s, quiet_s, finst_s, wait_s, rbase_s = [], [], [], [], [], [], []
    steady_s, incons_s, drop_s, inprog_s = [], [], [], []
    dropC_s, waitC_s, dropA_s, waitA_s = [], [], [], []
    prevW = None
    for W in Ws:
        started = steady = incons = drop = new = active = slow = quiet = fin = wait = 0
        inprog = rbase = 0
        dropC = waitC = dropA = waitA = 0
        for _flw, ds in flw_dates.items():
            dsW = sorted(d for d in ds if d <= W)
            if not dsW:
                continue
            started += 1
            fd, ld = dsW[0], dsW[-1]
            sil = (W - ld).days
            mg = _eng_maxgap(dsW)
            _fdate = finished_dates.get(_flw)
            is_finished = _fdate is not None and _fdate <= W
            _gt = (gap_of or {}).get(_flw, gap_thresh)
            _cad = (cad_of or {}).get(_flw) or max(_gt // 2, 1)
            _dls = (deadlines or {}).get(_flw, ())
            _prog = tsl.progress_at(_dls, W, _fdate)
            # ---- OUTCOME: where they ended up. Mutually exclusive, and computed three ways so the
            # chart can be read under any of the three published definitions of "dropped off". Only
            # who counts as dropped moves; the four buckets still close to 100 in every reading.
            _progC = tsl.progress_at_reading(_dls, W, _fdate, "C")
            _progA = tsl.progress_at_reading(_dls, W, _fdate, "A", silence_days=(sil > 14))
            if is_finished:
                fin += 1  # FINISHED outranks the other outcomes
            elif _prog == "dropped":
                drop += 1  # let a sent interview go past its deadline
            elif _prog == "waiting":
                wait += 1  # did everything sent; schedule sent no more
            else:
                inprog += 1  # still has a live interview in hand
            if not is_finished:
                if _progC == "dropped":
                    dropC += 1
                elif _progC == "waiting":
                    waitC += 1
                if _progA == "dropped":
                    dropA += 1
                elif _progA == "waiting":
                    waitA += 1
            # ---- RHYTHM: how they worked. Independent of the outcome, so a finisher counts too.
            # Needs at least two interviews - one interview has no gap to judge.
            if len(dsW) >= 2:
                rbase += 1
                if mg > _gt:
                    incons += 1
                else:
                    steady += 1
            if not is_finished:  # FINISHED outranks new/active/slow/quiet too
                is_new = (fd > prevW) if prevW is not None else (fd >= Ws[0] - timedelta(days=6))
                # Bands are one gap / two gaps rather than a flat 7 and 14, so "active" means the same
                # thing (on pace) in a 3-day cohort and a 14-day one.
                if is_new:
                    new += 1  # then: new -> active -> slow -> quiet
                elif sil <= _cad:
                    active += 1
                elif sil <= 2 * _cad:
                    slow += 1
                else:
                    quiet += 1
        weeks.append(W.isoformat())
        started_s.append(started)
        # outcome shares are of everyone who started; rhythm shares are of those with 2+ interviews
        # the four OUTCOME shares must close to 100 - the legend says so
        _f4, _d4, _w4, _p4 = _pcts_to_100([fin, drop, wait, inprog], started)
        fin_p.append(_f4)
        drop_p.append(_d4)
        wait_p.append(_w4)
        inprog_p.append(_p4)
        _s2, _i2 = _pcts_to_100([steady, incons], rbase)
        steady_p.append(_s2)
        incons_p.append(_i2)
        new_s.append(new)
        active_s.append(active)
        slow_s.append(slow)
        quiet_s.append(quiet)
        finst_s.append(fin)
        wait_s.append(wait)
        rbase_s.append(rbase)
        steady_s.append(steady)
        incons_s.append(incons)
        drop_s.append(drop)
        inprog_s.append(inprog)
        dropC_s.append(dropC)
        waitC_s.append(waitC)
        dropA_s.append(dropA)
        waitA_s.append(waitA)
        prevW = W
    ended = end_date is not None and TODAY > end_date
    return {
        "weeks": weeks,
        "started": started_s,
        # OUTCOME percentages are NOT shipped. They are exactly finished/dropped/waiting/inprog
        # over `started`, and shipping both meant two sources of truth for one number and ~8 KB of
        # a 512 KB render spent restating counts we already send. The page derives all four with
        # the same largest-remainder rounding, for whichever reading is selected - which is also
        # the only way the other two readings could be offered without shipping eight more arrays.
        # rhythm: sums to 100 across starters with 2+ interviews (rhythm_base)
        "steady_pct": steady_p,
        "incons_pct": incons_p,
        "rhythm_base": rbase_s,
        "steady": steady_s,
        "incons": incons_s,
        "dropped": drop_s,
        "inprog": inprog_s,
        "finished": finst_s,
        "new": new_s,
        "active": active_s,
        "slow": slow_s,
        "quiet": quiet_s,
        "waiting": wait_s,
        # the other two readings, as COUNTS - the render divides by `started` and takes
        # in-progress as the residual, so nothing has to be kept in sync in two places
        "dropC": dropC_s,
        "waitC": waitC_s,
        "dropA": dropA_s,
        "waitA": waitA_s,
        "gap_thresh": gap_thresh,
        "total_started": started_s[-1],
        "ended": ended,
        "end_date": end_date.isoformat() if end_date else None,
    }


cohort_engagement = {}
cohort_engagement_llo = {}  # {sg: {"COWACDI": {...}, "EHA": {...}}} — same series, split by partner
for _sg in SG_PRESENT:
    _dlen = len(bm.SUBGROUP_DESIGN[_sg]["topics"])
    _gt, _end = 2 * bm.SUBGROUP_DESIGN[_sg]["cadence"], _eng_end.get(_sg)
    _fd, _fn = _eng_flw_dates.get(_sg, {}), _eng_finished_dates(_sg, _dlen)
    _dl = _eng_deadlines.get(_sg, {})
    _ce = _eng_compute(_fd, _fn, _gt, _end, _dl, _eng_sg_cad.get(_sg, {}))
    if _ce:
        cohort_engagement[_sg] = _ce
    _llo_out = {}
    for _llo in ("COWACDI", "EHA"):
        _fdl, _fnl = _eng_filter_llo(_fd, _fn, _llo)
        _cl = _eng_compute(_fdl, _fnl, _gt, _end, _dl, _eng_sg_cad.get(_sg, {}))
        if _cl:
            _llo_out[_llo] = _cl
    if _llo_out:
        cohort_engagement_llo[_sg] = _llo_out
# "ALL" = program-wide: every started FLW (distinct), each FLW's dates = the UNION of their real-topic
# session dates across all subgroups. Each FLW's "finished" uses their OWN subgroup's schedule length.
# Cadences are mixed, so each FLW is judged against their OWN cohort's gap (_eng_flw_gap) rather than
# the single 8-day number this used to apply to all eleven designs — 8 days was 2x the modal 4-day
# cadence and therefore right for PANEL and wrong for the other ten.
_eng_all_dates = defaultdict(set)
_eng_all_finished = {}
_eng_all_deadlines = defaultdict(list)
for _sg_d in SG_PRESENT:
    _fd = _eng_finished_dates(_sg_d, len(bm.SUBGROUP_DESIGN[_sg_d]["topics"]))
    for _flw, _ds in _eng_flw_dates.get(_sg_d, {}).items():
        _eng_all_dates[_flw] |= _ds
    for _flw, _dls in _eng_deadlines.get(_sg_d, {}).items():
        _eng_all_deadlines[_flw].extend(_dls)
    for _flw, _dt in _fd.items():
        if _flw not in _eng_all_finished or _dt < _eng_all_finished[_flw]:
            _eng_all_finished[_flw] = _dt
_eng_flw_gap = {_f: 2 * _c for _f, _c in _eng_flw_cad.items()}
_ce_all = _eng_compute(_eng_all_dates, _eng_all_finished, 8, None, _eng_all_deadlines, _eng_flw_cad, _eng_flw_gap)


def _pool_rhythm(target, parts):
    """Rebuild a pooled series' RHYTHM from its parts instead of recomputing it on unioned dates.

    ALL gives each FLW the union of their session dates across every subgroup. That is right for the
    outcome (did this person finish anything, did they let a deadline pass) but wrong for rhythm: an FLW
    who ran TRS in April and EXT in August has a four-month hole in the union, so they scored
    "inconsistent" despite having kept perfect pace inside each cohort. It also picked their cadence by
    whichever subgroup happened to appear first in the master rows, which is arbitrary for anyone in
    more than one. The result was ALL reading 19% steady while every individual design read 56-92% - a
    flat contradiction between a view and its own parts.

    A gap BETWEEN two cohorts is not an interrupted rhythm, it is two separate engagements. So pool the
    per-subgroup classifications: for each of ALL's weeks, take each subgroup's most recent week at or
    before it and add up the counts. ALL then cannot disagree with its parts by construction.
    """
    weeks = target["weeks"]
    st, ic, rb = [0] * len(weeks), [0] * len(weeks), [0] * len(weeks)
    for part in parts:
        pw = part["weeks"]
        j = 0
        for i, w in enumerate(weeks):
            while j + 1 < len(pw) and pw[j + 1] <= w:
                j += 1
            if pw[j] <= w:
                st[i] += part["steady"][j]
                ic[i] += part["incons"][j]
                rb[i] += part["rhythm_base"][j]
    target["steady"], target["incons"], target["rhythm_base"] = st, ic, rb
    _sp, _ip = [], []
    for a, b, base in zip(st, ic, rb):
        _x, _y = _pcts_to_100([a, b], base)
        _sp.append(_x)
        _ip.append(_y)
    target["steady_pct"], target["incons_pct"] = _sp, _ip
    # A pooled base counts FLW-per-cohort enrolments, not unique FLWs, so it can legitimately exceed
    # this series' started count (an FLW in two cohorts has two rhythms). Flagged so the gates and the
    # render label it honestly instead of implying it is a share of people.
    target["rhythm_pooled"] = True
    return target


def _pool_outcome(target, parts):
    """Rebuild a pooled series' OUTCOME from its parts, for the same reason the rhythm is pooled.

    ALL marked a worker "finished" if they finished ANY ONE of their cohorts (the min finish date across
    subgroups), which is a materially more generous question than the one the label asks. Pooling the
    per-design counts answers the design-level question at program scale instead, and makes ALL
    arithmetically incapable of disagreeing with the rows beneath it.

    The base becomes ENROLMENTS (a worker in three cohorts contributes three), which is why
    `outcome_base` ships alongside and the render labels it rather than implying a headcount.
    """
    weeks = target["weeks"]
    n = len(weeks)
    acc = {k: [0] * n for k in ("started", "finished", "dropped", "waiting", "inprog")}
    for part in parts:
        pw = part["weeks"]
        j = 0
        for i, w in enumerate(weeks):
            while j + 1 < len(pw) and pw[j + 1] <= w:
                j += 1
            if pw[j] <= w:
                acc["started"][i] += part["started"][j]
                acc["finished"][i] += part["finished"][j]
                acc["dropped"][i] += part["dropped"][j]
                acc["waiting"][i] += part["waiting"][j]
                acc["inprog"][i] += part["inprog"][j]
    # ADDITIVE, deliberately. Overwriting finished_pct/finished would break Panel 3's identity
    # (finished + new + active + slow + quiet == started, which is person-level here) and would turn
    # the long-scrutinised "1,441 unique FLWs" headline into an enrolment count. Both readings now ship
    # side by side and the page states which is which:
    #   finished_pct  = person-level, "finished AT LEAST ONE of their schedules"
    #   enrol_*       = enrolment-level, the same question the per-design rows and the drop-off view ask
    target["enrol_base"] = acc["started"]
    _keys = ("enrol_finished_pct", "enrol_drop_pct", "enrol_waiting_pct", "enrol_inprog_pct")
    _srcs = ("finished", "dropped", "waiting", "inprog")
    for k in _keys:
        target[k] = []
    for i in range(n):
        _vals = _pcts_to_100([acc[sr][i] for sr in _srcs], acc["started"][i])
        for k, v in zip(_keys, _vals):
            target[k].append(v)
    target["enrol_finished"] = acc["finished"]
    target["outcome_pooled"] = True
    return target


if _ce_all:
    _all_parts = [cohort_engagement[_s] for _s in SG_PRESENT if _s in cohort_engagement]
    _ce_all = _pool_rhythm(_ce_all, _all_parts)
    _ce_all = _pool_outcome(_ce_all, _all_parts)
    cohort_engagement["ALL"] = _ce_all
    _all_llo = {}
    for _llo in ("COWACDI", "EHA"):
        _fdl, _fnl = _eng_filter_llo(_eng_all_dates, _eng_all_finished, _llo)
        _cl = _eng_compute(_fdl, _fnl, 8, None, _eng_all_deadlines, _eng_flw_cad, _eng_flw_gap)
        if _cl:
            _llo_parts = [
                cohort_engagement_llo[_s][_llo] for _s in SG_PRESENT if _llo in cohort_engagement_llo.get(_s, {})
            ]
            _all_llo[_llo] = _pool_outcome(_pool_rhythm(_cl, _llo_parts), _llo_parts)
    if _all_llo:
        cohort_engagement_llo["ALL"] = _all_llo
print(
    f"[eng] cohort_engagement: "
    f"{[(sg, cohort_engagement[sg]['total_started'], cohort_engagement[sg]['finished'][-1]) for sg in cohort_engagement]}"
)
print(f"[eng] by-LLO splits for: {sorted(cohort_engagement_llo)}")

# ---- per-COHORT drop-off, each scored at its OWN end date (Ali's task 2) --------------------------
# The weekly series above pools a whole design, and its "ended" flag uses the LATEST cohort in that
# design. That scores a TRS cohort which closed on 15 April against the same calendar as one that
# closed on 22 May, 37 days later. Here every cohort gets its own end date and is measured there, so
# the numbers are comparable across designs and across start dates.
# (cohort, flw, interview_n) -> (deadline, done_or_None, interview_n). The third element is what lets
# the SHARED reading function tell a skip from a stop; without it, progress_at_reading silently falls
# back to reading B, which is exactly how the two views drifted apart.
_coh_slot = {}
_coh_done = defaultdict(lambda: defaultdict(dict))  # cohort -> flw -> {topic: completed date}
_coh_dates = defaultdict(lambda: defaultdict(set))  # cohort -> flw -> {session dates}
for r in bm.rows:
    _c, _f, _sg = r["cohort_id"], r["connect_id"], r["subgroup"]
    if _sg not in bm.SUBGROUP_DESIGN or not r.get("interview_n"):
        continue
    _cad = bm.SUBGROUP_DESIGN[_sg]["cadence"]
    _tr = bm.cohort_info.get(_c, {}).get("start_date")
    _d = _sid2date.get(r.get("matched_session_id"))
    if _tr and _cad:
        _k = (_c, _f, int(r["interview_n"]))
        _done = _d if r.get("is_completed") == "Y" else None
        _prev = _coh_slot.get(_k)
        # Completed beats not-completed; between two completed rows keep the earlier date.
        if _prev is None or (_done is not None and (_prev[1] is None or _done < _prev[1])):
            _coh_slot[_k] = (
                _slot_deadline(int(r["interview_n"]), _tr, _cad, _c, r.get("trigger_received_on")),
                _done,
                int(r["interview_n"]),
            )
    if r.get("is_completed") == "Y" and _d:
        _coh_done[_c][_f][r["topic_code"]] = _d
    if r.get("is_started") == "Y" and _d:
        _coh_dates[_c][_f].add(_d)  # for option A, which is a pure silence rule

_coh_dl = defaultdict(lambda: defaultdict(list))
_coh_seq = defaultdict(lambda: defaultdict(list))  # cohort -> flw -> [(interview_n, completed?)]
for (_c, _f, _n), _v in _coh_slot.items():
    _coh_dl[_c][_f].append(_v)
    _coh_seq[_c][_f].append((_n, _v[1] is not None))

# Same universe as the FLW x Topic matrix (claimed OR holding a master row) - see DEFECT 2. Counting a
# different population here than the matrix counts would make the two views disagree on the size of the
# cohort, which is worse than either number being slightly off.
_coh_interviewed = tsl.interviewed_index(bm.rows)
_coh_seen = {}
for _c in bm.cohort_info:
    _coh_seen[_c] = set(tsl.universe_for(_c, bm.cohort_flws, bm.cohort_flw_meta, _coh_interviewed))

# The date option A is evaluated at, per cohort: its own last observed session. The old rule's weekly
# grid ended there, so evaluating at TODAY instead would mark every worker in a long-closed cohort as
# silent and report ~90% rather than the number people remember.
_cohort_last_session = {}
for _c2, _fm in _coh_dates.items():
    _all = [d for ds in _fm.values() for d in ds]
    if _all:
        _cohort_last_session[_c2] = max(_all)

cohort_dropoff = []
for _c, _inf in sorted(bm.cohort_info.items()):
    _sg = _inf["subgroup"]
    if _sg not in bm.SUBGROUP_DESIGN:
        continue
    _tops = bm.SUBGROUP_DESIGN[_sg]["topics"]
    _cad = bm.SUBGROUP_DESIGN[_sg]["cadence"]
    _inf_c = bm.cohort_info.get(_c, {})
    _tr, _tr_src = _inf_c.get("start_date"), _inf_c.get("start_src")
    if not _tr or not _cad:
        continue  # no start date at all: cannot say when it ended
    _end = COHORT_END.get(_c)  # the one shared map, not a second computation
    if _end is None:
        continue
    _asof = min(_end, TODAY)  # a cohort still running is scored as it stands
    _closed = _end <= TODAY
    # The date the three readings are evaluated at. NOT today: a slot sent after the cohort closed can
    # have a deadline in the future, so scoring at today would make an ended cohort accumulate
    # drop-outs as the calendar advances. Anchored to the cohort's own last activity, it tracks a
    # cohort that is genuinely still going and freezes the moment it stops. Same anchor reading A uses.
    # Scored at TODAY, deliberately. A deadline that has passed is real information, and anchoring
    # earlier invented "still in progress" workers in cohorts that finished in May - their interview
    # was triggered after the cohort went quiet and never touched, which is abandonment, not progress.
    # At TODAY both cases come out right: that May slot is overdue, while a PANEL slot due on the 29th
    # is genuinely still in hand.
    #
    # This does mean a cohort's numbers can move as a future deadline arrives. That is a deadline
    # passing, not silence accumulating, and gate G in audit_e2e distinguishes the two: it requires
    # invariance only of cohorts where EVERY deadline has already passed.
    _asof_read = TODAY
    _tally = defaultdict(int)
    # Slot-level companion to the worker-level headline. "46% of workers dropped off" and "92% of every
    # interview we sent got completed" are both true of PANEL, and quoting only the first reads as a
    # collapse when the reality is a lot of near-finishers hitting one wall.
    _sent = _cdone = 0
    for _f2, _lst in _coh_dl.get(_c, {}).items():
        _sent += len(_lst)
        _cdone += sum(1 for _t in _lst if _t[1] is not None)
    for _f in sorted(_coh_seen.get(_c, ())):
        _dts = _coh_done.get(_c, {}).get(_f, {})
        _fdate = sorted(_dts.values())[len(_tops) - 1] if len(_dts) >= len(_tops) else None
        _dl = _coh_dl.get(_c, {}).get(_f, ())
        if not _dl:
            _tally["never-began"] += 1  # claimed, but the bot never sent them anything
            continue

        # ---- the three readings, from the ONE shared definition. This used to be an inline copy that
        # omitted the deadline test, so a worker whose interview was sent three days ago and is not yet
        # due read as "stopped and never came back". Same function the engagement chart calls, same
        # 3-tuple input, so the two views cannot drift apart again.
        _finished_all = _fdate is not None
        if not _finished_all:
            _b = tsl.progress_at_reading(_dl, _asof_read, _fdate, "B")
            if _b == "dropped":
                _tally["B"] += 1
                _c_state = tsl.progress_at_reading(_dl, _asof_read, _fdate, "C")
                if _c_state == "dropped":
                    # ...unless the cohort is still running, in which case the tail may yet be done
                    if _closed:
                        _tally["C"] += 1
                    else:
                        _tally["C_open"] += 1
                else:
                    _tally["skipped"] += 1  # skipped one, came back
        # A: not finished, and silent for more than 14 days at this cohort's SCORING DATE.
        #
        # That date used to be the cohort's own last observed SESSION, which is not a date at all - it
        # is wherever the last straggler happened to log in. One worker finishing a long-overdue
        # interview dragged the endpoint forward and pushed everyone else in the cohort over the line,
        # while rescuing themselves. Two cohorts that behaved identically scored differently depending
        # on whether anyone trickled in afterwards, so cohorts were not comparable with each other.
        #
        # It is now a fixed calendar date: the cohort's own close plus one 14-day silence window,
        # capped at today so a cohort that has not yet reached that point is scored where it actually
        # is. Every cohort is judged at the same point in its OWN life, which is what the engagement
        # chart already does by measuring to the week on its axis. Measured on the live build: the
        # programme total moves 804 -> 687, and it redistributes (PANEL down, TRS up) because cohorts
        # that limped on were over-counted and cohorts that went quiet early were under-counted.
        _ds = _coh_dates.get(_c, {}).get(_f)
        _a_asof = min(_end + timedelta(days=14), TODAY)
        if _ds and _a_asof and not _finished_all:
            if (_a_asof - max(_ds)).days > 14:
                _tally["A"] += 1
                # Split the silence count by whether anything was actually OUTSTANDING for them.
                # Reading A does not ask, so 38% of the people it calls dropped had completed every
                # interview they were sent and were simply never sent the rest. That is the deliberate
                # choice (a worker we stopped sending to still counts as not retained), but describing
                # them as having dropped out, with nothing beside it, is not what happened to them.
                if any(_t[1] is None for _t in _dl):
                    _tally["A_out"] += 1     # left something we sent unanswered
                else:
                    _tally["A_clean"] += 1   # answered everything we sent; the schedule stopped
        # Someone who completed their whole design AFTER the window shut is not a drop-out - they
        # finished, late. Measuring strictly at the window end swept 140 such workers into "dropped",
        # which is what made completed look too low and dropped too high against every other view.
        if _fdate is not None and _fdate > _asof:
            _tally["completed-late"] += 1
            continue
        # Judge DROPPED on permanence, not on a snapshot date: did they leave an interview they were
        # sent permanently undone? Evaluating at the window end instead called 34 workers dropped who
        # did complete the interview, just after the window shut - and made this view disagree with the
        # FLW x Topic matrix, which reads the same slot as completed. The window end still decides
        # whether a COMPLETION was on time or late (above); it should not decide whether something
        # eventually happened at all.
        # Same anchor and same rule as the three readings above, so `d` and `dB` cannot disagree - the
        # render derives "still in progress" from `d` while displaying `dB`, so a gap between them
        # makes the row incoherent.
        #
        # The old code converted in-progress to dropped once the cohort's end date had passed, on the
        # premise that a future deadline meant the interview was sent after the window shut. That
        # premise is wrong whenever a cohort is past its nominal end but still triggering interviews,
        # which is the normal state here: it is what made PANEL workers who had started an interview
        # the previous day read as "stopped and never came back".
        _st = tsl.progress_at(_dl, _asof_read, _fdate)
        _tally[_st] += 1
    # The PARTITION keys only. dA/dB/dC/skipped/C_open are alternative READINGS of the same workers,
    # not extra people - summing them would count someone up to three times.
    _PART = ("finished", "completed-late", "dropped", "waiting", "never-began", "in-progress")
    _n = sum(_tally[k] for k in _PART)
    if not _n:
        continue
    # Compact on purpose: 72 rows x verbose keys came to 18.7 KB against 34 KB of render headroom.
    # Only what cannot be derived downstream is shipped. The render recovers subgroup from cohortSG,
    # interviews/gap from subgroupDesign, percentages and in-progress from the counts, and "closed"
    # from `e` against today. `g` appears only when a cohort's grace differs from its gap, and `x`
    # only when the start date came from the trigger fallback rather than a Connect invitation.
    # f = completed by the window end, l = completed after it, d = dropped, w = schedule never
    # fully sent, z = nothing ever sent. Exhaustive, so f+l+d+w+z+in-progress == n.
    # dA / dB / dC = the three readings. sk = skipped one and came back (B minus C). The render
    # switches which of the three it calls "Dropped off"; everything else is shared.
    # nb = the workers the bot actually ASKED (n minus never-began). Every rate except "never began"
    # is divided by this: someone who was never sent an interview cannot have stopped, so leaving them
    # in the denominator only deflates the rate against a population that can never be in the numerator.
    _all_due = all(_t[0] <= TODAY for _fl in _coh_dl.get(_c, {}).values() for _t in _fl)
    _row = {
        "c": _c,
        "s": _tr.isoformat(),
        "e": _end.isoformat(),
        "n": _n,
        "nb": _n - _tally["never-began"],
        # every deadline in this cohort has already passed -> nothing here can change again
        "settled": bool(_all_due),
        "f": _tally["finished"],
        "l": _tally["completed-late"],
        "d": _tally["dropped"],
        "dA": _tally["A"],
        "dAo": _tally["A_out"],
        "dAc": _tally["A_clean"],
        "dB": _tally["B"],
        "dC": _tally["C"],
        "sk": _tally["skipped"],
        "w": _tally["waiting"],
        "z": _tally["never-began"],
        # p = still in progress. Shipped explicitly so f+l+d+w+z+p == n for EVERY cohort; leaving
        # it as an implied residual meant three cohorts had 7 workers in no bucket at all.
        "p": _tally["in-progress"],
        "ts": _sent,
        "tc": _cdone,
    }
    if tsl.GRACE_DAYS.get(_c, _cad) != _cad:
        _row["g"] = GRACE_DAYS[_c]
    if _tr_src != "invitation":
        _row["x"] = 1
    cohort_dropoff.append(_row)
_cd_tot = sum(c["n"] for c in cohort_dropoff)
_cd_f, _cd_l, _cd_d, _cd_w, _cd_z = (sum(c[k] for c in cohort_dropoff) for k in ("f", "l", "d", "w", "z"))
_cd_A, _cd_B, _cd_C, _cd_sk = (sum(c[k] for c in cohort_dropoff) for k in ("dA", "dB", "dC", "sk"))
print(
    f"[eng] dropped, three readings: A(silent 14d)={_cd_A}  B(missed any)={_cd_B}  "
    f"C(stopped, never returned)={_cd_C}  skipped-but-returned={_cd_sk}"
)
print(
    f"[eng] cohort_dropoff: {len(cohort_dropoff)} cohorts, {_cd_tot} FLW-cohort pairs, "
    f"on-time={_cd_f} late={_cd_l} dropped={_cd_d} schedule-not-completed={_cd_w} "
    f"never-began={_cd_z} in_progress={_cd_tot - _cd_f - _cd_l - _cd_d - _cd_w - _cd_z} "
    f"(fallback start dates: {sum(1 for c in cohort_dropoff if c.get('x'))})"
)

# ---- OCS review status of every COMPLETED interview ------------------------------------------
# The recurring "OCS shows 8,6xx, Labs shows 9,4xx" question has one cause: the OCS screen filters to
# sessions a reviewer has TAGGED, and a tenth of completed interviews have not been reviewed yet. So
# the not-reviewed bucket is a first-class value here, never a blank and never filtered away by
# default - hiding it is the very thing that created the confusion.
#
# Counted over COMPLETED interviews only. A review verdict on an interview nobody finished would not
# mean anything, and mixing the two bases is how the two systems stopped agreeing in the first place.
_REVIEW_KEYS = ("acceptable", "unacceptable", "suspected_ai", "not-reviewed")
# Verdict priority when ONE interview has more than one session. A duplicate bot trigger produces two
# master rows for the same (FLW, cohort, interview), each with its own OCS session and therefore
# possibly its own verdict - live examples include one row not-reviewed beside its twin acceptable, and
# one acceptable beside its twin suspected_ai. Strongest signal wins, and anything a person actually
# looked at outranks something nobody has. Same order _review_status uses inside a single session.
_REVIEW_RANK = {"suspected_ai": 0, "unacceptable": 1, "acceptable": 2, "not-reviewed": 3}
_rev_cell = {}
for _r in bm.rows:
    if _r.get("is_completed") != "Y":
        continue
    _st = _r.get("review_status") or "not-reviewed"
    if _st not in _REVIEW_KEYS:
        _st = "not-reviewed"
    # Keyed on the INTERVIEW, not the row, so this ties to the Overview's completed count exactly.
    _key = (_r["connect_id"], _r["cohort_id"], _r["interview_n"])
    _prev = _rev_cell.get(_key)
    if _prev is None or _REVIEW_RANK[_st] < _REVIEW_RANK[_prev[0]]:
        _rev_cell[_key] = (_st, _r["subgroup"], _r["topic_code"])

_rev_overall = defaultdict(int)
_rev_sg = defaultdict(lambda: defaultdict(int))
_rev_topic = defaultdict(lambda: defaultdict(int))
for _st, _sg, _tc in _rev_cell.values():
    _rev_overall[_st] += 1
    _rev_sg[_sg][_st] += 1
    _rev_topic[_tc][_st] += 1
review_status = {
    "keys": list(_REVIEW_KEYS),
    "overall": {k: _rev_overall[k] for k in _REVIEW_KEYS},
    "by_sg": {sg: {k: v[k] for k in _REVIEW_KEYS} for sg, v in sorted(_rev_sg.items())},
    "by_topic": {tc: {k: v[k] for k in _REVIEW_KEYS} for tc, v in sorted(_rev_topic.items())},
}
_rev_tot = sum(_rev_overall[k] for k in _REVIEW_KEYS)
print(
    f"[rev] OCS review status over {_rev_tot} completed interviews "
    f"(unique FLW x cohort x interview, deduped from {sum(1 for r in bm.rows if r.get('is_completed') == 'Y')} rows): "
    + "  ".join(f"{k}={_rev_overall[k]}" for k in _REVIEW_KEYS)
)

# ---------------------------------------------------------------- OCS session census (Leah, 25 Aug)
# The block above answers "of the interviews we COMPLETED, what verdict did each get". It cannot show
# incomplete sessions at all, because an interview that never finished has no completed row - which is
# why the dashboard read 918 while OCS showed ~12,000 not-applicable.
#
# This one answers the question OCS's own screen answers: of every session an enrolled FLW ever had
# with the bot, how did the evaluator judge it. Four mutually exclusive buckets over SESSIONS, so
# incomplete work is visible and the numbers can be checked against OCS directly.
#
# The categories are the evaluator's own tags. Two things that are easy to get wrong:
#   * `suspected_ai` is NOT a clean subset of `unacceptable`. Leah's rule is that 1-3 AI-looking
#     answers are flagged but NOT penalised, and only 4+ fail the session. So 11 ACCEPTABLE sessions
#     carry the AI flag. Counting the union as "unacceptable" would drag those into the wrong bucket.
#     Unacceptable is the `unacceptable` tag alone; the AI figure is reported as a subset of it.
#   * a session with no tag at all is not "acceptable by default" - the evaluator has not reached it.
#     Only sessions at OCS status Waiting Final Review or Complete are evaluated.
_sr_flw = set()
for _c, _fs in bm.cohort_flws.items():
    _sr_flw |= set(_fs)
for _r in bm.rows:
    _sr_flw.add(_r["connect_id"])

_sr = {"acceptable": 0, "unacceptable": 0, "no-verdict": 0, "not-applicable": 0}
_sr_ai_in_unacc = _sr_ai_total = _sr_ai_in_acc = 0
_sr_all = _sr_enrolled = 0
_sr_ocs = {"acceptable": 0, "unacceptable": 0, "no-verdict": 0, "not-applicable": 0}
for _s in bm.sessions:
    _sid = _s.get("id") or _s.get("sid")
    _p = _s.get("participant") if isinstance(_s.get("participant"), dict) else {}
    _pid = _p.get("identifier") if _p else _s.get("pid")
    _ts = set(bm._ocs_tags.get(_sid) or ())
    if "acceptable" in _ts:
        _b = "acceptable"
    elif "unacceptable" in _ts:
        _b = "unacceptable"
    elif "n/a" in _ts:
        _b = "not-applicable"
    else:
        _b = "no-verdict"
    _sr_all += 1
    _sr_ocs[_b] += 1
    if _pid not in _sr_flw:
        continue                       # staff, test accounts and participants outside the programme
    _sr_enrolled += 1
    _sr[_b] += 1
    if "suspected_ai" in _ts:
        _sr_ai_total += 1
        if _b == "unacceptable":
            _sr_ai_in_unacc += 1
        elif _b == "acceptable":
            _sr_ai_in_acc += 1

session_review = {
    "order": ["acceptable", "unacceptable", "no-verdict", "not-applicable"],
    "counts": _sr,
    "sessions": _sr_enrolled,
    "ai_in_unacceptable": _sr_ai_in_unacc,   # the subset shown when Unacceptable is expanded
    "ai_total": _sr_ai_total,
    "ai_in_acceptable": _sr_ai_in_acc,       # flagged but under the 4-answer penalty threshold
    # what the same filters give on OCS's own screen, so the difference is a printed line, not a mystery
    "ocs_counts": _sr_ocs,
    "ocs_sessions": _sr_all,
}
print(
    f"[rev] OCS session census over {_sr_enrolled} enrolled-FLW sessions "
    f"(of {_sr_all} on OCS): " + "  ".join(f"{k}={_sr[k]}" for k in session_review["order"])
    + f"  | AI-flagged {_sr_ai_total} ({_sr_ai_in_unacc} inside unacceptable, {_sr_ai_in_acc} inside acceptable)"
)

payload = {
    "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),  # stamped at build; render shows this
    "today": str(TODAY),
    "review_status": review_status,
    "session_review": session_review,
    "counts": {
        "cohorts": len(bm.cohort_info),
        "flws": len({c["flw"] for c in cells}),
        "master_rows": len(bm.rows),
        # matrix universe = claimed ∪ interviewed (topic_status_lib.universe_for). Kept under the old
        # key name so downstream consumers don't break; it is the flwMatrix row count either way.
        "claimed_pairs": sum(
            len(tsl.universe_for(cohort, bm.cohort_flws, bm.cohort_flw_meta, _interviewed))
            for cohort in bm.cohort_info
        ),
    },
    "funnel": funnel,
    "line_pct_started": line,
    "line_days": line_days,  # median days from when FLW DID interview-1 to interview-N (session start)
    "line_pct_started_di": line_di,  # de-impacted %started series (item 8)
    "line_pct_started_prev": line_prev,  # %started vs FLWs who started the PREVIOUS interview (reached-prev denom)
    "line_status": line_status,  # per-point release status (not-available/in-progress/settled)
    "line_active": line_active,  # per-subgroup: still actively triggering -> dotted funnel line
    "deimpact": deimpact,  # {sg: {last_n, count}} penult/last artifact summary
    "cohort_dropoff": cohort_dropoff,  # per-cohort outcome scored at that cohort's OWN end date
    "table1": t1,
    "table2": t2,
    "table3": t3,
    "topic_status": topic_status_out,
    "topic_status_cohort": topic_status_cohort_out,
    "dropoff": dropoff,
    "connect_pending_subgroups": connect_pending_sgs,
    "cohort_engagement": cohort_engagement,
    "cohort_engagement_llo": cohort_engagement_llo,
    "states": STATES,
    "topics": APPLICABLE,
    "sg_order": SG_PRESENT,
    "unmapped_cohorts": sorted(bm.unmapped_cohorts),
    # Withdrawn on purpose. Shipped separately so the page can say so instead of implying an oversight.
    "retired_cohorts": sorted(getattr(bm, "retired_seen", set())),
}
out = json.dumps(payload, separators=(",", ":"))
open("payload_agg.json", "w", encoding="utf-8").write(out)
print(f"payload_agg.json: {len(out.encode())/1024:.1f} KB")
print(f"  counts: {payload['counts']}")
print(f"  funnel rows: {len(funnel)}, table2 rows: {len(t2)}, topic_status rows: {len(topic_status_out)}")
print(f"  sample funnel[0]: {funnel[0]}")
print(f"  sample topic_status[0]: {topic_status_out[0]}")
