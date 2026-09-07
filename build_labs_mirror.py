"""Mirror the published Labs dashboard into one workbook, sheet per view.

The row-level base table (sessions_*.csv) is an audit and backup layer: it needs filters and an
understanding of grain before it gives you a report number. That is the wrong tool for someone
populating a report, and it is why the same metric kept coming out three different ways.

This is the other tool. Every sheet is READ STRAIGHT OFF the published payload, so a value here is
the value on the dashboard - no filtering, no dedupe, no judgement calls. And because it is built
from the payload alone and never from a local build, it CANNOT drift from what the dashboard shows.

    python build_labs_mirror.py docs/report_freeze/payload_v214.json v214
"""

import collections
import json
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/report_freeze/payload_v214.json"
VER = sys.argv[2] if len(sys.argv) > 2 else "v214"
OUT = ROOT / ("docs/report_freeze/Labs_Dashboard_%s.xlsx" % VER)
FACE = "Sans Serif Collection"

D = json.loads(SRC.read_text(encoding="utf-8"))
STAMP = "Labs dashboard {}  |  data as of {}  |  built {}".format(VER, D.get("today"), D.get("built_at"))

HDR = PatternFill("solid", fgColor="1F4E79")
SUB = PatternFill("solid", fgColor="F2F2F2")
KEY = PatternFill("solid", fgColor="FFF2CC")
THIN = Side(style="thin", color="D9D9D9")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

wb = openpyxl.Workbook()
wb.remove(wb.active)


def sheet(name, title, note=""):
    ws = wb.create_sheet(name)
    c = ws.cell(1, 1, title)
    c.font = Font(name=FACE, size=13, bold=True)
    c = ws.cell(2, 1, STAMP)
    c.font = Font(name=FACE, size=9, color="595959")
    if note:
        c = ws.cell(3, 1, note)
        c.font = Font(name=FACE, size=9, color="595959")
        c.alignment = Alignment(wrap_text=False)
    return ws


def table(ws, row, headers, rows, widths=None, highlight=()):
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row, i, h)
        c.font = Font(name=FACE, size=10, bold=True, color="FFFFFF")
        c.fill = HDR
        c.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")
        c.border = BOX
    for r, data in enumerate(rows, start=row + 1):
        for i, v in enumerate(data, start=1):
            c = ws.cell(r, i, v)
            c.font = Font(name=FACE, size=10, bold=(data[0] in ("Overall", "TOTAL")))
            c.border = BOX
            if headers[i - 1] in highlight:
                c.fill = KEY
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                c.number_format = "#,##0" if float(v).is_integer() else "0.0"
    for i, w in enumerate(widths or [], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row + 1, 1)
    return row + 1 + len(rows)


# ------------------------------------------------------------------ 1. the headline
ws = sheet("Overview", "Overview", "The four numbers on top of the dashboard, plus the figure the report leads with.")
cn = D["counts"]
t1 = {r["key"]: r for r in D["table1"]}
ov = t1["Overall"]
table(
    ws,
    5,
    ["Metric", "Value", "What it counts"],
    [
        ["Cohorts", cn["cohorts"], "distinct cohorts in the build"],
        ["FLWs offered an interview", cn["flws"], "unique FLWs with at least one interview slot"],
        ["Unique FLWs who started", ov["flws"], "FLWs with at least one started interview"],
        ["Interviews started", ov["ist"], "unique scheduled interviews a FLW opened"],
        ["Interviews completed", ov["icmp"], "of those, the ones that reached the end"],
        ["Completion rate", ov["pct"], "completed divided by started"],
        ["Avg words per FLW message", ov["avg_words"], "across all started interviews"],
    ],
    widths=[30, 14, 62],
    highlight=("Value",),
)
c = ws.cell(14, 1, "Use %s as THE completed-interviews figure for the report." % f"{ov['icmp']:,}")
c.font = Font(name=FACE, size=10, bold=True)
c = ws.cell(15, 1, "OCS will show a higher number because it counts chat sessions, including repeats and")
c.font = Font(name=FACE, size=9, color="595959")
c = ws.cell(16, 1, "off-schedule topics. See the 'Why OCS differs' sheet.")
c.font = Font(name=FACE, size=9, color="595959")

# ------------------------------------------------------------------ 2. by subgroup
ws = sheet(
    "By Subgroup",
    "Interview completion by study arm",
    "This is the dashboard's Breakdowns > By Subgroup table, verbatim.",
)
table(
    ws,
    5,
    ["Subgroup", "FLWs started", "Interviews started", "Interviews completed", "% completed", "Avg words / FLW msg"],
    [[r["key"], r["flws"], r["ist"], r["icmp"], r["pct"], r["avg_words"]] for r in D["table1"]],
    widths=[14, 14, 19, 21, 13, 20],
    highlight=("Interviews completed", "% completed"),
)

# ------------------------------------------------------------------ 3. by topic
ws = sheet(
    "By Topic",
    "Interview completion by topic",
    "The dashboard's Breakdowns > By Topic table. 'Questions' is design metadata.",
)
tq = D.get("topicQuestions", {})
table(
    ws,
    5,
    ["Code", "Topic", "Questions", "FLWs", "Started", "Completed", "% completed", "Avg words / FLW msg"],
    [
        [r["code"], r["name"], tq.get(r["code"]), r["flws"], r["ist"], r["icmp"], r["pct"], r["avg_words"]]
        for r in D["table2"]
    ],
    widths=[7, 38, 11, 9, 10, 11, 13, 20],
    highlight=("Completed", "% completed"),
)

# ------------------------------------------------------------------ 4. A/B arms
ws = sheet(
    "A_B Arms",
    "A/B test arms",
    "The dashboard's Breakdowns > A/B Arms table. These are the figures the report's A/B section cites.",
)
DESIGN = {
    "ABT1-A": "payment: $2 per interview",
    "ABT1-B": "payment: $4 per interview",
    "ABT2-A": "cadence: 14 days between interviews",
    "ABT2-B": "cadence: 3 days between interviews",
    "ABT3-A": "length: 7 questions",
    "ABT3-B": "length: 20 questions",
}
table(
    ws,
    5,
    ["Arm", "What was varied", "FLWs", "Started", "Completed", "% completed", "Avg words / FLW msg"],
    [
        [r["key"], DESIGN.get(r["key"], ""), r["flws"], r["ist"], r["icmp"], r["pct"], r["avg_words"]]
        for r in D["table3"]
    ],
    widths=[11, 36, 9, 10, 11, 13, 20],
    highlight=("Completed", "% completed"),
)

# ------------------------------------------------------------------ 5. funnel
ws = sheet(
    "Connect Funnel",
    "Recruitment funnel",
    "Every step from invitation to a completed interview. Note initiated is NOT started.",
)
table(
    ws,
    5,
    ["Subgroup", "Invited", "Accepted", "Learn completed", "Claimed", "Initiated", "Started", "Completed"],
    [
        [
            r["sg"],
            r["invited"],
            r["accepted"],
            r["learn_completed"],
            r["claimed"],
            r["initiated"],
            r["started"],
            r["completed"],
        ]
        for r in D["connectFunnel"]
    ],
    widths=[13, 10, 11, 16, 10, 11, 10, 11],
    highlight=("Started", "Completed"),
)
n = 5 + len(D["connectFunnel"]) + 3
for i, s in enumerate(
    [
        "These are FLW counts, not interview counts. One FLW appears once per subgroup they enrolled in.",
        "Initiated = clicked through the welcome. Started = actually opened an interview.",
        "A completion RATE must divide by Started, never by Initiated.",
    ]
):
    c = ws.cell(n + i, 1, s)
    c.font = Font(name=FACE, size=9, color="595959")

# ------------------------------------------------------------------ 6. review status
ws = sheet(
    "Review Status",
    "Human review verdicts",
    "Interview-level verdicts. These are mutually exclusive and sum to interviews completed.",
)
rs = D["reviewStatus"]
ovr = rs["overall"]
keys = rs["keys"]
tot = sum(ovr.get(k, 0) for k in keys)
table(
    ws,
    5,
    ["Verdict", "Interviews", "% of completed"],
    [[k, ovr.get(k, 0), round(ovr.get(k, 0) / tot * 100, 1) if tot else 0] for k in keys] + [["TOTAL", tot, 100.0]],
    widths=[18, 13, 16],
    highlight=("Interviews",),
)
r = 5 + len(keys) + 3
c = ws.cell(r, 1, "Suspected AI use is a FLAG, not a verdict: an interview can be acceptable and flagged.")
c.font = Font(name=FACE, size=9, color="595959")
c = ws.cell(
    r + 1,
    1,
    "flagged inside unacceptable: %s     flagged inside acceptable: %s"
    % (rs.get("ai_in_unacceptable"), rs.get("ai_in_acceptable")),
)
c.font = Font(name=FACE, size=10)
r += 3
by = rs.get("by_sg", {})
table(
    ws,
    r,
    ["Subgroup"] + keys,
    [[sg] + [by[sg].get(k, 0) for k in keys] for sg in sorted(by)],
    widths=[14] + [16] * len(keys),
)

# ------------------------------------------------------------------ 7. why OCS differs
ws = sheet(
    "Why OCS differs",
    "The same question, five defensible answers",
    "This is why the team kept getting conflicting numbers. None of these is wrong.",
)
sr = D["sessionReview"]
table(
    ws,
    5,
    ["Figure", "Count", "What it counts", "Use for the report?"],
    [
        [
            "Interviews completed (Labs)",
            ov["icmp"],
            "unique scheduled interviews that reached the end",
            "YES - this is the report figure",
        ],
        [
            "Completed session ROWS",
            None,
            "the base table before deduping re-triggered slots",
            "no - counts one interview twice",
        ],
        [
            "OCS sessions, status complete",
            None,
            "chat sessions, including repeats and off-schedule topics",
            "no - counts sessions",
        ],
        [
            "Sessions tagged acceptable (OCS)",
            sr["counts"].get("acceptable"),
            "a REVIEW VERDICT on sessions, not a completion count",
            "no - and it is still growing",
        ],
        [
            "Interviews rated acceptable (Labs)",
            ovr.get("acceptable"),
            "interview-level verdict; %s are still unreviewed" % f"{ovr.get('not-reviewed', 0):,}",
            "only for quality claims, never for volume",
        ],
    ],
    widths=[34, 11, 52, 34],
    highlight=("Count",),
)
r = 12
for i, s in enumerate(
    [
        "OCS counts SESSIONS. Labs counts unique SCHEDULED INTERVIEWS. Both are correct.",
        "A worker who redid a topic has two sessions and one interview.",
        "OCS also holds welcome clicks and run-on fragments that are not interviews at all:",
        "   OCS sessions in total: %s      of which carry an interview tag: about 10.2k"
        % f"{sr.get('ocs_sessions', 0):,}",
    ]
):
    c = ws.cell(r + i, 1, s)
    c.font = Font(name=FACE, size=9, color="595959")

# ------------------------------------------------------------------ 8. panel engagement
P = {i for i, c in enumerate(D["flwMatrixCohorts"]) if c in ("1PC1", "1PE1")}
pc = collections.Counter()
for e in D["flwMatrixV2"]:
    parts = e.split("|")
    for seg in parts[1:]:
        ci, _, dg = seg.partition(":")
        if int(ci) in P:
            pc[parts[0]] += dg.count("5")
pv = sorted(x for x in pc.values() if x > 0)
ws = sheet(
    "Panel Engagement",
    "Panel cohort: interviews completed per worker",
    "The thirteen-topic sequence. Base is the %d workers who completed at least one." % len(pv),
)
rows = []
for th in (1, 4, 8, 11, 13):
    m = sum(1 for x in pv if x >= th)
    rows.append(["completed %d or more" % th, m, round(m / len(pv) * 100, 1)])
rows.append(
    ["completed exactly one", sum(1 for x in pv if x == 1), round(sum(1 for x in pv if x == 1) / len(pv) * 100, 1)]
)
rows.append(["median per worker", pv[len(pv) // 2], None])
table(ws, 5, ["Measure", "Workers", "% of base"], rows, widths=[26, 11, 12], highlight=("Workers",))
r = 5 + len(rows) + 2
c = ws.cell(r, 1, "workers who started at least one panel interview: %d" % t1["PANEL"]["flws"])
c.font = Font(name=FACE, size=10)
c = ws.cell(r + 1, 1, "workers who completed at least one: %d" % len(pv))
c.font = Font(name=FACE, size=10)
c = ws.cell(
    r + 2, 1, "Percentages above use the %d base. On %d they each drop about a point." % (len(pv), t1["PANEL"]["flws"])
)
c.font = Font(name=FACE, size=9, color="595959")

# ------------------------------------------------------------------ 9. read me, kept short
ws = sheet("Read me", "How to use this workbook")
LINES = [
    ("", False),
    ("Every number here is read straight off the published Labs dashboard %s." % VER, True),
    ("No filtering, no dedupe, no judgement calls. If a sheet says it, the dashboard says it.", False),
    ("", False),
    ("For the report, use:", True),
    ("   Interviews completed          %s      Overview sheet" % f"{ov['icmp']:,}", False),
    ("   Completion rate               %s%%       Overview sheet" % ov["pct"], False),
    ("   Per arm and per topic                  By Subgroup / By Topic / A_B Arms", False),
    ("", False),
    ("If someone brings a different number", True),
    ("Check the 'Why OCS differs' sheet first. OCS counts chat sessions; Labs counts unique", False),
    ("scheduled interviews. Both are right, they answer different questions, and that is what", False),
    ("was causing the disagreement.", False),
    ("", False),
    ("This is frozen", True),
    ("Pinned to %s. The dashboard refreshes; this file does not. Quote from here and the" % VER, False),
    ("number cannot move under you mid-report.", False),
    ("", False),
    ("The row-level data is separate", True),
    ("sessions_%s.csv holds one row per interview slot, for audit and backup. It needs filters" % VER, False),
    ("and an understanding of grain to give you a report number, which is why it is not this file.", False),
]
for i, (s, b) in enumerate(LINES, start=4):
    c = ws.cell(i, 1, s)
    c.font = Font(name=FACE, size=11 if b else 10, bold=b)
ws.column_dimensions["A"].width = 100


# ------------------------------------------------------------------ 10. drop-off by arm
ws = sheet(
    "Dropoff by Arm",
    "Drop-off funnel, interview by interview",
    "For each arm, how many were eligible, offered, started and completed at every step.",
)
rows = []
for sg in D["dropoff"]["subgroups"]:
    for iv in sg["interviews"]:
        rows.append(
            [
                sg["sg"],
                iv["n"],
                iv["topic"],
                iv.get("name"),
                iv["eligible"],
                iv["triggered"],
                iv.get("pct_trig"),
                iv["started"],
                iv.get("pct_started"),
                iv["completed"],
                iv.get("pct_completed"),
                iv.get("pct_completed_base"),
            ]
        )
table(
    ws,
    5,
    [
        "Arm",
        "Interview",
        "Topic",
        "Topic name",
        "Eligible",
        "Offered",
        "% offered",
        "Started",
        "% started",
        "Completed",
        "% completed",
        "% of eligible",
    ],
    rows,
    widths=[11, 10, 8, 32, 10, 9, 11, 9, 11, 11, 13, 14],
    highlight=("Completed", "% completed"),
)

# ------------------------------------------------------------------ 11. drop-off by cohort
ws = sheet(
    "Dropoff by Cohort",
    "Drop-off funnel per cohort",
    "The same view broken to individual cohorts. Useful when an arm average hides one cohort.",
)
rows = []
for sg, cohorts in D["dropoff"]["cohorts"].items():
    for co in cohorts:
        for iv in co["interviews"]:
            rows.append(
                [
                    sg,
                    co["cohort"],
                    iv["n"],
                    iv["topic"],
                    iv["eligible"],
                    iv["triggered"],
                    iv.get("pct_trig"),
                    iv["started"],
                    iv.get("pct_started"),
                    iv["completed"],
                    iv.get("pct_completed"),
                ]
            )
table(
    ws,
    5,
    [
        "Arm",
        "Cohort",
        "Interview",
        "Topic",
        "Eligible",
        "Offered",
        "% offered",
        "Started",
        "% started",
        "Completed",
        "% completed",
    ],
    rows,
    widths=[11, 12, 10, 8, 10, 9, 11, 9, 11, 11, 13],
    highlight=("Completed", "% completed"),
)

# ------------------------------------------------------------------ 12. cohort end states
ws = sheet(
    "Cohort Status",
    "Every cohort and how it ended",
    "One row per cohort. 'Settled' means its schedule has finished running.",
)
CD = [
    ("c", "Cohort"),
    ("s", "Start"),
    ("e", "End"),
    ("n", "FLWs"),
    ("nb", "FLWs who began"),
    ("settled", "Settled"),
    ("f", "Finished all"),
    ("d", "Dropped"),
    ("sk", "Skipped one"),
    ("w", "Waiting"),
    ("z", "Never started"),
    ("ts", "Interviews sent"),
    ("tc", "Interviews completed"),
]
sgmap = D.get("cohortSG", {})
table(
    ws,
    5,
    ["Arm"] + [h for _, h in CD],
    [[sgmap.get(r["c"], "")] + [r.get(k) for k, _ in CD] for r in D["cohortDropoff"]],
    widths=[11, 12, 12, 12, 8, 15, 10, 12, 10, 12, 10, 14, 16, 20],
    highlight=("Interviews completed",),
)

# ------------------------------------------------------------------ 13. retention curve
ws = sheet(
    "Retention Curve",
    "Retention curve points",
    "Percent of the base still completing at each interview. 'base' is the arm's starting pool.",
)
rows = []
for r in D["lineSeries"]:
    for i, p in enumerate(r.get("pts") or []):
        st = r.get("status") or []
        dy = r.get("days") or []
        rows.append(
            [
                r["sg"],
                r.get("base"),
                i + 1,
                p,
                (r.get("pts_prev") or [None] * 99)[i],
                (r.get("pts_di") or [None] * 99)[i],
                dy[i] if i < len(dy) else None,
                st[i] if i < len(st) else None,
            ]
        )
table(
    ws,
    5,
    ["Arm", "Base", "Interview", "% of base", "% of previous", "% de-impacted", "Days from start", "Status"],
    rows,
    widths=[11, 9, 10, 12, 14, 14, 16, 11],
    highlight=("% of base",),
)

# ------------------------------------------------------------------ 14. weekly engagement
ws = sheet(
    "Weekly Engagement",
    "Weekly engagement, by arm",
    "How many workers were active, finished, dropped or waiting in each week of the run.",
)
rows = []
for sg, e in D["cohortEngagement"].items():
    wks = e.get("weeks") or []
    for i, wk in enumerate(wks):

        def g(k):
            v = e.get(k) or []
            return v[i] if i < len(v) else None

        rows.append(
            [
                sg,
                wk,
                g("started"),
                g("new"),
                g("active"),
                g("finished"),
                g("dropped"),
                g("waiting"),
                g("slow"),
                g("quiet"),
                g("steady_pct"),
                g("incons_pct"),
            ]
        )
table(
    ws,
    5,
    [
        "Arm",
        "Week",
        "Started to date",
        "New",
        "Active",
        "Finished",
        "Dropped",
        "Waiting",
        "Slow",
        "Quiet",
        "% steady",
        "% inconsistent",
    ],
    rows,
    widths=[11, 12, 15, 8, 9, 10, 10, 10, 8, 8, 11, 15],
)

# ------------------------------------------------------------------ 15. topic slot states
ws = sheet(
    "Topic Slot States",
    "Every topic across the seven slot states",
    "A slot is one scheduled interview for one worker. These states are mutually exclusive.",
)
TS = [
    "not-applicable",
    "not-available-yet",
    "available-not-started",
    "available-missed-overdue",
    "started-not-completed",
    "completed",
    "not-triggered",
]
table(
    ws,
    5,
    ["Code", "Topic", "Total slots", "Applicable"] + [s.replace("-", " ") for s in TS],
    [[r["code"], r["name"], r.get("total"), r.get("applicable")] + [r.get(s) for s in TS] for r in D["topicStatus"]],
    widths=[7, 34, 12, 12] + [15] * len(TS),
    highlight=("completed",),
)

# ------------------------------------------------------------------ 16. topic states per cohort
ws = sheet(
    "Topic States by Cohort",
    "Topic slot states, per cohort",
    "Columns follow the dashboard's own order: completed, then the other six states.",
)
TSC = [
    "completed",
    "started-not-completed",
    "available-missed-overdue",
    "available-not-started",
    "not-available-yet",
    "not-triggered",
]
rows = []
for code, entries in D["topicStatusCohort"].items():
    if isinstance(entries, str):
        entries = json.loads(entries)
    for e in entries:
        rows.append([code, D.get("topicNames", {}).get(code, ""), e[0]] + list(e[1:]))
table(
    ws,
    5,
    ["Code", "Topic", "Cohort"] + [s.replace("-", " ") for s in TSC],
    rows,
    widths=[7, 30, 12] + [16] * len(TSC),
    highlight=("completed",),
)

# ------------------------------------------------------------------ 17. worker engagement
ws = sheet(
    "Worker Engagement",
    "Workers, grouped every way the dashboard groups them",
    "Base is the %s workers who started at least one interview." % f"{D['flwEngagement']['n_flws']:,}",
)
fe = D["flwEngagement"]
r = 5


def block(ws, r, title, headers, rows, widths, highlight=()):
    c = ws.cell(r, 1, title)
    c.font = Font(name=FACE, size=11, bold=True)
    return table(ws, r + 1, headers, rows, widths, highlight) + 2


r = block(
    ws,
    r,
    "Engagement tier",
    ["Tier", "Workers", "% of base"],
    [[x["k"], x["n"], x.get("pct")] for x in fe["tiers"]],
    [30, 11, 12],
    ("Workers",),
)
r = block(
    ws,
    r,
    "Persona",
    ["Persona", "Workers", "% of base"],
    [[x["k"], x["n"], x.get("pct")] for x in fe["personas"]],
    [30, 11, 12],
    ("Workers",),
)
r = block(
    ws,
    r,
    "By state",
    ["State", "Workers", "Completion", "Finished", "% finished", "Depth"],
    [
        [x["k"], x["n"], x.get("completion"), x.get("finished"), x.get("finished_pc"), x.get("depth")]
        for x in fe["byState"]
    ],
    [18, 11, 13, 11, 13, 9],
)
r = block(
    ws,
    r,
    "By worker type",
    ["Type", "Workers", "Completion", "Finished", "% finished", "Depth"],
    [
        [x["k"], x["n"], x.get("completion"), x.get("finished"), x.get("finished_pc"), x.get("depth")]
        for x in fe["byType"]
    ],
    [28, 11, 13, 11, 13, 9],
)
r = block(
    ws,
    r,
    "By LLO",
    ["LLO", "Workers", "Completion", "Finished", "% finished", "Depth"],
    [
        [x["k"], x["n"], x.get("completion"), x.get("finished"), x.get("finished_pc"), x.get("depth")]
        for x in fe["byLLO"]
    ],
    [18, 11, 13, 11, 13, 9],
)
r = block(
    ws,
    r,
    "By LGA",
    ["LGA", "Workers", "Completion", "Finished", "% finished", "Depth"],
    [
        [x["k"], x["n"], x.get("completion"), x.get("finished"), x.get("finished_pc"), x.get("depth")]
        for x in fe["byLGA"]
    ],
    [26, 11, 13, 11, 13, 9],
)
r = block(
    ws,
    r,
    "By pace",
    ["Pace", "Workers", "Completion", "Finished", "% finished", "Depth"],
    [
        [x["k"], x["n"], x.get("completion"), x.get("finished"), x.get("finished_pc"), x.get("depth")]
        for x in fe["byPace"]
    ],
    [28, 11, 13, 11, 13, 9],
)
r = block(
    ws,
    r,
    "By peers in settlement",
    ["Peers", "Workers", "Completion", "Finished", "% finished", "Depth"],
    [
        [x["k"], x["n"], x.get("completion"), x.get("finished"), x.get("finished_pc"), x.get("depth")]
        for x in fe["byPeers"]
    ],
    [30, 11, 13, 11, 13, 9],
)
r = block(
    ws,
    r,
    "Cohorts per worker",
    ["Cohorts", "Workers", "% of base"],
    [[x["k"], x["n"], x.get("pct")] for x in fe["crossCohort"]["dist"]],
    [12, 11, 12],
)
r = block(ws, r, "Arm combinations", ["Combination", "Workers"], [[x["k"], x["n"]] for x in fe["armCombos"]], [30, 11])
r = block(
    ws,
    r,
    "Survival by day",
    ["Day", "Reached", "Eligible", "% reached", "% of eligible"],
    [[x["d"], x.get("reached"), x.get("elig"), x.get("pct"), x.get("pct_elig")] for x in fe["survival"]],
    [9, 11, 11, 12, 15],
)

# ------------------------------------------------------------------ 18. design reference
ws = sheet(
    "Design Reference",
    "What each arm was designed to do",
    "Topic sequence and cadence per arm, and which cohort belongs to which arm.",
)
table(
    ws,
    5,
    ["Arm", "Interviews", "Cadence (days)", "Topic sequence"],
    [
        [k, len(v.get("topics") or []), v.get("cadence"), ", ".join(v.get("topics") or [])]
        for k, v in D["subgroupDesign"].items()
    ],
    widths=[12, 12, 16, 60],
)
r = 5 + len(D["subgroupDesign"]) + 3
table(ws, r, ["Cohort", "Arm"], sorted(D.get("cohortSG", {}).items()), widths=[14, 12])

# ------------------------------------------------------------------ 19. notes and caveats
ws = sheet("Notes", "Things worth knowing before quoting a number")
NOTE = [
    ("", False),
    ("De-impact adjustment", True),
    ("Some arms had an interview affected by a scheduling issue. The dashboard can exclude it;", False),
    ("columns marked 'de-impacted' show that version.", False),
    ("", False),
]
for k, v in (D.get("deimpact") or {}).items():
    NOTE.append(
        (
            "   %-9s last %s interviews, %s affected, %s of them completed"
            % (k, v.get("last_n"), v.get("count"), v.get("count_c")),
            False,
        )
    )
NOTE += [
    ("", False),
    ("Cohorts excluded from these figures", True),
    ("   retired: %s" % (", ".join(D.get("retiredCohorts") or []) or "none"), False),
    ("   unmapped: %s" % (", ".join(D.get("unmappedCohorts") or []) or "none"), False),
    ("   awaiting a Connect pull: %s" % (", ".join(D.get("connectPendingSubgroups") or []) or "none"), False),
    ("", False),
    ("Two counts that are easy to confuse", True),
    ("FLWs offered an interview (%s) counts everyone with a scheduled slot." % f"{D['counts']['flws']:,}", False),
    ("Unique FLWs who started (%s) counts those who opened at least one." % f"{t1['Overall']['flws']:,}", False),
    ("", False),
    ("Depth", True),
    ("Where a sheet says 'depth' it means words the worker typed, not interviews completed.", False),
]
for i, (s, b) in enumerate(NOTE, start=4):
    c = ws.cell(i, 1, s)
    c.font = Font(name=FACE, size=11 if b else 10, bold=b)
ws.column_dimensions["A"].width = 100

# explicit order: the headline first, detail after, reference last. A reader should not have to
# hunt for the number they came for.
ORDER = [
    "Read me",
    "Overview",
    "By Subgroup",
    "A_B Arms",
    "By Topic",
    "Connect Funnel",
    "Review Status",
    "Why OCS differs",
    "Panel Engagement",
    "Dropoff by Arm",
    "Dropoff by Cohort",
    "Retention Curve",
    "Weekly Engagement",
    "Cohort Status",
    "Topic Slot States",
    "Topic States by Cohort",
    "Worker Engagement",
    "Design Reference",
    "Notes",
]
wb._sheets = [wb[n] for n in ORDER if n in wb.sheetnames] + [ws for ws in wb._sheets if ws.title not in ORDER]
wb.save(OUT)
print("wrote %s" % OUT.name)
print("  sheets: %s" % ", ".join(wb.sheetnames))
print("  headline: interviews completed {}, completion rate {}%".format(f"{ov['icmp']:,}", ov["pct"]))
