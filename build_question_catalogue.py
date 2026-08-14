"""Reconstruct the interview question catalogue from the transcripts themselves.

Why: the repo's `questions_round3_expanded.csv` covers only 16 parent questions across 2 topics
(A, B). Question text for every other topic exists nowhere in this repo. But OCS stamps the verbatim
question block onto every session as `state.interview_questions`, so the full catalogue is
recoverable from actuals at complete coverage — no external dependency.

Two grains, because the source has two shapes:

  * PRIMARY question  — the `Qn:` blocks. Topics A and B (onboarding) have discrete Q1..Q9.
  * SUB-PART          — for every other topic `total_questions == 1`, and that single Q1 is several
                        questions concatenated with NO separator. Verified boundary rule: a sub-part
                        break is `[.?!]` IMMEDIATELY followed by an uppercase letter. Sentence breaks
                        *within* a sub-part always carry a space ("...different? For example, do you
                        see patterns...") so they are not split. Checked by hand across codes 10, 11
                        and 13 — every boundary the rule finds is real and none is missed.

Honest limitation, recorded in the output as `subpart_split`: the no-space signal only exists where
the bot config concatenated questions. Topics A and B pack several asks into one Qn separated by
ordinary spaces, so those are NOT split and stay at the `Qn` grain (which is the grain Neal's
16-parent catalogue used for A/B anyway).

Question text is NOT assumed stable per code: prompt versions changed over the study, so a code can
have several question-block variants. Every distinct variant is kept, with the sessions that used
it, and downstream joins on the session's own variant rather than a code-level guess.

Reads `_ocs_messages.jsonl` (from pull_ocs_messages.py). Writes question_catalogue.json + .csv.
"""
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SRC = Path("_ocs_messages.jsonl")
OUT_JSON = Path("question_catalogue.json")
OUT_CSV = Path("question_catalogue.csv")

# Test / non-study interview codes. te00* are the bot test scripts ("What is your favourite colour?"),
# AE001 is an internal duplicate of the mortality script. Excluded from the study universe but
# reported so the exclusion is visible rather than silent.
TEST_CODE = re.compile(r"^(te\d+|ae\d+|test.*|[\W_]+)$", re.I)  # [\W_]+ catches junk codes like "--"

HEADER = re.compile(r"^\s*INTERVIEW QUESTIONS:\s*", re.I)
QSPLIT = re.compile(r"(?:^|\n)\s*Q(\d+)\s*:\s*")
# a sub-part boundary: terminal punctuation immediately followed by a capital, i.e. no space
SUBSPLIT = re.compile(r"(?<=[.?!])(?=[A-Z])")
# guard against splitting on abbreviations that legitimately end with '.' before a capital
ABBREV = re.compile(r"(?:e\.g|i\.e|etc|no|dr|mr|mrs|vs|approx)\.$", re.I)


def split_subparts(text):
    """Split one primary question into sub-parts on the verified no-space boundary."""
    parts, buf = [], ""
    for piece in SUBSPLIT.split(text):
        if buf and ABBREV.search(buf.strip()):
            buf += piece  # "e.g.Something" is an abbreviation, not a question boundary
            continue
        if buf:
            parts.append(buf)
        buf = piece
    if buf:
        parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def parse_block(iq):
    """`state.interview_questions` -> [{qid, text, subparts:[...]}]. Returns [] if unparseable."""
    if not iq or not str(iq).strip():
        return []
    body = HEADER.sub("", str(iq)).strip()
    hits = list(QSPLIT.finditer(body))
    if not hits:
        # no Qn markers at all — treat the whole block as one question
        return [{"qid": "Q1", "text": body, "subparts": split_subparts(body)}]
    out = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(body)
        text = body[m.end() : end].strip()
        if text:
            out.append({"qid": f"Q{m.group(1)}", "text": text, "subparts": split_subparts(text)})
    return out


def main():
    if not SRC.exists():
        raise SystemExit(f"missing {SRC} — run pull_ocs_messages.py first")

    # variants[(code, hash)] = {topic counter, total_questions counter, raw text, sessions}
    variants = {}
    n_lines = n_no_iq = 0
    for ln in SRC.open(encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        n_lines += 1
        iq = r.get("interview_questions")
        if not iq or not str(iq).strip():
            n_no_iq += 1
            continue
        code = str(r.get("interview") or "").strip()
        h = hashlib.sha1(str(iq).encode("utf-8")).hexdigest()[:10]
        v = variants.setdefault(
            (code, h),
            {
                "code": code,
                "hash": h,
                "raw": str(iq),
                "topics": Counter(),
                "totals": Counter(),
                "sessions": [],
            },
        )
        v["topics"][str(r.get("interview_topic") or "")] += 1
        v["totals"][r.get("total_questions")] += 1
        v["sessions"].append(r["sid"])

    codes = defaultdict(list)
    for (code, _h), v in variants.items():
        qs = parse_block(v["raw"])
        n_sub = sum(len(q["subparts"]) for q in qs)
        codes[code].append(
            {
                "hash": v["hash"],
                "topic": (v["topics"].most_common(1)[0][0] or None) if v["topics"] else None,
                "total_questions_declared": v["totals"].most_common(1)[0][0] if v["totals"] else None,
                "n_sessions": len(v["sessions"]),
                "n_primary": len(qs),
                "n_subparts": n_sub,
                # A/B pack asks with spaces, so their sub-part split is not meaningful; say so in the data
                "subpart_split": "derived" if n_sub > len(qs) else "none",
                "questions": qs,
                "session_ids": v["sessions"],
            }
        )

    study, excluded = {}, {}
    for code, vs in codes.items():
        vs.sort(key=lambda x: -x["n_sessions"])
        (excluded if (not code or code == "None" or TEST_CODE.match(code)) else study)[code] = vs

    payload = {
        "source": str(SRC),
        "sessions_read": n_lines,
        "sessions_without_question_block": n_no_iq,
        "study_codes": study,
        "excluded_codes": {
            k: [{kk: vv for kk, vv in v.items() if kk != "session_ids"} for v in vs] for k, vs in excluded.items()
        },
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "topic", "variant", "n_sessions", "qid", "subpart_id", "n_words", "text"])
        for code in sorted(study):
            for v in study[code]:
                for q in v["questions"]:
                    subs = q["subparts"] or [q["text"]]
                    for i, s in enumerate(subs, 1):
                        w.writerow(
                            [
                                code,
                                v["topic"],
                                v["hash"],
                                v["n_sessions"],
                                q["qid"],
                                f"{q['qid']}.{i}",
                                len(s.split()),
                                s,
                            ]
                        )

    tot_sub = sum(v["n_subparts"] for vs in study.values() for v in vs[:1])
    multi = [c for c, vs in study.items() if vs[0]["n_primary"] == 1 and vs[0]["n_subparts"] > 1]
    print(f"[catalogue] read {n_lines} sessions ({n_no_iq} had no question block)")
    print(f"[catalogue] study codes: {len(study)} | excluded (test/blank): {sorted(excluded) or 'none'}")
    print(f"[catalogue] sub-parts in the primary variant of each code: {tot_sub}")
    print(f"[catalogue] mega-question codes (1 primary, many sub-parts): {sorted(multi)}")
    print(f"{'code':<6}{'topic':<38}{'var':<5}{'sess':>6}{'prim':>6}{'sub':>5}  variants")
    for code in sorted(study, key=lambda c: (len(c), c)):
        vs = study[code]
        v = vs[0]
        print(
            f"{code:<6}{str(v['topic'])[:36]:<38}{v['hash'][:4]:<5}{v['n_sessions']:>6}"
            f"{v['n_primary']:>6}{v['n_subparts']:>5}  {len(vs)}"
        )
    if any(len(vs) > 1 for vs in study.values()):
        print("\n[catalogue] codes with >1 question-block variant (text changed during the study):")
        for code in sorted(study):
            vs = study[code]
            if len(vs) > 1:
                print(
                    f"  {code}: "
                    + ", ".join(f"{v['hash'][:4]}(n={v['n_sessions']},sub={v['n_subparts']})" for v in vs)
                )
    print(f"\n-> {OUT_JSON}, {OUT_CSV}")


if __name__ == "__main__":
    sys.exit(main())
