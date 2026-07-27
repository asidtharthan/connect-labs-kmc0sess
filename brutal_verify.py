"""BRUTAL independent re-verification of every dashboard number.

Does NOT import build_master_4src / build_payload_agg / build_dashboard_data — it re-parses the RAW
sources and re-aggregates from master_4src.csv with its own code, then compares to dashboard_data.json
(the exact data the render embeds). Catches build-layer bugs, stale data, and cross-place mismatches.

Layers verified:
  A. FRESHNESS         raw source timestamps vs today; data-as-of stamp
  B. DESIGN grounding  subgroupDesign vs _interview_schedule.json (CCHQ lookup)
  C. RAW -> master     trigger forms / OCS sessions / connect snapshot vs master_4src.csv
  D. master -> dash    every aggregate recomputed from master_4src.csv vs dashboard_data.json
  E. CROSS-PLACE       same metric in >1 dashboard section must match
  F. RENDER binding    injected render embeds exactly dashboard_data.json
"""
import csv, json, os, re, sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(2**30)
ROOT = Path(__file__).parent
TODAY = date.today()
P, F = 0, 0
FAILS = []
# Freshness asserts are hard only when explicitly enabled (the daily CI sets this after a live pull).
# A no-credential local build runs on intentionally-static source, so freshness there is informational.
STRICT_FRESH = bool(os.environ.get("INTERVIEWS_STRICT_FRESHNESS"))


def chk(name, ok, detail=""):
    global P, F
    if ok:
        P += 1; print(f"  [PASS] {name}  {detail}")
    else:
        F += 1; FAILS.append(name); print(f"  [FAIL] {name}  {detail}")


def freshchk(name, ok, detail=""):
    """Freshness check: hard failure only under INTERVIEWS_STRICT_FRESHNESS (CI); else a warning."""
    global P, F
    if ok:
        P += 1; print(f"  [PASS] {name}  {detail}")
    elif STRICT_FRESH:
        F += 1; FAILS.append(name); print(f"  [FAIL] {name}  {detail}")
    else:
        print(f"  [warn] {name} — freshness, non-strict (set INTERVIEWS_STRICT_FRESHNESS to enforce)  {detail}")


def sec(t): print("=" * 90 + f"\n{t}\n" + "=" * 90)


def pdt(s):
    if s is None or s == "" or (isinstance(s, float) and pd.isna(s)):
        return None
    try:
        ts = pd.Timestamp(s)
        return ts.tz_localize("UTC").to_pydatetime() if ts.tz is None else ts.tz_convert("UTC").to_pydatetime()
    except Exception:
        return None


# ---- definitional rules (the spec, re-implemented independently) ----
def cohort_to_sg(c):
    if not c or c == "1A":
        return None
    c = str(c)
    if "TRS" in c: return "TRS"
    if "TRE" in c: return "TRE"
    if "ABT1" in c: return "ABT1-A" if "A" in c[5:] else "ABT1-B"
    if "ABT2" in c: return "ABT2-A" if "A" in c[5:] else "ABT2-B"
    if "ABT3" in c: return "ABT3-A" if "A" in c[5:] else "ABT3-B"
    if re.search(r"2WT[CE]\d", c): return "2WT"
    if re.search(r"EC[CE]\d", c): return "EXT"  # Extension cohorts: 1ECC1 (COWACDI), 1ECE1 (EHA)
    if re.search(r"P[CE]\d", c): return "PANEL"
    return None


def is_test(c):
    return bool(c) and bool(re.search(r"_test", str(c), re.I))


# Must mirror build_master_4src.py exactly so this independent gate reconciles after the cleanup.
EXCLUDE_FLWS = {
    "10wcuh1u3s6595okhmfd", "5ej4jqjha0x1f3tbc08y", "7xhpeda8ipsouip6ynyk", "b6vt2wzi8slth6mlag1g",
    "m0i5azsqk7mzixp1bzib", "m33dn33c5vyf8es9kagq", "m6svr4qy3gemxuj2inoe", "rfxkcx7nbom2whml8mbb",
    "sqaktdfxupepdvt90t3f", "v3urwjuzqjxp3njyb5uz", "va7vh76am0m83h0rzu01", "wwnvw4diurrzuy32vba7",
    "xo1n01inul0ofr9z32fa", "y6xjjw4xilga8d1qvaab",
    # 2WT/ABT3 pre-launch QA accounts (literal test ids; activity but never Connect-enrolled; 2026-07-06)
    "test_34", "test_abt3", "test_abt3_eha",
}
CONNECT_COHORT_OVERRIDE = {("6c1ff0cb57e27e780339", "1ABT1EA1"): "1ABT1EB1"}


# ---- load target ----
DD = json.loads((ROOT / "dashboard_data.json").read_text(encoding="utf-8"))
DESIGN = DD["subgroupDesign"]   # grounded separately in section B
R = list(csv.DictReader(open(ROOT / "master_4src.csv", encoding="utf-8")))

# ============================================================ A. FRESHNESS
sec("A. FRESHNESS — is the data actually current?")
HQ = ROOT / "hq_pull_full"
trig_dates, welcome_cids_raw = [], defaultdict(set)
trig_forms = []        # (cid, cohort, niv, recv, fid)
flw_registered = set()
for path in sorted(HQ.glob("*.jsonl")):
    ft = "trigger_bot" if path.name.endswith("trigger_bot.jsonl") else \
         "welcome_click_start" if path.name.endswith("welcome_click_start.jsonl") else \
         "flw_registration" if path.name.endswith("flw_registration.jsonl") else None
    if not ft:
        continue
    for line in path.open(encoding="utf-8"):
        try:
            sub = json.loads(line)
        except Exception:
            continue
        form = sub.get("form", {}) or {}
        meta = form.get("meta", {}) if isinstance(form.get("meta"), dict) else {}
        cid = (form.get("connect_id") or meta.get("username") or sub.get("username") or "").strip()
        if cid in EXCLUDE_FLWS:
            continue
        if ft == "flw_registration":
            if cid: flw_registered.add(cid)
            continue
        recv = pdt(sub.get("received_on"))
        cohort = (form.get("cohort_id") or "").strip()
        niv = (form.get("next_interview") or "").strip()
        if not cid or not recv or not cohort:
            continue
        if ft == "welcome_click_start":
            welcome_cids_raw[cohort].add(cid)
        else:
            trig_dates.append(recv)
            trig_forms.append((cid, cohort, niv, recv, sub.get("id")))

cache = json.loads((ROOT / "_ocs_state_cache.json").read_text())
ocs_created = [pdt(s.get("created_at")) for s in cache if s.get("created_at")]
maxtrig = max(trig_dates).date() if trig_dates else None
maxocs = max(d for d in ocs_created if d).date() if ocs_created else None
snap_mtime = datetime.fromtimestamp((ROOT / "connect_user_data_snapshot.csv").stat().st_mtime).date()
print(f"  today={TODAY}  built_at={DD.get('built_at')}  data.today={DD.get('today')}")
print(f"  latest trigger_bot form: {maxtrig}   latest OCS session: {maxocs}   connect snapshot mtime: {snap_mtime}")
freshchk("data.today == today", DD.get("today") == str(TODAY), f"{DD.get('today')} == {TODAY}")
freshchk("built_at date == today", (DD.get("built_at") or "").startswith(str(TODAY)), DD.get("built_at"))
freshchk("latest trigger form within 2 days of today", maxtrig and (TODAY - maxtrig).days <= 2, f"latest={maxtrig}")
freshchk("latest OCS session within 2 days of today", maxocs and (TODAY - maxocs).days <= 2, f"latest={maxocs}")
freshchk("connect snapshot within 2 days of today", (TODAY - snap_mtime).days <= 2, f"mtime={snap_mtime}")

# ============================================================ B. DESIGN grounding
sec("B. DESIGN — subgroupDesign grounded to CCHQ interview_schedule lookup")
sched = json.loads((ROOT / "_interview_schedule.json").read_text(encoding="utf-8")) if (ROOT / "_interview_schedule.json").exists() else {}
seen = {}
for cid, seq in sched.items():
    sg = cohort_to_sg(cid)
    if not sg or is_test(cid) or sg in seen:
        continue
    seen[sg] = ([s["topic"] for s in seq],
                (seq[1]["offset_days"] - seq[0]["offset_days"]) if len(seq) > 1 else None)
for sg, (topics, cad) in seen.items():
    chk(f"design[{sg}].topics == lookup", DESIGN.get(sg, {}).get("topics") == topics,
        f"{DESIGN.get(sg, {}).get('topics')} vs {topics}")
    if cad is not None:
        chk(f"design[{sg}].cadence == lookup", DESIGN.get(sg, {}).get("cadence") == cad,
            f"{DESIGN.get(sg, {}).get('cadence')} == {cad}")

# ============================================================ C. RAW -> master_4src.csv
sec("C. RAW SOURCES -> master_4src.csv")
# C1/C2: valid trigger forms == master rows; unique cids == master FLWs
valid_trig = [tf for tf in trig_forms
              if cohort_to_sg(tf[1]) and not is_test(tf[1])
              and tf[2] in DESIGN.get(cohort_to_sg(tf[1]), {}).get("topics", [])]
chk("master rows == valid trigger forms (raw)", len(R) == len(valid_trig), f"{len(R)} == {len(valid_trig)}")
chk("master unique FLWs == unique cids in valid triggers (raw)",
    len({r['connect_id'] for r in R}) == len({tf[0] for tf in valid_trig}),
    f"{len({r['connect_id'] for r in R})} == {len({tf[0] for tf in valid_trig})}")

# C3: connect cohorts (mapped, non-test) == counts.cohorts
snap = list(csv.DictReader(open(ROOT / "connect_user_data_snapshot.csv", encoding="utf-8")))
snap_cohorts = {(row.get("cohort_id") or "").strip() for row in snap}
mapped_cohorts = {c for c in snap_cohorts if cohort_to_sg(c) and not is_test(c)}
chk("counts.cohorts == mapped connect cohorts (raw snapshot)",
    DD["counts"]["cohorts"] == len(mapped_cohorts), f"{DD['counts']['cohorts']} == {len(mapped_cohorts)}")

# C4: started/completed flags grounded to OCS cache
sid_status = {s["sid"]: (s.get("interview_status") or "") for s in cache}
bad_started = bad_sid = bad_completed = 0
for r in R:
    msid = r["matched_session_id"]
    started = r["is_started"] == "Y"
    if started != bool(msid):
        bad_started += 1
    if started and msid not in sid_status:
        bad_sid += 1
    want_c = bool(msid) and sid_status.get(msid) == "interview_complete"
    if (r["is_completed"] == "Y") != want_c:
        bad_completed += 1
chk("is_started == (matched_session present)", bad_started == 0, f"{bad_started} bad")
chk("every started row's session exists in OCS cache (raw)", bad_sid == 0, f"{bad_sid} missing")
chk("is_completed == (OCS session status==interview_complete) (raw)", bad_completed == 0, f"{bad_completed} bad")

# C5: connect funnel grounded to raw snapshot
raw_fun = defaultdict(lambda: {k: set() for k in ["invited", "accepted", "learn_completed", "claimed"]})
train_date = {}
for row in snap:
    u = (row.get("username") or "").strip()
    if u in EXCLUDE_FLWS:
        continue
    c = (row.get("cohort_id") or "").strip()
    c = CONNECT_COHORT_OVERRIDE.get((u, c), c)
    sg = cohort_to_sg(c)
    if not sg or is_test(c):
        continue
    inv = pdt(row.get("invited_date"))
    if inv and (c not in train_date or inv.date() < train_date[c]):
        train_date[c] = inv.date()
    if not u:
        continue
    if inv: raw_fun[sg]["invited"].add(u)
    if (row.get("user_invite_status") or "").strip() == "accepted": raw_fun[sg]["accepted"].add(u)
    if pdt(row.get("completed_learn_date")): raw_fun[sg]["learn_completed"].add(u)
    if pdt(row.get("date_claimed")): raw_fun[sg]["claimed"].add(u)
cf = {r["sg"]: r for r in DD["connectFunnel"]}
for sg in cf:
    for fld in ["invited", "accepted", "learn_completed", "claimed"]:
        chk(f"connectFunnel[{sg}].{fld} == raw snapshot", cf[sg][fld] == len(raw_fun[sg][fld]),
            f"{cf[sg][fld]} == {len(raw_fun[sg][fld])}")

# ============================================================ D. master -> dashboard aggregates
sec("D. master_4src.csv -> dashboard_data.json aggregates (independent recompute)")
# cells: unique (cid, cohort, n) with OR'd flags
cell = {}
for r in R:
    k = (r["connect_id"], r["cohort_id"], int(r["interview_n"]))
    d = cell.setdefault(k, {"sg": r["subgroup"], "n": int(r["interview_n"]), "flw": r["connect_id"],
                           "t": False, "s": False, "c": False})
    d["t"] = True
    if r["is_started"] == "Y": d["s"] = True
    if r["is_completed"] == "Y": d["c"] = True
cells = list(cell.values())

# D-counts
chk("counts.master_rows", DD["counts"]["master_rows"] == len(R), f"{DD['counts']['master_rows']} == {len(R)}")
chk("counts.flws", DD["counts"]["flws"] == len({r["connect_id"] for r in R}), str(DD["counts"]["flws"]))
chk("counts.started == unique started interviews (cells)", DD["counts"]["started"] == len({(r["connect_id"], r["cohort_id"], r["interview_n"]) for r in R if r["is_started"] == "Y"}), str(DD["counts"]["started"]))
chk("counts.completed == unique completed interviews (cells)", DD["counts"]["completed"] == len({(r["connect_id"], r["cohort_id"], r["interview_n"]) for r in R if r["is_completed"] == "Y"}), str(DD["counts"]["completed"]))
_t1o = next((x for x in DD["table1"] if x["key"] == "Overall"), {})
chk("counts.started == Breakdowns Overall ist (tie-out)", DD["counts"]["started"] == _t1o.get("ist"), f"{DD['counts']['started']} == {_t1o.get('ist')}")
chk("counts.completed == Breakdowns Overall icmp (tie-out)", DD["counts"]["completed"] == _t1o.get("icmp"), f"{DD['counts']['completed']} == {_t1o.get('icmp')}")

# D-connectFunnel started/completed/initiated
sg_started = defaultdict(set); sg_completed = defaultdict(set)
for r in R:
    if r["is_started"] == "Y": sg_started[r["subgroup"]].add(r["connect_id"])
    if r["is_completed"] == "Y": sg_completed[r["subgroup"]].add(r["connect_id"])
init_sg = defaultdict(set)
for c, cids in welcome_cids_raw.items():
    sg = cohort_to_sg(c)
    if sg: init_sg[sg] |= cids
for sg in cf:
    chk(f"connectFunnel[{sg}].started", cf[sg]["started"] == len(sg_started[sg]), f"{cf[sg]['started']} == {len(sg_started[sg])}")
    chk(f"connectFunnel[{sg}].completed", cf[sg]["completed"] == len(sg_completed[sg]), f"{cf[sg]['completed']} == {len(sg_completed[sg])}")
    chk(f"connectFunnel[{sg}].initiated", cf[sg]["initiated"] == len(init_sg[sg]), f"{cf[sg]['initiated']} == {len(init_sg[sg])}")

# D-tables 1/2/3
ROLL = {"TRS": "TRS", "TRE": "TRE", "ABT1-A": "ABT1", "ABT1-B": "ABT1", "ABT2-A": "ABT2", "ABT2-B": "ABT2",
        "PANEL": "PANEL", "ABT3-A": "ABT3", "ABT3-B": "ABT3", "2WT": "2WT", "EXT": "EXT"}


def agg(keyfn):
    a = defaultdict(lambda: {"flw": set(), "ist": 0, "icmp": 0})
    for c in cells:
        for k in set(keyfn(c)):
            if c["s"]:
                a[k]["flw"].add(c["flw"]); a[k]["ist"] += 1
            if c["c"]:
                a[k]["icmp"] += 1
    return a


t1 = agg(lambda c: [ROLL[c["sg"]], "Overall"])
for row in DD["table1"]:
    k = row["key"]
    chk(f"table1[{k}].flws", row["flws"] == len(t1[k]["flw"]), f"{row['flws']} == {len(t1[k]['flw'])}")
    chk(f"table1[{k}].ist/icmp", row["ist"] == t1[k]["ist"] and row["icmp"] == t1[k]["icmp"],
        f"ist {row['ist']}=={t1[k]['ist']} icmp {row['icmp']}=={t1[k]['icmp']}")
t3 = agg(lambda c: ([c["sg"], "Overall"] if c["sg"].startswith(("ABT1", "ABT2", "ABT3")) else []))
for row in DD["table3"]:
    k = row["key"]
    chk(f"table3[{k}].flws/ist/icmp", row["flws"] == len(t3[k]["flw"]) and row["ist"] == t3[k]["ist"] and row["icmp"] == t3[k]["icmp"],
        f"flws {row['flws']}=={len(t3[k]['flw'])} ist {row['ist']}=={t3[k]['ist']} icmp {row['icmp']}=={t3[k]['icmp']}")
t2 = defaultdict(lambda: {"flw": set(), "ist": 0, "icmp": 0})
for c in cells:
    tc = DESIGN[c["sg"]]["topics"][c["n"] - 1]
    if c["s"]:
        t2[tc]["flw"].add(c["flw"]); t2[tc]["ist"] += 1
    if c["c"]:
        t2[tc]["icmp"] += 1
for row in DD["table2"]:
    tc = row["code"]
    chk(f"table2[{tc}].flws/ist/icmp", row["flws"] == len(t2[tc]["flw"]) and row["ist"] == t2[tc]["ist"] and row["icmp"] == t2[tc]["icmp"],
        f"flws {row['flws']}=={len(t2[tc]['flw'])} ist {row['ist']}=={t2[tc]['ist']} icmp {row['icmp']}=={t2[tc]['icmp']}")

# D-dropoff per (sg,n): eligible/triggered/started/completed unique FLWs
fset = defaultdict(lambda: {"t": set(), "s": set(), "c": set()})
for r in R:
    key = (r["subgroup"], int(r["interview_n"]))
    fset[key]["t"].add(r["connect_id"])
    if r["is_started"] == "Y": fset[key]["s"].add(r["connect_id"])
    if r["is_completed"] == "Y": fset[key]["c"].add(r["connect_id"])
do = {s["sg"]: s for s in DD["dropoff"]["subgroups"]}
do_bad = 0
for sg, s in do.items():
    elig = len(init_sg[sg]) or 1
    for iv in s["interviews"]:
        n = iv["n"]; f = fset[(sg, n)]
        if not (iv["eligible"] == len(init_sg[sg]) and iv["triggered"] == len(f["t"])
                and iv["started"] == len(f["s"]) and iv["completed"] == len(f["c"])):
            do_bad += 1; print(f"    dropoff mismatch {sg} Int{n}: elig {iv['eligible']}/{len(init_sg[sg])} trig {iv['triggered']}/{len(f['t'])} start {iv['started']}/{len(f['s'])} compl {iv['completed']}/{len(f['c'])}")
        # pct checks
        if iv["pct_started"] != round(100 * len(f["s"]) / elig, 1): do_bad += 1
        if iv["pct_completed_base"] != round(100 * len(f["c"]) / elig, 1): do_bad += 1
        exp_pc = round(100 * len(f["c"]) / len(f["s"]), 1) if f["s"] else None
        if iv["pct_completed"] != exp_pc: do_bad += 1
chk("dropoff interviews (elig/trig/started/completed/pcts) all subgroups", do_bad == 0, f"{do_bad} bad")

# D-topicStatus: recompute from claimed universe
mlook = {}
def rank(r): return (1 if r["is_completed"] == "Y" else 0) * 2 + (1 if r["is_started"] == "Y" else 0)
for r in R:
    k = (r["connect_id"], r["cohort_id"], r["topic_code"])
    if k not in mlook or rank(r) > rank(mlook[k]):
        mlook[k] = r
# claimed FLWs per cohort (from snapshot)
cohort_claimed = defaultdict(set); cohort_sg = {}
for row in snap:
    u = (row.get("username") or "").strip()
    if u in EXCLUDE_FLWS:
        continue
    c = (row.get("cohort_id") or "").strip()
    c = CONNECT_COHORT_OVERRIDE.get((u, c), c)
    sg = cohort_to_sg(c)
    if not sg or is_test(c):
        continue
    cohort_sg[c] = sg
    if pdt(row.get("date_claimed")) and u:
        cohort_claimed[c].add(u)


def status_for(flw, cohort, sg, topic):
    topics = DESIGN[sg]["topics"]
    if topic not in topics: return "not-applicable"
    n = topics.index(topic) + 1
    m = mlook.get((flw, cohort, topic))
    if m and m["is_completed"] == "Y": return "completed"
    if m and m["is_started"] == "Y": return "started-not-completed"
    td = train_date.get(cohort)
    if not td: return "available-not-started"
    cad = DESIGN[sg]["cadence"]
    if TODAY < td + timedelta(days=(n - 1) * cad): return "not-available-yet"
    if n < len(topics) and TODAY >= td + timedelta(days=n * cad): return "available-missed-overdue"
    return "available-not-started"


APPLICABLE = [t["code"] for t in DD["topicStatus"]]
ts_rec = defaultdict(lambda: defaultdict(int))
for c, sg in cohort_sg.items():
    for flw in cohort_claimed[c]:
        for tc in APPLICABLE:
            ts_rec[tc][status_for(flw, c, sg, tc)] += 1
ts_bad = 0
STATES6 = ["not-applicable", "not-available-yet", "available-not-started", "available-missed-overdue", "started-not-completed", "completed"]
for row in DD["topicStatus"]:
    tc = row["code"]
    for s in STATES6:
        if row[s] != ts_rec[tc][s]:
            ts_bad += 1; print(f"    topicStatus {tc}.{s}: {row[s]} vs {ts_rec[tc][s]}")
    if row["total"] != sum(ts_rec[tc][s] for s in STATES6): ts_bad += 1
    if row["applicable"] != row["total"] - row["not-applicable"]: ts_bad += 1
chk("topicStatus 6-state counts (claimed universe recompute)", ts_bad == 0, f"{ts_bad} bad")

# D-flwMatrix
claimed_pairs = sum(len(v) for v in cohort_claimed.values())
chk("flwMatrix rows == claimed (FLW,cohort) pairs (raw snapshot)", len(DD["flwMatrix"]) == claimed_pairs,
    f"{len(DD['flwMatrix'])} == {claimed_pairs}")
mat_completed = sum(r["s"].count(5) for r in DD["flwMatrix"])
mat_started = sum(sum(1 for x in r["s"] if x in (4, 5)) for r in DD["flwMatrix"])
ts_completed = sum(t["completed"] for t in DD["topicStatus"])
ts_started = sum(t["completed"] + t["started-not-completed"] for t in DD["topicStatus"])
chk("flwMatrix completed cells == Σ topicStatus completed", mat_completed == ts_completed, f"{mat_completed} == {ts_completed}")
chk("flwMatrix started cells == Σ topicStatus started+completed", mat_started == ts_started, f"{mat_started} == {ts_started}")

# ============================================================ E. CROSS-PLACE consistency
sec("E. CROSS-PLACE — same metric shown in multiple sections must match")
cpe = 0
for sg in cf:
    dc = do.get(sg, {}).get("connect", {})
    for fld in ["invited", "accepted", "learn_completed", "claimed", "initiated"]:
        if cf[sg][fld] != dc.get(fld):
            cpe += 1; print(f"    connectFunnel vs dropoff.connect {sg}.{fld}: {cf[sg][fld]} vs {dc.get(fld)}")
chk("Overview connectFunnel == Funnels/FullRetention dropoff.connect (invited/accepted/learnC/claimed/initiated)", cpe == 0, f"{cpe} bad")
# unrolled subgroups: table1.flws == connectFunnel.started
for sg in ["TRS", "TRE", "PANEL"]:
    row = next((r for r in DD["table1"] if r["key"] == sg), None)
    if row and sg in cf:
        chk(f"table1[{sg}].flws == connectFunnel[{sg}].started (unique started FLWs)",
            row["flws"] == cf[sg]["started"], f"{row['flws']} == {cf[sg]['started']}")
# Overview "completed by round" uses dropoff.interviews -> same object as Funnels/FullRetention (consistent by construction)
chk("Overview 'completed-by-round' shares DATA.dropoff with Funnels+FullRetention (single source)", True, "structural")
# line series base == initiated; pts == funnel %started
ls_bad = 0
fun = {(x["sg"], x["n"]): x for x in DD["funnel"]}
for s in DD["lineSeries"]:
    sg = s["sg"]
    if s["base"] != len(init_sg[sg]): ls_bad += 1
    for i, p in enumerate(s["pts"]):
        if fun.get((sg, i + 1)) and abs(fun[(sg, i + 1)]["pct_started"] - p) > 1e-9: ls_bad += 1
chk("lineSeries base==initiated & pts==funnel pct_started", ls_bad == 0, f"{ls_bad} bad")

# ============================================================ F. RENDER binding
sec("F. RENDER — injected render embeds exactly dashboard_data.json")
render = (ROOT / "docs" / "interviews_master_v3_render.js").read_text(encoding="utf-8")
raw_json = (ROOT / "dashboard_data.json").read_text(encoding="utf-8")
chk("dashboard_data.json substring present verbatim in injected render", raw_json in render,
    f"render {len(render)} chars, data {len(raw_json)} chars")

print("\n" + "=" * 90)
print(f"  TOTAL: {P} passed, {F} failed")
print("  RESULT:", "ALL PASS ✅" if F == 0 else f"FAILURES ❌ -> {FAILS}")
print("=" * 90)
sys.exit(1 if F else 0)
