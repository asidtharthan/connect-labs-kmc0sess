"""One row per COMPLETED interview with its review verdict, for sharing with GiveWell. No transcripts.

    python build_gw_session_tags.py                         # verdicts as frozen on 7 Sep (report basis)
    python build_gw_session_tags.py --tags <tags.json>      # verdicts from a fresh OCS pull {sid: [tags]}

Base: docs/report_freeze/sessions_v214.csv (canonical rows, is_completed=Y -> 9,431 interviews, one OCS
session each). Its ids are re-keyed; the local id map turns them back into real Connect and session ids,
because this file is for sharing the real Connect IDs (agreed 2026-10-01). Output therefore carries real
identifiers and goes to `Final reports/`, which must never be committed.

Two verdicts, kept apart on purpose:
  verdict / suspected_ai     the OCS session tags, applied by the LLM evaluator. Every completed
                             interview has one or is "Not yet reviewed".
  human_review_*             the EHA annotation rounds (Reportings/*annotations.jsonl): 245 sessions,
                             each read by two people. Recorded in the annotation exports, NOT written
                             back onto the OCS tags, so the two can and do disagree.
Verdict precedence matches build_master_4src._review_status: unacceptable outranks acceptable.
"""

import csv
import glob
import json
import os
import sys
from collections import Counter
from datetime import date

FREEZE = os.path.join("docs", "report_freeze")
OUT_DIR = "Final reports"
LABEL = {"acceptable": "Acceptable", "unacceptable": "Unacceptable", "not-reviewed": "Not yet reviewed"}


def yes(v):
    return v in ("Y", "1", "True", "true")


def verdict_from_tags(tags):
    ts = set(tags or ())
    for v in ("unacceptable", "acceptable"):
        if v in ts:
            return v, "suspected_ai" in ts
    return "not-reviewed", "suspected_ai" in ts


def human_reviews():
    out = {}
    for f in sorted(glob.glob(os.path.join("Reportings", "*annotations.jsonl"))):
        rnd = next((w for w in ("First", "Second", "Third", "Fourth") if w in f), "?")
        for line in open(f, encoding="utf-8"):
            d = json.loads(line)
            acc = d["fields"].get("Acceptability", {}) or {}
            auth = d.get("authoritative_annotator")
            final = acc.get(auth) or (next(iter(acc.values())) if acc else "")
            agreed = len(set(acc.values())) == 1 if len(acc) > 1 else None
            out[d["session_id"]] = {
                "human_review_round": rnd,
                "human_review_verdict": final,
                "human_reviewers": len(acc),
                "human_reviewers_agreed": "" if agreed is None else ("Yes" if agreed else "No"),
            }
    return out


def main():
    tags_path = sys.argv[sys.argv.index("--tags") + 1] if "--tags" in sys.argv else None
    fresh = json.load(open(tags_path, encoding="utf-8")) if tags_path else None
    real = {
        r["code"]: r["real"] for r in csv.DictReader(open(os.path.join(FREEZE, ".id_map_v214.csv"), encoding="utf-8"))
    }
    human = human_reviews()
    allrows = list(csv.DictReader(open(os.path.join(FREEZE, "sessions_v214.csv"), encoding="utf-8")))
    rows = [r for r in allrows if yes(r["canonical_row"]) and yes(r["is_completed"])]
    # An interview sent twice can have two completed sessions with different tags. The verdict belongs to
    # the INTERVIEW, so take the strongest across all its completed sessions and OR the AI flag - the same
    # rule build_payload_agg uses for the dashboard (unacceptable > acceptable > not-reviewed). Without it
    # this file read 925 not-reviewed against the dashboard's 923 (two TRE interviews, 2026-10-02).
    twins = {}
    for r in allrows:
        if yes(r["is_completed"]) and r["matched_session_id"]:
            twins.setdefault((r["connect_id"], r["cohort_id"], r["interview_n"]), []).append(r)
    out, unmapped, changed = [], 0, Counter()
    for r in rows:
        cid, sid = real.get(r["connect_id"]), real.get(r["matched_session_id"])
        if not cid or not sid:
            unmapped += 1
            continue
        sibs = twins.get((r["connect_id"], r["cohort_id"], r["interview_n"]), [r])
        rank = {"unacceptable": 0, "acceptable": 1, "not-reviewed": 2}
        frozen_v = min((x["review_status"] or "not-reviewed" for x in sibs), key=rank.get)
        frozen_ai = any(x["review_ai"] == "Y" for x in sibs)
        if fresh is not None:
            vs = [verdict_from_tags(fresh.get(real.get(x["matched_session_id"]))) for x in sibs]
            v, ai = min((a for a, _ in vs), key=rank.get), any(b for _, b in vs)
        else:
            v, ai = frozen_v, frozen_ai
        if fresh is not None and (v, ai) != (frozen_v, frozen_ai):
            changed[(frozen_v, v)] += 1
        h = human.get(sid, {})
        out.append(
            {
                "connect_id": cid,
                "cohort_id": r["cohort_id"],
                "subgroup": r["subgroup"],
                "interview_n": r["interview_n"],
                "topic_code": r["topic_code"],
                "topic_name": r["topic_name"],
                "session_id": sid,
                "session_date": (r["session_created_at"] or "")[:10],
                "verdict": LABEL[v],
                "suspected_ai": "Yes" if ai else "No",
                "verdict_source": "OCS evaluator tags" if v != "not-reviewed" else "",
                "human_review_round": h.get("human_review_round", ""),
                "human_review_verdict": h.get("human_review_verdict", ""),
                "human_reviewers_agreed": h.get("human_reviewers_agreed", ""),
            }
        )
    out.sort(key=lambda x: (x["connect_id"], x["cohort_id"], int(x["interview_n"] or 0)))
    asof = "2026-09-07" if fresh is None else date.today().isoformat()
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "GW_interview_review_verdicts_%s.csv" % asof)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    c = Counter(x["verdict"] for x in out)
    print("tags: %s" % (tags_path or "frozen 7 Sep (sessions_v214.csv)"))
    print(
        "rows %d (completed interviews), unmapped ids %d, distinct Connect IDs %d"
        % (len(out), unmapped, len({x["connect_id"] for x in out}))
    )
    print("verdicts: %s | suspected AI: %d" % (dict(c), sum(x["suspected_ai"] == "Yes" for x in out)))
    print(
        "human-reviewed rows: %d | %s"
        % (
            sum(1 for x in out if x["human_review_verdict"]),
            dict(Counter(x["human_review_verdict"] for x in out if x["human_review_verdict"])),
        )
    )
    if fresh is not None:
        print("verdicts changed vs frozen (frozen -> fresh): %s" % dict(changed))
    print("-> %s" % path)


if __name__ == "__main__":
    main()
