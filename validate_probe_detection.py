"""Draw a stratified sample of classified bot turns for HAND validation of the probe detector.

The whole probing analysis depends on one judgement per bot turn — did it open a new question (ASK) or
revisit the one already open (PROBE / RE-ASK)? That judgement is made by regex + word overlap, so its
error rate has to be measured and published, not assumed. This script produces the sample; a human
reads `probe_validation_sample.txt` and fills in `probe_validation_labels.csv`, and
`--score` then computes precision per class and per detection channel.

Stratified by language (english / hausa) and prompt-version era, because the bot's phrasing changed
across the study (bold markup appears only from ~v50; Hausa carries explicit "Sashi na N" part
indices that English often omits) and a detector can be strong in one stratum and weak in another.

Deterministic: fixed seed, so the sample is reproducible and a reviewer can re-draw exactly it.

  python validate_probe_detection.py            # draw the sample
  python validate_probe_detection.py --score    # score it once labels are filled in
"""
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from build_probing_analysis import variant_subparts
from build_question_catalogue import TEST_CODE
from probe_detect import classify_turns, norm_lang

SRC = Path("_ocs_messages.jsonl")
SAMPLE_TXT = Path("probe_validation_sample.txt")
SAMPLE_CSV = Path("probe_validation_labels.csv")
SEED = 20260813
PER_CELL = 10  # per (class x language x era) cell


def era_of(version):
    m = re.match(r"v(\d+)", str(version or ""))
    if not m:
        return "unknown"
    n = int(m.group(1))
    return "early(<=v33)" if n <= 33 else ("mid(v34-v49)" if n <= 49 else "late(v50+)")


def collect():
    """Every classified bot turn, with the context a human needs to judge it."""
    items = []
    for ln in SRC.open(encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        code = str(rec.get("interview") or "").strip()
        if not code or TEST_CODE.match(code):
            continue
        if "test" in [str(t).lower() for t in (rec.get("session_tags") or [])]:
            continue
        msgs = rec.get("messages") or []
        if len(msgs) < 4:
            continue
        _v, subs, stoks, qp = variant_subparts(rec.get("interview_questions"))
        if not subs:
            continue
        turns, _w = classify_turns(msgs, subs, subpart_toks=stoks, subpart_qp=qp)
        lang = norm_lang(rec.get("preferred_language"))
        by_i = {t["i"]: t for t in turns}
        for t in turns:
            if t["role"] != "assistant" or t["kind"] not in ("ask", "reask", "probe"):
                continue
            prev_flw = ""
            for j in range(t["i"] - 1, -1, -1):
                if by_i.get(j, {}).get("role") == "user":
                    prev_flw = by_i[j]["text"]
                    break
            # what the detector believes is open, and the question text for it
            idx = t.get("subpart_idx")
            qtext = subs[idx] if isinstance(idx, int) and 0 <= idx < len(subs) else ""
            items.append(
                {
                    "sid": rec["sid"],
                    "i": t["i"],
                    "code": code,
                    "topic": rec.get("interview_topic") or f"code {code}",
                    "lang": lang,
                    "version": t.get("version"),
                    "era": era_of(t.get("version")),
                    "kind": t["kind"],
                    "channel": t["channel"],
                    "subpart_idx": idx,
                    "declared_part": t.get("declared_part"),
                    "best_overlap": t.get("best_overlap"),
                    "question": qtext,
                    "prev_flw": prev_flw,
                    "text": t["text"],
                }
            )
    return items


def draw(items):
    rng = random.Random(SEED)
    cells = defaultdict(list)
    for it in items:
        cls = "ask" if it["kind"] == "ask" else "probe"  # reask groups with probe: both are probing
        cells[(cls, it["lang"], it["era"])].append(it)
    picked = []
    for key in sorted(cells, key=str):
        cls, lang, era = key
        if lang not in ("english", "hausa"):
            continue
        pool = cells[key]
        picked += rng.sample(pool, min(PER_CELL, len(pool)))
    rng.shuffle(picked)  # shuffled so the reader is not primed by class order
    return picked


def write_sample(picked):
    with SAMPLE_TXT.open("w", encoding="utf-8") as fh:
        fh.write(
            "HAND VALIDATION — is each bot turn an ASK (opens a question not yet asked) or\n"
            "PROBE (follows up / re-asks the question already open)?\n"
            "Write your judgement in probe_validation_labels.csv under `true_label`\n"
            "using: ask | probe | admin | unclear\n"
            "The detector's own guess is deliberately NOT shown here.\n" + "=" * 96 + "\n\n"
        )
        for n, it in enumerate(picked, 1):
            fh.write(f"[{n:>3}] {it['lang']}/{it['era']} | topic: {it['topic']} | sid {it['sid'][:8]} msg#{it['i']}\n")
            fh.write(f"      QUESTION THE DETECTOR THINKS IS OPEN:\n        {(it['question'] or '(none)')[:300]}\n")
            fh.write(f"      PREVIOUS FLW TURN:\n        {' '.join((it['prev_flw'] or '(none)').split())[:300]}\n")
            fh.write(f"      BOT TURN TO JUDGE:\n        {' '.join(it['text'].split())[:520]}\n\n")
    with SAMPLE_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "n",
                "sid",
                "msg_i",
                "lang",
                "era",
                "detector_kind",
                "detector_channel",
                "declared_part",
                "best_overlap",
                "true_label",
            ]
        )
        for n, it in enumerate(picked, 1):
            w.writerow(
                [
                    n,
                    it["sid"],
                    it["i"],
                    it["lang"],
                    it["era"],
                    it["kind"],
                    it["channel"],
                    it["declared_part"],
                    it["best_overlap"],
                    "",
                ]
            )
    print(f"[validate] {len(picked)} turns sampled (seed {SEED}, {PER_CELL}/cell)")
    print(f"[validate] read {SAMPLE_TXT}, fill `true_label` in {SAMPLE_CSV}, then --score")
    print("[validate] cells:", dict(Counter(f"{i['kind']}/{i['lang']}/{i['era']}" for i in picked).most_common()))


def refresh_detector_labels():
    """Re-run the CURRENT detector over exactly the turns already hand-labelled, and overwrite the
    detector_kind/channel columns in place.

    Needed because the hand labels are tied to specific (sid, msg_i) pairs. Redrawing the sample after
    a detector fix would produce a different sample and silently discard the human judgements, so the
    honest way to measure a fix is to re-classify the same turns and re-score against the same labels.
    """
    rows = list(csv.DictReader(SAMPLE_CSV.open(encoding="utf-8")))
    want = defaultdict(set)
    for r in rows:
        want[r["sid"]].add(int(r["msg_i"]))
    fresh = {}
    for ln in SRC.open(encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except ValueError:
            continue  # a pull may be appending: tolerate a partially-written final line
        if rec.get("sid") not in want:
            continue
        _v, subs, stoks, qp = variant_subparts(rec.get("interview_questions"))
        turns, _w = classify_turns(rec.get("messages") or [], subs, subpart_toks=stoks, subpart_qp=qp)
        for t in turns:
            if t["i"] in want[rec["sid"]]:
                fresh[(rec["sid"], t["i"])] = t
    changed = 0
    for r in rows:
        t = fresh.get((r["sid"], int(r["msg_i"])))
        if not t:
            continue
        if r["detector_kind"] != t["kind"]:
            changed += 1
        r["detector_kind"], r["detector_channel"] = t["kind"], t["channel"] or ""
        r["declared_part"] = t.get("declared_part") or ""
        r["best_overlap"] = t.get("best_overlap") or ""
    with SAMPLE_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(
        f"[validate] re-classified {len(fresh)} labelled turns with the current detector " f"({changed} changed class)"
    )


def score():
    rows = [r for r in csv.DictReader(SAMPLE_CSV.open(encoding="utf-8")) if (r.get("true_label") or "").strip()]
    if not rows:
        raise SystemExit(f"no labels filled in {SAMPLE_CSV}")

    def cls(k):
        return "ask" if k == "ask" else ("probe" if k in ("probe", "reask") else k)

    tot = len(rows)
    ok = sum(1 for r in rows if cls(r["detector_kind"]) == cls(r["true_label"].strip().lower()))
    print(f"[validate] labelled {tot} turns | overall agreement {100 * ok / tot:.1f}%")
    for field in ("detector_kind", "detector_channel", "lang", "era"):
        g = defaultdict(lambda: [0, 0])
        for r in rows:
            k = r[field]
            g[k][0] += 1
            g[k][1] += 1 if cls(r["detector_kind"]) == cls(r["true_label"].strip().lower()) else 0
        print(f"  by {field}:")
        for k, (n, c) in sorted(g.items(), key=lambda kv: -kv[1][0]):
            print(f"    {str(k):<22} n={n:<4} correct={c:<4} precision={100 * c / n:.0f}%")
    conf = Counter((cls(r["detector_kind"]), cls(r["true_label"].strip().lower())) for r in rows)
    print("  confusion (detector -> truth):")
    for (d, t), n in conf.most_common():
        print(f"    {d:<8} -> {t:<8} {n}")


if __name__ == "__main__":
    if "--rescore" in sys.argv:
        refresh_detector_labels()
        score()
    elif "--score" in sys.argv:
        score()
    else:
        write_sample(draw(collect()))
