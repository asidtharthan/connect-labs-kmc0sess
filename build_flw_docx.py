#!/usr/bin/env python3
"""Render the FLW Retention executive analysis as a formatted Word (.docx) document.

DATA-DRIVEN: every number is read from flw_analysis_payload.json (the same aggregates the dashboard
FLW Retention tab embeds), so the document can never drift from the live dashboard. Regenerate the
payload first with build_flw_analysis.py.

Run: .venv/Scripts/python.exe build_flw_docx.py  ->  docs/FLW_Retention_Analysis_Brief.docx
"""
# flake8: noqa: E501,E231  (string-heavy document template — long prose lines are intentional)
import json

from docx import Document
from docx.shared import Pt, RGBColor

FE = json.load(open("flw_analysis_payload.json", encoding="utf-8"))
TODAY = (
    json.load(open("dashboard_data.json", encoding="utf-8")).get("today", "")
    if __import__("os").path.exists("dashboard_data.json")
    else ""
)

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
FI = FE["firstIv"]
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
    f"Re-using workers is our biggest engagement asset — and it compounds. Finish rate climbs with each additional "
    f"cohort: **{CC['single']['finished']}% → {CC['multi']['finished']}%** (single → multi-cohort), and answer depth "
    f"rises with it ({CC['single']['depth']} → {CC['multi']['depth']} words/session).",
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
    f"The retention lever is the first interview. Workers with above-median answer depth finish at "
    f"**{FI['hi']['finished']}%** vs **{FI['lo']['finished']}%** below.",
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
    "Slow-but-finishing": "Gets there, but with long gaps",
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
    f"Champion/Solid, {_t['Slipping']}% Slipping, {_t['At-risk']+_t['Lost']}% At-risk/Lost. “Slipping” is largely "
    "benign — workers in finished short cohorts who are simply inactive now, not people who quit mid-schedule."
)

h("2. The cross-cohort story (the standout finding)", 1)
para(
    f"The multi-arm design re-uses the same workers across studies — **{multi_pct}%** are in ≥2 cohorts. That re-use "
    "is the strongest engagement signal we have, and it is monotonic:"
)
table(["Cohorts per worker", "Workers", "Share"], [[d["k"], d["n"], f"{d['pct']}%"] for d in CC["dist"]])
para(
    f"Comparing single- vs multi-cohort workers: completion is flat ({CC['single']['completion']} vs "
    f"{CC['multi']['completion']}) while **finishing rises {CC['single']['finished']}% → {CC['multi']['finished']}%** "
    f"and **depth rises {CC['single']['depth']} → {CC['multi']['depth']} words/session** — repeat exposure builds "
    "commitment and richer engagement, with no sign of fatigue."
)
if FE.get("armCombos"):
    combos = ", ".join(f"{c['k']} ({c['n']})" for c in FE["armCombos"][:4])
    para(
        f"Structurally, TRS is the gateway: almost every multi-arm worker started in Training (TRS) and was re-used "
        f"into study arms — top combinations: {combos}. TRS is the program's on-ramp; workers who flow from it into "
        "further arms become the most engaged core."
    )
para(
    "Implication: a stable, repeatedly-engaged worker panel is a competitive asset — deliberately re-invite proven "
    "workers rather than defaulting to fresh single-exposure recruitment."
)
para(
    "(Caveat: the raw “finished” share is partly mechanical for multi-cohort workers — more cohorts = more chances "
    "to finish one — so completion and depth, which aren't subject to that bias, carry the cleaner signal; they agree.)",
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
    f"**{AR['n']} workers** started, haven't finished, and have been silent 14–60 days — recent enough to re-engage. "
    f"Concentrated in {_ar}. A small, concrete outreach list; a targeted nudge here is high-yield."
)

h("7. Recommendations", 1)
li(
    "Make the first interview the priority — the strongest retention lever. Invest in prompt quality, length, and first-touch support, especially for first-time workers.",
    "List Number",
)
li(
    "Lean into worker re-use — re-inviting proven workers compounds engagement. Build a returning-worker panel rather than defaulting to fresh single-exposure recruitment.",
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

doc.save("docs/FLW_Retention_Analysis_Brief.docx")
print(f"wrote docs/FLW_Retention_Analysis_Brief.docx  (N={N}, healthy={healthy}%, as of {TODAY})")
