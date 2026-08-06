#!/usr/bin/env python3
"""build_flw_analysis.py — per-FLW cross-cohort retention & engagement analysis.

Everything else on the dashboard is cohort/subgroup-level. This rolls the data up to ONE ROW PER UNIQUE
FLW, unioning their interview timeline across EVERY cohort/arm they were part of (~64% of FLWs are in ≥2
cohorts), and derives engagement metrics, an RFM-style score+tier, and a behavioral persona.

Reuses build_master_4src (bm.rows, bm.session_start_by_flw_iv, bm.flw_demographics, bm.cohort_llo,
bm.SUBGROUP_DESIGN, bm.TODAY). Outputs:
  - flw_analysis.csv           one row per FLW (full detail — for export/analysis, NOT the render embed)
  - flw_analysis_payload.json  compact AGGREGATES for the dashboard "FLW Retention" tab (small)
  - prints a written insights summary

Importable: build_records() -> per-FLW records; aggregate(records) -> compact payload dict.
Run: .venv/Scripts/python.exe build_flw_analysis.py
"""
import bisect
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict

import build_master_4src as bm

TIER_ORDER = ["Champion", "Solid", "Slipping", "At-risk", "Lost"]
PERSONA_ORDER = [
    "Champion",
    "Steady finisher",
    "Slow-but-finishing",
    "Re-engager",
    "Early dropper",
    "One-and-done",
    "Lapsed",
]


def build_records():
    """One record per unique FLW who started ≥1 interview, unioned across all their cohorts."""
    TODAY, DEMO, DESIGN = bm.TODAY, bm.flw_demographics, bm.SUBGROUP_DESIGN
    LLO = getattr(bm, "cohort_llo", {})
    start = bm.session_start_by_flw_iv

    flws = defaultdict(
        lambda: {
            "cohorts": set(),
            "subgroups": set(),
            "trig": set(),
            "started": set(),
            "completed": set(),
            "sessions": {},
        }
    )
    for r in bm.rows:
        f = flws[r["connect_id"]]
        c, n = r["cohort_id"], int(r["interview_n"])
        f["cohorts"].add(c)
        f["subgroups"].add(r["subgroup"])
        f["trig"].add((c, n))
        if r["is_started"] == "Y":
            f["started"].add((c, n))
            sid = r.get("matched_session_id")
            if sid and sid not in f["sessions"]:
                d = start.get((r["connect_id"], r["topic_code"]))
                f["sessions"][sid] = {
                    "date": d.date() if d else None,
                    "words": r.get("session_human_words") or 0,
                    "msgs": r.get("session_human_msgs") or 0,
                }
        if r["is_completed"] == "Y":
            f["completed"].add((c, n))

    def finished_any(f):
        comp = defaultdict(set)
        for c, n in f["completed"]:
            comp[c].add(n)
        for c in f["cohorts"]:
            sg = bm.cohort_to_sg(c)
            if sg and len(comp.get(c, ())) >= len(DESIGN[sg]["topics"]):
                return True
        return False

    records = []
    for flw, f in flws.items():
        if not f["started"]:
            continue
        dates = sorted({s["date"] for s in f["sessions"].values() if s["date"]})
        n_trig, n_started, n_completed, n_sess = (
            len(f["trig"]),
            len(f["started"]),
            len(f["completed"]),
            len(f["sessions"]),
        )
        words = sum(s["words"] for s in f["sessions"].values())
        msgs = sum(s["msgs"] for s in f["sessions"].values())
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        demo = DEMO.get(flw, {})
        records.append(
            {
                "connect_id": flw,
                "name": demo.get("name", ""),
                "state": demo.get("state", ""),
                "lga": demo.get("lga", ""),
                "settlement": demo.get("settlement", ""),
                "type_of_flw": demo.get("type_of_flw", ""),
                "education": demo.get("education", ""),
                "native_language": demo.get("native_language", ""),
                "n_cohorts": len(f["cohorts"]),
                "cohorts": "|".join(sorted(f["cohorts"])),
                "subgroups": "|".join(sorted(f["subgroups"])),
                "llos": "|".join(sorted({LLO.get(c, "") for c in f["cohorts"] if LLO.get(c)})),
                "interviews_triggered": n_trig,
                "interviews_started": n_started,
                "interviews_completed": n_completed,
                "progression_depth": max((n for (_c, n) in f["started"]), default=0),
                "completion_rate": round(n_completed / n_trig, 3) if n_trig else 0,
                "started_rate": round(n_started / n_trig, 3) if n_trig else 0,
                "finished_any": finished_any(f),
                "n_sessions": n_sess,
                "first_session": dates[0].isoformat() if dates else "",
                "last_session": dates[-1].isoformat() if dates else "",
                "recency_days": (TODAY - dates[-1]).days if dates else None,
                "max_gap_days": max(gaps) if gaps else 0,
                "median_cadence_days": round(statistics.median(gaps), 1) if gaps else None,
                "avg_words_per_session": round(words / n_sess, 1) if n_sess else 0,
                "words_per_msg": round(words / msgs, 1) if msgs else 0,
            }
        )

    depth_vals = sorted(x["avg_words_per_session"] for x in records if x["avg_words_per_session"] > 0)

    def dscore(v):
        if not depth_vals or v <= 0:
            return 1
        return min(5, int(bisect.bisect_left(depth_vals, v) / len(depth_vals) * 5) + 1)

    def persona(x):
        cr, depth, started = x["completion_rate"], x["progression_depth"], x["interviews_started"]
        rec, mg, mc = x["recency_days"], x["max_gap_days"], x["median_cadence_days"]
        steady = (mc is None) or (mg <= 2 * mc) or mg <= 10
        reengaged = mc is not None and mg >= 21 and rec is not None and rec <= 14
        if started == 1 and not x["finished_any"]:
            return "One-and-done"
        if x["finished_any"] and cr >= 0.8 and steady:
            return "Champion"
        if x["finished_any"]:
            return "Steady finisher"
        if reengaged:
            return "Re-engager"
        if cr >= 0.5:
            return "Slow-but-finishing"
        if depth <= 2 and cr < 0.5:
            return "Early dropper"
        return "Lapsed"

    for x in records:
        r = x["recency_days"]
        R = (
            5
            if r is not None and r <= 7
            else 4
            if r is not None and r <= 14
            else 3
            if r is not None and r <= 30
            else 2
            if r is not None and r <= 60
            else 1
        )
        cr = x["completion_rate"]
        F = 5 if cr >= 0.9 else 4 if cr >= 0.7 else 3 if cr >= 0.5 else 2 if cr >= 0.3 else 1
        D = dscore(x["avg_words_per_session"])
        tot = R + F + D
        x["R"], x["F"], x["D"], x["rfm"] = R, F, D, tot
        x["tier"] = (
            "Champion"
            if tot >= 13
            else "Solid"
            if tot >= 10
            else "Slipping"
            if tot >= 7
            else "At-risk"
            if tot >= 5
            else "Lost"
        )
        x["persona"] = persona(x)
    return records


def aggregate(records):
    """Compact aggregates for the dashboard tab (small enough to embed)."""
    N = len(records) or 1

    def dist(key, order):
        c = Counter(x[key] for x in records)
        return [{"k": k, "n": c[k], "pct": round(100 * c[k] / N)} for k in order if c.get(k)]

    def crosscut(key, minn=20):
        grp = defaultdict(list)
        for x in records:
            if x[key]:
                grp[x[key]].append(x)
        rows = [
            {
                "k": k,
                "n": len(v),
                "completion": round(sum(z["completion_rate"] for z in v) / len(v), 2),
                "finished": round(100 * sum(z["finished_any"] for z in v) / len(v)),
                "depth": round(sum(z["avg_words_per_session"] for z in v) / len(v)),
            }
            for k, v in grp.items()
            if len(v) >= minn
        ]
        return sorted(rows, key=lambda t: -t["finished"])

    depth_c = Counter(x["progression_depth"] for x in records)
    survival = [
        {
            "d": d,
            "reached": sum(v for k, v in depth_c.items() if k >= d),
            "pct": round(100 * sum(v for k, v in depth_c.items() if k >= d) / N),
        }
        for d in range(1, max(depth_c) + 1)
    ]

    def grpstats(rs):
        n = len(rs) or 1
        return {
            "n": len(rs),
            "completion": round(sum(x["completion_rate"] for x in rs) / n, 2),
            "finished": round(100 * sum(x["finished_any"] for x in rs) / n),
            "depth": round(sum(x["avg_words_per_session"] for x in rs) / n),
        }

    dvals = sorted(x["avg_words_per_session"] for x in records if x["avg_words_per_session"] > 0)
    med = statistics.median(dvals) if dvals else 0
    return {
        "n_flws": len(records),
        "tiers": dist("tier", TIER_ORDER),
        "personas": dist("persona", PERSONA_ORDER),
        "survival": survival,
        "crossCohort": {
            "dist": [
                {
                    "k": str(k),
                    "n": Counter(x["n_cohorts"] for x in records)[k],
                    "pct": round(100 * Counter(x["n_cohorts"] for x in records)[k] / N),
                }
                for k in sorted({x["n_cohorts"] for x in records})
            ],
            "multi": grpstats([x for x in records if x["n_cohorts"] > 1]),
            "single": grpstats([x for x in records if x["n_cohorts"] == 1]),
        },
        "firstIv": {
            "hi": grpstats([x for x in records if x["avg_words_per_session"] >= med]),
            "lo": grpstats([x for x in records if x["avg_words_per_session"] < med]),
        },
        "byState": crosscut("state"),
        "byType": crosscut("type_of_flw"),
        "byLLO": crosscut("llos", minn=1),
        "coverage_lga": round(100 * sum(1 for x in records if x["lga"]) / N),
    }


CSV_COLS = [
    "connect_id",
    "name",
    "state",
    "lga",
    "settlement",
    "type_of_flw",
    "education",
    "native_language",
    "n_cohorts",
    "cohorts",
    "subgroups",
    "llos",
    "interviews_triggered",
    "interviews_started",
    "interviews_completed",
    "progression_depth",
    "completion_rate",
    "started_rate",
    "finished_any",
    "n_sessions",
    "first_session",
    "last_session",
    "recency_days",
    "max_gap_days",
    "median_cadence_days",
    "avg_words_per_session",
    "words_per_msg",
    "R",
    "F",
    "D",
    "rfm",
    "tier",
    "persona",
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    recs = build_records()
    with open("flw_analysis.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS)
        w.writeheader()
        for x in sorted(recs, key=lambda z: -z["rfm"]):
            w.writerow({k: x.get(k) for k in CSV_COLS})
    agg = aggregate(recs)
    json.dump(agg, open("flw_analysis_payload.json", "w", encoding="utf-8"), separators=(",", ":"))
    N = len(recs)
    print(f"\n=== FLW-LEVEL ANALYSIS: {N} unique FLWs (wrote flw_analysis.csv + flw_analysis_payload.json) ===")
    print("\nTIERS:", [(t["k"], t["n"], f"{t['pct']}%") for t in agg["tiers"]])
    print("PERSONAS:", [(t["k"], t["n"], f"{t['pct']}%") for t in agg["personas"]])
    print("SURVIVAL:", [(f"Int≥{s['d']}", f"{s['pct']}%") for s in agg["survival"][:8]])
    cc = agg["crossCohort"]
    print(
        f"CROSS-COHORT: dist={[(d['k'], d['pct']) for d in cc['dist']]} | multi={cc['multi']} | single={cc['single']}"
    )
    print(f"FIRST-IV depth: hi={agg['firstIv']['hi']} lo={agg['firstIv']['lo']}")
    print("BY STATE:", [(s["k"], s["finished"]) for s in agg["byState"]])
    print("BY TYPE:", [(s["k"], s["finished"]) for s in agg["byType"]])
    print("BY LLO:", [(s["k"], s["finished"]) for s in agg["byLLO"]])


if __name__ == "__main__":
    main()
