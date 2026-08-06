#!/usr/bin/env python3
"""Render the FLW Retention executive analysis as a formatted Word (.docx) document.

DATA-DRIVEN: every number is read from flw_analysis_payload.json (the same aggregates the dashboard
FLW Retention tab embeds), so the document can never drift from the live dashboard. Regenerate the
payload first with build_flw_analysis.py.

Run: .venv/Scripts/python.exe build_flw_docx.py  ->  docs/FLW_Retention_Analysis_Brief.docx
"""
# flake8: noqa: E501,E231  (string-heavy document template — long prose lines are intentional)
import json
import os

from docx import Document
from docx.shared import Pt, RGBColor

FE = json.load(open("flw_analysis_payload.json", encoding="utf-8"))
if os.path.exists("_flw_today.json"):
    TODAY = json.load(open("_flw_today.json", encoding="utf-8")).get("today", "")
elif os.path.exists("dashboard_data.json"):
    TODAY = json.load(open("dashboard_data.json", encoding="utf-8")).get("today", "")
else:
    TODAY = ""

NAVY = RGBColor(0x1F, 0x38, 0x64)
GREY = RGBColor(0x6B, 0x72, 0x80)
doc = Document()
doc.styles["Normal"].font.name = "Calibri"
doc.styles["Normal"].font.size = Pt(10.5)

N = FE["n_flws"]
P = {t["k"]: t for t in FE["personas"]}  # persona -> {n,pct}
T = {t["k"]: t for t in FE["tiers"]}
CC = FE["crossCohort"]
CCD = {d["k"]: d for d in CC["dist"]}  # ncohorts -> {n,pct}
FI = FE.get("depthSplit") or FE["firstIv"]  # depthSplit = FIRST-session depth (firstIv was lifetime avg)
OAD = FE["oneAndDone"]
AR = FE["atRisk"]
ST = {s["k"]: s for s in FE["byState"]}
LLO = {s["k"]: s for s in FE["byLLO"]}
TY = {s["k"]: s for s in FE["byType"]}
SV = {s["d"]: s for s in FE["survival"]}
healthy = P.get("Champion", {}).get("pct", 0) + P.get("Steady finisher", {}).get("pct", 0)
multi_pct = 100 - CCD.get("1", {}).get("pct", 0)


def h(text, level=1):
    p = doc.add_heading(text, level=level)
    for r in p.runs:
        r.font.color.rgb = NAVY


def _runs(p, text):
    for i, seg in enumerate(text.split("**")):
        if seg:
            r = p.add_run(seg)
            r.bold = i % 2 == 1


def para(text, italic=False, color=None, size=None, sa=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(sa)
    _runs(p, text)
    for r in p.runs:
        if italic:
            r.italic = True
        if color:
            r.font.color.rgb = color
        if size:
            r.font.size = Pt(size)


def li(text, style="List Bullet"):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_after = Pt(3)
    _runs(p, text)


def table(headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    for j, x in enumerate(headers):
        run = t.rows[0].cells[j].paragraphs[0].add_run(x)
        run.bold = True
        run.font.size = Pt(9.5)
    for row in rows:
        cells = t.add_row().cells
        for j, v in enumerate(row):
            run = cells[j].paragraphs[0].add_run(str(v))
            run.font.size = Pt(9.5)
            if j == 0:
                run.bold = True
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


# ---------------- Title ----------------
tr = doc.add_paragraph().add_run("FLW Retention & Engagement — Executive Analysis")
tr.bold = True
tr.font.size = Pt(20)
tr.font.color.rgb = NAVY
para(f"Connect Interviews program · per-FLW, cross-cohort · data as of {TODAY}", italic=True, color=GREY, size=9, sa=1)
para(
    f"Universe: {N:,} unique front-line workers (FLWs) who started ≥ 1 interview · {FE['coverage_lga']}% demographic "
    "coverage · every metric dedups the worker across all cohorts/arms they were part of. Figures match the live "
    "dashboard (FLW Retention tab) — generated from the same data.",
    italic=True,
    color=GREY,
    size=9,
    sa=10,
)

h("Why this analysis exists", 1)
para(
    "Every other view of this program is cohort-level — how a study arm performed. This one looks at the program "
    "through the worker: one row per unique FLW, their interview history stitched across every cohort and arm they "
    "touched. That matters because most workers are re-used across studies — so the worker's cumulative experience, "
    "not any single cohort, drives whether they stay engaged. This lens tells us who the program retains, when it "
    "loses people, and what to do about it."
)

h("Executive summary", 1)
li(
    f"Engagement is fundamentally healthy. **{healthy}%** of workers are reliable engagers "
    f"(**{P.get('Champion',{}).get('pct',0)}%** Champions, **{P.get('Steady finisher',{}).get('pct',0)}%** Steady finishers). "
    f"Genuine early loss is small — **{OAD['pct']}%** one-and-done.",
    "List Number",
)
li(
    f"Re-use is the norm, but it does not by itself raise finishing. Multi-cohort workers finish ≥1 schedule far more "
    f"often ({CC['single']['finished']}% → {CC['multi']['finished']}%), but that measure is a maximum over cohorts, so "
    f"more cohorts mechanically means more chances. On the like-for-like measure — the share of their own schedules "
    f"they complete — it is **{CC['single'].get('finished_pc', 0)}% (single) vs {CC['multi'].get('finished_pc', 0)}% "
    f"(multi)**, i.e. flat. What re-used workers do show is greater depth "
    f"({CC['single']['depth']} → {CC['multi']['depth']} words/session).",
    "List Number",
)
li(
    f"The drop-off has a clear face. One-and-done workers are disproportionately "
    f"**{(OAD['topState'][0]['k'] if OAD['topState'] else '—')} ({OAD['topState'][0]['pct'] if OAD['topState'] else 0}%)**, "
    f"**single-cohort ({OAD['singleCohortPct']}%)**, and "
    f"**{(OAD['topType'][0]['k'] if OAD['topType'] else '—')} cadre ({OAD['topType'][0]['pct'] if OAD['topType'] else 0}%)**.",
    "List Number",
)
li(
    f"Depth at the first interview is associated with finishing, modestly. Splitting workers at the median "
    f"first-session answer depth, the per-cohort finish rate is **{FI['hi'].get('finished_pc', 0)}%** (above median) "
    f"vs **{FI['lo'].get('finished_pc', 0)}%** (below) — a {abs(FI['hi'].get('finished_pc', 0) - FI['lo'].get('finished_pc', 0))}-point gap. "
    f"On the “finished ≥1 schedule” measure the same split reads {FI['hi']['finished']}% vs {FI['lo']['finished']}%, but "
    f"the deeper group is also in more cohorts, which inflates that version. Treat this as an association worth "
    f"testing, not a proven lever.",
    "List Number",
)
li(
    f"The recoverable at-risk pool is small and targetable — **{AR['n']} workers** (started, not finished, silent 14–60 days).",
    "List Number",
)

h("1. The engagement landscape", 1)
para("Behavioral personas (rule-based segments over the worker's whole history):")
persona_desc = {
    "Champion": "Finishes, steady cadence, high depth — the backbone",
    "Steady finisher": "Completes their schedule reliably",
    "Partial progress": "≥50% of triggered interviews done, but no schedule finished yet",
    "One-and-done": "Started once and stopped — the real early-loss group",
    "Re-engager": "Went silent, then came back",
    "Early dropper": "Shallow start, left early",
    "Lapsed": "Inactive, unfinished",
}
table(
    ["Persona", "Count", "Share", "What it means"],
    [[t["k"], t["n"], f"{t['pct']}%", persona_desc.get(t["k"], "")] for t in FE["personas"]],
)
_t = {k: T.get(k, {}).get("pct", 0) for k in ("Champion", "Solid", "Slipping", "At-risk", "Lost")}
para(
    f"Engagement tiers (RFM blend of recency + completion + answer depth): {_t['Champion']+_t['Solid']}% "
    f"Champion/Solid, {_t['Slipping']}% Slipping, {_t['At-risk']+_t['Lost']}% At-risk/Lost. “Slipping” is mixed: most "
    "are finishers from short cohorts who are simply inactive now, but it also contains a large share of the "
    "one-and-done group, so it should not be read as uniformly benign. Recency is measured against the freshest "
    "session in the dataset rather than the wall clock, so these tiers do not drift when a data pull runs late."
)

h("2. The cross-cohort picture (and a measurement trap)", 1)
para(f"The multi-arm design re-uses the same workers across studies — **{multi_pct}%** are in ≥2 cohorts:")
table(["Cohorts per worker", "Workers", "Share"], [[d["k"], d["n"], f"{d['pct']}%"] for d in CC["dist"]])
para(
    f"It is tempting to read re-use as compounding engagement, because “finished ≥1 schedule” rises "
    f"{CC['single']['finished']}% → {CC['multi']['finished']}% from single- to multi-cohort workers. That reading is "
    "wrong. “Finished ≥1” is a maximum over a worker's cohorts, so a worker in three cohorts has three independent "
    "chances to clear the bar; the rise is largely arithmetic."
)
para(
    f"The two measures that are not distorted by cohort count both say the effect is flat: per-cohort finish rate is "
    f"**{CC['single'].get('finished_pc', 0)}% (single) vs {CC['multi'].get('finished_pc', 0)}% (multi)**, and "
    f"completion rate is {CC['single']['completion']} vs {CC['multi']['completion']}. The one real difference is "
    f"**depth: {CC['single']['depth']} → {CC['multi']['depth']} words/session**. Re-use is operationally valuable — "
    "these are known, trained, available workers who answer at greater length — but this data does not show that "
    "re-using a worker makes them more likely to finish."
)
if FE.get("armCombos"):
    combos = ", ".join(f"{c['k']} ({c['n']})" for c in FE["armCombos"][:4])
    para(
        f"Structurally, TRS sits in almost every multi-arm worker's history — top combinations: {combos}. (The arm "
        "set is unordered in this data, so we can say TRS is nearly always present, not that it always came first.)"
    )
para(
    "Implication: a stable, repeatedly-engaged worker panel is operationally valuable — known, trained, available "
    "workers who answer at greater length. Just don't budget for a finish-rate gain from re-use itself.",
    italic=True,
    color=GREY,
    size=9,
)

h("3. Where the program loses people — and who they are", 1)
para(
    f"Genuine early loss is the One-and-done segment ({OAD['n']} workers, {OAD['pct']}%). They are not a random slice:"
)
table(
    ["Cut", "One-and-done", "Program overall"],
    [
        [
            f"{OAD['topState'][0]['k'] if OAD['topState'] else '—'} (top state)",
            f"{OAD['topState'][0]['pct'] if OAD['topState'] else 0}%",
            f"{ST.get(OAD['topState'][0]['k'],{}).get('n','') if OAD['topState'] else ''} workers",
        ],
        ["Single-cohort", f"{OAD['singleCohortPct']}%", f"{FE['overallSingleCohortPct']}%"],
        [
            f"{OAD['topType'][0]['k'] if OAD['topType'] else '—'} cadre (top)",
            f"{OAD['topType'][0]['pct'] if OAD['topType'] else 0}%",
            "",
        ],
        ["Median answer depth", f"{OAD['medianDepth']} words", f"Champions: {FE['champMedianDepth']}"],
    ],
)
para(
    "The drop-off profile is a first-time, single-exposure worker (top geography above), engaging shallowly on their "
    "one interview and not returning. This points at who to support and when — at/just after the first interview."
)
para(
    f"The depth curve (share reaching each interview: Int≥1 {SV.get(1,{}).get('pct',0)}% → Int≥2 "
    f"{SV.get(2,{}).get('pct',0)}% → Int≥3 {SV.get(3,{}).get('pct',0)}%) partly reflects cohort schedule length — most "
    "workers are in short cohorts, so deeper steps largely mean “was this worker in a longer-schedule cohort,” not "
    f"attrition. The clean FLW-level attrition number is the {OAD['pct']}% one-and-done."
)

h("4. The retention lever: early engagement depth", 1)
para("Splitting the population at the median answer-depth:")
table(
    ["Group", "Workers", "Finish rate", "Avg depth"],
    [
        ["Above-median depth", FI["hi"]["n"], f"{FI['hi']['finished']}%", f"{FI['hi']['depth']} words/session"],
        ["Below-median depth", FI["lo"]["n"], f"{FI['lo']['finished']}%", f"{FI['lo']['depth']} words/session"],
    ],
)
para(
    f"A {FI['hi']['finished'] - FI['lo']['finished']}-point finish gap tracks with how deeply a worker engages early "
    "— consistent with the longitudinal-survey literature. The highest-leverage intervention is making the first "
    "interview(s) genuinely engaging (prompt design, length, onboarding support)."
)

h("5. Cross-cuts: geography, partner, cadre", 1)
para("By state:")
table(["State", "Workers", "Finish rate"], [[s["k"], s["n"], f"{s['finished']}%"] for s in FE["byState"]])
_c = LLO.get("COWACDI", {}).get("finished", "—")
_e = LLO.get("EHA", {}).get("finished", "—")
li(
    f"By implementing partner (LLO): COWACDI **{_c}%** vs EHA **{_e}%** finish — the cohort-level gap confirmed at the "
    "worker level; workers spanning both partners finish ~100%."
)
_top = FE["byType"][0] if FE["byType"] else {}
_chew = TY.get("chew", {})
li(
    f"By FLW cadre: {_top.get('k','')} leads at {_top.get('finished','')}%; the largest cadre, "
    f"**“chew” ({_chew.get('n','')} workers) at {_chew.get('finished','')}%** — mid-pack but, by size, the single "
    "biggest opportunity to lift the average."
)

h("6. The recoverable at-risk list", 1)
_ar = ", ".join(f"{s['k']} ({s['n']})" for s in AR["byState"])
para(
    f"**{AR['n']} workers** started, haven't finished, were offered a complete schedule, and have been silent "
    f"14–60 days — recent enough to re-engage. Concentrated in {_ar}. "
    + (
        f"They are the recent slice of **{AR['ofUnfinished']}** unfinished workers overall, not the whole unfinished "
        "population; the rest have been silent longer than 60 days. "
        if AR.get("ofUnfinished")
        else ""
    )
    + "Note this list moves with data freshness: it is defined off the newest session in the dataset."
)

h("7. Recommendations", 1)
li(
    "Test first-interview support as the leading candidate lever. Depth at interview 1 is the strongest early signal "
    "we have, but the association is modest once cohort count is held constant — so run it as a trial with a "
    "control group rather than a programme-wide bet.",
    "List Number",
)
li(
    "Keep re-using proven workers for operational reasons (known, trained, available, and they answer at greater "
    "length) — but do not forecast a finish-rate improvement from re-use; per-cohort finishing is flat across "
    "single- and multi-cohort workers.",
    "List Number",
)
li(
    f"Target {OAD['topState'][0]['k'] if OAD['topState'] else 'the lagging state'} and the “chew” cadre — where one-and-done concentrates. Pair them with the onboarding support that works elsewhere.",
    "List Number",
)
li(f"Run the {AR['n']}-worker recovery list now — the fastest available win.", "List Number")
li(
    f"Investigate the EHA gap — COWACDI retains ~{(LLO.get('COWACDI',{}).get('finished',0)-LLO.get('EHA',{}).get('finished',0))} points better; understanding why could lift EHA materially.",
    "List Number",
)

h("Method & data", 1)
li(
    "Grain: one row per unique worker (connect_id), deduped across cohorts; metrics union the worker's sessions across every arm. Ties out to the canonical started-worker count."
)
li(
    "Engagement tier (RFM): Recency + completion rate + answer depth, each 1–5. Persona: rule-based "
    "behavioral segment. Finished: completed all scheduled interviews in ≥1 cohort."
)
li(
    "Sources: CommCare trigger + session data · OCS sessions (depth) · Connect funnel · flw_registration "
    "demographics. Full per-worker detail: flw_analysis.csv. Live: dashboard → FLW Retention tab (daily). "
    "This document is generated from the same payload, so it always matches the dashboard."
)
li(
    "Caveats: multi-cohort “finished” share is upward-biased (§2; completion & depth agree and are unbiased); "
    "progression-depth conflates schedule lengths (§3); experience_years unreliable and excluded."
)

_out = "docs/FLW_Retention_Analysis_Brief.docx"
try:
    doc.save(_out)
except PermissionError:
    _out = "docs/FLW_Retention_Analysis_Brief_UPDATED.docx"
    doc.save(_out)
    print("(canonical file was locked/open — wrote to _UPDATED variant instead)")
print(f"wrote {_out}  (N={N}, healthy={healthy}%, as of {TODAY})")
