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
import build_flw_analysis as bfa  # per-FLW cross-cohort rollup (import-safe; reuses cached bm)
import topic_status_lib as _tsl  # shared slot-state rule (also used by build_payload_agg)

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

# ---- topicStatus reshaped: every state (incl not-applicable) + total (for %-stack to 100) ----
# sourced from topic_status_lib so a new state can never be silently dropped on the way to the render
ORDER6 = list(_tsl.STATES)
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
# Kept small deliberately: this is an ILLUSTRATIVE sample of 10,000+ rows, and the build warns to
# reduce it when the render nears the 512 KB cap. The full data lives in the tables and exports.
# Lowered from 60 on 2026-08-25: the Asked column and the new payload fields pushed the projected LIVE
# render 8 KB OVER the 512 KB cap and the render gate refused to publish. This sample is illustrative -
# the full data is in the tables and the CSV export - so it is the right thing to trade for headroom,
# which is what the build's own warning has always said.
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
_STATE_IDX = _tsl.STATE_IDX
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
    # Shares the FUNCTION and the INPUTS with build_payload_agg. Sharing only the function was not
    # enough: this passed `training_date` while the drop-off view fell back to the first trigger, so on
    # a stale Connect snapshot the matrix called a slot "window still open" while the drop-off view
    # called it missed, and 27 cohorts disagreed. `start_date` and GRACE_DAYS now have one home each.
    return _tsl.status_idx(
        topic,
        topics,
        _mlook.get((flw, cohort, topic)),
        bm.cohort_info.get(cohort, {}).get("start_date"),
        bm.SUBGROUP_DESIGN[sg]["cadence"],
        _TODAY,
        _tsl.GRACE_DAYS.get(cohort),
    )


flw_matrix = []
_interviewed = _tsl.interviewed_index(bm.rows)
for _cohort, _info in bm.cohort_info.items():
    _sg = _info["subgroup"]
    _topics = bm.SUBGROUP_DESIGN[_sg]["topics"]
    # claimed ∪ anyone with a master row here, so an interview that happened is never outside the matrix
    _claimed = sorted(_tsl.universe_for(_cohort, bm.cohort_flws, bm.cohort_flw_meta, _interviewed))
    for _flw in _claimed:
        # drop per-row "g" (subgroup) — re-derived in the render from cohortSG below; and omit "u" when 0
        # (render treats a missing u as untrained=false). Both shrink this, the largest DATA key (~59%).
        _row = {"f": _flw, "c": _cohort,
                "s": [_status_idx(_flw, _cohort, _sg, t, _topics) for t in _topics]}
        if _untrained.get(_flw):
            _row["u"] = 1
        flw_matrix.append(_row)

# The rhythm COUNT arrays exist only so build_payload_agg can pool the All-cohorts figure from its
# parts; the render reads the percentages and the base, never the counts. Shipping them cost ~3 KB
# across 12 series plus their two per-LLO copies, which pushed the injected render to 513.6 KB and
# tripped the 512 KB gate. Dropped here rather than upstream so the pooling still has them.
# Also dropped: the `waiting` per-week COUNT array (the render uses waiting_pct and the KPI tile only),
# and `ended` / `end_date`, which no longer have a single reader anywhere in the template.
# `dropped`/`inprog` counts exist only so _pool_outcome can sum the parts; the render reads the
# percentages and enrol_base. Same reasoning as steady/incons.
# `dropped` and `waiting` are now the render's SOURCE for the default reading - the outcome
# percentages are no longer shipped, so stripping the counts would leave the page with nothing to
# draw. `inprog` stays dropped because it is the exact residual started-finished-dropped-waiting.
_ENG_DROP = ("steady", "incons", "ended", "end_date", "inprog", "enrol_finished")


def _eng_trim(series_map):
    out = {}
    for _k, _v in (series_map or {}).items():
        if isinstance(_v, dict) and "weeks" in _v:
            out[_k] = {a: b for a, b in _v.items() if a not in _ENG_DROP}
        elif isinstance(_v, dict):
            out[_k] = {a: (({c: d for c, d in b.items() if c not in _ENG_DROP}
                            if isinstance(b, dict) else b)) for a, b in _v.items()}
        else:
            out[_k] = _v
    return out


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
    "cohortEngagement": _eng_trim(payload.get("cohort_engagement", {})),
    "cohortEngagementLLO": {_sg: _eng_trim(_v) for _sg, _v in
                            (payload.get("cohort_engagement_llo") or {}).items()},
    # Per-cohort outcome, each cohort scored at its OWN end date rather than a date shared across its
    # whole design. Feeds the cross-cohort drop-off comparison.
    "cohortDropoff": payload.get("cohort_dropoff", []),
    "flwEngagement": bfa.aggregate(bfa.build_records()),  # per-FLW cross-cohort analysis (compact aggregates)
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
    # OCS review verdict on every COMPLETED interview, with not-yet-reviewed as its own bucket.
    # Small (four counts per subgroup and per topic), so it survives the render prune.
    "reviewStatus": payload.get("review_status", {}),
    "unmappedCohorts": payload.get("unmapped_cohorts", []),
    "retiredCohorts": payload.get("retired_cohorts", []),
}
s = json.dumps(out, separators=(",", ":"))
open("dashboard_data.json", "w", encoding="utf-8").write(s)
print(f"dashboard_data.json: {len(s.encode()) / 1024:.1f} KB")
# render_data.json — the PRUNED payload the render actually embeds (dashboard_data.json stays
# complete so every audit gate keeps asserting against it). Written here so the two can't drift.
import build_render_data  # noqa: E402  (local module; imported late so a failure names this step)

build_render_data.build_and_write(os.path.dirname(os.path.abspath(__file__)))
print(f"  counts: {counts}")
print(
    f"  connectFunnel rows: {len(connect_funnel)}; funnel rows: {len(out['funnel'])}; topicStatus: {len(topic_status)}; granular: {len(granular)}/{len(bm.rows)}"
)
print(f"  connectFunnel[0]: {connect_funnel[0]}")
