"""Build dashboard_data.json — the exact data the Labs render embeds (display-only).
Aggregates come straight from payload_agg.json (already validated by audit_e2e 26/26).
Adds: counts, connectFunnel (per subgroup), lineSeries bases, topicStatus reshaped, granular sample.
Run build_payload_agg.py first. Then audit with build_dashboard_data_audit.py.
"""
import json
import os
from collections import defaultdict
from datetime import date as _date, timedelta as _timedelta

import build_master_4src as bm

STATES_NA = [
    "completed",
    "started-not-completed",
    "available-missed-overdue",
    "available-not-started",
    "not-available-yet",
]

payload = json.loads(open("payload_agg.json", encoding="utf-8").read())
cohort_meta = json.loads(open("cohort_meta.json", encoding="utf-8").read())
# Present subgroups (in display order) come from the payload — auto-load: PANEL/ABT3 fold in only
# once they have data, so connectFunnel/lineSeries follow the same set the funnel/dropoff used.
SG_ORDER = payload["sg_order"]

# ---- initiated per subgroup (welcome union) ----
elig_sg = defaultdict(set)
for (cohort, topic), flws in bm.welcome_flws_by_key.items():
    sg = bm.cohort_to_sg(cohort)
    if sg:
        elig_sg[sg] |= flws

# ---- started/completed unique FLWs per subgroup (from master) ----
sg_started, sg_completed = defaultdict(set), defaultdict(set)
for r in bm.rows:
    sg = r["subgroup"]
    if r["is_started"] == "Y":
        sg_started[sg].add(r["connect_id"])
    if r["is_completed"] == "Y":
        sg_completed[sg].add(r["connect_id"])

# ---- connect funnel per subgroup (REAL Connect funnel from user_data.csv via bm.sg_unique) ----
# invited -> accepted -> completed-learn -> claimed -> initiated (welcome) -> started -> completed
connect_funnel = []
for sg in SG_ORDER:
    u = bm.sg_unique[sg]
    connect_funnel.append(
        {
            "sg": sg,
            "invited": len(u["invited"]),
            "accepted": len(u["accepted"]),
            "learn_completed": len(u["learn_completed"]),
            "claimed": len(u["claimed"]),
            "initiated": len(elig_sg.get(sg, set())),
            "started": len(sg_started.get(sg, set())),
            "completed": len(sg_completed.get(sg, set())),
        }
    )

# ---- line series bases ----
line_series = []
_line_di = payload.get("line_pct_started_di", {})
_line_prev = payload.get("line_pct_started_prev", {})
_line_st = payload.get("line_status", {})
_line_active = payload.get("line_active", {})
_line_days = payload.get("line_days", {})
for sg in SG_ORDER:
    line_series.append({"sg": sg, "base": len(elig_sg.get(sg, set())),
                        "pts": payload["line_pct_started"].get(sg, []),
                        "pts_di": _line_di.get(sg, []),       # de-impacted %started (item 8)
                        "pts_prev": _line_prev.get(sg, []),   # %started vs previous-interview starters (reached-prev denom)
                        "days": _line_days.get(sg, []),       # median days interview-1 -> interview-N (cadence view)
                        "status": _line_st.get(sg, []),       # per-point release status (items A1/A2)
                        "active": _line_active.get(sg, False)})  # still triggering -> dotted line

# ---- topicStatus reshaped: all 6 states (incl not-applicable) + total (for %-stack to 100) ----
ORDER6 = [
    "not-applicable",
    "not-available-yet",
    "available-not-started",
    "available-missed-overdue",
    "started-not-completed",
    "completed",
]
topic_status = []
for t in payload["topic_status"]:
    total = sum(t[s] for s in ORDER6)
    row = {"code": t["code"], "name": t["name"], "total": total, "applicable": total - t["not-applicable"]}
    for s in ORDER6:
        row[s] = t[s]
    topic_status.append(row)

# ---- counts ----
# Count UNIQUE interviews (FLW × cohort × interview position), not bot-trigger rows, so a duplicate
# trigger for the same interview isn't double-counted. Ties the Overview headline to the Breakdowns /
# Full-Retention tables, which also count unique interviews (table1 Overall ist/icmp).
_started_cells, _completed_cells = set(), set()
for r in bm.rows:
    _k = (r["connect_id"], r["cohort_id"], r["interview_n"])
    if r["is_started"] == "Y":
        _started_cells.add(_k)
    if r["is_completed"] == "Y":
        _completed_cells.add(_k)
tot_started = len(_started_cells)
tot_completed = len(_completed_cells)
counts = {
    "cohorts": payload["counts"]["cohorts"],
    "flws": payload["counts"]["flws"],
    "master_rows": payload["counts"]["master_rows"],
    "started": tot_started,
    "completed": tot_completed,
}

# ---- granular sample (first 500 rows, stable sort) ----
gcols = [
    "connect_id",
    "cohort_id",
    "subgroup",
    "interview_n",
    "topic_code",
    "is_triggered",
    "is_started",
    "is_completed",
    "matched_session_id",
]
rows_sorted = sorted(bm.rows, key=lambda r: (r["cohort_id"], r["connect_id"], int(r["interview_n"])))
GRANULAR_N = 30
granular = []
for r in rows_sorted[:GRANULAR_N]:
    granular.append(
        {
            "connect_id": r["connect_id"],
            "cohort_id": r["cohort_id"],
            "subgroup": r["subgroup"],
            "interview_n": int(r["interview_n"]),
            "topic_code": r["topic_code"],
            "is_triggered": r.get("is_triggered", "Y") == "Y",
            "is_initiated": r.get("is_initiated", "") == "Y",
            "is_started": r["is_started"] == "Y",
            "is_completed": r["is_completed"] == "Y",
            "session_id": r.get("matched_session_id", "") or "",
        }
    )

# ---- per-(FLW × cohort) × topic status matrix (item 4: "FLW × Topic" granular table) ----
# Reuses the SAME status logic as topicStatus, so the matrix reconciles to the stacked bar.
# Universe = claimed FLWs per cohort (the topic-completion denominator). Cells are state indices
# aligned to SUBGROUP_DESIGN[sg] topic order. Short keys keep the embed small (verified well under
# the 512 KB render limit). `u` (untrained) is filled from _untrained_flw.json when present (item 1).
_TODAY = _date.today()
_STATE_IDX = {s: i for i, s in enumerate(
    ["not-applicable", "not-available-yet", "available-not-started",
     "available-missed-overdue", "started-not-completed", "completed"])}
_untrained = {}
if os.path.exists("_untrained_flw.json"):
    _untrained = json.load(open("_untrained_flw.json", encoding="utf-8"))

_mlook = {}


def _mrank(r):
    return (1 if r["is_completed"] == "Y" else 0) * 2 + (1 if r["is_started"] == "Y" else 0)


for _r in bm.rows:
    _k = (_r["connect_id"], _r["cohort_id"], _r["topic_code"])
    if _k not in _mlook or _mrank(_r) > _mrank(_mlook[_k]):
        _mlook[_k] = _r


def _status_idx(flw, cohort, sg, topic, topics):
    if topic not in topics:
        return 0  # not-applicable
    n = topics.index(topic) + 1
    m = _mlook.get((flw, cohort, topic))
    if m and m["is_completed"] == "Y":
        return _STATE_IDX["completed"]
    if m and m["is_started"] == "Y":
        return _STATE_IDX["started-not-completed"]
    td = bm.cohort_info.get(cohort, {}).get("training_date")
    if not td:
        return _STATE_IDX["available-not-started"]
    cad = bm.SUBGROUP_DESIGN[sg]["cadence"]
    if _TODAY < td + _timedelta(days=(n - 1) * cad):
        return _STATE_IDX["not-available-yet"]
    if n < len(topics) and _TODAY >= td + _timedelta(days=n * cad):
        return _STATE_IDX["available-missed-overdue"]
    return _STATE_IDX["available-not-started"]


flw_matrix = []
for _cohort, _info in bm.cohort_info.items():
    _sg = _info["subgroup"]
    _topics = bm.SUBGROUP_DESIGN[_sg]["topics"]
    _claimed = [f for f in bm.cohort_flws[_cohort] if bm.cohort_flw_meta[(_cohort, f)].get("date_claimed")]
    for _flw in _claimed:
        # drop per-row "g" (subgroup) — re-derived in the render from cohortSG below; and omit "u" when 0
        # (render treats a missing u as untrained=false). Both shrink this, the largest DATA key (~59%).
        _row = {"f": _flw, "c": _cohort,
                "s": [_status_idx(_flw, _cohort, _sg, t, _topics) for t in _topics]}
        if _untrained.get(_flw):
            _row["u"] = 1
        flw_matrix.append(_row)

out = {
    "built_at": payload.get("built_at", ""),
    "today": payload.get("today", ""),
    "counts": counts,
    "connectFunnel": connect_funnel,
    "funnel": payload["funnel"],
    "lineSeries": line_series,
    "table1": payload["table1"],
    "table2": payload["table2"],
    "table3": payload["table3"],
    "topicStatus": topic_status,
    "topicStatusCohort": payload["topic_status_cohort"],
    "dropoff": payload["dropoff"],
    "connectPendingSubgroups": payload.get("connect_pending_subgroups", []),
    "cohortEngagement": payload.get("cohort_engagement", {}),
    "cohortEngagementLLO": payload.get("cohort_engagement_llo", {}),
    "granular": granular,
    "granular_total": len(bm.rows),
    "flwMatrix": flw_matrix,
    "cohortSG": {_c: _i["subgroup"] for _c, _i in bm.cohort_info.items()},  # cohort->subgroup (flwMatrix rows drop g)
    "deimpact": payload.get("deimpact", {}),
    # design + topic names derived from the CCHQ interview_schedule lookup — single source of truth
    # so the render stops hardcoding them (fixes PANEL's 13-topic sequence everywhere).
    "subgroupDesign": bm.SUBGROUP_DESIGN,
    "topicNames": bm.TOPIC_NAMES,
    "topicQuestions": bm.TOPIC_QUESTIONS,
    "unmappedCohorts": payload.get("unmapped_cohorts", []),
}
s = json.dumps(out, separators=(",", ":"))
open("dashboard_data.json", "w", encoding="utf-8").write(s)
print(f"dashboard_data.json: {len(s.encode()) / 1024:.1f} KB")
print(f"  counts: {counts}")
print(
    f"  connectFunnel rows: {len(connect_funnel)}; funnel rows: {len(out['funnel'])}; topicStatus: {len(topic_status)}; granular: {len(granular)}/{len(bm.rows)}"
)
print(f"  connectFunnel[0]: {connect_funnel[0]}")
