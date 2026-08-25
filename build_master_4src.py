"""Build the COMPLETE 4-source master dataset and reconcile vs master_v7_2026-06-10.csv.

Sources, all interlocked on connect_id:
  1. Connect  : <cohort>_audit/user_data.csv -> funnel flags + training_date (earliest invited_date)
  2. CCHQ Trigger Bot : hq_pull_full/*__trigger_bot.jsonl  (V7 anchor)
  3. CCHQ Welcome     : hq_pull_full/*__welcome_click_start.jsonl  (eligible / initiated denominators)
  4. OCS sessions     : live API state cache (_ocs_state_cache.json)  (started/completed)

Pure functions copied VERBATIM from build_dropoff_v7f.py (the canonical builder).
Reconciles every column reproducible from live state (excludes session_human_msgs/_words,
which need message content not on the OCS list payload). is_released uses TODAY=2026-06-10
to match the baseline snapshot.
"""
import csv as _csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
HQ_DIR = ROOT / "hq_pull_full"
CACHE = ROOT / "_ocs_state_cache.json"
TAGS_CACHE = ROOT / "_ocs_tags_cache.json"   # {sid: [tags]} from pull_ocs_tags.py (full daily scan)

# OCS review verdicts, most specific first. `suspected_ai` is checked BEFORE acceptable/unacceptable
# because a session can carry both, and "we think the FLW pasted an AI answer" is the more important
# fact about it. Everything else OCS puts in `tags` (Run-on Session, n/a, Test) is bookkeeping, not a
# verdict, and must never be mixed in - that is what makes "how many were acceptable" unanswerable.
_REVIEW_ORDER = ("suspected_ai", "unacceptable", "acceptable")


def _review_status(sid, tags_by_sid):
    """One of suspected_ai / unacceptable / acceptable / not-reviewed, for a matched session.

    ABSENCE of a verdict is itself the answer, and a meaningful one: on 2026-08-25, 931 of the 9,624
    sessions OCS marks interview_complete (10%) carried no verdict at all. Filtering those away
    silently is exactly what made the OCS screen read 8,6xx against the dashboard's 9,4xx, so
    not-reviewed is a first-class value here rather than a blank.
    """
    if not sid:
        return ""
    ts = set(tags_by_sid.get(sid) or ())
    for v in _REVIEW_ORDER:
        if v in ts:
            return v
    return "not-reviewed"
WORDS_CACHE = ROOT / "_ocs_words_cache.json"  # {sid: {human_words, human_msgs}} from pull_ocs_words.py
BASELINE = ROOT / "master_v7_2026-06-10.csv"
TODAY = date.today()  # dynamic: is_released / time-gating reflect the real run date
_csv.field_size_limit(2**30)

ALL_DOMAINS = [
    "connect-interview-cowacdi",
    "connect-interview-eha",
    "connect-interview-cowac-2",
    "connect-interview-eha-2",
    # Panel (Long-Term Engagement) — separate domains, cohorts 1PC1 (COWACDI) / 1PE1 (EHA).
    "ccc-interview-panel-cowac",
    "ccc-interview-panel-eha",
    # 2WT (2-Week Test) — separate domains, cohorts 2WTC1 (COWACDI) / 2WTE1 (EHA).
    "connect-int-ng-cowac-2wt",
    "connect-int-ng-eha-2wt",
    # ABT3 (Interview Length A/B test) — separate domains, cohorts 3ABT3C* (COWACDI) / 3ABT3E* (EHA).
    "ccc-interview-abtest3-cow",
    "ccc-interview-abtest3-eha",
    # Extension cohorts — separate domains, cohorts 1ECC1 (COWACDI) / 1ECE1 (EHA).
    "connect-int-ng-cowac-ext",
    "connect-int-ng-eha-ext",
    # NPS (Net Promoter Score) - single-interview cohort 1NPS1, COWACDI only (no EHA domain exists).
    "connect-int-ng-cowac-nps",
]

# FALLBACK only — the live SUBGROUP_DESIGN is derived from the CommCare HQ `interview_schedule`
# lookup table (_interview_schedule.json, via pull_hq_interview_schedule.py), the bot's runtime
# source of truth. This dict is used only for subgroups the lookup doesn't cover (e.g. ABT3 before
# it launches). NOTE: the PANEL entry here is the OLD/stale 11-topic guess; the real schedule (13
# topics 7,1,2,12,3,4,5,6,C,10,11,8,13) comes from the lookup.
_FALLBACK_DESIGN = {
    "TRS": {"topics": ["A", "B"], "cadence": 7},
    "TRE": {"topics": ["A", "B", "C", "D", "E"], "cadence": 3},
    "ABT1-A": {"topics": ["1", "2", "3", "4"], "cadence": 7},
    "ABT1-B": {"topics": ["1", "2", "3", "4"], "cadence": 7},
    "ABT2-A": {"topics": ["1", "2"], "cadence": 14},
    "ABT2-B": {"topics": ["1", "2", "5", "6", "7", "8", "9", "3"], "cadence": 3},
    "PANEL": {"topics": ["7", "1", "2", "3", "4", "5", "6", "8", "9", "10", "11"], "cadence": 4},
    "ABT3-A": {"topics": ["8S", "13", "10S", "11S"], "cadence": 3},
    "ABT3-B": {"topics": ["8L", "13L", "10L", "11L"], "cadence": 3},
    "2WT": {"topics": ["14"], "cadence": 14},  # 2-Week Test: single interview on topic 14; live design from CCHQ lookup
    "NPS": {"topics": ["101"], "cadence": 9},  # NPS: single terminal interview on topic 101 (cohort window 2026-08-21..2026-08-30); live design from CCHQ lookup
    "EXT": {"topics": ["11", "C", "99"], "cadence": 3},  # Extension: 3 interviews (Water & Diarrhea 2, Nutrition, Qualitative); live design from CCHQ lookup
}
# Authoritative map locked to master_v7_2026-06-10 (incl. the 'Prevalance' typo in C).
TOPIC_NAMES = {
    "A": "Community Demographics",
    "B": "Malaria",
    "C": "Nutrition Prevalance and Programs",
    "D": "Water & Diarrhea",
    "E": "Community & FLW Profile",
    "1": "Seasonal Malaria Chemoprevention",
    "2": "Seasonal Malaria Chemoprevention 2",
    "3": "Bed Net Usage",
    "4": "Health Worker Experience",
    "5": "Family Planning",
    "6": "Vitamin A Supplementation",
    "7": "Vaccines",
    "8": "Antibiotics and ACT Use",
    "9": "Medicine Quality & Counterfeiting",
    "10": "Malaria 2",
    "11": "Water & Diarrhea 2",
    "12": "Community & FLW Profile 2",
    "13": "Medicine Quality & Counterfeiting 2",
    "14": "Malaria 5",
    # ABT3 (Interview Length A/B test) short/long variants
    "8S": "Antibiotics and ACT Use 2",
    "8L": "Antibiotics and ACT Use 3",
    "10S": "Malaria 3",
    "10L": "Malaria 4",
    "11S": "Water & Diarrhea 3",
    "11L": "Water & Diarrhea 4",
    "13L": "Medicine Quality & Counterfeiting 3",
    "F": "Care Seeking Behavior",
    "G": "Trust, Beliefs & Health Perceptions",
    "99": "Qualitative Interview",  # Extension cohort's 3rd interview (open-ended experience/feedback)
    "101": "NPS",  # NPS cohort's single terminal interview (literal interview_topic value OCS returns)
}
# Question count per topic (Cohort Tracker → Topics_Master). Design metadata for Breakdowns → By Topic.
TOPIC_QUESTIONS = {
    "A": 7, "B": 9, "C": 8, "D": 6, "E": 8,
    "1": 9, "2": 10, "3": 19, "4": 16, "5": 5, "6": 13, "7": 7,
    "8": 10, "9": 5, "10": 8, "11": 10, "12": 13, "13": 7, "14": 20,
    "8S": 7, "8L": 20, "10S": 7, "10L": 20, "11S": 7, "11L": 20, "13L": 20,
    "99": 1,  # Extension qualitative interview: 1 multi-part question
    "101": 9,  # OCS state reports total_questions=1, but that Q1 block holds 9 concatenated sub-questions
}
COHORT_TYPE_MAP = {
    "TRS": "Standard",
    "TRE": "Enhanced",
    "ABT1-A": "ABT1 A",
    "ABT1-B": "ABT1 B",
    "ABT2-A": "ABT2 A",
    "ABT2-B": "ABT2 B",
    "PANEL": "Panel",
    "ABT3-A": "ABT3 A",
    "ABT3-B": "ABT3 B",
    "2WT": "2WT (2-Week Test)",
    "EXT": "Extension",
    "NPS": "NPS (Net Promoter Score)",
}

# Cohorts seen in the data whose id doesn't map to any known subgroup design. Collected (not dropped
# silently) so a newly-launched program type is SURFACED on the dashboard instead of vanishing.
unmapped_cohorts = set()


def cohort_to_sg(c):
    if not c or c == "1A":
        return None
    c = str(c)
    if "TRS" in c:
        return "TRS"
    if "TRE" in c:
        return "TRE"
    if "ABT1" in c:
        return "ABT1-A" if "A" in c[5:] else "ABT1-B"
    if "ABT2" in c:
        return "ABT2-A" if "A" in c[5:] else "ABT2-B"
    if "ABT3" in c:
        return "ABT3-A" if "A" in c[5:] else "ABT3-B"
    if re.search(r"2WT[CE]\d", c):  # 2-Week Test cohorts: 2WTC1 (COWACDI), 2WTE1 (EHA)
        return "2WT"
    if re.search(r"EC[CE]\d", c):  # Extension cohorts: 1ECC1 (COWACDI), 1ECE1 (EHA) — COWACDI+EHA share one EXT subgroup
        return "EXT"
    if re.search(r"NPS\d", c):  # NPS cohorts: 1NPS1 (COWACDI only) - tested before the P[CE]\d Panel pattern
        return "NPS"
    if re.search(r"P[CE]\d", c):  # Panel cohorts: 1PC1 (COWACDI), 1PE1 (EHA) — tight pattern, not a loose "PE" substring
        return "PANEL"


# Test/QA cohorts (e.g. "02_Test", "01_Test" seen in the Panel domains) — drop entirely,
# don't surface them as amber "unmapped" notices on the dashboard.
_TEST_COHORT_RE = re.compile(r"_test", re.IGNORECASE)


def is_test_cohort(c):
    return bool(c) and bool(_TEST_COHORT_RE.search(str(c)))


# FLWs with interview activity (HQ triggers/sessions) but ZERO Connect enrollment across ALL interview
# opportunities — verified 2026-06-25: non-hex connect_ids, active for ~2.5 months (since early April)
# yet never present in any Connect user_data snapshot (06-22/06-24/06-25). Confirmed non-enrolled
# test/manual accounts; dropped from every source so the dashboard counts only real Connect-enrolled
# FLWs. Explicit list (NOT a blanket "no-Connect -> drop" rule) so a snapshot-timing gap can't silently
# drop a real FLW. See brutal-revalidation-2026-06-25 memory.
EXCLUDE_FLWS = {
    "10wcuh1u3s6595okhmfd", "5ej4jqjha0x1f3tbc08y", "7xhpeda8ipsouip6ynyk", "b6vt2wzi8slth6mlag1g",
    "m0i5azsqk7mzixp1bzib", "m33dn33c5vyf8es9kagq", "m6svr4qy3gemxuj2inoe", "rfxkcx7nbom2whml8mbb",
    "sqaktdfxupepdvt90t3f", "v3urwjuzqjxp3njyb5uz", "va7vh76am0m83h0rzu01", "wwnvw4diurrzuy32vba7",
    "xo1n01inul0ofr9z32fa", "y6xjjw4xilga8d1qvaab",
    # 2WT/ABT3 pre-launch QA accounts (literal test ids; HQ interview activity but never Connect-enrolled
    # — absent from the live claimed set and the render; verified 2026-07-06).
    "test_34", "test_abt3", "test_abt3_eha",
}
# Cross-arm cohort mis-tag fix (1 FLW): 6c1ff0cb… was Connect-enrolled in 1ABT1EA1 (ABT1-A) but
# HQ-triggered + completed ALL interviews under 1ABT1EB1 (ABT1-B). ABT1-A/B share identical topics so
# OCS can't distinguish the arms; align his Connect record to the arm where 100% of his interviews ran
# (as-treated). Maps (connect_id, original_cohort) -> corrected_cohort, applied to the Connect snapshot.
CONNECT_COHORT_OVERRIDE = {("6c1ff0cb57e27e780339", "1ABT1EA1"): "1ABT1EB1"}


# ---- live interview design from the CCHQ `interview_schedule` lookup (the bot's runtime truth) ----
# pull_hq_interview_schedule.py writes _interview_schedule.json = {cohort_id: [{n, topic, offset_days}]}.
# We derive SUBGROUP_DESIGN (topics + cadence) per subgroup from it, falling back to _FALLBACK_DESIGN
# for any subgroup the lookup doesn't cover (e.g. ABT3 before launch). cohort_schedule keeps the
# per-cohort offsets (for accurate, cohort-specific release dates / "not yet offered" logic).
cohort_schedule = {}
_sched_path = ROOT / "_interview_schedule.json"
if _sched_path.exists():
    try:
        cohort_schedule = json.loads(_sched_path.read_text(encoding="utf-8"))
    except Exception:
        cohort_schedule = {}


def _derive_subgroup_design():
    design = {sg: dict(v) for sg, v in _FALLBACK_DESIGN.items()}
    seen = {}
    for cid, seq in cohort_schedule.items():
        sg = cohort_to_sg(cid)
        if not sg or is_test_cohort(cid) or sg in seen:
            continue
        offs = [s["offset_days"] for s in seq]
        cad = (offs[1] - offs[0]) if len(offs) > 1 else design.get(sg, {}).get("cadence", 7)
        design[sg] = {"topics": [s["topic"] for s in seq], "cadence": cad}
        seen[sg] = True
    # A subgroup that has LIVE COHORTS but no CCHQ schedule silently falls back to the guess above, and
    # the guesses drift: PANEL's fallback still lists 11 topics while its real schedule has 13. Silently
    # redefining a design changes both the denominator and every deadline, so say so loudly instead.
    _live = {cohort_to_sg(c) for c in cohort_schedule if not is_test_cohort(c)}
    _fellback = sorted(sg for sg in design if sg not in seen and sg in _live)
    if _fellback:
        print(f"[1!] WARNING: no CCHQ schedule for {_fellback} - using the FALLBACK design, which may be "
              f"stale. Check pull_hq_interview_schedule.py ran.")
    for _sg, _v in design.items():
        _fb = _FALLBACK_DESIGN.get(_sg)
        if _sg in seen and _fb and len(_fb["topics"]) != len(_v["topics"]):
            print(f"[1!] NOTE: {_sg} fallback lists {len(_fb['topics'])} interviews but the live CCHQ "
                  f"schedule has {len(_v['topics'])}. The live one is in use; the fallback is stale and "
                  f"would silently redefine the design if the schedule pull ever failed.")
    return design


SUBGROUP_DESIGN = _derive_subgroup_design()


def parse_dt(s):
    if s is None or s == "" or (isinstance(s, float) and pd.isna(s)):
        return None
    try:
        ts = pd.Timestamp(s)
        return ts.tz_localize("UTC").to_pydatetime() if ts.tz is None else ts.tz_convert("UTC").to_pydatetime()
    except Exception:
        return None


def clean_csv(path):
    raw = open(path, encoding="utf-8", errors="replace").read().replace("\x00", "")
    return list(_csv.DictReader(StringIO(raw)))


def pick_best(sessions, after_dt, claimed):
    avail = [s for s in sessions if s["sid"] not in claimed]
    if not avail:
        return None
    after = [s for s in avail if s["first"] >= after_dt]
    if after:
        return min(after, key=lambda s: (0 if s["status"] == "interview_complete" else 1, s["first"]))
    return min(avail, key=lambda s: abs((s["first"] - after_dt).total_seconds()))


# ---------------- 1. Connect ----------------
# Source = per-cohort <cohort>_audit/user_data.csv folders (local), OR a single committed
# consolidated snapshot `connect_user_data_snapshot.csv` (for server/CI runs with no folders).
# The Connect funnel + training dates are STATIC (Connect user_data can't be pulled headless),
# so the snapshot is the frozen real Connect leg; triggers/welcome/OCS still pull live.
SNAPSHOT = ROOT / "connect_user_data_snapshot.csv"


def _iter_connect_sources():
    folders = [
        d
        for d in sorted(os.listdir(ROOT))
        if d.endswith("_audit") and d != "manual_audit" and (ROOT / d / "user_data.csv").exists()
    ]
    use_snap = bool(os.environ.get("INTERVIEWS_CONNECT_SNAPSHOT")) or (not folders and SNAPSHOT.exists())
    if use_snap and SNAPSHOT.exists():
        by_cohort = defaultdict(list)
        for row in clean_csv(SNAPSHOT):
            u = (row.get("username") or "").strip()
            if u in EXCLUDE_FLWS:
                continue
            c = (row.get("cohort_id") or "").strip()
            c = CONNECT_COHORT_OVERRIDE.get((u, c), c)  # cross-arm mis-tag correction
            by_cohort[c].append(row)
        print(f"[1] Connect: consolidated snapshot {SNAPSHOT.name} ({len(by_cohort)} cohorts)")
        yield from by_cohort.items()
    else:
        for d in folders:
            yield d.replace("_audit", ""), clean_csv(ROOT / d / "user_data.csv")


cohort_info, cohort_flw_meta, cohort_flws = {}, {}, defaultdict(set)
for cohort, rows in _iter_connect_sources():
    sg = cohort_to_sg(cohort)
    if sg is None:
        if cohort and not is_test_cohort(cohort):
            unmapped_cohorts.add(cohort)
        continue
    training_date = None
    for row in rows:
        inv = parse_dt(row.get("invited_date"))
        if inv and (training_date is None or inv < training_date):
            training_date = inv
    cohort_info[cohort] = {"subgroup": sg, "training_date": training_date.date() if training_date else None}
    for row in rows:
        u = (row.get("username") or "").strip()
        if not u:
            continue
        cohort_flws[cohort].add(u)
        cohort_flw_meta[(cohort, u)] = {
            "invited_date": parse_dt(row.get("invited_date")),
            "accepted": (row.get("user_invite_status") or "").strip() == "accepted",
            "learn_started": parse_dt(row.get("date_learn_started")),
            "learn_completed": parse_dt(row.get("completed_learn_date")),
            "date_claimed": parse_dt(row.get("date_claimed")),
        }
sg_unique = defaultdict(
    lambda: {k: set() for k in ["invited", "accepted", "learn_started", "learn_completed", "claimed"]}
)
for cohort, info in cohort_info.items():
    sg = info["subgroup"]
    for u in cohort_flws[cohort]:
        m = cohort_flw_meta[(cohort, u)]
        if m["invited_date"]:
            sg_unique[sg]["invited"].add(u)
        if m["accepted"]:
            sg_unique[sg]["accepted"].add(u)
        if m["learn_started"]:
            sg_unique[sg]["learn_started"].add(u)
        if m["learn_completed"]:
            sg_unique[sg]["learn_completed"].add(u)
        if m["date_claimed"]:
            sg_unique[sg]["claimed"].add(u)
print(f"[1] Connect: {len(cohort_info)} cohorts, {sum(len(v) for v in cohort_flws.values())} FLW-rows")

# ---------------- 2+3. CCHQ welcome + trigger + flw_registration ----------------
welcome_flws_by_key = defaultdict(set)
triggers_by_flw_iv = defaultdict(list)
flw_registered = set()  # connect_ids that submitted an HQ FLW-registration form (for "FLW Reg (HQ)" funnel column)
flw_demographics = {}   # connect_id -> {name,gender,state,lga,settlement,type_of_flw,native_language,education,experience_years,training_batch} from the Learn flw_registration form (for the FLW-level retention analysis)


def _flw_demo(form):
    """Extract demographics from an flw_registration form (settlement key varies by LGA)."""
    loc = form.get("location") if isinstance(form.get("location"), dict) else {}
    setl = form.get("settlement") if isinstance(form.get("settlement"), dict) else {}
    settlement = (setl.get("settlements") or next((v for k, v in setl.items() if k.endswith("_settlement") and v), "") or "")
    exp = form.get("years_of_experience_as_flw")
    try:
        exp = int(float(exp)) if exp not in (None, "") else None
    except (TypeError, ValueError):
        exp = None
    return {
        "name": (form.get("name") or "").strip(),
        "gender": (form.get("gender") or "").strip(),
        "state": (loc.get("state_of_work") or "").strip(),
        "lga": (loc.get("lga") or "").strip(),
        "settlement": str(settlement).strip(),
        "type_of_flw": (form.get("type_of_flw") or "").strip(),
        "native_language": (form.get("native_language") or "").strip(),
        "education": (form.get("highest_educational_qual") or "").strip(),
        "experience_years": exp,
        "training_batch": (form.get("training_batch") or "").strip(),
    }
# Each HQ domain is LLO-specific (…cowac… = COWACDI, …eha… = EHA). Tally each cohort's trigger forms by
# the domain's LLO, then assign the cohort to its MAJORITY LLO — robust to a few stray cross-posted forms
# (e.g. 1ECE1 had 73 EHA vs 1 COWACDI). Drives the render's per-LLO retention comparison.
_cohort_llo_ct = defaultdict(Counter)
for domain in ALL_DOMAINS:
    for ft in ["welcome_click_start", "trigger_bot", "flw_registration"]:
        path = HQ_DIR / f"{domain}__{ft}.jsonl"
        if not path.exists():
            continue
        for line in path.open(encoding="utf-8"):
            try:
                sub = json.loads(line)
            except Exception:
                continue
            form = sub.get("form", {})
            meta = form.get("meta", {}) if isinstance(form.get("meta"), dict) else {}
            cid = (form.get("connect_id") or meta.get("username") or sub.get("username") or "").strip()
            if cid in EXCLUDE_FLWS:  # confirmed non-enrolled test/manual accounts — drop from all HQ legs
                continue
            if ft == "flw_registration":
                if cid:
                    flw_registered.add(cid)
                    # keep the first non-empty demographic record per FLW (they register once)
                    if cid not in flw_demographics or not flw_demographics[cid].get("lga"):
                        flw_demographics[cid] = _flw_demo(form)
                continue
            recv = parse_dt(sub.get("received_on"))
            if not cid or not recv:
                continue
            cohort_id = (form.get("cohort_id") or "").strip()
            niv = (form.get("next_interview") or "").strip()
            if not cohort_id:
                continue
            if ft == "welcome_click_start":
                # Backfill blank next_interview -> the subgroup's FIRST topic, so Int#1 Eligible
                # ties out to # Initiated (a blank Welcome = an Interview-1 Welcome). Trigger forms
                # with blank next_interview are still dropped (deliberate asymmetry; 0 effect on
                # started/completed). Unmapped/test cohorts (sg None) keep the blank key -> excluded.
                wniv = niv
                if wniv == "":
                    _wsg = cohort_to_sg(cohort_id)
                    if _wsg:
                        wniv = SUBGROUP_DESIGN[_wsg]["topics"][0]
                welcome_flws_by_key[(cohort_id, wniv)].add(cid)
            else:
                _llo = "EHA" if "eha" in domain else ("COWACDI" if "cowac" in domain else None)
                if _llo:
                    _cohort_llo_ct[cohort_id][_llo] += 1
                triggers_by_flw_iv[(cid, niv)].append(
                    {
                        "connect_id": cid,
                        "cohort_id": cohort_id,
                        "next_interview": niv,
                        "received_on": recv,
                        "form_id": sub.get("id"),
                    }
                )
for k in triggers_by_flw_iv:
    triggers_by_flw_iv[k].sort(key=lambda tb: tb["received_on"])
# cohort_id -> LLO (COWACDI / EHA) by majority of trigger-form domains
cohort_llo = {c: ct.most_common(1)[0][0] for c, ct in _cohort_llo_ct.items() if ct}
print(f"[2/3] welcome keys={len(welcome_flws_by_key)}, trigger (flw,iv) keys={len(triggers_by_flw_iv)}, "
      f"cohort_llo={Counter(cohort_llo.values())}")

# ---- union in cohorts present in the CommCare interview data but MISSING from the Connect snapshot ----
# cohort_info is otherwise Connect-only, so when the Connect pull is stale/failed for a subgroup
# (e.g. ABT3/2WT/EXT while the CONNECT_SNAP fallback predates them) those whole cohorts vanish from
# counts.cohorts and the per-cohort drop-off — even though their interviews are fully counted from
# CommCare/OCS. Add them here: subgroup + interview funnel populate now; their Connect-funnel columns
# stay empty (cohort_flws stays empty) until a fresh Connect pull fills them in. cohort_flws emptiness
# is the "Connect funnel pending" signal used downstream.
_cc_cohorts = {t["cohort_id"] for lst in triggers_by_flw_iv.values() for t in lst}
_conn_pending = []
for _c in sorted(_cc_cohorts):
    if not _c or _c in cohort_info:
        continue
    _sg = cohort_to_sg(_c)
    if _sg is None:
        if not is_test_cohort(_c):
            unmapped_cohorts.add(_c)
        continue
    cohort_info[_c] = {"subgroup": _sg, "training_date": None}
    _conn_pending.append(_c)
CONNECT_PENDING_COHORTS = set(_conn_pending)  # cohorts with interview data but no Connect funnel yet

# ---- ONE resolved start date per cohort, for every consumer ---------------------------------------
# A cohort's start is its Connect invitation date, else the first interview trigger recorded for it.
# The fallback matters because the Connect snapshot is missing invitation dates for newer cohorts
# whenever the pull is stale (the documented 2026-08-04 case). Resolved HERE, once, because consumers
# that each rolled their own fallback reached different answers about the same cohort: the FLW x Topic
# matrix would call a slot "window still open" while the per-cohort drop-off view called it missed.
# Sharing a function is not enough when the INPUTS differ, so the input is shared instead.
_first_trig_by_cohort = {}
for _lst in triggers_by_flw_iv.values():
    for _tb in _lst:
        _tc, _ro = _tb.get("cohort_id"), _tb.get("received_on")
        if _tc and _ro and (_tc not in _first_trig_by_cohort or _ro < _first_trig_by_cohort[_tc]):
            _first_trig_by_cohort[_tc] = _ro
for _c, _inf in cohort_info.items():
    _td = _inf.get("training_date")
    if _td:
        _inf["start_date"], _inf["start_src"] = _td, "invitation"
    else:
        _ft = _first_trig_by_cohort.get(_c)
        _inf["start_date"] = _ft.date() if _ft else None
        _inf["start_src"] = "first trigger" if _ft else None
_n_fb = sum(1 for _i in cohort_info.values() if _i.get("start_src") == "first trigger")
_n_none = sum(1 for _i in cohort_info.values() if not _i.get("start_date"))
print(f"[1+] cohort start dates: {len(cohort_info) - _n_fb - _n_none} from invitation, {_n_fb} from "
      f"first trigger, {_n_none} unknown")
if _conn_pending:
    print(f"[1+] {len(_conn_pending)} cohort(s) in CommCare data but missing from the Connect snapshot "
          f"(Connect funnel PENDING until next successful Connect pull): {_conn_pending}")

# ---------------- 4. OCS live ----------------
ocs_by_key = defaultdict(list)
sessions = json.loads(CACHE.read_text())
for s in sessions:
    pid, iv = s.get("pid"), s.get("interview")
    if not pid or not iv or str(iv).strip() == "":
        continue
    first = parse_dt(s.get("created_at"))
    if not first:
        continue
    ocs_by_key[(pid, str(iv))].append(
        {"sid": s["sid"], "first": first, "h": 1, "status": s.get("interview_status") or ""}
    )
for k in ocs_by_key:
    ocs_by_key[k].sort(key=lambda x: x["first"])
_ocs_tags = {}
if TAGS_CACHE.exists():
    try:
        _ocs_tags = json.loads(TAGS_CACHE.read_text())
    except (ValueError, OSError):
        _ocs_tags = {}
if not _ocs_tags:
    print("[4t] NOTE: no OCS review-tag cache - every row will read 'not-reviewed'. "
          "Run pull_ocs_tags.py.", flush=True)
else:
    print(f"[4t] OCS review tags: {len(_ocs_tags):,} tagged sessions", flush=True)
print(f"[4] OCS live: {len(sessions)} sessions, {len(ocs_by_key)} (pid,iv) keys")

# ---------------- OCS message word counts (per session; from pull_ocs_words.py) ----------------
words = json.loads(WORDS_CACHE.read_text()) if WORDS_CACHE.exists() else {}
print(f"[4b] OCS words cache: {len(words)} sessions")

# ---------------- match ----------------
matched = {}
for (flw, iv), trs in triggers_by_flw_iv.items():
    sess, claimed = ocs_by_key.get((flw, iv), []), set()
    for tb in trs:
        best = pick_best(sess, tb["received_on"], claimed)
        matched[tb["form_id"]] = best
        if best:
            claimed.add(best["sid"])

# Per-(flw, interview topic) EARLIEST matched session START date (OCS created_at) = when the FLW
# actually DID that interview. Feeds the "days since they did their first interview" retention x-axis
# (build_payload_agg line_days) — distinct from trigger_received_on (when the bot merely offered it).
session_start_by_flw_iv = {}
for (_flw, _iv), _trs in triggers_by_flw_iv.items():
    for _tb in _trs:
        _m = matched.get(_tb["form_id"])
        if _m and _m.get("first"):
            _k = (_flw, _iv)
            if _k not in session_start_by_flw_iv or _m["first"] < session_start_by_flw_iv[_k]:
                session_start_by_flw_iv[_k] = _m["first"]

# ---------------- emit master ----------------
rows = []
for (flw, iv), trs in triggers_by_flw_iv.items():
    for tb in trs:
        cohort_id = tb["cohort_id"]
        sg = cohort_to_sg(cohort_id)
        if not sg:
            if cohort_id and not is_test_cohort(cohort_id):
                unmapped_cohorts.add(cohort_id)  # has HQ trigger activity but no known design -> surface it
            continue
        if iv not in SUBGROUP_DESIGN[sg]["topics"]:
            continue
        n = SUBGROUP_DESIGN[sg]["topics"].index(iv) + 1
        m = matched.get(tb["form_id"])
        td = cohort_info.get(cohort_id, {}).get("training_date")
        cad = SUBGROUP_DESIGN[sg]["cadence"]
        rel = (td + timedelta(days=(n - 1) * cad)) if td else None
        cm = cohort_flw_meta.get((cohort_id, flw), {})
        sw = words.get(m["sid"], {}) if m else {}
        rows.append(
            {
                "connect_id": flw,
                "cohort_id": cohort_id,
                "subgroup": sg,
                "cohort_type": COHORT_TYPE_MAP[sg],
                "interview_n": n,
                "topic_code": iv,
                "topic_name": TOPIC_NAMES.get(iv, iv),
                "training_date": str(td) if td else "",
                "release_date": str(rel) if rel else "",
                "is_released": "Y" if (rel and TODAY >= rel) else "N",
                "trigger_form_id": tb["form_id"],
                "trigger_received_on": tb["received_on"].isoformat(),
                "matched_session_id": m["sid"] if m else "",
                "review_status": _review_status(m["sid"] if m else "", _ocs_tags),
                "session_status": m["status"] if m else "",
                "session_human_words": sw.get("human_words", 0) if m else 0,
                "session_human_msgs": sw.get("human_msgs", 0) if m else 0,
                "is_triggered": "Y",
                "is_started": "Y" if m else "N",
                "is_completed": "Y" if (m and m["status"] == "interview_complete") else "N",
                # 4-source enrichment (Connect funnel per FLW):
                "c_invited": "Y" if cm.get("invited_date") else "N",
                "c_accepted": "Y" if cm.get("accepted") else "N",
                "c_learn_completed": "Y" if cm.get("learn_completed") else "N",
                "c_claimed": "Y" if cm.get("date_claimed") else "N",
                "is_initiated": "Y" if flw in welcome_flws_by_key.get((cohort_id, iv), set()) else "N",
            }
        )
out = ROOT / "master_4src.csv"
with out.open("w", newline="", encoding="utf-8") as f:
    w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"\nwrote {out.name}: {len(rows)} rows, {len({r['connect_id'] for r in rows})} FLWs")
print(f"  [cleanup] excluded {len(EXCLUDE_FLWS)} non-enrolled FLWs; re-tagged {len(CONNECT_COHORT_OVERRIDE)} cross-arm Connect record(s)")
if unmapped_cohorts:
    print(f"[!] {len(unmapped_cohorts)} UNMAPPED cohort(s) (new program type? add a SUBGROUP_DESIGN entry): "
          f"{sorted(unmapped_cohorts)}")

# ---------------- reconcile vs baseline (optional; absent server-side where the participant baseline isn't shipped) ----------------
if BASELINE.exists():
    base = {r["trigger_form_id"]: r for r in _csv.DictReader(open(BASELINE, encoding="utf-8"))}
    live = {r["trigger_form_id"]: r for r in rows}
    shared = set(base) & set(live)
    print(f"\n===== RECONCILE vs {BASELINE.name} =====")
    print(
        f"  rows: live={len(live)} base={len(base)} shared={len(shared)} only_live={len(set(live)-set(base))} only_base={len(set(base)-set(live))}"
    )
    EXACT_COLS = [
        "cohort_id",
        "subgroup",
        "cohort_type",
        "interview_n",
        "topic_code",
        "topic_name",
        "training_date",
        "release_date",
        "is_released",
    ]
    col_mismatch = {c: 0 for c in EXACT_COLS}
    for k in shared:
        for c in EXACT_COLS:
            if str(live[k][c]) != str(base[k][c]):
                col_mismatch[c] += 1
    print("  EXACT-match columns (mismatches across shared rows):")
    for c in EXACT_COLS:
        tag = "OK" if col_mismatch[c] == 0 else f"*** {col_mismatch[c]} MISMATCH"
        print(f"    {c:<20} {tag}")
    # started/completed drift (live newer)
    st = Counter()
    co = Counter()
    for k in shared:
        st[(base[k]["is_started"], live[k]["is_started"])] += 1
        co[(base[k]["is_completed"], live[k]["is_completed"])] += 1
    print(
        f"  is_started (base->live): same={st[('Y','Y')]+st[('N','N')]}  N->Y={st[('N','Y')]}  Y->N(REGRESSION)={st[('Y','N')]}"
    )
    print(
        f"  is_completed(base->live): same={co[('Y','Y')]+co[('N','N')]}  N->Y={co[('N','Y')]}  Y->N(REGRESSION)={co[('Y','N')]}"
    )
else:
    print(f"\n===== RECONCILE: baseline {BASELINE.name} absent — skipped (server/CI) =====")

# ---------------- Connect/Welcome funnel audit ----------------
print("\n===== 4-SOURCE FUNNEL AUDIT (unique FLWs per subgroup) =====")
print(f"  {'SG':<8} {'invited':>7} {'accept':>7} {'learnC':>7} {'claimed':>7} {'initiated(welcome-any)':>22}")
for sg in ["TRS", "TRE", "ABT1-A", "ABT1-B", "ABT2-A", "ABT2-B"]:
    u = sg_unique[sg]
    init = set()
    for (c, t), flws in welcome_flws_by_key.items():
        if cohort_to_sg(c) == sg:
            init |= flws
    print(
        f"  {sg:<8} {len(u['invited']):>7} {len(u['accepted']):>7} {len(u['learn_completed']):>7} {len(u['claimed']):>7} {len(init):>22}"
    )
