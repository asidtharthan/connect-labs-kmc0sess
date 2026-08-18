#!/usr/bin/env python3
"""build_transcript_insights.py - every interview transcript, analysed level by level, plus a gem dump.

Reads the FULL local archive (_ocs_messages.jsonl, produced by pull_ocs_messages.py --all) and walks it
from the smallest unit upward:

    L0 corpus -> L1 message -> L2 answer -> L3 question -> L4 session -> L5 FLW -> L6 topic
    -> L7 subgroup -> L8 programme

Nothing is sampled for the AGGREGATES: every session in the archive is visited, and the coverage
counters at the end must reconcile to the archive totals or the run reports a gap. Sampling applies
only to the verbatim examples, and there it is deterministic (fixed seed) and stratified.

WHY A SEPARATE SCRIPT FROM THE PROBING ANALYSIS
build_probing_analysis.py asks one narrow question (did probing improve the answer). This asks the open
question - what is actually IN these conversations - so it keeps every message, including the ones the
probing analysis deliberately ignores.

GEM DETECTORS ARE BILINGUAL AND DATA-GROUNDED
~40% of sessions run in Hausa, so English-only keywords would have quietly reported that Hausa FLWs say
less of interest. Every marker below was chosen by mining the corpus's own vocabulary first:
    reasoning   because            / saboda, domin
    absence     don't, no, without / babu ("there is none"), rashin ("lack of")
    contrast    but                / amma
    candour     honestly, truly    / gaskiya
Frequencies were checked before use, so these are observed usage rather than guessed translations.

PRIVACY: no participant identifier is ever written out. Session ids are truncated to 8 characters for
traceability only, and long digit runs (phone-number shaped) are redacted from quoted text.

Outputs: insights_payload.json (all aggregates + selected gems), transcript_gems.csv (the full dump).
Run: .venv/Scripts/python.exe build_transcript_insights.py
"""
import csv
import json
import random
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from build_probing_analysis import variant_subparts
from build_question_catalogue import TEST_CODE
from probe_detect import classify_turns, is_nonanswer, norm_lang

SRC = Path("_ocs_messages.jsonl")
OUT_PAYLOAD = Path("insights_payload.json")
OUT_GEMS = Path("transcript_gems.csv")
SEED = 20260817
PER_CELL = 6  # verbatim examples kept per (category x topic) cell
MAX_QUOTE = 420  # characters of an answer kept in the dump


# ---------------------------------------------------------------- text helpers
def fold(s):
    s = (s or "").lower().replace("ɓ", "b").replace("ɗ", "d").replace("ƙ", "k")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


PHONE = re.compile(r"\d[\d\s\-]{6,}\d")
EMAIL = re.compile(r"\S+@\S+")


def clean(t, limit=MAX_QUOTE):
    """One line, no identifiers, truncated. Long digit runs are phone-shaped and get redacted."""
    t = " ".join(str(t or "").split())
    t = PHONE.sub("[number removed]", t)
    t = EMAIL.sub("[email removed]", t)
    return t[:limit] + ("..." if len(t) > limit else "")


# markers, each verified against corpus frequency before being relied on
M_REASON = re.compile(r"\bbecause\b|\bsaboda\b|\bdomin\b|\bdon haka\b|\bshi ya sa\b")
M_ABSENT = re.compile(
    r"\bbabu\b|\brashin\b|\bdon'?t have\b|\bno\b" r"|\bnot available\b|\bwithout\b|\bshortage\b|\bran out\b"
)
# "rashin lafiya" literally reads "lack of health" but simply means ILLNESS, so it is not a report of
# something missing. Checked before excluding: it is 9% of all "rashin" uses, while the rest are real
# shortages (rashin tsaro = insecurity, rashin kudi = no money, rashin abinci = no food). Excluding the
# whole word would have thrown away far more signal than it removed.
M_ILLNESS = re.compile(r"\brashin\s+lafiy\w*\b|\brashin\s+lfy\b")
# What FLWs say is missing, taken from their own words rather than a prepared list.
BARRIER_OF = re.compile(r"\b(?:rashin|babu)\s+([a-z]{3,})|\b(?:lack of|no|without)\s+([a-z]{3,})")
M_CONTRAST = re.compile(r"\bbut\b|\bamma\b|\bhowever\b")
M_CANDOUR = re.compile(r"\bgaskiya\b|\bhonestly\b|\bto be honest\b|\btruly\b|\bin truth\b")
M_EXAMPLE = re.compile(r"\bfor example\b|\bmisali\b|\bsuch as\b|\be\.g\b")
M_DIGIT = re.compile(r"\d")
M_DONTKNOW = re.compile(r"\bban sani\b|\bbansani\b|\bdon'?t know\b|\bno idea\b|\bnot sure\b")
M_CONFUSED = re.compile(r"\bban gane\b|\bdon'?t understand\b|\bwhat do you mean\b|\brepeat the question\b")
# concrete subject matter, all present in the mined vocabulary
M_TOPICWORDS = re.compile(
    r"\basibiti\b|\bmagani\b|\bmaganin\b|\byara\b|\bsauro\b|\blafiya\b|\bgida\b|"
    r"\bhospital\b|\bclinic\b|\bdrug\b|\bmedicine\b|\bchildren\b|\bmosquito\b|\bfacility\b"
)
# Words that follow an absence marker without naming what is missing: agreement tokens ("no yes"),
# connectives ("no because"), modifiers ("no proper", "no enough") and the negation itself ("nobody").
# Removed only after reading the collocations - the real shortages FLWs name are nouns, and those stay.
BARRIER_STOP = {
    "one",
    "any",
    "the",
    "and",
    "for",
    "not",
    "but",
    "you",
    "they",
    "wani",
    "wata",
    "wanda",
    "sai",
    "har",
    "sun",
    "suna",
    "ban",
    "kuma",
    "dai",
    "shi",
    "koda",
    "que",
    "lokacin",
    "abin",
    "yadda",
    "matsala",
    "matsalar",
    "problem",
    "idea",
    "more",
    "yes",
    "because",
    "there",
    "gaskiya",
    "proper",
    "other",
    "only",
    "sir",
    "need",
    "good",
    "saboda",
    "wannan",
    "babu",
    "body",
    "enough",
    "some",
    "much",
    "many",
    "that",
    "this",
    "well",
    "such",
    "very",
    "just",
    "also",
    "even",
    "still",
    "been",
    "have",
    "has",
    "was",
    "were",
    "are",
    "will",
    "can",
    "would",
    "should",
    "could",
    "amma",
    "duk",
    "sosai",
    "kadan",
    "yawa",
    "haka",
    "nan",
    "wasu",
    "masu",
    "cikin",
}
GIBBERISH = re.compile(r"^[^aeiou\s]{6,}$|^(.)\1{3,}$")

CATEGORIES = [
    (
        "rich_detail",
        "Unusually full answers",
        "Top-decile length with at least two specificity markers - the answers that actually carry " "content.",
    ),
    (
        "reasoning",
        "Answers that explain WHY",
        "Contains a causal marker (because / saboda / domin). These are the ones that tell you a "
        "mechanism, not just a number.",
    ),
    (
        "barrier",
        "Problems and shortages reported",
        "Contains an absence marker (babu / rashin / no / not available). What the FLW says is missing " "or broken.",
    ),
    (
        "quantified",
        "Numbers with reasoning attached",
        "A figure AND an explanation in the same answer - an estimate you can interrogate rather than a "
        "bare digit.",
    ),
    (
        "candour",
        "Candid and hedged answers (mostly Hausa)",
        "Marked with gaskiya / honestly. NOT comparable across languages: gaskiya is an everyday "
        "Hausa discourse particle appearing in about 4% of Hausa messages, while English honestly is "
        "rarer, so this category is overwhelmingly Hausa by construction rather than because Hausa "
        "speakers are more candid.",
    ),
    (
        "example",
        "Concrete examples given",
        "Contains an example marker (misali / for example) - a specific case rather than a " "generality.",
    ),
    (
        "probe_rescue",
        "Answers the probe rescued",
        "Started unusable, ended usable. The clearest evidence of what the conversational format " "buys.",
    ),
    (
        "confusion_recovery",
        "Recovered from not understanding",
        "FLW said they did not understand, then produced a usable answer after the bot " "rephrased.",
    ),
    (
        "dontknow",
        "Explicit 'I do not know'",
        "Where knowledge genuinely stops - useful in itself, and distinct from a " "refusal.",
    ),
    (
        "data_quality",
        "Low-quality or junk answers",
        "Gibberish, single characters or repeats. Counted honestly so the corpus is not " "oversold.",
    ),
    (
        "bot_error",
        "Platform errors mid-interview",
        "The bot failed to process a message. Rare, but it interrupts a real " "conversation.",
    ),
    (
        "suspected_ai",
        "Sessions flagged as suspected AI use",
        "Flagged upstream by OCS, surfaced here so the team can review " "them.",
    ),
]


def ai_flagged(v):
    """OCS stores suspected_ai_use as 'yes' / 'no' / '' (sometimes wrapped in a list), never a boolean.
    A plain truth test therefore counts every 'no' as a flag - which reported 45% of sessions as
    suspected AI use instead of the true 1.2%. Only an explicit yes counts."""
    if isinstance(v, (list, tuple)):
        return any(ai_flagged(x) for x in v)
    return str(v or "").strip().lower() in ("yes", "true", "1")


def markers(f):
    return {
        "reason": bool(M_REASON.search(f)),
        "absent": bool(M_ABSENT.search(M_ILLNESS.sub(" ", f))),
        "contrast": bool(M_CONTRAST.search(f)),
        "candour": bool(M_CANDOUR.search(f)),
        "example": bool(M_EXAMPLE.search(f)),
        "digit": bool(M_DIGIT.search(f)),
        "topical": bool(M_TOPICWORDS.search(f)),
    }


def main():
    if not SRC.exists():
        raise SystemExit(f"missing {SRC} - run pull_ocs_messages.py --all first")
    rng = random.Random(SEED)

    # Some sessions carry no interview_topic even though others of the same code do, which left topics
    # showing as "code A" instead of their name. Cheap pre-pass to resolve every code to the name its
    # own sessions use most often, so no topic is reported by bare code.
    name_votes = defaultdict(Counter)
    for _ln in SRC.open(encoding="utf-8"):
        _ln = _ln.strip()
        if not _ln:
            continue
        try:
            _r = json.loads(_ln)
        except ValueError:
            continue
        _c, _t = str(_r.get("interview") or "").strip(), (_r.get("interview_topic") or "").strip()
        if _c and _t:
            name_votes[_c][_t] += 1
    TOPIC_NAME = {c: v.most_common(1)[0][0] for c, v in name_votes.items()}

    # ---- coverage counters: these must reconcile to the archive or the run says so
    cov = Counter()
    L1 = {"flw_words": [], "bot_words": [], "roles": Counter(), "errors": 0, "system_msgs": 0, "system_words": 0}
    answers = []  # per FLW turn (compact: words + marker bits) for L2
    windows_n = probes_n = 0
    sess_rows = []  # L4
    flw_words = Counter()
    flw_sessions = Counter()
    topic_stat = defaultdict(
        lambda: {
            "sessions": 0,
            "answers": 0,
            "words": 0,
            "probes": 0,
            "windows": 0,
            "rescued": 0,
            "dontknow": 0,
            "name": "",
        }
    )
    sg_stat = defaultdict(lambda: {"sessions": 0, "answers": 0, "words": 0, "flws": set()})
    lang_stat = Counter()
    marker_stat = Counter()
    barrier_of = Counter()
    hour_stat = Counter()
    gems = defaultdict(list)

    def dt(s):
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    for line in SRC.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            cov["unparseable_lines"] += 1
            continue
        cov["sessions_in_archive"] += 1
        code = str(rec.get("interview") or "").strip()
        msgs = rec.get("messages") or []
        cov["messages_in_archive"] += len(msgs)

        if not code:
            cov["skipped_untagged"] += 1
            continue
        if TEST_CODE.match(code):
            cov["skipped_test_code"] += 1
            continue
        tags = [str(t).lower() for t in (rec.get("session_tags") or [])]
        if "test" in tags:
            cov["skipped_test_tag"] += 1
            continue
        if len(msgs) < 2:
            cov["skipped_too_short"] += 1
            continue

        cov["sessions_analysed"] += 1
        cov["messages_analysed"] += len(msgs)
        lang = norm_lang(rec.get("preferred_language"))
        topic = (rec.get("interview_topic") or "").strip() or TOPIC_NAME.get(code) or ("code " + code)
        sid = rec.get("sid") or ""
        pid = rec.get("pid") or ""
        lang_stat[lang] += 1
        topic_stat[code]["name"] = topic
        topic_stat[code]["sessions"] += 1
        sg_stat[code]["sessions"] += 1
        if pid:
            flw_sessions[pid] += 1

        _v, subs, stoks, qp = variant_subparts(rec.get("interview_questions"))
        turns, wins = classify_turns(msgs, subs, subpart_toks=stoks, subpart_qp=qp)

        # ---------- L1 message level
        first_dt = last_dt = None
        sess_flw_words = 0
        for m in msgs:
            role = m.get("role")
            L1["roles"][role] += 1
            txt = m.get("content") or ""
            w = len(txt.split())
            d = dt(m.get("created_at"))
            if d:
                first_dt = d if first_dt is None or d < first_dt else first_dt
                last_dt = d if last_dt is None or d > last_dt else last_dt
            if role == "user":
                L1["flw_words"].append(w)
                sess_flw_words += w
            elif role == "assistant":
                L1["bot_words"].append(w)
                if re.search(r"something went wrong|please try again later", txt, re.I):
                    L1["errors"] += 1
                    gems["bot_error"].append(
                        {
                            "cat": "bot_error",
                            "sid": sid[:8],
                            "code": code,
                            "topic": topic,
                            "lang": lang,
                            "q": "",
                            "text": clean(txt, 200),
                            "before": "",
                            "after": "",
                            "words": w,
                        }
                    )
            elif role == "system":
                L1["system_msgs"] += 1
                L1["system_words"] += w
        if first_dt:
            hour_stat[first_dt.hour] += 1
        if pid:
            flw_words[pid] += sess_flw_words
        sg_stat[code]["words"] += sess_flw_words
        if pid:
            sg_stat[code]["flws"].add(pid)

        # ---------- L2/L3 answer and question level
        for w in wins:
            windows_n += 1
            topic_stat[code]["windows"] += 1
            probes = w["probes"]
            probes_n += len(probes)
            topic_stat[code]["probes"] += len(probes)
            qtext = w.get("subpart_text") or w.get("ask_text") or ""
            ans = w["answers"]
            cut = probes[0]["i"] if probes else None
            pre = " ".join(a["text"] for a in ans if cut is None or a["i"] < cut)
            fin = " ".join(a["text"] for a in ans)
            if fin.strip():
                f = fold(fin)
                mk = markers(f)
                nw = len(fin.split())
                answers.append((nw, mk["reason"], mk["absent"], mk["candour"], mk["example"], mk["digit"]))
                topic_stat[code]["answers"] += 1
                topic_stat[code]["words"] += nw
                sg_stat[code]["answers"] += 1
                for k, v in mk.items():
                    if v:
                        marker_stat[k] += 1
                # what is missing, in the FLW's own words
                for a1, a2 in BARRIER_OF.findall(M_ILLNESS.sub(" ", f)):
                    w0 = (a1 or a2).strip()
                    if w0 and w0 not in BARRIER_STOP:
                        barrier_of[w0] += 1

                base = {
                    "sid": sid[:8],
                    "code": code,
                    "topic": topic,
                    "lang": lang,
                    "q": clean(qtext, 220),
                    "text": clean(fin),
                    "words": nw,
                    "before": "",
                    "after": "",
                }
                _mk_keys = ("reason", "absent", "contrast", "candour", "example", "digit", "topical")
                nmark = sum(1 for k in _mk_keys if mk[k])
                if nw >= 45 and nmark >= 2:
                    gems["rich_detail"].append(dict(base, cat="rich_detail"))
                if mk["reason"] and nw >= 15:
                    gems["reasoning"].append(dict(base, cat="reasoning"))
                if mk["absent"] and nw >= 12 and mk["topical"]:
                    gems["barrier"].append(dict(base, cat="barrier"))
                if mk["digit"] and mk["reason"] and nw >= 12:
                    gems["quantified"].append(dict(base, cat="quantified"))
                if mk["candour"] and nw >= 12:
                    gems["candour"].append(dict(base, cat="candour"))
                if mk["example"] and nw >= 15:
                    gems["example"].append(dict(base, cat="example"))
                if M_DONTKNOW.search(f):
                    topic_stat[code]["dontknow"] += 1
                    if nw <= 25:
                        gems["dontknow"].append(dict(base, cat="dontknow"))
                if GIBBERISH.search(fold(fin.strip())) or nw <= 1:
                    gems["data_quality"].append(dict(base, cat="data_quality"))

                # probe rescue + confusion recovery, using the same usable test as the probing analysis
                if probes and is_nonanswer(pre) and not is_nonanswer(fin):
                    topic_stat[code]["rescued"] += 1
                    gems["probe_rescue"].append(
                        dict(base, cat="probe_rescue", before=clean(pre, 200), after=clean(probes[0]["text"], 220))
                    )
                # Confusion is expressed in ANY turn of the exchange, and usually AFTER the bot has
                # probed - not in the opening answer. Scanning only the pre-probe text found zero cases
                # when the pattern is plainly present, so scan every FLW turn in the window and require
                # that a LATER turn recovered.
                if probes:
                    conf_i = next((a["i"] for a in ans if M_CONFUSED.search(fold(a["text"]))), None)
                    if conf_i is not None:
                        later = " ".join(a["text"] for a in ans if a["i"] > conf_i)
                        if later.strip() and not is_nonanswer(later):
                            gems["confusion_recovery"].append(
                                dict(
                                    base,
                                    cat="confusion_recovery",
                                    before=clean(next(a["text"] for a in ans if a["i"] == conf_i), 160),
                                    after=clean(
                                        next((p["text"] for p in probes if p["i"] > conf_i), probes[-1]["text"]), 240
                                    ),
                                    text=clean(later),
                                )
                            )

        # ---------- L4 session level
        dur = round((last_dt - first_dt).total_seconds() / 60, 1) if (first_dt and last_dt) else None
        sess_rows.append(
            {
                "sid": sid[:8],
                "code": code,
                "topic": topic,
                "lang": lang,
                "status": rec.get("interview_status"),
                "msgs": len(msgs),
                "flw_words": sess_flw_words,
                "windows": len(wins),
                "probes": sum(len(w["probes"]) for w in wins),
                "dur_min": dur,
                "tags": "|".join(tags),
                "suspected_ai": ai_flagged(rec.get("suspected_ai_use")),
            }
        )
        if ai_flagged(rec.get("suspected_ai_use")):
            gems["suspected_ai"].append(
                {
                    "cat": "suspected_ai",
                    "sid": sid[:8],
                    "code": code,
                    "topic": topic,
                    "lang": lang,
                    "q": "",
                    "text": "session flagged by OCS as suspected AI use",
                    "before": "",
                    "after": "",
                    "words": sess_flw_words,
                }
            )

    # ---------------------------------------------------------------- aggregate
    def pct(a, b, nd=1):
        return round(100 * a / b, nd) if b else 0.0

    def dist(xs):
        if not xs:
            return {}
        s = sorted(xs)
        return {
            "n": len(s),
            "mean": round(statistics.mean(s), 1),
            "median": s[len(s) // 2],
            "p10": s[int(0.10 * len(s))],
            "p90": s[int(0.90 * len(s))],
            "max": s[-1],
        }

    n_ans = len(answers)
    aw = [a[0] for a in answers]
    durs = [r["dur_min"] for r in sess_rows if r["dur_min"] is not None and 0 <= r["dur_min"] <= 60 * 24]

    payload = {
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "seed": SEED,
        "coverage": dict(cov),
        "L0_corpus": {
            "sessions_analysed": cov["sessions_analysed"],
            "messages_analysed": cov["messages_analysed"],
            "flws": len(flw_sessions),
            "topics": len(topic_stat),
            "languages": dict(lang_stat.most_common()),
        },
        "L1_message": {
            "roles": dict(L1["roles"]),
            "flw_words": dist(L1["flw_words"]),
            "bot_words": dist(L1["bot_words"]),
            "platform_errors": L1["errors"],
            "system_messages": L1["system_msgs"],
            "system_words": L1["system_words"],
        },
        "barriers_named": [{"word": w, "n": c} for w, c in barrier_of.most_common(40)],
        "L2_answer": {
            "answers": n_ans,
            "words": dist(aw),
            "markers": {k: {"n": v, "pct": pct(v, n_ans)} for k, v in marker_stat.most_common()},
        },
        "L3_question": {
            "questions_asked": windows_n,
            "probing_turns": probes_n,
            "probes_per_question": round(probes_n / windows_n, 2) if windows_n else 0,
        },
        "L4_session": {
            "sessions": len(sess_rows),
            "duration_min": dist(durs),
            "messages": dist([r["msgs"] for r in sess_rows]),
            "flw_words": dist([r["flw_words"] for r in sess_rows]),
            "complete_pct": pct(sum(1 for r in sess_rows if r["status"] == "interview_complete"), len(sess_rows)),
            "suspected_ai": sum(1 for r in sess_rows if r["suspected_ai"]),
            "start_hour_utc": {str(h): hour_stat[h] for h in sorted(hour_stat)},
            "human_tags": dict(Counter(t for r in sess_rows for t in r["tags"].split("|") if t).most_common()),
        },
        "L5_flw": {
            "flws": len(flw_sessions),
            "sessions_per_flw": dist(list(flw_sessions.values())),
            "total_words_per_flw": dist(list(flw_words.values())),
        },
        "L6_topic": sorted(
            [
                {
                    "code": c,
                    "name": v["name"],
                    "sessions": v["sessions"],
                    "answers": v["answers"],
                    "mean_words": round(v["words"] / v["answers"], 1) if v["answers"] else 0,
                    "probes_per_question": round(v["probes"] / v["windows"], 2) if v["windows"] else 0,
                    "rescued": v["rescued"],
                    "dontknow_pct": pct(v["dontknow"], v["answers"]),
                }
                for c, v in topic_stat.items()
            ],
            key=lambda r: -r["sessions"],
        ),
        "L7_subgroup": sorted(
            [
                {
                    "code": c,
                    "sessions": v["sessions"],
                    "flws": len(v["flws"]),
                    "answers": v["answers"],
                    "mean_words": round(v["words"] / v["answers"], 1) if v["answers"] else 0,
                }
                for c, v in sg_stat.items()
            ],
            key=lambda r: -r["sessions"],
        ),
    }

    # ---------------------------------------------------------------- gems: counts, then a fair sample
    cats = []
    picked = []
    for key, title, how in CATEGORIES:
        pool = gems.get(key, [])
        # stratify by topic so one big cohort cannot dominate the examples
        by_topic = defaultdict(list)
        for g in pool:
            by_topic[g["topic"]].append(g)
        sample = []
        for t in sorted(by_topic):
            items = by_topic[t]
            rng.shuffle(items)
            sample += items[:PER_CELL]
        rng.shuffle(sample)
        cats.append(
            {
                "key": key,
                "title": title,
                "how": how,
                "found": len(pool),
                "pct_of_answers": pct(len(pool), n_ans) if key not in ("bot_error", "suspected_ai") else None,
                "topics_covered": len(by_topic),
                "sampled": len(sample),
                "by_language": dict(Counter(g["lang"] for g in pool).most_common()),
                "examples": sample[:32],
            }
        )
        picked += sample
    payload["gems"] = cats
    payload["gem_totals"] = {
        "categories": len(cats),
        "candidates": sum(c["found"] for c in cats),
        "dumped": len(picked),
    }

    OUT_PAYLOAD.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    with OUT_GEMS.open("w", newline="", encoding="utf-8") as fh:
        # english_gloss is intentionally EMPTY. Published guidance on multilingual qualitative work
        # is to show the original beside a translation, but an unverified machine translation of a
        # participant quote is worse than none - so the column is left for a Hausa speaker to fill.
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "cat",
                "sid",
                "code",
                "topic",
                "lang",
                "words",
                "q",
                "before",
                "after",
                "text",
                "needs_translation",
                "english_gloss",
            ],
        )
        w.writeheader()
        for g in picked:
            row = {k: g.get(k, "") for k in w.fieldnames}
            row["needs_translation"] = "yes" if g.get("lang") in ("hausa", "mixed") else ""
            row["english_gloss"] = ""
            w.writerow(row)

    # ---------------------------------------------------------------- report
    c = payload["coverage"]
    seen = (
        c["sessions_analysed"]
        + c.get("skipped_untagged", 0)
        + c.get("skipped_test_code", 0)
        + c.get("skipped_test_tag", 0)
        + c.get("skipped_too_short", 0)
    )
    print(f"[insights] archive: {c['sessions_in_archive']} sessions / {c['messages_in_archive']} messages")
    print(f"[insights] visited: {seen} == archive? {'YES' if seen == c['sessions_in_archive'] else 'NO - GAP'}")
    print(
        f"[insights] analysed {c['sessions_analysed']} sessions ({c['messages_analysed']} messages); "
        f"excluded untagged={c.get('skipped_untagged', 0)} test_code={c.get('skipped_test_code', 0)} "
        f"test_tag={c.get('skipped_test_tag', 0)} too_short={c.get('skipped_too_short', 0)}"
    )
    print(
        f"[insights] answers {n_ans} | questions {windows_n} | FLWs {len(flw_sessions)} | " f"topics {len(topic_stat)}"
    )
    print(f"[insights] FLW words per answer: {payload['L2_answer']['words']}")
    print(f"[insights] session duration min: {payload['L4_session']['duration_min']}")
    print("[insights] gem candidates by category:")
    for cat in cats:
        print(f"    {cat['key']:<20}{cat['found']:>7}  ({cat['topics_covered']} topics)  " f"sampled {cat['sampled']}")
    print(f"-> {OUT_PAYLOAD}, {OUT_GEMS}")


if __name__ == "__main__":
    sys.exit(main())
