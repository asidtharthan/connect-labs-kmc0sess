"""Build the AGGREGATES payload (tiny, render-ready) from the validated master + status.
Funnel + Tables 1-3 + topic/subgroup status distributions + %Started line series.
No per-row data (those need the server-side phase). Emits payload_agg.json + size.
"""
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import build_master_4src as bm

TODAY = date.today()  # drives status time-gating; dynamic so the daily job gates against the real date
# Canonical topic order; include every topic ANY subgroup design uses (auto-picks up 12/13/C from the
# CCHQ-derived schedule) so topic-completion never silently drops a topic the bot actually runs.
_CANON_TOPICS = ["A", "B", "C", "D", "E", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "8S", "8L", "10S", "10L", "11S", "11L", "13L", "99", "F", "G"]
TOPICS = [t for t in _CANON_TOPICS if any(t in bm.SUBGROUP_DESIGN[sg]["topics"] for sg in bm.SUBGROUP_DESIGN)]
SG_ORDER = ["TRS", "TRE", "ABT1-A", "ABT1-B", "ABT2-A", "ABT2-B", "PANEL", "ABT3-A", "ABT3-B", "2WT", "EXT"]
ROLL = {"TRS": "TRS", "TRE": "TRE", "ABT1-A": "ABT1", "ABT1-B": "ABT1", "ABT2-A": "ABT2", "ABT2-B": "ABT2",
        "PANEL": "PANEL", "ABT3-A": "ABT3", "ABT3-B": "ABT3", "2WT": "2WT", "EXT": "EXT"}

# ---- cells: unique (flw,cohort,interview_n) ----
cell = {}
for r in bm.rows:
    k = (r["connect_id"], r["cohort_id"], int(r["interview_n"]))
    c = cell.setdefault(
        k,
        {"sg": r["subgroup"], "n": int(r["interview_n"]), "flw": r["connect_id"],
         "t": False, "s": False, "c": False, "hw": 0, "hm": 0},
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
deimpact = {}   # sg -> {"last_n": int, "count": int}
for sg in SG_PRESENT:
    topics = bm.SUBGROUP_DESIGN[sg]["topics"]
    if len(topics) < 3:   # 2-interview subgroups: normal-cadence non-sequential takers, not artifacts
        continue
    last_n, pen_n = len(topics), len(topics) - 1
    last_top, pen_top = topics[-1], topics[-2]
    started_last, started_pen = fset[(sg, last_n)]["s"], fset[(sg, pen_n)]["s"]
    did_last_only = started_last - started_pen
    if not did_last_only:
        continue
    gaps = []
    for flw in (started_last | started_pen):
        pt = bm.triggers_by_flw_iv.get((flw, pen_top))
        lt = bm.triggers_by_flw_iv.get((flw, last_top))
        if pt and lt:
            gaps.append(abs((lt[0]["received_on"] - pt[0]["received_on"]).total_seconds()) / 86400.0)
    med = _median(gaps)
    if med is not None and med < DEIMPACT_GAP_DAYS:
        deimpact[sg] = {"last_n": last_n, "count": len(did_last_only)}
print(f"[8] de-impact (penult/last artifact): {sum(d['count'] for d in deimpact.values())} FLWs across {sorted(deimpact)}")

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
line_status = {}
line_days = {}   # per-subgroup: median days from the FLW's interview-1 trigger to interview-N trigger
for sg in SG_PRESENT:
    elig = len(elig_sg[sg]) or 1
    di = deimpact.get(sg)
    topic1 = bm.SUBGROUP_DESIGN[sg]["topics"][0]
    series = []
    series_di = []
    statuses = []
    days_series = []
    for i, tc in enumerate(bm.SUBGROUP_DESIGN[sg]["topics"]):
        n = i + 1
        f = fset[(sg, n)]
        t, s, cc = len(f["t"]), len(f["s"]), len(f["c"])
        s_di = s - di["count"] if (di and n == di["last_n"]) else s
        st = _release_status(sg, n)
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
                "pct_trig": round(100 * t / elig, 1),
                "pct_started": round(100 * s / elig, 1),
                "pct_completed": round(100 * cc / s, 1) if s else None,
                # completion as a share of the INITIATED base (retention), not of this interview's
                # starters — for the "pay per interview" / full retention table (Screenshot 104).
                "pct_completed_base": round(100 * cc / elig, 1),
                # de-impacted started (penult/last artifact removed from the LAST interview only)
                "started_di": s_di,
                "pct_started_di": round(100 * s_di / elig, 1),
                # release status (not-available / in-progress / settled) for funnel display
                "status": st,
            }
        )
        series.append(round(100 * s / elig, 1))
        series_di.append(round(100 * s_di / elig, 1))
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
        days_series.append(round(med_days, 1) if med_days is not None else None)
    line[sg] = series
    line_di[sg] = series_di
    line_status[sg] = statuses
    line_days[sg] = days_series

# ---- per-subgroup "still rolling out" flag (drives the dotted funnel line) ----
# A subgroup's funnel line is DOTTED (still collecting) through its explicit rollout cutoff, and SOLID
# the day after. These dates come from the program schedule (authoritative), NOT a derived heuristic:
# the old design-span guess (today - first_trigger <= num_interviews x cadence) mis-timed the switch
# because late/early triggers and re-draw cohorts skew the start, so a line would settle while
# interviews were still firing (or vice-versa). Interviews for every subgroup conclude 2026-07-31;
# the Extension cohort (EXT) runs on to 2026-08-09. Update these dates as the schedule changes.
# Additive: does not touch line_status, funnel numbers, or the nulling.
_LINE_DOTTED_UNTIL = {"EXT": date(2026, 8, 9)}
_LINE_DOTTED_UNTIL_DEFAULT = date(2026, 7, 31)
line_active = {sg: TODAY <= _LINE_DOTTED_UNTIL.get(sg, _LINE_DOTTED_UNTIL_DEFAULT) for sg in SG_PRESENT}


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
            "pct": round(100 * a[k]["icmp"] / a[k]["ist"], 1) if a[k]["ist"] else None,
            "avg_words": round(a[k]["hw"] / a[k]["hm"], 1) if a[k]["hm"] else None,
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
        "pct": round(100 * t2a[tc]["icmp"] / t2a[tc]["ist"], 1) if t2a[tc]["ist"] else None,
        "avg_words": round(t2a[tc]["hw"] / t2a[tc]["hm"], 1) if t2a[tc]["hm"] else None,
    }
    # all applicable topics (not just those with started data) so the By-Topic breakdown shows the
    # full roster incl. not-yet-started ones (10/11/12/13) — zero-activity rows get 0 / None metrics.
    for tc in APPLICABLE
]

# ---- topic-status distribution (per topic + per subgroup) for stacked bars ----
STATES = [
    "not-applicable",
    "not-available-yet",
    "available-not-started",
    "available-missed-overdue",
    "started-not-completed",
    "completed",
]
mlook = {}


def rank(r):
    return (1 if r["is_completed"] == "Y" else 0) * 2 + (1 if r["is_started"] == "Y" else 0)


for r in bm.rows:
    k = (r["connect_id"], r["cohort_id"], r["topic_code"])
    if k not in mlook or rank(r) > rank(mlook[k]):
        mlook[k] = r


def status_for(flw, cohort, topic):
    sg = bm.cohort_to_sg(cohort)
    topics = bm.SUBGROUP_DESIGN[sg]["topics"]
    if topic not in topics:
        return "not-applicable"
    n = topics.index(topic) + 1
    m = mlook.get((flw, cohort, topic))
    if m and m["is_completed"] == "Y":
        return "completed"
    if m and m["is_started"] == "Y":
        return "started-not-completed"
    td = bm.cohort_info.get(cohort, {}).get("training_date")
    if not td:
        return "available-not-started"
    cad = bm.SUBGROUP_DESIGN[sg]["cadence"]
    if TODAY < td + timedelta(days=(n - 1) * cad):
        return "not-available-yet"
    if n < len(topics) and TODAY >= td + timedelta(days=n * cad):
        return "available-missed-overdue"
    return "available-not-started"


topic_status = defaultdict(lambda: defaultdict(int))
sg_status = defaultdict(lambda: defaultdict(int))
topic_status_cohort = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # topic -> cohort -> state -> n
for cohort, info in bm.cohort_info.items():
    sg = info["subgroup"]
    claimed = [f for f in bm.cohort_flws[cohort] if bm.cohort_flw_meta[(cohort, f)].get("date_claimed")]
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
# per-cohort topic status (for the by-cohort drilldown); only the 5 applicable states (topic is in the cohort)
STATES5 = ["completed", "started-not-completed", "available-missed-overdue", "available-not-started", "not-available-yet"]
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


def _iv_blocks(topics, init_set, fget, di_n=None, di_ct=0):
    base = len(init_set) or 1
    out = []
    for i, tc in enumerate(topics):
        n = i + 1
        f = fget(n)
        t, s, c = len(f["t"]), len(f["s"]), len(f["c"])
        s_di = s - di_ct if (di_n is not None and n == di_n and di_ct) else s
        out.append({
            "n": n, "topic": tc, "name": bm.TOPIC_NAMES[tc],
            "eligible": len(init_set), "triggered": t, "pct_trig": round(100 * t / base, 1),
            "started": s, "pct_started": round(100 * s / base, 1),
            "completed": c, "pct_completed": round(100 * c / s, 1) if s else None,
            "pct_completed_base": round(100 * c / base, 1),  # completed / initiated base (retention)
            "started_di": s_di, "pct_started_di": round(100 * s_di / base, 1),  # de-impacted (item 8)
        })
    return out


dropoff_sg = []
for sg in SG_PRESENT:
    u = bm.sg_unique[sg]
    claimed = u["claimed"]
    init = elig_sg.get(sg, set())
    connect = {
        "invited": len(u["invited"]), "accepted": len(u["accepted"]),
        "learn_started": len(u["learn_started"]), "learn_completed": len(u["learn_completed"]),
        "claimed": len(claimed), "flw_reg": len(claimed & bm.flw_registered), "initiated": len(init),
    }
    cohorts_n = sum(1 for c in bm.cohort_info if bm.cohort_info[c]["subgroup"] == sg)
    dropoff_sg.append({
        "sg": sg, "cohorts_n": cohorts_n, "connect": connect,
        "interviews": _iv_blocks(bm.SUBGROUP_DESIGN[sg]["topics"], init, lambda n, _sg=sg: fset[(_sg, n)],
                                 di_n=deimpact.get(sg, {}).get("last_n"), di_ct=deimpact.get(sg, {}).get("count", 0)),
    })

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
        "invited": inv, "accepted": acc, "learn_started": ls, "learn_completed": lc,
        "claimed": len(claimed_set), "flw_reg": len(claimed_set & bm.flw_registered), "initiated": len(init),
    }
    dropoff_cohorts[sg].append({
        "cohort": cohort, "connect": connect,
        "interviews": _iv_blocks(bm.SUBGROUP_DESIGN[sg]["topics"], init,
                                 lambda n, _c=cohort: coh_fset.get((_c, n), {"t": set(), "s": set(), "c": set()})),
    })

dropoff = {"subgroups": dropoff_sg, "cohorts": dict(dropoff_cohorts)}

payload = {
    "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),  # stamped at build; render shows this
    "today": str(TODAY),
    "counts": {
        "cohorts": len(bm.cohort_info),
        "flws": len({c["flw"] for c in cells}),
        "master_rows": len(bm.rows),
        "claimed_pairs": sum(
            1
            for cohort in bm.cohort_info
            for f in bm.cohort_flws[cohort]
            if bm.cohort_flw_meta[(cohort, f)].get("date_claimed")
        ),
    },
    "funnel": funnel,
    "line_pct_started": line,
    "line_days": line_days,           # median days from when FLW DID interview-1 to interview-N (session start)
    "line_pct_started_di": line_di,   # de-impacted %started series (item 8)
    "line_status": line_status,       # per-point release status (not-available/in-progress/settled)
    "line_active": line_active,       # per-subgroup: still actively triggering -> dotted funnel line
    "deimpact": deimpact,             # {sg: {last_n, count}} penult/last artifact summary
    "table1": t1,
    "table2": t2,
    "table3": t3,
    "topic_status": topic_status_out,
    "topic_status_cohort": topic_status_cohort_out,
    "dropoff": dropoff,
    "states": STATES,
    "topics": APPLICABLE,
    "sg_order": SG_PRESENT,
    "unmapped_cohorts": sorted(bm.unmapped_cohorts),
}
out = json.dumps(payload, separators=(",", ":"))
open("payload_agg.json", "w", encoding="utf-8").write(out)
print(f"payload_agg.json: {len(out.encode())/1024:.1f} KB")
print(f"  counts: {payload['counts']}")
print(f"  funnel rows: {len(funnel)}, table2 rows: {len(t2)}, topic_status rows: {len(topic_status_out)}")
print(f"  sample funnel[0]: {funnel[0]}")
print(f"  sample topic_status[0]: {topic_status_out[0]}")
