"""Chatbot probing analysis — census, static-form counterfactual, cost of probing, prompt-version trend.

Runs entirely on transcripts (`_ocs_messages.jsonl`) plus the catalogue reconstructed from the
transcripts themselves (`question_catalogue.json`). No LLM, no external dataset, no hardcoded figures.

The four analyses (see docs/plans for why each one):
  1. CENSUS         how often the bot probed, what triggered it, what kind of probe it was.
  2. COUNTERFACTUAL what a static Google Form would have captured. In a form the first answer IS the
                    final answer, so the pre-probe text is the form-equivalent and we already hold it.
  3. COST           dose-response by probe count, and whether probing predicts abandonment.
  4. VERSION        probe rate and recovery by bot prompt version (directional, confounded with time).

MEASUREMENT NOTE — the single most important design decision. Most topics hand the bot ONE question
containing 3-19 concatenated sub-questions, so the bot must walk the FLW through them. A bot turn that
OPENS the next sub-part is the interview proceeding, not a probe. Only turns that revisit an
already-open sub-part are probing. Blending the two (what a single probe-regex does) would inflate the
apparent quality problem and understate the measured lift. See probe_detect.py.

Outputs: probing_payload.json (aggregates, for the brief and any dashboard tab),
         probing_windows.csv (one row per session x sub-part), probing_probes.csv (one row per probe).
"""
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from build_question_catalogue import TEST_CODE, parse_block
from probe_detect import classify_turns, is_nonanswer, norm_lang, probe_type, toks, trigger_of

# Parsing + tokenising a question block is identical for every session sharing a variant, and there
# are ~20 variants across ~10k sessions, so this cache is the difference between minutes and hours.
_VARIANT_CACHE = {}


def variant_subparts(iq):
    """(variant_hash, subpart texts, subpart token sets, (question_no, part_no) per subpart).

    The (question_no, part_no) map is what lets a position the bot declares — "Question 2 of 9",
    "Tambaya ta 1 (Sashi na 3)" — resolve to a real sub-part instead of a guessed flat offset. Topics A
    and B have discrete Q1..Q9; every other topic is one question with many parts.
    """
    key = hashlib.sha1(str(iq or "").encode("utf-8")).hexdigest()[:10]
    hit = _VARIANT_CACHE.get(key)
    if hit is None:
        qs = parse_block(iq or "")
        subs, qp = [], []
        for q in qs:
            try:
                qn = int(str(q["qid"]).lstrip("Qq") or 1)
            except ValueError:
                qn = len({x[0] for x in qp}) + 1
            for j, s in enumerate(q["subparts"] or [q["text"]], 1):
                subs.append(s)
                qp.append((qn, j))
        hit = _VARIANT_CACHE[key] = (key, subs, [toks(s) for s in subs], qp)
    return hit


SRC = Path("_ocs_messages.jsonl")
OUT_PAYLOAD = Path("probing_payload.json")
OUT_WINDOWS = Path("probing_windows.csv")
OUT_PROBES = Path("probing_probes.csv")

TODAY = datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- statistics (hand-rolled; no scipy)
def mcnemar(b, c):
    """Paired binary before/after. b = fixed by probing (bad->good), c = broke (good->bad).

    Returns (chi2, p) using the continuity-corrected form, or the exact binomial p when b+c is small
    (the chi-square approximation is unreliable below ~25 discordant pairs).
    """
    n = b + c
    if n == 0:
        return 0.0, 1.0
    if n < 25:
        # two-sided exact binomial at p=0.5
        k = min(b, c)
        tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2**n)
        return None, min(1.0, 2 * tail)
    chi2 = (abs(b - c) - 1) ** 2 / n
    return chi2, math.erfc(math.sqrt(chi2 / 2))


def two_prop_z(x1, n1, x2, n2):
    """Two-proportion z-test. Used only for descriptive contrasts, never for a causal claim."""
    if not n1 or not n2:
        return None, None
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p1 - p2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


def median(xs):
    s = sorted(xs)
    if not s:
        return 0
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def pct(a, b, nd=1):
    return round(100 * a / b, nd) if b else 0.0


# ---------------------------------------------------------------- per-session record building
def session_rows(rec):
    """One session -> (window rows, probe rows, session summary). Returns (None, None, None) if unusable."""
    code = str(rec.get("interview") or "").strip()
    if not code:
        return None, None, "untagged"  # no interview assigned: nothing was ever asked
    if TEST_CODE.match(code):
        return None, None, "test_code"
    tags = [str(t).lower() for t in (rec.get("session_tags") or [])]
    if "test" in tags:
        return None, None, "test_tag"
    msgs = rec.get("messages") or []
    if len(msgs) < 2:
        return None, None, "too_short"

    variant, subs, sub_toks, qp = variant_subparts(rec.get("interview_questions"))
    turns, windows = classify_turns(msgs, subs, subpart_toks=sub_toks, subpart_qp=qp)

    lang = norm_lang(rec.get("preferred_language"))
    versions = [t["version"] for t in turns if t.get("version")]
    version = Counter(versions).most_common(1)[0][0] if versions else None
    topic = rec.get("interview_topic") or f"code {code}"

    wrows, prows = [], []
    for w in windows:
        answers = w["answers"]
        qtext = w.get("subpart_text") or w.get("ask_text") or ""
        probes = w["probes"]
        # The form-equivalent answer is EVERYTHING the FLW volunteered before the bot first pushed
        # back — not just their first message. FLWs frequently send several messages in a row
        # ("yes" then the actual content), and in a static form all of that uninterrupted typing
        # would have been one answer. Taking only answers[0] would understate the form baseline and
        # flatter the result.
        cut = probes[0]["i"] if probes else None
        pre = [a for a in answers if cut is None or a["i"] < cut]
        first = " ".join(a["text"] for a in pre)
        final = " ".join(a["text"] for a in answers)
        # trigger = state of the FLW turn that immediately preceded the FIRST probe
        trig = None
        if probes:
            before = [a for a in answers if a["i"] < probes[0]["i"]]
            trig = trigger_of(before[-1]["text"] if before else "", qtext)
        f_non = is_nonanswer(first, qtext)
        l_non = is_nonanswer(final, qtext)
        wrows.append(
            {
                "sid": rec["sid"],
                "pid": rec.get("pid"),
                "code": code,
                "topic": topic,
                "lang": lang,
                "version": version,
                "variant": variant,
                "subpart_idx": w["subpart_idx"],
                "declared_part": w["declared_part"],
                "has_catalogue_text": bool(w.get("subpart_text")),
                "n_subparts": len(subs),
                "ask_channel": w["ask_channel"],
                "n_probes": w["n_probes"],
                "n_reasks": w["n_reasks"],
                "n_probing_turns": w["n_probes"] + w["n_reasks"],
                "n_answers": len(answers),
                "words_first": len(first.split()),
                "words_final": len(final.split()),
                "first_nonanswer": f_non,
                "final_nonanswer": l_non,
                "recovered": bool(f_non and not l_non),
                "trigger": trig,
                "q_words": len(qtext.split()),
            }
        )
        for j, p in enumerate(probes, 1):
            before = [a for a in answers if a["i"] < p["i"]]
            after = [a for a in answers if a["i"] > p["i"]]
            prows.append(
                {
                    "sid": rec["sid"],
                    "code": code,
                    "topic": topic,
                    "lang": lang,
                    "version": p.get("version") or version,
                    "subpart_idx": w["subpart_idx"],
                    "probe_seq": j,
                    "kind": p["kind"],
                    "probe_type": probe_type(p["text"]),
                    "trigger": trigger_of(before[-1]["text"] if before else "", qtext),
                    "words_before": len(before[-1]["text"].split()) if before else 0,
                    "words_after": len(after[0]["text"].split()) if after else 0,
                    "answered_after": bool(after),
                    "probe_words": p["words"],
                }
            )

    n_ai = sum(1 for t in turns if t["role"] == "assistant")
    summary = {
        "sid": rec["sid"],
        "pid": rec.get("pid"),
        "code": code,
        "topic": topic,
        "lang": lang,
        "version": version,
        "status": rec.get("interview_status"),
        "complete": (rec.get("interview_status") == "interview_complete"),
        "session_tags": tags,
        "created_at": rec.get("created_at"),
        "n_msgs": len(msgs),
        "n_ai": n_ai,
        "n_subparts_catalogue": len(subs),
        "n_windows": len(windows),
        "n_probes": sum(w["n_probes"] for w in windows),
        "n_reasks": sum(w["n_reasks"] for w in windows),
        "n_admin": sum(1 for t in turns if t["kind"] == "admin"),
        "detected": bool(windows),
        "channels": Counter(t["channel"] for t in turns if t["role"] == "assistant"),
    }
    return wrows, prows, summary


# ---------------------------------------------------------------- aggregation
def aggregate(W, P, S):
    """Every figure the brief can quote, computed here. Nothing downstream may hardcode a number."""
    out = {"generated": TODAY, "source": str(SRC)}

    # ---- universe and detector coverage (published, not hidden)
    det = [s for s in S if s["detected"]]
    ch = Counter()
    for s in S:
        ch.update(s["channels"])
    out["universe"] = {
        "sessions_in_file": len(S),
        "sessions_with_detected_questions": len(det),
        "sessions_detection_failed": len(S) - len(det),
        "detection_coverage_pct": pct(len(det), len(S)),
        "flws": len({s["pid"] for s in S if s.get("pid")}),
        "codes": len({s["code"] for s in S}),
        "messages": sum(s["n_msgs"] for s in S),
        "ai_turns": sum(s["n_ai"] for s in S),
        "windows": len(W),
        "languages": dict(Counter(s["lang"] for s in S).most_common()),
        "ask_channel_mix": dict(ch.most_common()),
    }

    # ---- 1. CENSUS
    probing = [w for w in W if w["n_probing_turns"] > 0]
    dist = Counter(min(w["n_probing_turns"], 5) for w in W)
    out["census"] = {
        "windows": len(W),
        "windows_probed": len(probing),
        "probe_rate_pct": pct(len(probing), len(W)),
        "probing_turns": sum(w["n_probing_turns"] for w in W),
        "reasks": sum(w["n_reasks"] for w in W),
        "probes_per_window_mean": round(sum(w["n_probing_turns"] for w in W) / max(len(W), 1), 2),
        "probes_per_probed_window_mean": round(sum(w["n_probing_turns"] for w in probing) / max(len(probing), 1), 2),
        "turns_per_window_mean": round(sum(w["n_answers"] for w in W) / max(len(W), 1), 2),
        "distribution": {("5+" if k == 5 else str(k)): v for k, v in sorted(dist.items())},
        "triggers": {
            k: {"n": v, "pct": pct(v, len(probing))}
            for k, v in Counter(w["trigger"] for w in probing if w["trigger"]).most_common()
        },
        "probe_types": {
            k: {"n": v, "pct": pct(v, len(P))} for k, v in Counter(p["probe_type"] for p in P).most_common()
        },
        "by_topic": [],
        "by_language": [],
    }
    for key, field in (("by_topic", "topic"), ("by_language", "lang")):
        g = defaultdict(list)
        for w in W:
            g[w[field]].append(w)
        out["census"][key] = sorted(
            [
                {
                    "k": k,
                    "windows": len(v),
                    "probe_rate_pct": pct(sum(1 for x in v if x["n_probing_turns"]), len(v)),
                    "probes_per_window": round(sum(x["n_probing_turns"] for x in v) / max(len(v), 1), 2),
                    "turns_per_window": round(sum(x["n_answers"] for x in v) / max(len(v), 1), 2),
                }
                for k, v in g.items()
            ],
            key=lambda r: -r["windows"],
        )

    # ---- 2. COUNTERFACTUAL: the form-equivalent answer is the pre-probe answer
    usable_final = [w for w in W if not w["final_nonanswer"]]
    rescued = [w for w in usable_final if w["first_nonanswer"]]
    b = sum(1 for w in W if w["first_nonanswer"] and not w["final_nonanswer"])  # bad -> good
    c = sum(1 for w in W if not w["first_nonanswer"] and w["final_nonanswer"])  # good -> bad
    chi2, p = mcnemar(b, c)
    pw = [w for w in W if w["n_probing_turns"] > 0]
    out["counterfactual"] = {
        "windows": len(W),
        "usable_final": len(usable_final),
        "usable_first": sum(1 for w in W if not w["first_nonanswer"]),
        "rescued_by_probing": len(rescued),
        "rescued_share_of_usable_pct": pct(len(rescued), len(usable_final)),
        "form_equivalent_usable_pct": pct(sum(1 for w in W if not w["first_nonanswer"]), len(W)),
        "actual_usable_pct": pct(len(usable_final), len(W)),
        # p underflows to 0.0 at this sample size; printing "0.00e+00" would claim a p-value of
        # exactly zero, which is false. Report the floor instead.
        "mcnemar": {
            "fixed": b,
            "broke": c,
            "chi2": (round(chi2, 2) if chi2 is not None else None),
            "p": ("< 1e-300" if p == 0 else (f"{p:.2e}" if p < 1e-4 else round(p, 4))),
            "exact": chi2 is None,
        },
        "words": {
            "first_mean": round(sum(w["words_first"] for w in W) / max(len(W), 1), 1),
            "final_mean": round(sum(w["words_final"] for w in W) / max(len(W), 1), 1),
            "first_median": median([w["words_first"] for w in W]),
            "final_median": median([w["words_final"] for w in W]),
            "probed_first_mean": round(sum(w["words_first"] for w in pw) / max(len(pw), 1), 1),
            "probed_final_mean": round(sum(w["words_final"] for w in pw) / max(len(pw), 1), 1),
        },
        "by_topic": [],
        "by_language": [],
    }

    # SENSITIVITY. "Usable" is a >3-word threshold, so an answer can cross it without becoming
    # substantively better. Hand-reading rescued cases found exactly that: "9" -> "9 0 not available"
    # counts as a rescue but no reader would call it one. Rather than defend the threshold, re-run the
    # headline with every barely-over-the-line rescue (<=5 words final) discounted, and publish both.
    marg = [w for w in rescued if w["words_final"] <= 5]
    strict_usable = len(usable_final) - len(marg)
    strict_res = len(rescued) - len(marg)
    out["counterfactual"]["sensitivity"] = {
        "marginal_rescues_le5_words": len(marg),
        "marginal_share_of_rescues_pct": pct(len(marg), len(rescued)),
        "strict_actual_usable_pct": pct(strict_usable, len(W)),
        "strict_rescued": strict_res,
        "strict_rescued_share_of_usable_pct": pct(strict_res, strict_usable),
        "rescue_size_distribution": {
            "4-5 words": len(marg),
            "6-10 words": sum(1 for w in rescued if 5 < w["words_final"] <= 10),
            "11-25 words": sum(1 for w in rescued if 10 < w["words_final"] <= 25),
            "26+ words": sum(1 for w in rescued if w["words_final"] > 25),
        },
    }
    # Broken out by language on purpose: the interview runs in English and Hausa, the usable-answer
    # test is word-count based, and Hausa may carry the same content in fewer words. Publishing the
    # split is what makes any residual measurement asymmetry auditable instead of buried in a total.
    for key, field in (("by_topic", "topic"), ("by_language", "lang")):
        g = defaultdict(list)
        for w in W:
            g[w[field]].append(w)
        out["counterfactual"][key] = sorted(
            [
                {
                    "k": k,
                    "windows": len(v),
                    "form_equivalent_usable_pct": pct(sum(1 for x in v if not x["first_nonanswer"]), len(v)),
                    "actual_usable_pct": pct(sum(1 for x in v if not x["final_nonanswer"]), len(v)),
                    "rescued": sum(1 for x in v if x["first_nonanswer"] and not x["final_nonanswer"]),
                    "words_first_mean": round(sum(x["words_first"] for x in v) / max(len(v), 1), 1),
                    "words_final_mean": round(sum(x["words_final"] for x in v) / max(len(v), 1), 1),
                }
                for k, v in g.items()
            ],
            key=lambda r: -r["windows"],
        )

    # ---- 3. COST: dose-response, then abandonment
    dose = []
    for k in (0, 1, 2, 3):
        v = [w for w in W if (w["n_probing_turns"] == k if k < 3 else w["n_probing_turns"] >= 3)]
        if not v:
            continue
        first_bad = [w for w in v if w["first_nonanswer"]]
        dose.append(
            {
                "probes": ("3+" if k == 3 else str(k)),
                "windows": len(v),
                "usable_final_pct": pct(sum(1 for w in v if not w["final_nonanswer"]), len(v)),
                "started_unusable": len(first_bad),
                "recovery_pct": pct(sum(1 for w in first_bad if not w["final_nonanswer"]), len(first_bad)),
                "words_final_mean": round(sum(w["words_final"] for w in v) / len(v), 1),
            }
        )
    # marginal value of the Nth probe: did the answer improve after probe N, among windows that got one
    marg = []
    byseq = defaultdict(list)
    for p in P:
        byseq[min(p["probe_seq"], 4)].append(p)
    for k in sorted(byseq):
        v = byseq[k]
        marg.append(
            {
                "probe_seq": ("4+" if k == 4 else str(k)),
                "n": len(v),
                "answered_after_pct": pct(sum(1 for x in v if x["answered_after"]), len(v)),
                "words_before_mean": round(sum(x["words_before"] for x in v) / len(v), 1),
                "words_after_mean": round(sum(x["words_after"] for x in v) / len(v), 1),
            }
        )
    # abandonment: compare completion by probe intensity per window, controlling for topic
    sess = [s for s in S if s["n_windows"] > 0]
    aband = []
    for lo, hi, lab in ((0, 0.5, "0"), (0.5, 1.0, "0.5-1"), (1.0, 2.0, "1-2"), (2.0, 99, "2+")):
        v = [s for s in sess if lo <= (s["n_probes"] + s["n_reasks"]) / max(s["n_windows"], 1) < hi]
        if not v:
            continue
        aband.append(
            {
                "probes_per_window": lab,
                "sessions": len(v),
                "completed_pct": pct(sum(1 for s in v if s["complete"]), len(v)),
                "windows_reached_mean": round(sum(s["n_windows"] for s in v) / len(v), 1),
            }
        )
    out["cost"] = {"dose_response": dose, "marginal_probe": marg, "abandonment": aband}

    # ---- 4. VERSION trend (directional only: versions are correlated with time, topic and cohort)
    g = defaultdict(list)
    for w in W:
        if w["version"]:
            g[w["version"]].append(w)

    def vkey(v):
        m = re.match(r"v(\d+)", v or "")
        return int(m.group(1)) if m else -1

    out["version_trend"] = [
        {
            "version": v,
            "windows": len(x),
            "probe_rate_pct": pct(sum(1 for w in x if w["n_probing_turns"]), len(x)),
            "probes_per_window": round(sum(w["n_probing_turns"] for w in x) / len(x), 2),
            "usable_final_pct": pct(sum(1 for w in x if not w["final_nonanswer"]), len(x)),
            "form_equivalent_usable_pct": pct(sum(1 for w in x if not w["first_nonanswer"]), len(x)),
            "topics": len({w["topic"] for w in x}),
        }
        for v, x in sorted(g.items(), key=lambda kv: vkey(kv[0]))
        if len(x) >= 30
    ]

    # ---- human-review cross-check. The team tags sessions `acceptable` / `unacceptable` in OCS and
    # those tags come back on the API, so they are an INDEPENDENT check on our automated measures —
    # available now, without waiting on any LLM scoring.
    #
    # It also settles a live disagreement recorded in the OCS evaluation notes: one reviewer treats bot
    # prompting as the chatbot doing its job, others mark needing probing against the FLW. If probed
    # sessions were simply worse, probe intensity would be higher in `unacceptable` sessions AND their
    # recovery rate would be lower. Both numbers are reported here rather than argued.
    def _tagged(tag):
        return [s for s in S if tag in s["session_tags"]]

    win_by_sid = defaultdict(list)
    for w in W:
        win_by_sid[w["sid"]].append(w)
    human = []
    for tag in ("acceptable", "unacceptable"):
        ss = [s for s in _tagged(tag) if s["n_windows"]]
        if not ss:
            continue
        ws = [w for s in ss for w in win_by_sid[s["sid"]]]
        first_bad = [w for w in ws if w["first_nonanswer"]]
        human.append(
            {
                "tag": tag,
                "sessions": len(ss),
                "windows": len(ws),
                "probes_per_window": round(sum(w["n_probing_turns"] for w in ws) / max(len(ws), 1), 2),
                "probe_rate_pct": pct(sum(1 for w in ws if w["n_probing_turns"]), len(ws)),
                "usable_final_pct": pct(sum(1 for w in ws if not w["final_nonanswer"]), len(ws)),
                "form_equivalent_usable_pct": pct(sum(1 for w in ws if not w["first_nonanswer"]), len(ws)),
                "recovery_pct": pct(sum(1 for w in first_bad if not w["final_nonanswer"]), len(first_bad)),
                "completed_pct": pct(sum(1 for s in ss if s["complete"]), len(ss)),
            }
        )
    if len(human) == 2:
        a, u = human[0], human[1]
        za, pa = two_prop_z(
            round(a["usable_final_pct"] * a["windows"] / 100),
            a["windows"],
            round(u["usable_final_pct"] * u["windows"] / 100),
            u["windows"],
        )
        human_test = {
            "usable_final_z": (round(za, 2) if za else None),
            "usable_final_p": (
                f"{pa:.2e}" if pa is not None and pa < 1e-4 else (round(pa, 4) if pa is not None else None)
            ),
        }
    else:
        human_test = {}
    out["human_review"] = {
        "groups": human,
        "contrast": human_test,
        "tag_counts": dict(Counter(t for s in S for t in s["session_tags"]).most_common()),
    }

    # ---- hand-validation of the ask/probe classifier, read from the labelled file rather than
    # asserted. If the file is absent or unlabelled the brief says so instead of quoting a number.
    lab = Path("probe_validation_labels.csv")
    if lab.exists():
        rows = [r for r in csv.DictReader(lab.open(encoding="utf-8")) if (r.get("true_label") or "").strip()]

        def _c(k):
            return "ask" if k == "ask" else ("probe" if k in ("probe", "reask") else k)

        if rows:
            hit = [r for r in rows if _c(r["detector_kind"]) == _c(r["true_label"].strip().lower())]
            asks = [r for r in rows if _c(r["detector_kind"]) == "ask"]
            prbs = [r for r in rows if _c(r["detector_kind"]) == "probe"]
            out["hand_validation"] = {
                "labelled": len(rows),
                "agreement_pct": pct(len(hit), len(rows)),
                "ask_precision_pct": pct(
                    sum(1 for r in asks if _c(r["true_label"].strip().lower()) == "ask"), len(asks)
                ),
                "probe_precision_pct": pct(
                    sum(1 for r in prbs if _c(r["true_label"].strip().lower()) == "probe"), len(prbs)
                ),
                "by_channel": {
                    ch: pct(
                        sum(
                            1
                            for r in rows
                            if r["detector_channel"] == ch
                            and _c(r["detector_kind"]) == _c(r["true_label"].strip().lower())
                        ),
                        sum(1 for r in rows if r["detector_channel"] == ch),
                    )
                    for ch in sorted({r["detector_channel"] for r in rows})
                },
            }

    # ---- cross-check against the bot's own numbering (validates the catalogue split)
    # Does the split of the bot's own question block cover the positions the bot itself announces?
    # NOT `declared_part - 1 == subpart_idx`: that was the earlier test and it is wrong for topics A
    # and B, where every question has exactly one part, so the declared part is always 1 while the
    # sub-part index runs 0..8 (question 3, part 1 -> index 2). It reported a false 10.7% disagreement.
    # The meaningful measure is how often a declared position resolved to a real catalogue sub-part
    # rather than needing a synthetic slot (which happens where the bot splits an ask that the
    # no-space rule leaves joined).
    dec = [w for w in W if w["ask_channel"] == "declared"]
    synth = [w for w in dec if w["subpart_idx"] >= w["n_subparts"]]
    out["validation"] = {
        "windows_opened_by_declared_position": len(dec),
        "resolved_to_a_catalogue_subpart_pct": pct(len(dec) - len(synth), len(dec)),
        "needed_a_synthetic_slot": len(synth),
        "note": (
            "share of bot-declared positions that landed on a sub-part the question split derived; "
            "the remainder are asks the bot separated but the no-space split left joined"
        ),
    }
    return out


def main():
    if not SRC.exists():
        raise SystemExit(f"missing {SRC} — run pull_ocs_messages.py first")
    W, P, S = [], [], []
    skipped = {}
    for ln in SRC.open(encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        w, p, s = session_rows(rec)
        if not isinstance(s, dict):
            # s is a reason string: record WHY the session was excluded rather than a bare total.
            # 11,775 of these are sessions with no interview ever assigned (abandoned at the welcome
            # or language step), which is a very different fact from "test data" and was previously
            # reported as if it were the same thing.
            skipped[s or "other"] = skipped.get(s or "other", 0) + 1
            continue
        W += w
        P += p
        S.append(s)

    payload = aggregate(W, P, S)
    payload["universe"]["sessions_excluded"] = dict(sorted(skipped.items(), key=lambda kv: -kv[1]))
    payload["universe"]["sessions_excluded_total"] = sum(skipped.values())
    OUT_PAYLOAD.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    if W:
        with OUT_WINDOWS.open("w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(W[0].keys()))
            wr.writeheader()
            wr.writerows(W)
    if P:
        with OUT_PROBES.open("w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(P[0].keys()))
            wr.writeheader()
            wr.writerows(P)

    u, c, cf = payload["universe"], payload["census"], payload["counterfactual"]
    print(
        f"[probing] sessions {u['sessions_in_file']} analysed | FLWs {u['flws']} | "
        f"codes {u['codes']} | messages {u['messages']}"
    )
    print(
        f"[probing] excluded {payload['universe']['sessions_excluded_total']}: "
        + ", ".join(f"{k}={v}" for k, v in payload["universe"]["sessions_excluded"].items())
    )
    print(
        f"[probing] detection coverage {u['detection_coverage_pct']}% "
        f"({u['sessions_detection_failed']} sessions no questions detected)"
    )
    print(
        f"[probing] windows {c['windows']} | probed {c['windows_probed']} ({c['probe_rate_pct']}%) | "
        f"probing turns {c['probing_turns']} (re-asks {c['reasks']})"
    )
    print(
        f"[probing] FLW turns per question: {c['turns_per_window_mean']} | "
        f"probes per probed question: {c['probes_per_probed_window_mean']}"
    )
    print(
        f"[probing] COUNTERFACTUAL: usable now {cf['actual_usable_pct']}% vs "
        f"form-equivalent {cf['form_equivalent_usable_pct']}% | "
        f"rescued {cf['rescued_by_probing']} = {cf['rescued_share_of_usable_pct']}% of usable answers"
    )
    print(
        f"[probing] McNemar fixed={cf['mcnemar']['fixed']} broke={cf['mcnemar']['broke']} " f"p={cf['mcnemar']['p']}"
    )
    print(f"[probing] words first {cf['words']['first_mean']} -> final {cf['words']['final_mean']}")
    print("[probing] triggers: " + ", ".join(f"{k} {v['pct']}%" for k, v in list(c["triggers"].items())[:6]))
    v = payload["validation"]
    print(
        f"[probing] bot-declared positions landing on a derived sub-part: "
        f"{v['resolved_to_a_catalogue_subpart_pct']}% of {v['windows_opened_by_declared_position']} "
        f"({v['needed_a_synthetic_slot']} needed a synthetic slot)"
    )
    hv = payload.get("hand_validation") or {}
    if hv:
        print(
            f"[probing] hand validation: {hv['labelled']} turns read blind — agreement "
            f"{hv['agreement_pct']}% (asks {hv['ask_precision_pct']}%, probes {hv['probe_precision_pct']}%)"
        )
    print(f"-> {OUT_PAYLOAD}, {OUT_WINDOWS}, {OUT_PROBES}")


if __name__ == "__main__":
    sys.exit(main())
