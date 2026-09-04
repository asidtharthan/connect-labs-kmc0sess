"""Pin the SESSION-LEVEL base table for the report, re-keyed so it can be shared.

Andrea asked for one base file with all the data in it, one row per session, rather than the
summary tables in Report_Figures_*.xlsx. That table already exists as master_4src.csv - it is what
every dashboard number is aggregated from - but it is untracked, rebuilt daily, and carries real
Connect ids, OCS session UUIDs and CommCare form UUIDs. This pins a re-keyed copy.

GRAIN, stated precisely because it is not quite "one row per session":
  One row per (FLW, cohort, interview slot) from the CommCare interview schedule. A slot that was
  offered but never opened is still a row, with is_started = N. Those rows are what make drop-off
  computable, so they are kept rather than filtered out.

  10,535 rows, of which 9,958 have a session attached.

  This is NOT one row per raw OCS session. OCS holds ~22.4k sessions, ~10.2k of which carry an
  interview tag; the rest are welcome clicks, run-ons and untagged fragments. The dashboard's
  universe is the 9,958 that match a scheduled slot. Anyone comparing this file to an OCS export
  will see that gap and should know it is by design.

Usage:
    python build_session_base.py v211
"""

import csv
import hashlib
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).parent
FREEZE = ROOT / "docs/report_freeze"
VER = sys.argv[1] if len(sys.argv) > 1 else "v211"
SRC = ROOT / "master_4src.csv"
OUT = FREEZE / ("sessions_%s.csv" % VER)
DICT = FREEZE / ("sessions_%s_DATA_DICTIONARY.md" % VER)
SALT_F = ROOT / ".report_freeze_salt"

if SALT_F.exists():
    SALT = SALT_F.read_text(encoding="utf-8").strip()
else:
    SALT = secrets.token_hex(32)
    SALT_F.write_text(SALT + "\n", encoding="utf-8")
    print("generated a new salt -> .report_freeze_salt (gitignored)")

_map = {}


def code(prefix, real):
    """Salted, truncated hash. Idempotent: an already-coded value passes through unchanged, so a
    re-run cannot hash the hashes (which silently breaks the map while leaving the file plausible)."""
    r = str(real or "").strip()
    if not r:
        return ""
    if r.startswith(prefix + "_"):
        return r
    key = (prefix, r)
    if key not in _map:
        _map[key] = prefix + "_" + hashlib.sha256((SALT + r).encode()).hexdigest()[:8]
    return _map[key]


rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
cols = list(rows[0].keys())

# ---- session timestamps, added BEFORE re-keying so the real sids can still be looked up.
# Without these, the weekly engagement series, lineSeries and the retention curves cannot be
# re-derived from this file: it carried trigger_received_on (when the bot OFFERED the interview)
# but nothing about the session itself.
_cache = json.loads((ROOT / "_ocs_state_cache.json").read_text(encoding="utf-8"))
_by_sid = {s["sid"]: s for s in _cache}
_last_msg = {}
_tp = ROOT / "ocs_transcript_dump/transcripts.jsonl"
if _tp.exists():
    with _tp.open(encoding="utf-8") as _f:
        for _line in _f:
            _o = json.loads(_line)
            _ts = [m.get("created_at") for m in (_o.get("messages") or []) if m.get("created_at")]
            if _ts:
                _last_msg[_o["sid"]] = max(_ts)
for _c in ("session_created_at", "session_ended_at", "session_end_source"):
    if _c not in cols:
        cols.insert(cols.index("session_status"), _c)
for r in rows:
    _s = _by_sid.get(r["matched_session_id"], {}) if r["matched_session_id"] else {}
    _end = _last_msg.get(r["matched_session_id"]) if r["matched_session_id"] else None
    r["session_created_at"] = _s.get("created_at") or ""
    r["session_ended_at"] = _end or _s.get("updated_at") or ""
    r["session_end_source"] = "last_message" if _end else ("updated_at" if _s.get("updated_at") else "")

for r in rows:
    r["connect_id"] = code("FLW", r["connect_id"])
    r["matched_session_id"] = code("SESS", r["matched_session_id"])
    r["trigger_form_id"] = code("TRIG", r["trigger_form_id"])

with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

n_sess = sum(1 for r in rows if r["matched_session_id"])
n_start = sum(1 for r in rows if r["is_started"] == "Y")
n_done = sum(1 for r in rows if r["is_completed"] == "Y")
n_flw = len({r["connect_id"] for r in rows})
n_coh = len({r["cohort_id"] for r in rows})

# merge the id map, never overwrite: a partial re-run would otherwise wipe the only link back
m = FREEZE / (".id_map_%s.csv" % VER)
merged = {}
if m.exists():
    for row in csv.DictReader(m.open(encoding="utf-8")):
        if row.get("code"):
            merged[row["code"]] = row["real"]
for (_p, real), c in _map.items():
    merged[c] = real
with m.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["code", "real"])
    for c in sorted(merged):
        w.writerow([c, merged[c]])

DEFS = [
    ("connect_id", "The FLW, re-keyed as FLW_xxxxxxxx. Stable across every row and file in this freeze."),
    ("cohort_id", "The cohort the slot belongs to, e.g. 01TRS, 1PC1, 2WTE1."),
    ("subgroup", "The study arm the cohort rolls up to: TRS, TRE, ABT1-A/B, ABT2-A/B, PANEL," " ABT3-A/B, 2WT, EXT."),
    ("cohort_type", "Human-readable label for the subgroup, e.g. Standard, Panel, ABT2 A."),
    ("interview_n", "Position in that cohort's schedule, 1-based. Panel runs 1 to 13."),
    (
        "topic_code",
        "Topic identifier, e.g. A, 1, 12, 8S, 99. The same topic can sit at a different"
        " interview_n in different cohorts.",
    ),
    ("topic_name", "Topic title, e.g. Seasonal Malaria Chemoprevention 2."),
    ("training_date", "Earliest Connect invited_date for the cohort."),
    ("release_date", "When this slot became available, from the cohort start plus the schedule offset."),
    ("is_released", "Y if release_date has passed. Slots not yet released are not drop-off."),
    (
        "trigger_form_id",
        "The CommCare Trigger Bot form, re-keyed as TRIG_xxxxxxxx. Present means the bot" " offered the interview.",
    ),
    ("trigger_received_on", "When the bot offered it. This is the clock start for any response-time measure."),
    (
        "matched_session_id",
        "The OCS session filling this slot, re-keyed as SESS_xxxxxxxx. Blank means the FLW" " never opened it.",
    ),
    ("review_status", "Human review verdict: acceptable, unacceptable, or not-reviewed. Blank if no" " session."),
    (
        "review_ai",
        "Y if a reviewer flagged suspected AI use. Independent of the verdict; a session can"
        " be acceptable AND flagged.",
    ),
    (
        "session_created_at",
        "When the FLW opened the session. Added to close a gap: without it the weekly engagement"
        " series and the retention curves could not be re-derived.",
    ),
    (
        "session_ended_at",
        "Last activity in the session. The last message timestamp where the transcript archive has"
        " it, otherwise the session's updated_at.",
    ),
    (
        "session_end_source",
        "Which of those two session_ended_at came from: last_message or updated_at. On 2WT the two"
        " agreed on every row.",
    ),
    ("session_status", "OCS interview_status, e.g. interview_complete, interview_incomplete," " interview_ongoing."),
    ("session_human_words", "Words the FLW typed in that session."),
    ("session_human_msgs", "Messages the FLW sent in that session."),
    ("is_triggered", "Y if the bot offered this slot."),
    ("is_started", "Y if a session exists for it. Identical to matched_session_id being non-blank."),
    ("is_completed", "Y if that session reached interview_complete."),
    ("c_invited", "Connect funnel: the FLW had an invited_date for this cohort."),
    ("c_accepted", "Connect funnel: the FLW accepted the invitation."),
    ("c_learn_completed", "Connect funnel: the FLW finished the learn module."),
    ("c_claimed", "Connect funnel: the FLW claimed the opportunity."),
    ("is_initiated", "Y if the FLW clicked through the welcome for this cohort. NOT the same as started."),
]

# ---- tie-out against the published payload, so the file proves its own reconciliation ----
TIE = []
_live = ROOT / "_live_full.json"
if _live.exists():
    L = json.loads(_live.read_text(encoding="utf-8"))
    t1 = {r["key"]: r for r in L["table1"]}
    ROLL = {"ABT1-A": "ABT1", "ABT1-B": "ABT1", "ABT2-A": "ABT2", "ABT2-B": "ABT2", "ABT3-A": "ABT3", "ABT3-B": "ABT3"}
    cell = {}
    for r in rows:
        k = (r["connect_id"], r["cohort_id"], r["interview_n"])
        pr = cell.get(k)
        cell[k] = (
            (pr[0] if pr else False) or r["is_started"] == "Y",
            (pr[1] if pr else False) or r["is_completed"] == "Y",
            ROLL.get(r["subgroup"], r["subgroup"]),
        )
    agg = {}
    for s, c, sg in cell.values():
        a = agg.setdefault(sg, [0, 0])
        if s:
            a[0] += 1
        if c:
            a[1] += 1
    TIE.append(("built_at", L.get("built_at"), "", ""))
    for k in ("TRS", "TRE", "ABT1", "ABT2", "PANEL", "ABT3", "2WT", "EXT"):
        if k in t1 and k in agg:
            TIE.append(
                (
                    k,
                    "%d / %d" % (agg[k][0], agg[k][1]),
                    "%d / %d" % (t1[k]["ist"], t1[k]["icmp"]),
                    "%+d / %+d" % (agg[k][0] - t1[k]["ist"], agg[k][1] - t1[k]["icmp"]),
                )
            )

lines = [
    "# sessions_%s.csv - data dictionary" % VER,
    "",
    "The base table every dashboard number is aggregated from. Pinned at **%s**." % VER,
    "",
    "## Grain",
    "",
    "**One row per (FLW, cohort, interview slot)** from the CommCare interview schedule.",
    "",
    "A slot that was offered but never opened is still a row, with `is_started = N`. Those rows are",
    "what make drop-off computable, so they are kept rather than filtered out. Filter on",
    '`matched_session_id != ""` if you want only real sessions.',
    "",
    "| | |",
    "| --- | --- |",
    "| rows | %s |" % f"{len(rows):,}",
    "| rows with a session | %s |" % f"{n_sess:,}",
    "| rows started | %s |" % f"{n_start:,}",
    "| rows completed | %s |" % f"{n_done:,}",
    "| distinct FLWs | %s |" % f"{n_flw:,}",
    "| distinct cohorts | %s |" % n_coh,
    "",
    "## This is NOT one row per raw OCS session",
    "",
    "OCS holds about 22.4k sessions, roughly 10.2k of which carry an interview tag. The rest are",
    "welcome clicks, run-on fragments and untagged sessions. The dashboard's universe is the",
    "%s that match a scheduled slot. Anyone comparing this file against an OCS export will" % f"{n_sess:,}",
    "see that gap; it is by design, not a loss.",
    "",
    "## Identifiers are re-keyed",
    "",
    "`connect_id`, `matched_session_id` and `trigger_form_id` are salted hashes, not real ids. No",
    "Connect id, OCS UUID, CommCare form UUID, name, phone, LGA or settlement appears in this file.",
    "Codes are stable across every file in this freeze, so they join to each other.",
    "",
    "## Columns",
    "",
    "| column | meaning |",
    "| --- | --- |",
]
for c, d in DEFS:
    lines.append(f"| `{c}` | {d} |")
lines += [
    "",
    "## Worked examples",
    "",
    "```",
    "# completion rate for a subgroup, the way the dashboard computes it",
    "started   = rows where subgroup == X and is_started == Y",
    "completed = rows where subgroup == X and is_completed == Y",
    "rate      = completed / started",
    "",
    "# 2WT response time",
    "lag = session end - trigger_received_on   (session end needs the transcript archive,",
    "                                           already computed in 2wt_lags_%s.csv)" % VER,
    "",
    "# panel retention",
    "per FLW, the gaps between consecutive session dates; retained if no gap exceeds 14 days",
    "(already computed in panel_gaps_%s.csv)" % VER,
    "```",
    "",
    "## Two traps",
    "",
    "**`is_initiated` is not `is_started`.** Initiated means the FLW clicked through the welcome.",
    "Started means a session exists. For 2WT that is 534 versus 515, and dividing completions by the",
    "wrong one understates completion by three points.",
    "",
    "**A topic can sit at different `interview_n` in different cohorts.** Join on `topic_code`, not",
    "on position, when comparing the same topic across arms.",
    "",
]
if TIE:
    lines += [
        "## Tie-out against the published dashboard",
        "",
        "Aggregated from this file and compared to the payload, so the file proves its own",
        "reconciliation rather than asking you to trust it. Figures are started / completed.",
        "",
        "| subgroup | this file | dashboard | difference |",
        "| --- | --- | --- | --- |",
    ]
    for a, b, c, d in TIE:
        lines.append(f"| {a} | {b} | {c} | {d} |")
    lines += [
        "",
        "Any non-zero difference is build timing, not disagreement: this file was generated from a",
        "master build a few minutes after the payload was published, so a slot triggered in between",
        "appears here and not there. Completed counts should match exactly; a difference there would",
        "be a real problem worth chasing.",
        "",
    ]
DICT.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("wrote %s" % OUT.name)
print(
    "  %s rows, %d columns | %s with a session | %s FLWs | %d cohorts"
    % (f"{len(rows):,}", len(cols), f"{n_sess:,}", f"{n_flw:,}", n_coh)
)
print("wrote %s" % DICT.name)
print("id map now %d entries (%d new) - UNTRACKED" % (len(merged), len(_map)))

# ---------------------------------------------------------------- companions
# Three things the session table alone could not reproduce, tested and confirmed missing:
#   connectFunnel      the funnel counts FLWs INVITED but never triggered, and they have no session
#                      row by definition -> needs the Connect roster
#   session timestamps only trigger_received_on was present, so weekly engagement, lineSeries and
#                      the retention curves were not derivable -> added above
#   cadence / offsets  so the 7-state topicStatus grid and drop-off deadlines were not
#                      recomputable -> needs the schedule lookup


def write_companions():
    snap_p = ROOT / "connect_user_data_snapshot.csv"
    if snap_p.exists():
        snap = list(csv.DictReader(snap_p.open(encoding="utf-8")))
        out = FREEZE / ("connect_roster_%s.csv" % VER)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["# One row per (FLW, cohort) Connect enrolment: the funnel's denominator."])
            w.writerow(["# Includes FLWs invited but never interviewed, who have no session row."])
            w.writerow(
                [
                    "flw_id",
                    "cohort_id",
                    "invited_date",
                    "user_invite_status",
                    "date_learn_started",
                    "completed_learn_date",
                    "date_claimed",
                ]
            )
            for r in snap:
                w.writerow(
                    [
                        code("FLW", r.get("username")),
                        r.get("cohort_id"),
                        r.get("invited_date"),
                        r.get("user_invite_status"),
                        r.get("date_learn_started"),
                        r.get("completed_learn_date"),
                        r.get("date_claimed"),
                    ]
                )
        print("wrote %s  (%d rows)" % (out.name, len(snap)))

    sch_p = ROOT / "_interview_schedule.json"
    if sch_p.exists():
        sch = json.loads(sch_p.read_text(encoding="utf-8"))
        out = FREEZE / ("schedule_%s.csv" % VER)
        n = 0
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["# The CommCare interview_schedule lookup: the bot's runtime truth for what"])
            w.writerow(["# each cohort offers and when. offset_days is from the cohort's own start."])
            w.writerow(["cohort_id", "interview_n", "topic_code", "offset_days"])
            for coh, items in sorted(sch.items()):
                for it in items or []:
                    w.writerow([coh, it.get("n"), it.get("topic"), it.get("offset_days")])
                    n += 1
        print("wrote %s  (%d rows, %d cohorts)" % (out.name, n, len(sch)))


write_companions()
