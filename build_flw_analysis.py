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

# Engagement TIERS describe a worker's CURRENT activity state (an RFM score band). Behavioural
# PERSONAS (below) describe their whole history. Those are different questions, so they must not share
# vocabulary: until 2026-08-11 both lists contained "Champion" (297 vs 276 workers on live data) and
# both were clickable filters on the same screen, so "Champion" meant two things depending on which
# panel you clicked. Tiers renamed to activity-state language; personas keep the behavioural names.
TIER_ORDER = ["Highly engaged", "Engaged", "Slipping", "Gone quiet", "Lost"]
# old label -> new, so a payload built before the rename still renders
TIER_ALIASES = {"Champion": "Highly engaged", "Solid": "Engaged", "At-risk": "Gone quiet"}
PERSONA_ORDER = [
    "Champion",
    "Steady finisher",
    "Partial progress",
    "Re-engager",
    "Early dropper",
    "One-and-done",
    "Lapsed",
]


# Cadence-relative thresholds. Every "days" threshold below used to be a fixed number - 14 days
# recently-active, 21 days for a break, 14-60 days for the at-risk pool - applied to designs whose
# interviews are anywhere from 3 to 14 days apart. Two gaps means the same thing in every design;
# 14 days does not (it is one interview in ABT2-A and nearly five in TRE). Falls back to 7 days when
# a design has no cadence, e.g. a single-interview cohort with nothing to space.
FALLBACK_GAP_DAYS = 7


def _gap(x):
    """One gap for this FLW: the spacing their own schedule asks for."""
    return x.get("design_cadence_days") or FALLBACK_GAP_DAYS


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

    def cohort_finish(f):
        """(#cohorts finished, #cohorts with a known design, #cohorts where the full schedule was offered).

        finished_any (= finished >=1 cohort) is a MAX over cohorts, so it mechanically rises with the number
        of cohorts an FLW was in — being in 3 cohorts gives 3 independent chances. Reporting it as evidence
        that re-use "compounds engagement" is a bug, not a finding. We therefore also return the per-cohort
        rate, which is the comparable quantity, plus how many of their cohorts actually offered the whole
        schedule (an FLW can't "finish" a schedule the programme never finished triggering).
        """
        comp = defaultdict(set)
        for c, n in f["completed"]:
            comp[c].add(n)
        trig = defaultdict(set)
        for c, n in f["trig"]:
            trig[c].add(n)
        fin = known = offered = 0
        for c in f["cohorts"]:
            sg = bm.cohort_to_sg(c)
            if not sg:
                continue
            need = len(DESIGN[sg]["topics"])
            known += 1
            if len(trig.get(c, ())) >= need:
                offered += 1
            if len(comp.get(c, ())) >= need:
                fin += 1
        return fin, known, offered

    # Recency is measured against the freshest session in the DATA, not date.today(): with a lagging OCS
    # pull those differ, and every recency-derived number (RFM tier, at-risk pool) would silently degrade
    # as the pipeline aged rather than as workers disengaged.
    _all_dates = [s["date"] for f in flws.values() for s in f["sessions"].values() if s["date"]]
    ASOF = max(_all_dates) if _all_dates else TODAY

    records = []
    for flw, f in flws.items():
        if not f["started"]:
            continue
        dates = sorted({s["date"] for s in f["sessions"].values() if s["date"]})
        first_words = 0
        if dates:
            _first = [s for s in f["sessions"].values() if s["date"] == dates[0]]
            first_words = round(sum(s["words"] for s in _first) / len(_first), 1) if _first else 0
        n_fin, n_known, n_offered = cohort_finish(f)
        # The panel-survey literature separates two things we can measure independently: how LATE a
        # worker responds (pace) and how ERRATIC they are (stability). Stability is the stronger
        # retention signal there, so keep them apart rather than collapsing into "engagement".
        design_cadence = max(
            (DESIGN[bm.cohort_to_sg(c)]["cadence"] for c in f["cohorts"] if bm.cohort_to_sg(c)), default=None
        )
        train = [
            bm.cohort_info[c]["training_date"] for c in f["cohorts"] if bm.cohort_info.get(c, {}).get("training_date")
        ]
        onboarding_lag = (dates[0] - min(train)).days if (dates and train) else None
        max_design_len = max(
            (len(DESIGN[bm.cohort_to_sg(c)]["topics"]) for c in f["cohorts"] if bm.cohort_to_sg(c)), default=0
        )
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
                "finished_any": n_fin > 0,
                "cohorts_finished": n_fin,
                "cohorts_known": n_known,
                "cohorts_offered_full": n_offered,
                "max_design_len": max_design_len,
                # Share of THIS FLW's cohorts they finished — no max-over-N inflation. TWO bases, because
                # the choice materially changes the headline and neither is wrong:
                #   _known   = every cohort with a known design, INCLUDING ones whose full schedule has
                #              not been triggered yet. Honest "so far", but ~22% of enrolment slots have
                #              not been fully offered, so it counts un-offered work as unfinished — and
                #              it does so unevenly: multi-cohort FLWs are ~2.3x more likely to be
                #              carrying a still-rolling schedule, which biases the multi-vs-single
                #              comparison against exactly the group that comparison is about.
                #   _offered = only cohorts whose whole schedule was actually put to them. The fair
                #              like-for-like rate, but silent about work still in flight.
                # Both are published and the dashboard shows both, rather than picking one silently.
                "finish_rate_per_cohort": round(n_fin / n_known, 3) if n_known else 0,
                "finish_rate_offered": round(n_fin / n_offered, 3) if n_offered else None,
                "n_sessions": n_sess,
                "first_session": dates[0].isoformat() if dates else "",
                "last_session": dates[-1].isoformat() if dates else "",
                "first_session_words": first_words,
                "recency_days": (ASOF - dates[-1]).days if dates else None,
                "max_gap_days": max(gaps) if gaps else 0,
                "median_cadence_days": round(statistics.median(gaps), 1) if gaps else None,
                "design_cadence_days": design_cadence,
                # >1 = slower than the schedule asks; the schedule is the fair yardstick, not a fixed
                # number of days, because cadences differ by subgroup (3 to 14 days).
                "pace_ratio": (
                    round(statistics.median(gaps) / design_cadence, 2) if gaps and design_cadence else None
                ),
                # how erratic: longest silence relative to their own typical gap (1.0 = perfectly even)
                "gap_ratio": (
                    round(max(gaps) / statistics.median(gaps), 2) if gaps and statistics.median(gaps) > 0 else None
                ),
                "onboarding_lag_days": onboarding_lag,
                "avg_words_per_session": round(words / n_sess, 1) if n_sess else 0,
                "words_per_msg": round(words / msgs, 1) if msgs else 0,
            }
        )

    # Peer density: how many other workers share a worker's settlement. The CHW-attrition literature
    # repeatedly identifies informal PEER SUPPORT as a retention factor, and settlement is the finest
    # geography we hold (804 distinct values) — too granular to report as a cut, but exactly right for
    # asking "does working alongside others help?".
    _by_settlement = Counter(x["settlement"] for x in records if x["settlement"])
    for x in records:
        peers = _by_settlement.get(x["settlement"], 0)
        x["settlement_peers"] = peers
        # "Tangaza (Sokoto)" rather than "Tangaza" — an LGA name alone means nothing to most readers,
        # and the state is the whole point of the comparison.
        x["lga_label"] = f"{x['lga']} ({x['state']})" if x.get("lga") and x.get("state") else (x.get("lga") or "")
        x["peer_band"] = (
            "Only worker in settlement" if peers <= 1 else "2-4 in settlement" if peers <= 4 else "5+ in settlement"
        )
        pr = x["pace_ratio"]
        x["pace_band"] = (
            "On/ahead of schedule"
            if pr is not None and pr <= 1.25
            else "Somewhat slow"
            if pr is not None and pr <= 2
            else "Very slow"
            if pr is not None
            else "Single interview (no pace)"
        )
        gr = x["gap_ratio"]
        x["stability_band"] = (
            "Steady rhythm"
            if gr is not None and gr <= 1.5
            else "Some variation"
            if gr is not None and gr <= 3
            else "Erratic"
            if gr is not None
            else "Single interview (no rhythm)"
        )
        ol = x["onboarding_lag_days"]
        x["onboarding_band"] = (
            "Started within a week"
            if ol is not None and ol <= 7
            else "1-2 weeks"
            if ol is not None and ol <= 14
            else "2-4 weeks"
            if ol is not None and ol <= 28
            else "Over a month"
            if ol is not None
            else "Unknown"
        )

    depth_vals = sorted(x["avg_words_per_session"] for x in records if x["avg_words_per_session"] > 0)

    def dscore(v):
        if not depth_vals or v <= 0:
            return 1
        return min(5, int(bisect.bisect_left(depth_vals, v) / len(depth_vals) * 5) + 1)

    def persona(x):
        cr, depth, started = x["completion_rate"], x["progression_depth"], x["interviews_started"]
        rec, mg, mc = x["recency_days"], x["max_gap_days"], x["median_cadence_days"]
        cad = _gap(x)
        steady = (mc is None) or (mg <= 2 * mc) or mg <= 2 * cad
        reengaged = mc is not None and mg >= 3 * cad and rec is not None and rec <= 2 * cad
        if started == 1 and not x["finished_any"]:
            return "One-and-done"
        if x["finished_any"] and cr >= 0.8 and steady:
            return "Champion"
        if x["finished_any"]:
            return "Steady finisher"
        if reengaged:
            return "Re-engager"
        if cr >= 0.5:
            # NB reached only after both finished_any branches returned, so these FLWs have finished
            # NOTHING. The old name "Slow-but-finishing" ("gets there eventually") described the exact
            # opposite of what the branch selects.
            return "Partial progress"
        if depth <= 2 and cr < 0.5:
            return "Early dropper"
        return "Lapsed"

    for x in records:
        r, _c = x["recency_days"], _gap(x)
        R = (
            5
            if r is not None and r <= _c
            else 4
            if r is not None and r <= 2 * _c
            else 3
            if r is not None and r <= 4 * _c
            else 2
            if r is not None and r <= 8 * _c
            else 1
        )
        cr = x["completion_rate"]
        F = 5 if cr >= 0.9 else 4 if cr >= 0.7 else 3 if cr >= 0.5 else 2 if cr >= 0.3 else 1
        D = dscore(x["avg_words_per_session"])
        tot = R + F + D
        x["R"], x["F"], x["D"], x["rfm"] = R, F, D, tot
        # score bands -> TIER_ORDER, so the ladder and the published order can never disagree
        x["tier"] = (
            TIER_ORDER[0]
            if tot >= 13
            else TIER_ORDER[1]
            if tot >= 10
            else TIER_ORDER[2]
            if tot >= 7
            else TIER_ORDER[3]
            if tot >= 5
            else TIER_ORDER[4]
        )
        x["persona"] = persona(x)
    return records


def aggregate(records):
    """Compact aggregates for the dashboard tab (small enough to embed)."""
    N = len(records) or 1

    def dist(key, order):
        c = Counter(x[key] for x in records)
        return [{"k": k, "n": c[k], "pct": round(100 * c[k] / N)} for k in order if c.get(k)]

    def _row(k, v):
        return {
            "k": k,
            "n": len(v),
            "completion": round(sum(z["completion_rate"] for z in v) / len(v), 2),
            "finished": round(100 * sum(z["finished_any"] for z in v) / len(v)),
            # per-cohort finish rate: the version of "finished" that does NOT reward being in more cohorts
            "finished_pc": round(100 * sum(z["finish_rate_per_cohort"] for z in v) / len(v)),
            "depth": round(sum(z["avg_words_per_session"] for z in v) / len(v)),
        }

    def ordered_cut(key, order, minn=1):
        """Like crosscut but preserves a meaningful order (these are bands, not nominal groups) and
        keeps every band so the reader can see the whole gradient, including small ones."""
        grp = defaultdict(list)
        for x in records:
            grp[x.get(key) or "Unknown"].append(x)
        return [_row(k, grp[k]) for k in order if len(grp.get(k, [])) >= minn]

    def crosscut(key, minn=20):
        """Group by `key`. Buckets under `minn` are pooled into one honest residual row rather than
        silently dropped — byType used to omit ~29 FLWs, so its bars didn't cover the population."""
        grp = defaultdict(list)
        for x in records:
            grp[x[key] or "(not recorded)"].append(x)
        rows, small = [], []
        for k, v in grp.items():
            (rows if (len(v) >= minn and k != "(not recorded)") else small).append((k, v))
        out = sorted([_row(k, v) for k, v in rows], key=lambda t: -t["finished"])
        if small:
            pooled = [z for _k, v in small for z in v]
            r = _row("Other / not recorded", pooled)
            r["pooled"] = sorted(k for k, _v in small)
            r["residual"] = True  # render keeps it last + muted: it is coverage, never a finding
            out.append(r)  # always LAST, never ranked — a 1-FLW bucket must not top the chart
        return out

    depth_c = Counter(x["progression_depth"] for x in records)
    # `elig` = FLWs whose longest cohort schedule even HAS an interview d. Dividing by all N (the old
    # behaviour) made the curve read as drop-off when most of the fall is simply "their cohort was 2
    # interviews long" — e.g. Int>=3 was 39% of everyone but 64% of those who could reach it.
    elig_c = Counter(x["max_design_len"] for x in records)
    survival = []
    for d in range(1, (max(depth_c) if depth_c else 0) + 1):
        reached = sum(v for k, v in depth_c.items() if k >= d)
        elig = sum(v for k, v in elig_c.items() if k >= d)
        survival.append(
            {
                "d": d,
                "reached": reached,
                "elig": elig,
                "pct": round(100 * reached / N),  # of everyone (kept for continuity)
                "pct_elig": round(100 * reached / elig) if elig else None,  # of those who could reach it
            }
        )

    def grpstats(rs):
        n = len(rs) or 1
        return {
            "n": len(rs),
            "completion": round(sum(x["completion_rate"] for x in rs) / n, 2),
            "finished": round(100 * sum(x["finished_any"] for x in rs) / n),
            "finished_pc": round(100 * sum(x["finish_rate_per_cohort"] for x in rs) / n),
            "depth": round(sum(x["avg_words_per_session"] for x in rs) / n),
            "first_depth": round(sum(x["first_session_words"] for x in rs) / n),
        }

    # split on FIRST-session depth only (the lifetime-average median this replaced is gone: it mixed the
    # outcome into the predictor)
    fvals = sorted(x["first_session_words"] for x in records if x["first_session_words"] > 0)
    fmed = statistics.median(fvals) if fvals else 0

    # ---- deep cuts (for the executive brief): who drops off, arm combos, recoverable at-risk ----
    def _pct_by(rs, key, top=1):
        c = Counter(x[key] for x in rs if x[key])
        n = len(rs) or 1
        return [{"k": k, "n": v, "pct": round(100 * v / n)} for k, v in c.most_common(top)]

    oad = [x for x in records if x["persona"] == "One-and-done"]
    oad_med_depth = (
        statistics.median([x["avg_words_per_session"] for x in oad if x["avg_words_per_session"]]) if oad else 0
    )
    champ_med_depth = statistics.median(
        [x["avg_words_per_session"] for x in records if x["persona"] == "Champion" and x["avg_words_per_session"]]
        or [0]
    )
    # "Recoverable at-risk": unfinished AND recently silent AND the programme actually finished offering
    # them a schedule. Without the last condition ~44% of the pool were people the programme simply hadn't
    # finished triggering — not lapsed workers, and not nudgeable.
    at_risk = [
        x
        for x in records
        if not x["finished_any"]
        and x["cohorts_offered_full"] > 0
        and x["recency_days"] is not None
        and 2 * _gap(x) <= x["recency_days"] <= 8 * _gap(x)
    ]
    unfinished_total = sum(1 for x in records if not x["finished_any"])
    combos = Counter(x["subgroups"] for x in records if x["n_cohorts"] > 1)
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
        # Median split on the FIRST session's answer depth. The old `firstIv` key split on
        # avg_words_per_session — the LIFETIME average over every interview in every cohort — so it was
        # partly made of the very sessions whose existence is the outcome. First-session-only is the
        # honest "does early depth predict finishing" test, and it reports the per-cohort rate alongside.
        "depthSplit": {
            "basis": "first session only",
            "median": round(fmed, 1),
            "hi": grpstats([x for x in records if x["first_session_words"] >= fmed]),
            "lo": grpstats([x for x in records if x["first_session_words"] < fmed]),
        },
        "byState": crosscut("state"),
        "byType": crosscut("type_of_flw"),
        # minn=20 (was 1): with minn=1 the single FLW who spans both partners published as its own
        # "COWACDI|EHA — 100% finished" bar, and the brief quoted it.
        "byLLO": crosscut("llos", minn=20),
        "coverage_lga": round(100 * sum(1 for x in records if x["lga"]) / N),
        # deep cuts for the executive brief
        "oneAndDone": {
            "n": len(oad),
            "pct": round(100 * len(oad) / N),
            "topState": _pct_by(oad, "state", 1),
            "topType": _pct_by(oad, "type_of_flw", 1),
            "singleCohortPct": round(100 * sum(1 for x in oad if x["n_cohorts"] == 1) / (len(oad) or 1)),
            "medianDepth": round(oad_med_depth),
        },
        "champMedianDepth": round(champ_med_depth),
        "overallSingleCohortPct": round(100 * sum(1 for x in records if x["n_cohorts"] == 1) / N),
        "atRisk": {
            "n": len(at_risk),
            "ofUnfinished": unfinished_total,
            "byState": _pct_by(at_risk, "state", 4),
        },
        "armCombos": [{"k": k, "n": v} for k, v in combos.most_common(5)],
        # ---- first-pass additions (2026-08-11): geography below state, peer support, response
        # behaviour, onboarding speed. Grounded in the CHW-attrition and panel-survey literature:
        # peer support is a repeatedly-identified retention factor, and response STABILITY predicts
        # retention more strongly than response SPEED.
        "byLGA": crosscut("lga_label", minn=20),
        "byPeers": ordered_cut("peer_band", ["Only worker in settlement", "2-4 in settlement", "5+ in settlement"]),
        "byPace": ordered_cut(
            "pace_band", ["On/ahead of schedule", "Somewhat slow", "Very slow", "Single interview (no pace)"]
        ),
        "geoVariance": geo_variance(records),
        "micro": micro(records),
    }


def geo_variance(records):
    """How much of the finish-rate spread is BETWEEN states vs WITHIN a state (between its LGAs)?

    This is the one number that speaks to the state-vs-partner problem. Partner and state are perfectly
    nested here, so no cut of this data can separate them — but if most of the variation sits WITHIN
    each state, then a partner-wide or state-wide explanation is the wrong shape regardless, and the
    action is local. Reported as the spread (max-min) at each level, which is what a reader can act on.
    """
    from statistics import mean

    by_state, by_lga = {}, {}
    for x in records:
        if not x.get("state"):
            continue
        by_state.setdefault(x["state"], []).append(x["finish_rate_per_cohort"])
        if x.get("lga"):
            by_lga.setdefault((x["state"], x["lga"]), []).append(x["finish_rate_per_cohort"])
    st = {k: round(100 * mean(v)) for k, v in by_state.items() if len(v) >= 20}
    lg = {k: round(100 * mean(v)) for k, v in by_lga.items() if len(v) >= 20}
    if not st or not lg:
        return {}
    within = {}
    for (state, _lga), rate in lg.items():
        within.setdefault(state, []).append(rate)
    worst_state = min(st, key=lambda k: st[k])
    return {
        "state_spread": max(st.values()) - min(st.values()),
        "lga_spread": max(lg.values()) - min(lg.values()),
        "n_lgas": len(lg),
        "states": [
            {
                "k": k,
                "pc": v,
                "lga_spread": (max(within[k]) - min(within[k])) if within.get(k) else 0,
                "n_lgas": len(within.get(k, [])),
            }
            for k, v in sorted(st.items(), key=lambda kv: -kv[1])
        ],
        "worst_state": worst_state,
        "worst_state_best_lga": max((v for (s2, _l), v in lg.items() if s2 == worst_state), default=None),
        "best_state_worst_lga": max(
            [(min((v for (s2, _l), v in lg.items() if s2 == s), default=None), s) for s in st], key=lambda t: st[t[1]]
        )[0],
    }


def micro(records):
    """Column-oriented per-FLW micro-data so the dashboard can cross-filter client-side.

    One character per FLW per dimension (every dimension has <10 distinct values), plus two small numeric
    columns. ~1.4 KB per categorical column for 1,441 FLWs — the whole block is ~12 KB, which is what buys
    real drill-down instead of a static sheet. NO identifier is emitted: these are attributes only, so the
    block cannot be re-linked to a person.
    """
    dims = [
        ("state", lambda x: x["state"] or "(not recorded)"),
        ("type", lambda x: x["type_of_flw"] or "(not recorded)"),
        ("llo", lambda x: x["llos"] or "(not recorded)"),
        ("tier", lambda x: x["tier"]),
        ("persona", lambda x: x["persona"]),
        ("nco", lambda x: str(x["n_cohorts"])),
        ("fin", lambda x: "Finished ≥1 schedule" if x["finished_any"] else "No schedule finished"),
        ("peers", lambda x: x["peer_band"]),
        ("pace", lambda x: x["pace_band"]),
    ]
    # Dimensions whose values have a NATURAL ORDER must publish the dictionary in that order, because
    # the dashboard renders rows in dictionary order. Frequency-ordering an ordered scale made the tab
    # show tiers as "Engaged, Slipping, Highly engaged, Gone quiet, Lost" and cohort counts as
    # "2, 3, 1, 4, 5" — which reads as a bug. Nominal dimensions stay frequency-ordered (commonest
    # first) since that is the useful reading for them.
    ORDERED = {
        "tier": TIER_ORDER,
        "persona": PERSONA_ORDER,
        "fin": ["Finished ≥1 schedule", "No schedule finished"],
        "peers": ["Only worker in settlement", "2-4 in settlement", "5+ in settlement"],
        "pace": ["On/ahead of schedule", "Somewhat slow", "Very slow", "Single interview (no pace)"],
    }
    out = {"n": len(records), "dict": {}, "col": {}}
    for name, fn in dims:
        vals = [fn(x) for x in records]
        if name in ORDERED:
            order = [k for k in ORDERED[name] if k in set(vals)]
        elif name == "nco":
            order = sorted(set(vals), key=int)
        else:
            # nominal: frequency-ordered so the commonest value is index 0
            order = [k for k, _ in Counter(vals).most_common()]
        if len(order) > 10:  # keep one char per FLW; pool the tail
            keep = order[:9]
            order = keep + ["Other"]
            idx = {k: i for i, k in enumerate(keep)}
            vals = [v if v in idx else "Other" for v in vals]
        idx = {k: i for i, k in enumerate(order)}
        out["dict"][name] = order
        out["col"][name] = "".join(str(idx[v]) for v in vals)

    # Numeric columns as fixed-width base36 strings rather than JSON int arrays: an array of 1,441
    # 3-digit ints costs ~5 KB in commas and quotes alone, the packed string costs 1,441*w chars.
    def pack(vals, width):
        cap = 36**width - 1
        return "".join(_b36(min(max(int(v), 0), cap)).rjust(width, "0") for v in vals)

    out["num"] = {}
    for name, width, fn in [
        ("depth", 3, lambda x: round(x["avg_words_per_session"])),  # words/session, 0..46655
        ("fdepth", 3, lambda x: round(x["first_session_words"])),
        ("pcf", 2, lambda x: round(100 * x["finish_rate_per_cohort"])),  # 0..100
        # offered-basis twin of pcf, so the drill-down can show both bases under any filter combination.
        # None (no cohort fully offered yet) is encoded as 101 = "not measurable", never as 0, because a
        # 0 would drag the average down and read as "finished nothing".
        ("pcfo", 2, lambda x: 101 if x.get("finish_rate_offered") is None else round(100 * x["finish_rate_offered"])),
        ("deep", 1, lambda x: x["progression_depth"]),  # deepest interview reached, 0..35
    ]:
        out["num"][name] = {"w": width, "s": pack((fn(x) for x in records), width)}
    return out


_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def _b36(n):
    if n <= 0:
        return "0"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = _B36[r] + s
    return s


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
    "cohorts_finished",
    "cohorts_known",
    "cohorts_offered_full",
    "finish_rate_per_cohort",
    "finish_rate_offered",
    "max_design_len",
    "first_session_words",
    "n_sessions",
    "first_session",
    "last_session",
    "recency_days",
    "max_gap_days",
    "median_cadence_days",
    "design_cadence_days",
    "pace_ratio",
    "gap_ratio",
    "onboarding_lag_days",
    "settlement_peers",
    "peer_band",
    "pace_band",
    "stability_band",
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
    ds = agg["depthSplit"]
    print(f"FIRST-SESSION depth split (median {ds['median']}): hi={ds['hi']} lo={ds['lo']}")
    print(f"MICRO: {agg['micro']['n']} FLWs, dims={list(agg['micro']['dict'])}")
    print("BY STATE:", [(s["k"], s["finished"]) for s in agg["byState"]])
    print("BY TYPE:", [(s["k"], s["finished"]) for s in agg["byType"]])
    print("BY LLO:", [(s["k"], s["finished"]) for s in agg["byLLO"]])


if __name__ == "__main__":
    main()
