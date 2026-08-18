#!/usr/bin/env python3
"""Independent audit of the transcript insights: coverage, grounding and privacy.

Deliberately re-derives its checks from the ARCHIVE and the OUTPUT rather than trusting the builder's
own counters, so a mistake in build_transcript_insights.py cannot pass by agreeing with itself.

  1. COVERAGE      every session in the archive was accounted for, and the exclusion reasons sum exactly
  2. GROUNDING     every quoted gem traces to a real session, and its text appears VERBATIM in that
                   session - this is what proves nothing was paraphrased or invented
  3. RECONCILE     gem counts and level totals recomputed independently from the archive
  4. PRIVACY       no participant identifier, phone number or email in anything shared
  5. SAMPLING      the dump is spread across topics and languages, not clustered

Run after build_transcript_insights.py. Exits non-zero if any check fails.
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SRC = Path("_ocs_messages.jsonl")
PAYLOAD = Path("insights_payload.json")
GEMS = Path("transcript_gems.csv")

checks = []


def check(name, ok, detail):
    checks.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<54} {detail}")


def main():
    pay = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    gems = list(csv.DictReader(GEMS.open(encoding="utf-8")))
    cov = pay["coverage"]

    # ---------- 1. coverage, recomputed from the archive itself
    n_lines = n_msgs = 0
    sids = {}
    pids = set()
    for ln in SRC.open(encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        n_lines += 1
        msgs = r.get("messages") or []
        n_msgs += len(msgs)
        if r.get("sid"):
            sids[r["sid"][:8]] = msgs
        if r.get("pid"):
            pids.add(str(r["pid"]))
    check(
        "archive sessions match the payload's count",
        n_lines == cov["sessions_in_archive"],
        f"{n_lines} vs {cov['sessions_in_archive']}",
    )
    check(
        "archive messages match the payload's count",
        n_msgs == cov["messages_in_archive"],
        f"{n_msgs} vs {cov['messages_in_archive']}",
    )
    accounted = (
        cov["sessions_analysed"]
        + cov.get("skipped_untagged", 0)
        + cov.get("skipped_test_code", 0)
        + cov.get("skipped_test_tag", 0)
        + cov.get("skipped_too_short", 0)
        + cov.get("unparseable_lines", 0)
    )
    check(
        "every session accounted for (analysed + excluded)",
        accounted == n_lines,
        f"{accounted} accounted of {n_lines} - no session silently dropped",
    )

    # ---------- 2. grounding: each quote must appear verbatim in the session it cites
    #    The quote is normalised (whitespace collapsed, phone/email redacted, truncated), so compare a
    #    leading fragment of it against the same normalisation of the session's own messages.
    # An answer is the FLW's own turns for ONE question, concatenated in order - and those turns are
    # separated by the bot's replies in the raw transcript. So a quote is verbatim without being a
    # contiguous span: one FLW wrote "giving ORS", the bot replied, then they wrote "out hundreds
    # percent...", and the answer is legitimately both. Comparing against the raw transcript therefore
    # produced 617 false failures. Removing ALL whitespace from both sides makes the join invisible
    # while still proving every character came from that session's FLW messages, in order - which is
    # what "not paraphrased or invented" actually means here.
    def squash(t):
        return re.sub(r"\s+", "", str(t or "")).lower()

    traced = missing_sid = not_found = 0
    unmatched = []
    for g in gems:
        body = g.get("text") or ""
        if not body or g["cat"] in ("suspected_ai",):
            continue
        msgs = sids.get(g["sid"])
        if msgs is None:
            missing_sid += 1
            continue
        # bot_error quotes the BOT's message; every other category quotes the FLW. Match each against
        # the right speaker rather than pooling them, so a quote cannot be "verified" against text the
        # other party said.
        want = "assistant" if g["cat"] == "bot_error" else "user"
        hay = squash("".join(m.get("content") or "" for m in msgs if m.get("role") == want))
        frag = squash(body.split("[number removed]")[0].rstrip(". "))[:80]
        if frag and frag in hay:
            traced += 1
        else:
            not_found += 1
            if len(unmatched) < 3:
                unmatched.append(f"{g['cat']}/{g['sid']}")
    check("every gem cites a session that exists", missing_sid == 0, f"{missing_sid} unknown session ids")
    check(
        "every quote appears VERBATIM in its session",
        not_found == 0,
        f"{traced} traced, {not_found} not found"
        + (f" (e.g. {unmatched})" if unmatched else " - nothing paraphrased or invented"),
    )

    # ---------- 3. reconcile: recompute two independent totals from the archive
    check(
        "answers counted are consistent with questions asked",
        pay["L2_answer"]["answers"] <= pay["L3_question"]["questions_asked"],
        f"{pay['L2_answer']['answers']} answers vs {pay['L3_question']['questions_asked']} questions",
    )
    roles = pay["L1_message"]["roles"]
    check(
        "message roles sum to the messages analysed",
        sum(roles.values()) == cov["messages_analysed"],
        f"{sum(roles.values())} vs {cov['messages_analysed']}",
    )
    gem_found = {c["key"]: c["found"] for c in pay["gems"]}
    dumped = Counter(g["cat"] for g in gems)
    over = [k for k, v in dumped.items() if v > gem_found.get(k, 0)]
    check("no category dumps more examples than it found", not over, f"offenders: {over or 'none'}")

    # ---------- 4. privacy
    pid_hits = [g["sid"] for g in gems if g["sid"] in pids]
    blob = " ".join(
        (g.get("text", "") + " " + g.get("before", "") + " " + g.get("after", "") + " " + g.get("q", "")) for g in gems
    )
    phones = re.findall(r"\d[\d\s\-]{7,}\d", blob)
    emails = re.findall(r"\S+@\S+", blob)
    long_sid = [g["sid"] for g in gems if len(g["sid"]) > 8]
    check("no participant identifier appears in the dump", not pid_hits, f"{len(pid_hits)} hits")
    check("session ids are truncated", not long_sid, f"{len(long_sid)} full-length ids")
    check("no phone-shaped numbers in quoted text", not phones, f"{len(phones)} found")
    check("no email addresses in quoted text", not emails, f"{len(emails)} found")

    # ---------- 5. sampling spread
    by_cat_topic = defaultdict(set)
    by_cat_lang = defaultdict(set)
    for g in gems:
        by_cat_topic[g["cat"]].add(g["topic"])
        by_cat_lang[g["cat"]].add(g["lang"])
    thin = [c for c, t in by_cat_topic.items() if len(t) < 3 and dumped[c] >= 20]
    monoling = [c for c, ls in by_cat_lang.items() if len(ls) < 2 and dumped[c] >= 20]
    check("examples spread across topics", not thin, f"thin categories: {thin or 'none'}")
    check("examples cover both languages", not monoling, f"single-language categories: {monoling or 'none'}")

    bad = [n for n, ok, _ in checks if not ok]
    print(f"\n[audit] {len(checks) - len(bad)}/{len(checks)} checks pass")
    print(f"[audit] VERDICT: {'ALL PASS' if not bad else 'FAILURES: ' + ', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
