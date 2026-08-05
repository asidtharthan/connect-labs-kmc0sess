"""Audit dashboard_data.json (the data the render embeds) — independent recompute vs the
master (build_master_4src) and vs the audit_e2e-validated payload_agg.json. All PASS required.
Run after build_dashboard_data.py.  UTF-8: run with PYTHONUTF8=1.
"""
import json
from collections import defaultdict

import build_master_4src as bm

STATES_NA = [
    "completed",
    "started-not-completed",
    "available-missed-overdue",
    "available-not-started",
    "not-available-yet",
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
         "PANEL": "PANEL", "ABT3-A": "ABT3", "ABT3-B": "ABT3", "2WT": "2WT", "EXT": "EXT"}


def _avg(pred):
    hw = hm = 0
    for r in bm.rows:
        if r["is_started"] == "Y" and pred(r):
            hw += int(r.get("session_human_words", 0) or 0)
            hm += int(r.get("session_human_msgs", 0) or 0)
    return round(hw / hm, 1) if hm else None


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
           "started-not-completed", "completed"]
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
    # every claimed (cohort,flw) gets exactly one of the 6 states per topic -> total == claimed_pairs (constant)
    if t["total"] != claimed_pairs:
        ts_ok = False
        ts_bad += 1
chk("topicStatus 6 states==payload, total==Σstates==claimed_pairs, applicable==total-NA", ts_ok, f"{ts_bad} bad")
# per-cohort topic breakdown: every cohort row's total == its 5 applicable-state sum; cohorts only where topic applies
tsc_bad = 0
for tc, rows_c in dd["topicStatusCohort"].items():
    for rc in rows_c:
        if rc["total"] != sum(rc[s] for s in STATES_NA):
            tsc_bad += 1
        sg = bm.cohort_to_sg(rc["cohort"])
        if tc not in bm.SUBGROUP_DESIGN[sg]["topics"]:
            tsc_bad += 1
chk("topicStatusCohort: row total==Σ5states & topic applicable in cohort", tsc_bad == 0, f"{tsc_bad} bad")
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
mono = all(
    cf[sg]["invited"] >= cf[sg]["accepted"] >= cf[sg]["learn_completed"] >= cf[sg]["claimed"] for sg in SG_ORDER
)
chk("connect funnel monotonic invited>=accepted>=learnC>=claimed", mono)
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
        if round(1000 * st / base) / 10 != p:
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
chk("flwMatrix row count == claimed (FLW,cohort) pairs", len(fm) == claimed_pairs, f"{len(fm)} == {claimed_pairs}")
cell_bad = 0
for r in fm:
    topics = bm.SUBGROUP_DESIGN.get(r["g"], {}).get("topics", [])
    if len(r["s"]) != len(topics):
        cell_bad += 1
    if any((not isinstance(x, int)) or x < 1 or x > 5 for x in r["s"]):
        cell_bad += 1  # cells for in-design topics are always states 1..5 (never not-applicable)
chk("flwMatrix: cells align to subgroup topics & are states 1..5", cell_bad == 0, f"{cell_bad} bad rows")
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
    if f["started_di"] > f["started"] or f["pct_started_di"] != round(100 * f["started_di"] / f["elig"], 1):
        dq_bad += 1
chk("funnel started_di<=started & pct_started_di consistent (all rows)", dq_bad == 0, f"{dq_bad} bad")
ldi_bad = 0
for sg in SG_ORDER:
    for i, p in enumerate(ls[sg].get("pts_di", [])):
        if fmap2[sg][i + 1]["pct_started_di"] != p:
            ldi_bad += 1
chk("lineSeries pts_di == funnel pct_started_di", ldi_bad == 0, f"{ldi_bad} mismatched points")
cb_bad = sum(1 for f in dd["funnel"] if f["pct_completed_base"] != round(100 * f["completed"] / f["elig"], 1))
chk("funnel pct_completed_base == 100*completed/eligible (all rows)", cb_bad == 0, f"{cb_bad} bad")

# ---- Cohort Engagement (3-panel): internal consistency + tie-out to canonical started count ----
_eng = dd.get("cohortEngagement", {})
_eng_started = defaultdict(set)
for r in bm.rows:
    if r.get("is_started") == "Y" and r.get("matched_session_id"):
        _eng_started[r["subgroup"]].add(r["connect_id"])
_eng_started["ALL"] = set().union(*_eng_started.values()) if _eng_started else set()  # program-wide distinct
_eng_bad = []
_eng_keys = ("weeks", "started", "finished_pct", "steady_pct", "incons_pct", "drop_pct",
             "finished", "new", "active", "slow", "quiet")


def _eng_consistent(label, c, expect_started=None):
    """Internal invariants for one engagement series; append issues to _eng_bad."""
    if len({len(c[k]) for k in _eng_keys}) != 1:
        _eng_bad.append(f"{label}: array lengths differ"); return
    for i in range(len(c["weeks"])):
        if c["finished"][i] + c["new"][i] + c["active"][i] + c["slow"][i] + c["quiet"][i] != c["started"][i]:
            _eng_bad.append(f"{label}[{i}]: Panel3 stack != Panel1 started")
        if not (99 <= c["finished_pct"][i] + c["steady_pct"][i] + c["incons_pct"][i] + c["drop_pct"][i] <= 101):
            _eng_bad.append(f"{label}[{i}]: quality % sum != 100")
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

print("=" * 80)
n_pass = sum(results)
n_tot = len(results)
print(f"  TOTAL: {n_pass}/{n_tot} checks passed")
print(f"  RESULT: {'ALL PASS' if n_pass == n_tot else 'FAILURES PRESENT'}")
print("=" * 80)
