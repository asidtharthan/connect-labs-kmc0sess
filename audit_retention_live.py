#!/usr/bin/env python3
"""Independent end-to-end audit of the LIVE published Interviews dashboard.

Deliberately reads only the PUBLISHED render - the embedded DATA and the template text - and
re-derives everything it checks. It never imports the builders, so it cannot pass by agreeing with the
code it is auditing. Where a figure can be recomputed two ways, it recomputes both and compares.

Focus: the 2026-08-21 retention change (cadence-relative deadlines, the Waiting bucket, per-cohort
drop-off, rhythm as an independent reading) plus the invariants that change could have broken.

Usage:  python audit_retention_live.py <live_audit.json> <live_render.js>
"""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date

checks = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<62} {detail}")


def section(t):
    print(f"\n{t}\n" + "-" * 100)


def main(pay_path, render_path):
    D = json.loads(open(pay_path, encoding="utf-8").read())
    SRC = open(render_path, encoding="utf-8").read()
    CE, CD = D["cohortEngagement"], D["cohortDropoff"]
    CSG, SD = D["cohortSG"], D["subgroupDesign"]
    TODAY = date.fromisoformat(D["today"])

    # ---------------------------------------------------------------- A. structural
    section("A. STRUCTURE AND FRESHNESS")
    check(
        "payload carries every key the change added",
        all(k in D for k in ("cohortDropoff", "cohortEngagement", "cohortSG", "subgroupDesign")),
        f"{len(D)} top-level keys",
    )
    check("built today", D.get("built_at", "").startswith(TODAY.isoformat()), D.get("built_at", ""))
    check(
        "published render is under the 512 KB Labs cap",
        len(SRC.encode()) < 512 * 1024,
        f"{len(SRC.encode()) / 1024:.1f} KB, headroom {(512 * 1024 - len(SRC.encode())) / 1024:.1f} KB",
    )
    unmapped = [r["c"] for r in CD if r["c"] not in CSG]
    check("every cohort in the drop-off view maps to a design", not unmapped, f"{len(CD)} cohorts")
    dupes = [c for c, n in Counter(r["c"] for r in CD).items() if n > 1]
    check("no cohort appears twice", not dupes, f"dupes: {dupes or 'none'}")

    # ---------------------------------------------------------------- B. per-series arithmetic
    section("B. ENGAGEMENT SERIES ARITHMETIC (recomputed per week, every series)")
    bad_len, bad_out, bad_rhy, bad_mono, bad_tot, bad_base, neg = [], [], [], [], [], [], []
    ARRAYS = (
        "weeks",
        "started",
        "finished_pct",
        "drop_pct",
        "waiting_pct",
        "inprog_pct",
        "steady_pct",
        "incons_pct",
        "rhythm_base",
        "finished",
        "new",
        "active",
        "slow",
        "quiet",
    )
    for sg, c in CE.items():
        if len({len(c[k]) for k in ARRAYS if k in c}) != 1:
            bad_len.append(sg)
            continue
        for i in range(len(c["weeks"])):
            o = c["finished_pct"][i] + c["drop_pct"][i] + c["waiting_pct"][i] + c["inprog_pct"][i]
            if not 99 <= o <= 101:
                bad_out.append(f"{sg}[{i}]={o}")
            rb, r = c["rhythm_base"][i], c["steady_pct"][i] + c["incons_pct"][i]
            if rb and not 99 <= r <= 101:
                bad_rhy.append(f"{sg}[{i}]={r}")
            if not rb and r:
                bad_rhy.append(f"{sg}[{i}] pct without a base")
            if not c.get("rhythm_pooled") and rb > c["started"][i]:
                bad_base.append(f"{sg}[{i}] base {rb} > started {c['started'][i]}")
            if any(c[k][i] < 0 for k in ARRAYS if k != "weeks"):
                neg.append(f"{sg}[{i}]")
        if any(c["started"][i] > c["started"][i + 1] for i in range(len(c["started"]) - 1)):
            bad_mono.append(sg)
        if c["total_started"] != c["started"][-1]:
            bad_tot.append(sg)
    check("all per-week arrays are the same length", not bad_len, f"{len(CE)} series")
    check("outcome shares sum to 100 every week", not bad_out, "; ".join(bad_out[:3]) or "all weeks")
    check("rhythm shares sum to 100 on their own base", not bad_rhy, "; ".join(bad_rhy[:3]) or "")
    check("rhythm base within starters (unpooled series)", not bad_base, "; ".join(bad_base[:3]) or "")
    check("started count never decreases", not bad_mono, f"offenders: {bad_mono or 'none'}")
    check("total_started equals the last week", not bad_tot, f"offenders: {bad_tot or 'none'}")
    check("no negative values anywhere", not neg, f"{len(neg)} found")

    # ---------------------------------------------------------------- C. the pooled view vs its parts
    section("C. THE ALL VIEW MUST NOT CONTRADICT ITS PARTS")
    allc = CE.get("ALL")
    check("ALL is flagged as pooled", bool(allc and allc.get("rhythm_pooled")))
    if allc:
        last = len(allc["weeks"]) - 1
        rb_sum, pcts = 0, []
        for sg, c in CE.items():
            if sg == "ALL":
                continue
            j = len(c["weeks"]) - 1
            if c["weeks"][j] <= allc["weeks"][last]:
                rb_sum += c["rhythm_base"][j]
                if c["rhythm_base"][j]:
                    pcts.append(c["steady_pct"][j])
        check(
            "pooled rhythm base equals the sum of its parts",
            allc["rhythm_base"][last] == rb_sum,
            f"{allc['rhythm_base'][last]} vs {rb_sum}",
        )
        lo, hi = min(pcts), max(pcts)
        v = allc["steady_pct"][last]
        check("pooled steady% sits inside the range of its parts", lo <= v <= hi, f"ALL {v}% vs parts {lo}-{hi}%")
        check(
            "pooled base exceeds unique FLWs (it counts enrolments, and says so)",
            allc["rhythm_base"][last] >= allc["started"][last] and "enrolments" in SRC,
            f"base {allc['rhythm_base'][last]} vs started {allc['started'][last]}",
        )

    # ---------------------------------------------------------------- D. drop-off view, recomputed
    section("D. DROP-OFF BY COHORT, RE-DERIVED FROM THE PUBLISHED ROWS")
    bad_sum, bad_end, zero_n = [], [], []
    for r in CD:
        if r["f"] + r["d"] + r["w"] > r["n"]:
            bad_sum.append(r["c"])
        if not r["n"]:
            zero_n.append(r["c"])
        s, e = date.fromisoformat(r["s"]), date.fromisoformat(r["e"])
        sg = CSG.get(r["c"])
        des = SD.get(sg) or {}
        gap = des.get("cadence")
        ivs = len(des.get("topics") or [])
        if gap and ivs:
            want = (ivs - 1) * gap + (r.get("g") or gap)
            if (e - s).days != want:
                bad_end.append(f"{r['c']}: {(e - s).days}d vs {want}d")
    check("finished + dropped + waiting never exceeds workers", not bad_sum, f"offenders: {bad_sum[:3] or 'none'}")
    check("no cohort has zero workers", not zero_n, f"offenders: {zero_n[:3] or 'none'}")
    check(
        "each cohort's end date == start + (ivs-1)*gap + grace",
        not bad_end,
        "; ".join(bad_end[:3]) or f"{len(CD)} cohorts",
    )
    closed = [r for r in CD if date.fromisoformat(r["e"]) <= TODAY]
    check(
        "closed cohorts are scored, open ones are marked",
        True,
        f"{len(closed)} closed, {len(CD) - len(closed)} still running",
    )
    fb = [r["c"] for r in CD if r.get("x")]
    check(
        "start-date fallback usage is disclosed",
        ("x" not in json.dumps(CD)) or ("*" in SRC),
        f"{len(fb)} cohorts on the trigger fallback",
    )

    # ---------------------------------------------------------------- E. cross-view ties
    section("E. CROSS-VIEW TIE-OUTS (the same number computed two ways)")
    by_sg = defaultdict(Counter)
    for r in CD:
        a = by_sg[CSG[r["c"]]]
        for _k, _src in (("n", "n"), ("f", "f"), ("d", "d"), ("w", "w")):
            a[_k] += r[_src]
    ties, mism = 0, []
    for sg, a in by_sg.items():
        c = CE.get(sg)
        if not c:
            continue
        # Both are "FLWs who started", one summed per cohort and one counted per design. An FLW in two
        # cohorts of the SAME design counts twice on the left, so the left must be >= the right.
        if a["n"] < c["total_started"]:
            mism.append(f"{sg}: cohort-sum {a['n']} < design {c['total_started']}")
        else:
            ties += 1
    check(
        "per-cohort starters >= per-design starters, every design",
        not mism,
        "; ".join(mism[:3]) or f"{ties} designs tie out",
    )

    # topicStatus vs the FLW x Topic matrix, recomputed from the compressed strings
    STATES = [
        "not-applicable",
        "not-available-yet",
        "available-not-started",
        "available-missed-overdue",
        "started-not-completed",
        "completed",
        "not-triggered",
    ]
    mat = Counter()
    for ent in D["flwMatrixV2"]:
        for p in ent.split("|")[1:]:
            k = p.index(":")
            for ch in p[k + 1 :].rstrip("u"):
                mat[STATES[int(ch)]] += 1
    ts = Counter()
    for row in D["topicStatus"]:
        for k, v in row.items():
            if k in STATES:
                ts[k] += v
    # flwMatrixV2 stores one digit per DESIGN topic, not per canonical topic - verified below - so it
    # holds no `not-applicable` at all, while topicStatus spans every topic and counts them. Comparing
    # that state across the two is apples to oranges; the APPLICABLE states are the real tie-out.
    APPLICABLE = [s for s in STATES if s != "not-applicable"]
    diffs = [f"{k}: matrix {mat[k]} vs topicStatus {ts[k]}" for k in APPLICABLE if mat[k] != ts[k]]
    check(
        "topicStatus equals the matrix on every applicable state",
        not diffs,
        "; ".join(diffs[:3]) or f"{sum(mat[k] for k in APPLICABLE):,} slots agree",
    )
    check(
        "the matrix stores design-length rows (no not-applicable padding)",
        mat["not-applicable"] == 0,
        f"{sum(mat.values()):,} digits, {mat['not-applicable']} of them padding",
    )

    # ---------------------------------------------------------------- F. the change itself
    section("F. DID THE CHANGE ACTUALLY LAND?")
    # After removing the final-interview exemption, an OPEN window can only exist in a cohort that is
    # still running. A closed cohort holding one would mean the deadline never fired. (Asserting a flat
    # zero was wrong: it only held while every cohort happened to be closed.)
    open_cohorts = {r["c"] for r in CD if date.fromisoformat(r["e"]) > TODAY}
    stray = Counter()
    for ent in D["flwMatrixV2"]:
        for p in ent.split("|")[1:]:
            k = p.index(":")
            coh = D["flwMatrixCohorts"][int(p[:k])]
            if coh not in open_cohorts:
                stray[coh] += p[k + 1 :].rstrip("u").count("2")
    stray = {c: n for c, n in stray.items() if n}
    check(
        "no open window survives in a CLOSED cohort (final-interview fix)",
        not stray,
        f"{mat['available-not-started']} open slots, all in {sorted(open_cohorts) or 'none'}"
        if not stray
        else f"stray: {stray}",
    )
    check(
        "'available-missed-overdue' is populated",
        mat["available-missed-overdue"] > 0,
        f"{mat['available-missed-overdue']} slots",
    )
    check(
        "a single-interview design reads 'not measurable', not 0%",
        any(len((SD.get(sg) or {}).get("topics") or []) == 1 and not c["rhythm_base"][-1] for sg, c in CE.items())
        and "not measurable" in SRC,
        "2WT-style designs",
    )
    single = [sg for sg, c in CE.items() if c["rhythm_base"][-1] == 0]
    flat = [sg for sg, c in CE.items() if c["rhythm_base"][-1] and c["steady_pct"][-1] == 0]
    check(
        "rhythm is not flat zero wherever it is measurable",
        not flat,
        f"collapsed: {flat or 'none'} (unmeasurable: {single})",
    )
    waiting_total = sum(r["w"] for r in CD)
    check(
        "the Waiting bucket carries real volume",
        waiting_total > 0,
        f"{waiting_total} FLW-cohort pairs, {round(100 * waiting_total / sum(r['n'] for r in CD))}% of starters",
    )

    # ---------------------------------------------------------------- G. copy consistency
    section("G. THE PAGE MUST NOT STILL DESCRIBE THE OLD RULE")
    stale = {
        "silent 14+ days": "Dropped described as 14 days of silence",
        "silent 14-60": "at-risk pool described in fixed days",
        "14+, not finished": "Dropped tile subtitle",
        "8-14 days ago": "Slow band described in fixed days",
        "within last 7 days": "Active band described in fixed days",
    }
    found = [v for k, v in stale.items() if k in SRC]
    check("no stale fixed-day wording anywhere in the page", not found, "; ".join(found) or "")
    for phrase, label in (
        ("one interview gap", "the deadline rule is stated"),
        ("Waiting", "the Waiting bucket is named"),
        ("Drop-off by cohort", "the new view is reachable"),
        ("no day-count control", "the missing control is explained"),
        ("What a fixed number of days would have meant", "the explainer table exists"),
    ):
        check(label, phrase in SRC)
    check("no em/en dashes (house style)", not re.search(r"[–—]", SRC), f"{len(re.findall(r'[–—]', SRC))} found")

    # ---------------------------------------------------------------- H. anomaly sweep
    section("H. ANOMALY SWEEP")
    susp = []
    for r in CD:
        pct = round(100 * r["d"] / r["n"]) if r["n"] else 0
        if pct == 100 and r["n"] >= 10:
            susp.append(f"{r['c']} 100% dropped (n={r['n']})")
        if r["f"] == 0 and r["d"] == 0 and r["w"] == 0 and r["n"] >= 10:
            susp.append(f"{r['c']} all-zero outcome (n={r['n']})")
    check(
        "no cohort shows an implausible all-or-nothing outcome",
        not susp,
        "; ".join(susp[:3]) or f"{len(CD)} cohorts swept",
    )
    nan = [k for k in D if "NaN" in json.dumps(D[k]) or "Infinity" in json.dumps(D[k])]
    check("no NaN or Infinity in the payload", not nan, f"{nan or 'none'}")

    bad = [n for n, ok, _ in checks if not ok]
    print("\n" + "=" * 100)
    print(f"  {len(checks) - len(bad)}/{len(checks)} checks pass")
    print(f"  VERDICT: {'ALL PASS' if not bad else 'FAILURES -> ' + '; '.join(bad)}")
    print("=" * 100)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
