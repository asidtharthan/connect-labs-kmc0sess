"""Audit dashboard_data.json (the data the render embeds) — independent recompute vs the
master (build_master_4src) and vs the audit_e2e-validated payload_agg.json. All PASS required.
Run after build_dashboard_data.py.  UTF-8: run with PYTHONUTF8=1.
"""
import json
import topic_status_lib as tsl
import sys
from collections import defaultdict

import build_master_4src as bm

# the states a topic can be in when it IS part of the cohort's design (i.e. everything but
# not-applicable). "not-triggered" joined the model on 2026-08-07 — see topic_status_lib.
STATES_NA = [
    "completed",
    "started-not-completed",
    "available-missed-overdue",
    "available-not-started",
    "not-available-yet",
    "not-triggered",
]

dd = json.loads(open("dashboard_data.json", encoding="utf-8").read())
pay = json.loads(open("payload_agg.json", encoding="utf-8").read())
SG_ORDER = pay["sg_order"]  # present subgroups (auto-load); checks run over exactly what was emitted

results = []


def chk(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")


print("=" * 80)
print("A. AGGREGATES in dashboard_data == validated payload_agg.json")
print("=" * 80)
chk("funnel identical to payload", dd["funnel"] == pay["funnel"], f"{len(dd['funnel'])} rows")
chk("table1 identical", dd["table1"] == pay["table1"])
chk("table2 identical", dd["table2"] == pay["table2"])
chk("table3 identical", dd["table3"] == pay["table3"])

# avg_words: independent recompute = Σ session_human_words / Σ session_human_msgs over STARTED rows
_ROLL = {"TRS": "TRS", "TRE": "TRE", "ABT1-A": "ABT1", "ABT1-B": "ABT1", "ABT2-A": "ABT2", "ABT2-B": "ABT2",
         "PANEL": "PANEL", "ABT3-A": "ABT3", "ABT3-B": "ABT3", "2WT": "2WT", "EXT": "EXT", "NPS": "NPS"}


def _avg(pred):
    hw = hm = 0
    for r in bm.rows:
        if r["is_started"] == "Y" and pred(r):
            hw += int(r.get("session_human_words", 0) or 0)
            hm += int(r.get("session_human_msgs", 0) or 0)
    return tsl.r1(hw / hm) if hm else None


_abt = ("ABT1-A", "ABT1-B", "ABT2-A", "ABT2-B", "ABT3-A", "ABT3-B")
aw_bad = 0
for r in dd["table1"]:
    exp = _avg((lambda x: True)) if r["key"] == "Overall" else _avg(lambda x, k=r["key"]: _ROLL[x["subgroup"]] == k)
    if r.get("avg_words") != exp:
        aw_bad += 1
        print(f"   t1 {r['key']}: dd={r.get('avg_words')} exp={exp}")
for r in dd["table3"]:
    exp = _avg(lambda x: x["subgroup"] in _abt) if r["key"] == "Overall" else _avg(lambda x, k=r["key"]: x["subgroup"] == k)
    if r.get("avg_words") != exp:
        aw_bad += 1
        print(f"   t3 {r['key']}: dd={r.get('avg_words')} exp={exp}")
for r in dd["table2"]:
    exp = _avg(lambda x, c=r["code"]: bm.SUBGROUP_DESIGN[x["subgroup"]]["topics"][int(x["interview_n"]) - 1] == c)
    if r.get("avg_words") != exp:
        aw_bad += 1
        print(f"   t2 {r['code']}: dd={r.get('avg_words')} exp={exp}")
chk("avg_words == independent recompute (Σwords/Σmsgs over started rows)", aw_bad == 0, f"{aw_bad} mismatches")

ts_ok = True
ts_bad = 0
pay_ts = {t["code"]: t for t in pay["topic_status"]}
_ORDER6 = ["not-applicable", "not-available-yet", "available-not-started", "available-missed-overdue",
           "started-not-completed", "completed", "not-triggered"]
claimed_pairs = dd["counts"]["claimed_pairs"] if "claimed_pairs" in dd["counts"] else pay["counts"]["claimed_pairs"]
for t in dd["topicStatus"]:
    p = pay_ts[t["code"]]
    for s in _ORDER6:
        if t[s] != p[s]:
            ts_ok = False
            ts_bad += 1
    if t["total"] != sum(t[s] for s in _ORDER6):
        ts_ok = False
        ts_bad += 1
    if t["applicable"] != t["total"] - t["not-applicable"]:
        ts_ok = False
        ts_bad += 1
    # every (cohort,flw) in the universe gets exactly one state per topic -> total == claimed_pairs
    if t["total"] != claimed_pairs:
        ts_ok = False
        ts_bad += 1
chk("topicStatus 7 states==payload, total==Σstates==universe pairs, applicable==total-NA", ts_ok, f"{ts_bad} bad")
# per-cohort topic breakdown: every cohort row's total == its 5 applicable-state sum; cohorts only where topic applies
tsc_bad = 0
for tc, rows_c in dd["topicStatusCohort"].items():
    for rc in rows_c:
        if rc["total"] != sum(rc[s] for s in STATES_NA):
            tsc_bad += 1
        sg = bm.cohort_to_sg(rc["cohort"])
        if tc not in bm.SUBGROUP_DESIGN[sg]["topics"]:
            tsc_bad += 1
chk("topicStatusCohort: row total==Σ applicable states & topic applicable in cohort", tsc_bad == 0, f"{tsc_bad} bad")
# cross-check: Σ per-cohort totals for a topic == that topic's applicable count
xc_bad = 0
tsmap = {t["code"]: t for t in dd["topicStatus"]}
for tc, rows_c in dd["topicStatusCohort"].items():
    if sum(rc["total"] for rc in rows_c) != tsmap[tc]["applicable"]:
        xc_bad += 1
chk("Σ per-cohort topic totals == topic applicable", xc_bad == 0, f"{xc_bad} mismatches")

print("=" * 80)
print("B. CONNECT FUNNEL — independent recompute from master + bm.sg_unique")
print("=" * 80)
elig_sg = defaultdict(set)
for (cohort, topic), flws in bm.welcome_flws_by_key.items():
    sg = bm.cohort_to_sg(cohort)
    if sg:
        elig_sg[sg] |= flws
sg_started, sg_completed = defaultdict(set), defaultdict(set)
for r in bm.rows:
    if r["is_started"] == "Y":
        sg_started[r["subgroup"]].add(r["connect_id"])
    if r["is_completed"] == "Y":
        sg_completed[r["subgroup"]].add(r["connect_id"])
cf = {r["sg"]: r for r in dd["connectFunnel"]}
bad = 0
for sg in SG_ORDER:
    u = bm.sg_unique[sg]
    exp = {
        "invited": len(u["invited"]),
        "accepted": len(u["accepted"]),
        "learn_completed": len(u["learn_completed"]),
        "claimed": len(u["claimed"]),
        "initiated": len(elig_sg[sg]),
        "started": len(sg_started[sg]),
        "completed": len(sg_completed[sg]),
    }
    for k, v in exp.items():
        if cf[sg][k] != v:
            bad += 1
            print(f"    MISMATCH {sg}.{k}: dash={cf[sg][k]} exp={v}")
chk("connectFunnel every cell == independent recompute", bad == 0, f"{bad} mismatches / {len(SG_ORDER)*7}")
# invited >= accepted >= learn_completed is guaranteed by the Connect flow, so it is a hard check and
# names the offender (this used to be a bare `all(...)` that failed with an empty message).
_hard = [
    f"{sg}: invited={cf[sg]['invited']} accepted={cf[sg]['accepted']} learnC={cf[sg]['learn_completed']}"
    for sg in SG_ORDER
    if not (cf[sg]["invited"] >= cf[sg]["accepted"] >= cf[sg]["learn_completed"])
]
chk("connect funnel monotonic invited>=accepted>=learnC", not _hard, "; ".join(_hard))
# learn_completed >= claimed is NOT guaranteed: Connect can record a claim with no completed-learn
# timestamp. Verified in the raw snapshot (2026-08-07): ABT1-B 1 FLW, 2WT 3 FLWs claimed with a blank
# completed_learn_date. So this is a tolerance check on a known source artifact — a handful is data,
# a large gap means the learn leg genuinely broke.
_CLAIM_OVER_LEARN_TOL = 5
_soft = [
    f"{sg}: claimed={cf[sg]['claimed']} > learnC={cf[sg]['learn_completed']} (+{cf[sg]['claimed'] - cf[sg]['learn_completed']})"
    for sg in SG_ORDER
    if cf[sg]["claimed"] - cf[sg]["learn_completed"] > _CLAIM_OVER_LEARN_TOL
]
_over = [sg for sg in SG_ORDER if cf[sg]["claimed"] > cf[sg]["learn_completed"]]
chk(
    f"claimed <= learnC within tolerance (+{_CLAIM_OVER_LEARN_TOL}; claim-without-learn-date is a known Connect artifact)",
    not _soft,
    "; ".join(_soft) or (f"{len(_over)} sg over by <= tol: {_over}" if _over else "0 over"),
)
mono2 = all(cf[sg]["started"] >= cf[sg]["completed"] for sg in SG_ORDER)
chk("started >= completed (all subgroups)", mono2)

print("=" * 80)
print("B2. DROPOFF matrix integrity + cross-consistency")
print("=" * 80)
fmap = {(f["sg"], f["n"]): f for f in dd["funnel"]}
dsg = {s["sg"]: s for s in dd["dropoff"]["subgroups"]}
xbad = 0
for sg in SG_ORDER:
    for iv in dsg[sg]["interviews"]:
        f = fmap.get((sg, iv["n"]))
        if not f or iv["triggered"] != f["trig"] or iv["started"] != f["started"] \
                or iv["completed"] != f["completed"] or iv["eligible"] != f["elig"]:
            xbad += 1
chk("dropoff subgroup interviews == validated funnel (trig/started/completed/elig)", xbad == 0, f"{xbad} mismatches")
cbad = 0
for sg in SG_ORDER:
    d, o = dsg[sg]["connect"], cf[sg]
    for k in ("invited", "accepted", "learn_completed", "claimed", "initiated"):
        if d[k] != o[k]:
            cbad += 1
chk("dropoff connect == Overview connectFunnel (shared fields)", cbad == 0, f"{cbad} mismatches")
groups = [(s["sg"], s) for s in dd["dropoff"]["subgroups"]]
ncoh = 0
for sglist in dd["dropoff"]["cohorts"].values():
    for c in sglist:
        groups.append((c["cohort"], c))
        ncoh += 1
mbad = ibad = 0
for name, g in groups:
    c = g["connect"]
    # logically-guaranteed monotonic subset: accepted<=invited, learn_completed<=learn_started, flw_reg<=claimed
    if not (c["invited"] >= c["accepted"] and c["learn_started"] >= c["learn_completed"] and c["claimed"] >= c["flw_reg"]):
        mbad += 1
        print(f"    connect monotonic violation: {name} {c}")
    for iv in g["interviews"]:
        if not (iv["completed"] <= iv["started"] <= iv["triggered"]):
            ibad += 1
chk("connect funnel monotonic (accepted<=invited, learnC<=learnS, flwReg<=claimed) all groups", mbad == 0, f"{mbad} bad / {len(groups)}")
chk("each interview completed<=started<=triggered (all subgroups+cohorts)", ibad == 0, f"{ibad} bad")
chk("per-cohort dropoff present for every cohort", ncoh == len({r["cohort_id"] for r in bm.rows}), f"{ncoh} cohorts")

print("=" * 80)
print("C. COUNTS")
print("=" * 80)
chk(
    "counts.master_rows == len(rows)",
    dd["counts"]["master_rows"] == len(bm.rows),
    f"{dd['counts']['master_rows']} == {len(bm.rows)}",
)
uflw = len({r["connect_id"] for r in bm.rows})
chk("counts.flws == unique connect_ids", dd["counts"]["flws"] == uflw, f"{dd['counts']['flws']} == {uflw}")
ucoh = len({r["cohort_id"] for r in bm.rows})
chk("counts.cohorts == unique cohort_ids", dd["counts"]["cohorts"] == ucoh, f"{dd['counts']['cohorts']} == {ucoh}")
ts2 = len({(r["connect_id"], r["cohort_id"], r["interview_n"]) for r in bm.rows if r["is_started"] == "Y"})
tc2 = len({(r["connect_id"], r["cohort_id"], r["interview_n"]) for r in bm.rows if r["is_completed"] == "Y"})
chk("counts.started == unique started interviews", dd["counts"]["started"] == ts2, f"{dd['counts']['started']} == {ts2}")
chk(
    "counts.completed == unique completed interviews",
    dd["counts"]["completed"] == tc2,
    f"{dd['counts']['completed']} == {tc2}",
)

print("=" * 80)
print("D. LINE SERIES")
print("=" * 80)
ls = {s["sg"]: s for s in dd["lineSeries"]}
lbad = 0
for sg in SG_ORDER:
    if ls[sg]["base"] != len(elig_sg[sg]):
        lbad += 1
    if ls[sg]["pts"] != pay["line_pct_started"].get(sg, []):
        lbad += 1
chk("lineSeries base==initiated & pts==payload line_pct_started", lbad == 0, f"{lbad} bad")
# cross-check: pts == round(100*funnel.started/base)
fmap = defaultdict(dict)
for f in dd["funnel"]:
    fmap[f["sg"]][f["n"]] = f
xbad = 0
for sg in SG_ORDER:
    base = ls[sg]["base"] or 1
    for i, p in enumerate(ls[sg]["pts"]):
        st = fmap[sg][i + 1]["started"]
        if tsl.r1(100 * st / base) != p:
            xbad += 1
chk("lineSeries pts == 100*funnel.started/base (recompute)", xbad == 0, f"{xbad} mismatched points")

print("=" * 80)
print("E. GRANULAR SAMPLE integrity")
print("=" * 80)
chk("granular_total == len(rows)", dd["granular_total"] == len(bm.rows), f"{dd['granular_total']} == {len(bm.rows)}")
chk("granular sample size in (0,500]", 0 < len(dd["granular"]) <= 500, f"{len(dd['granular'])}")
# every granular row exists in master with matching flags
mindex = {}
for r in bm.rows:
    mindex[(r["connect_id"], r["cohort_id"], int(r["interview_n"]))] = r
gbad = 0
for g in dd["granular"]:
    key = (g["connect_id"], g["cohort_id"], g["interview_n"])
    r = mindex.get(key)
    if not r:
        gbad += 1
        continue
    if (
        (r["is_started"] == "Y") != g["is_started"]
        or (r["is_completed"] == "Y") != g["is_completed"]
        or r["topic_code"] != g["topic_code"]
    ):
        gbad += 1
chk("every granular row matches a real master row (flags+topic)", gbad == 0, f"{gbad} bad / 500")

print("=" * 80)
print("F. NEW FEATURES — FLW×Topic matrix (4), de-impact (8), completed-of-base (6)")
print("=" * 80)
fm = dd.get("flwMatrix", [])
chk("flwMatrix row count == (claimed ∪ interviewed) (FLW,cohort) pairs", len(fm) == claimed_pairs,
    f"{len(fm)} == {claimed_pairs}")
cell_bad = 0
for r in fm:
    _rsg = r.get("g") or bm.cohort_info.get(r["c"], {}).get("subgroup")   # flwMatrix rows now drop g; derive from cohort
    topics = bm.SUBGROUP_DESIGN.get(_rsg, {}).get("topics", [])
    if len(r["s"]) != len(topics):
        cell_bad += 1
    # in-design topics are never state 0 (not-applicable); 6 = not-triggered joined the model 2026-08-07
    if any((not isinstance(x, int)) or x < 1 or x > 6 for x in r["s"]):
        cell_bad += 1
chk("flwMatrix: cells align to subgroup topics & are in-design states (1..6)", cell_bad == 0, f"{cell_bad} bad rows")
m_comp = sum(1 for r in fm for x in r["s"] if x == 5)
ts_comp = sum(t["completed"] for t in dd["topicStatus"])
chk("flwMatrix completed cells == Σ topicStatus completed", m_comp == ts_comp, f"{m_comp} == {ts_comp}")
m_start = sum(1 for r in fm for x in r["s"] if x in (4, 5))
ts_start = sum(t["started-not-completed"] + t["completed"] for t in dd["topicStatus"])
chk("flwMatrix started cells == Σ topicStatus (started+completed)", m_start == ts_start, f"{m_start} == {ts_start}")

di = dd.get("deimpact", {})
fmap2 = defaultdict(dict)
for f in dd["funnel"]:
    fmap2[f["sg"]][f["n"]] = f
di_bad = 0
for sg, info in di.items():
    if len(bm.SUBGROUP_DESIGN[sg]["topics"]) < 3:
        di_bad += 1  # de-impact must never apply to 2-interview subgroups
    last = fmap2[sg][info["last_n"]]
    if last["started_di"] != last["started"] - info["count"]:
        di_bad += 1
chk("deimpact: last started_di == started − count; only >=3-interview subgroups", di_bad == 0, f"{di_bad} bad; sgs={sorted(di)}")
dq_bad = 0
for f in dd["funnel"]:
    if f["started_di"] > f["started"] or f["pct_started_di"] != tsl.r1(100 * f["started_di"] / f["elig"]):
        dq_bad += 1
chk("funnel started_di<=started & pct_started_di consistent (all rows)", dq_bad == 0, f"{dq_bad} bad")
ldi_bad = 0
for sg in SG_ORDER:
    for i, p in enumerate(ls[sg].get("pts_di", [])):
        if fmap2[sg][i + 1]["pct_started_di"] != p:
            ldi_bad += 1
chk("lineSeries pts_di == funnel pct_started_di", ldi_bad == 0, f"{ldi_bad} mismatched points")
# reached-previous-interview retention: numerator = |started(n) ∩ started(n-1)| (intersection, so it's
# bounded ≤100%), denom = |started(n-1)| (n=1 -> elig / started). Validate arithmetic + bounds.
lp_bad = 0
for sg in SG_ORDER:
    rows = fmap2.get(sg, {})
    for n in sorted(rows):
        f = rows[n]
        denom = rows[n - 1]["started"] if n > 1 else f["elig"]
        num = f.get("prev_num")
        exp = tsl.r1(100 * num / denom) if denom else None
        if f.get("prev_started") != denom or f.get("pct_started_prev") != exp:
            lp_bad += 1
        # numerator must be a subset count of the denominator -> rate can never exceed 100%
        if num is not None and (num > denom or (f.get("pct_started_prev") or 0) > 100):
            lp_bad += 1
        # lineSeries pts_prev must equal the funnel value
        if ls[sg].get("pts_prev", [])[n - 1] != f.get("pct_started_prev"):
            lp_bad += 1
chk("pct_started_prev = 100*|started(n)∩started(n-1)|/started(n-1) (n=1->elig), bounded ≤100, lineSeries matches",
    lp_bad == 0, f"{lp_bad} bad")
cb_bad = sum(1 for f in dd["funnel"] if f["pct_completed_base"] != tsl.r1(100 * f["completed"] / f["elig"]))
chk("funnel pct_completed_base == 100*completed/eligible (all rows)", cb_bad == 0, f"{cb_bad} bad")

# ---- Cohort Engagement (3-panel): internal consistency + tie-out to canonical started count ----
_eng = dd.get("cohortEngagement", {})
_eng_started = defaultdict(set)
for r in bm.rows:
    if r.get("is_started") == "Y" and r.get("matched_session_id"):
        _eng_started[r["subgroup"]].add(r["connect_id"])
# ---- OCS review status -------------------------------------------------------------------------
# The verdict split must account for EVERY completed interview exactly once, and the by-design and
# by-topic breakdowns must each add back to the overall. If they do not, the view would show a number
# that cannot be reconciled with the completed count - which is the exact failure mode this whole
# feature exists to close.
_rs = dd.get("reviewStatus") or {}
if _rs:
    _rk = _rs.get("keys") or []
    # TIE OUT TO THE OVERVIEW, not to this block's own basis. The first version of this check counted
    # master ROWS, which is what the payload was doing too - so both were wrong in the same direction
    # and the check passed while the view read 9,480 against the Overview's 9,459. A gate that shares
    # the bug it is meant to catch is worse than no gate. counts.completed is the published headline,
    # so that is the number the split has to add up to.
    _cells = {(r["connect_id"], r["cohort_id"], r["interview_n"])
              for r in bm.rows if r.get("is_completed") == "Y"}
    _tot = sum(_rs["overall"].get(k, 0) for k in _rk)
    chk("reviewStatus: verdicts add up to the OVERVIEW completed count, exactly",
        _tot == len(_cells) == dd["counts"]["completed"],
        f"split {_tot} | unique interviews {len(_cells)} | Overview {dd['counts']['completed']}")
    chk("reviewStatus: duplicate bot triggers are not double-counted",
        _tot <= sum(1 for r in bm.rows if r.get("is_completed") == "Y"),
        f"{sum(1 for r in bm.rows if r.get('is_completed') == 'Y') - _tot} duplicate row(s) collapsed")
    _bysg = sum(v.get(k, 0) for v in _rs.get("by_sg", {}).values() for k in _rk)
    chk("reviewStatus: by-design breakdown adds back to the overall", _bysg == _tot,
        f"{_bysg} vs {_tot}")
    _bytop = sum(v.get(k, 0) for v in _rs.get("by_topic", {}).values() for k in _rk)
    chk("reviewStatus: by-topic breakdown adds back to the overall", _bytop == _tot,
        f"{_bytop} vs {_tot}")
    # Independent recompute of the verdict itself, straight off the master rows.
    _RANK = {"suspected_ai": 0, "unacceptable": 1, "acceptable": 2, "not-reviewed": 3}
    _best = {}
    for r in bm.rows:
        if r.get("is_completed") != "Y":
            continue
        _v = r.get("review_status") or "not-reviewed"
        if _v not in _RANK:
            _v = "not-reviewed"
        _k2 = (r["connect_id"], r["cohort_id"], r["interview_n"])
        if _k2 not in _best or _RANK[_v] < _RANK[_best[_k2]]:
            _best[_k2] = _v
    _own = {}
    for _v in _best.values():
        _own[_v] = _own.get(_v, 0) + 1
    _bad = [k for k in _rk if _own.get(k, 0) != _rs["overall"].get(k, 0)]
    chk("reviewStatus: payload == independent recompute from master rows", not _bad,
        ", ".join(f"{k}: {_own.get(k, 0)} vs {_rs['overall'].get(k, 0)}" for k in _bad) or "all four match")
else:
    chk("reviewStatus present in the payload", False,
        "missing - the daily job step 2t (pull_ocs_tags.py) may not have run")

_eng_started["ALL"] = set().union(*_eng_started.values()) if _eng_started else set()  # program-wide distinct
_eng_bad = []
# Per-week arrays that must all be the same length. Deliberately lists only what the RENDER receives:
# the rhythm counts, the `waiting` count and ended/end_date are stripped in build_dashboard_data
# because nothing in the template reads them, so naming them here would fail on their absence.
_eng_keys = ("weeks", "started", "steady_pct", "incons_pct", "rhythm_base", "finished",
             "new", "active", "slow", "quiet", "dropped", "waiting", "dropC", "waitC",
             "dropA", "waitA")


def _largest_remainder(counts, base):
    """Largest-remainder percentages. Deliberately a SEPARATE implementation from the payload's."""
    if not base:
        return [0] * len(counts)
    exact = [100.0 * c / base for c in counts]
    out = [int(e) for e in exact]
    rem = 100 - sum(out)
    order = sorted(range(len(counts)), key=lambda i: exact[i] - int(exact[i]), reverse=True)
    for k in range(rem):
        out[order[k % len(order)]] += 1
    return out


def _eng_consistent(label, c, expect_started=None):
    """Internal invariants for one engagement series; append issues to _eng_bad."""
    if len({len(c[k]) for k in _eng_keys}) != 1:
        _eng_bad.append(f"{label}: array lengths differ"); return
    for i in range(len(c["weeks"])):
        if c["finished"][i] + c["new"][i] + c["active"][i] + c["slow"][i] + c["quiet"][i] != c["started"][i]:
            _eng_bad.append(f"{label}[{i}]: Panel3 stack != Panel1 started")
        # TWO independent readings, each summing to 100 on its own base.
        #   outcome: finished / dropped / waiting / in-progress, over everyone who started
        #   rhythm:  steady / inconsistent, over starters with 2+ interviews (rhythm_base)
        # Rhythm used to be the residual of the outcome stack, so it emptied to 0 once every cohort
        # closed. Checking them as one sum would hide exactly that failure.
        # EXACTLY 100 now, not 99-101: largest-remainder rounding closes the stack, and the legend
        # promises it closes. A tolerance here would let the promise quietly break again.
        # The outcome percentages are no longer shipped: the page derives them from the counts for
        # whichever reading is selected. So this recomputes them the way the page will, INDEPENDENTLY
        # of the render, and does it for all three readings - each has to close on its own.
        for _tag, _dk, _wk in (("B", "dropped", "waiting"), ("C", "dropC", "waitC"),
                               ("A", "dropA", "waitA")):
            _st = c["started"][i]
            _ip = _st - c["finished"][i] - c[_dk][i] - c[_wk][i]
            if _ip < 0:
                _eng_bad.append(f"{label}[{i}]/{_tag}: in-progress residual is negative ({_ip})")
                continue
            _o = sum(_largest_remainder([c["finished"][i], c[_dk][i], c[_wk][i], _ip], _st))
            if _o != (100 if _st else 0):
                _eng_bad.append(f"{label}[{i}]/{_tag}: outcome % sum {_o}, expected "
                                f"{100 if _st else 0}")
        if c["dropC"][i] > c["dropped"][i]:
            _eng_bad.append(f"{label}[{i}]: C ({c['dropC'][i]}) exceeds B ({c['dropped'][i]})")
        _r = c["steady_pct"][i] + c["incons_pct"][i]
        _rb = c["rhythm_base"][i]
        if _rb and _r != 100:
            _eng_bad.append(f"{label}[{i}]: rhythm % sum {_r}, expected 100 on base {_rb}")
        if not _rb and _r:
            _eng_bad.append(f"{label}[{i}]: rhythm % non-zero ({_r}) with an empty base")
        # A POOLED rhythm base counts enrolments (FLW x cohort), so it may exceed the unique-FLW
        # started count. Only an unpooled series must stay within it.
        if not c.get("rhythm_pooled") and _rb > c["started"][i]:
            _eng_bad.append(f"{label}[{i}]: rhythm base {_rb} exceeds started {c['started'][i]}")
    if any(c["started"][i] > c["started"][i + 1] for i in range(len(c["started"]) - 1)):
        _eng_bad.append(f"{label}: started not monotonic")
    if c["total_started"] != (c["started"][-1] if c["started"] else 0):
        _eng_bad.append(f"{label}: total_started != started[-1]")
    if expect_started is not None and c["total_started"] != expect_started:
        _eng_bad.append(f"{label}: total_started {c['total_started']} != {expect_started}")


for sg, c in _eng.items():
    _eng_consistent(sg, c, expect_started=len(_eng_started.get(sg, ())))
chk("cohortEngagement: Panel3==Panel1, %~100, monotonic, ties to distinct started FLWs (all subgroups)",
    not _eng_bad, "; ".join(_eng_bad[:6]))

# by-LLO splits: each split internally consistent AND COWACDI+EHA started == the all-LLO started
_engllo = dd.get("cohortEngagementLLO", {})
_llo_bad = []
for sg, splits in _engllo.items():
    for llo, c in splits.items():
        _eng_before = len(_eng_bad)
        _eng_consistent(f"{sg}/{llo}", c)
        _llo_bad += _eng_bad[_eng_before:]
    all_c = _eng.get(sg)
    if all_c:
        split_sum = sum(splits[llo]["total_started"] for llo in splits)
        if split_sum != all_c["total_started"]:
            _llo_bad.append(f"{sg}: COWACDI+EHA started {split_sum} != all {all_c['total_started']}")
chk("cohortEngagementLLO: each LLO split consistent AND COWACDI+EHA started == all-LLO started",
    not _llo_bad, "; ".join(_llo_bad[:6]))

# ---- FLW-level analysis (flwEngagement): ties to canonical distinct-started-FLW count + %s sum ~100 ----
_fe = dd.get("flwEngagement", {})
_fe_bad = []
_distinct_started = len({r["connect_id"] for r in bm.rows if r.get("is_started") == "Y"})
if _fe.get("n_flws") != _distinct_started:
    _fe_bad.append(f"n_flws {_fe.get('n_flws')} != distinct started FLWs {_distinct_started}")
for _k in ("tiers", "personas"):
    _s = sum(t["pct"] for t in _fe.get(_k, []))
    if _fe.get(_k) and not (97 <= _s <= 103):
        _fe_bad.append(f"{_k} pct sum {_s} != ~100")
    if _fe.get(_k) and sum(t["n"] for t in _fe[_k]) != _fe["n_flws"]:
        _fe_bad.append(f"{_k} counts != n_flws")
for _cc in ("byState", "byType", "byLLO"):
    rows_ = _fe.get(_cc, [])
    if any(not (0 <= r["finished"] <= 100) or not (0 <= r["completion"] <= 1) for r in rows_):
        _fe_bad.append(f"{_cc} out of range")
    if any(not (0 <= r.get("finished_pc", 0) <= 100) for r in rows_):
        _fe_bad.append(f"{_cc} finished_pc out of range")
    # a pooled residual bucket is coverage, never a finding: it must be last and never outrank a real group
    if rows_ and any(r.get("residual") for r in rows_[:-1]):
        _fe_bad.append(f"{_cc} residual row is not last")
    # every FLW must land in some bucket, so the bars describe the whole population
    if rows_ and sum(r["n"] for r in rows_) != _fe.get("n_flws"):
        _fe_bad.append(f"{_cc} covers {sum(r['n'] for r in rows_)} != n_flws {_fe.get('n_flws')}")
# survival: reached must be bounded by the eligible base, and both curves monotone non-increasing
_sv = _fe.get("survival", [])
for i, s in enumerate(_sv):
    if s.get("elig") is not None and s["reached"] > s["elig"]:
        _fe_bad.append(f"survival d={s['d']} reached {s['reached']} > elig {s['elig']}")
    if s.get("pct_elig") is not None and not (0 <= s["pct_elig"] <= 100):
        _fe_bad.append(f"survival d={s['d']} pct_elig {s['pct_elig']} out of range")
    if i and s["reached"] > _sv[i - 1]["reached"]:
        _fe_bad.append(f"survival not monotone at d={s['d']}")
_ds = _fe.get("depthSplit")
if _ds and _ds["hi"]["n"] + _ds["lo"]["n"] != _fe.get("n_flws"):
    _fe_bad.append(f"depthSplit halves {_ds['hi']['n']}+{_ds['lo']['n']} != n_flws {_fe.get('n_flws')}")
# ---- micro block: the FLW-Retention tab computes its drill-down numbers from this client-side, so it
# must agree with the aggregates it sits next to, or the tab silently contradicts the same page.
_mi = _fe.get("micro")
if _mi:
    _n = _mi.get("n")
    if _n != _fe.get("n_flws"):
        _fe_bad.append(f"micro.n {_n} != n_flws {_fe.get('n_flws')}")
    for _k, _col in (_mi.get("col") or {}).items():
        if len(_col) != _n:
            _fe_bad.append(f"micro.col[{_k}] len {len(_col)} != n {_n}")
        _card = len(_mi["dict"].get(_k, []))
        if _card and any(int(ch) >= _card for ch in _col):
            _fe_bad.append(f"micro.col[{_k}] has an index outside its dictionary")
    for _k, _spec in (_mi.get("num") or {}).items():
        if len(_spec["s"]) != _n * _spec["w"]:
            _fe_bad.append(f"micro.num[{_k}] packed len {len(_spec['s'])} != n*w {_n * _spec['w']}")
    # cross-check one categorical dimension against its published aggregate
    if _mi.get("dict", {}).get("state") and _fe.get("byState"):
        _mc = {k: 0 for k in _mi["dict"]["state"]}
        for ch in _mi["col"]["state"]:
            _mc[_mi["dict"]["state"][int(ch)]] += 1
        for r in _fe["byState"]:
            if not r.get("residual") and r["k"] in _mc and _mc[r["k"]] != r["n"]:
                _fe_bad.append(f"micro state {r['k']} n={_mc[r['k']]} != byState n={r['n']}")
chk("flwEngagement: n_flws==distinct started FLWs; tier/persona counts sum to n_flws & %~100; cross-cuts in "
    "range+complete; survival bounded by elig; micro block aligns with the aggregates",
    not _fe_bad, "; ".join(_fe_bad[:6]))

print("=" * 80)
n_pass = sum(results)
n_tot = len(results)
print(f"  TOTAL: {n_pass}/{n_tot} checks passed")
print(f"  RESULT: {'ALL PASS' if n_pass == n_tot else 'FAILURES PRESENT'}")
print("=" * 80)
# Exit non-zero so the orchestrator actually ABORTS on failure. Until 2026-08-07 this gate only
# printed its verdict and returned 0, so refresh_interviews_dashboard.py logged "OK" and published
# anyway — the 2026-08-07 run shipped v140 with 37/38 (a real monotonicity failure) unnoticed.
sys.exit(1 if n_pass != n_tot else 0)
