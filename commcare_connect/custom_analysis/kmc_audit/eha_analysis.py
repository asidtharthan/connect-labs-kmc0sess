"""
EHA data-quality snapshot — net-new pattern analyses.

These computations are NOT part of the 16-flag engine (``flag_logic.py``)
and are deliberately kept in a separate module so the ``.kmc_validation``
JS-parity guarantee on ``flag_logic.py`` is untouched. They reuse
``flag_logic`` helpers (weight unit auto-detection, date parsing, robust
row access, weight valid-range / pair-window constants) so the numbers are
consistent with the flag engine.

All functions take ``visit_rows`` — the visit-level pipeline output for a
single opportunity (each row carries ``username``, ``beneficiary_case_id``,
``visit_date``, ``weight``, ``visit_number``, ``reg_date``,
``discharge_date``, ``kmc_status``, ``child_alive`` …) — and return plain
dicts/lists suitable for both the Markdown report and CSV/JSON export.

Computed here:
  * weight_distribution        — enrollment-weight histogram by weight class
  * days_between_visits        — per-FLW mean/median gap between follow-up visits
  * early_discharge            — discharged-too-soon rate (two definitions)
  * weight_gain_by_class_45d   — avg daily weight gain per class, 0–45d post-reg
"""

from __future__ import annotations

import statistics
from typing import Any

from .flag_logic import (
    _PAIR_MAX_DAYS,
    _PAIR_MIN_DAYS,
    _WEIGHT_MAX_G,
    _WEIGHT_MIN_G,
    _parse_date,
    _read_weight_g,
    _row_get,
)

# Neonatal weight classes (grams), half-open [lo, hi). The first three match
# the bonus brief (<1500 / 1500-2000 / 2000-2500); ">=2500" catches the rest
# so every classified infant lands in exactly one bucket.
WEIGHT_CLASSES: tuple[tuple[str, float, float], ...] = (
    ("<1500", 0.0, 1500.0),
    ("1500-2000", 1500.0, 2000.0),
    ("2000-2500", 2000.0, 2500.0),
    (">=2500", 2500.0, float("inf")),
)

# Bonus weight-gain window: visits within this many days of registration.
GAIN_WINDOW_DAYS: int = 45

# Early-discharge "soon after registration" threshold (definition A).
EARLY_DISCHARGE_DAYS: int = 7
# Early-discharge "too few follow-up visits" threshold (definition B).
EARLY_DISCHARGE_MAX_FOLLOWUPS: int = 2


def classify_weight(weight_g: float | None) -> str | None:
    """Return the weight-class label for a gram weight, or None if missing."""
    if weight_g is None:
        return None
    for label, lo, hi in WEIGHT_CLASSES:
        if lo <= weight_g < hi:
            return label
    return None


# ---------------------------------------------------------------------------
# Shared per-case roll-up — every analysis below works off these summaries.
# ---------------------------------------------------------------------------


def _case_summaries(visit_rows: list[Any]) -> list[dict[str, Any]]:
    """Collapse visit rows into one summary per (username, beneficiary_case_id).

    Each summary carries enrollment weight (earliest valid weight by date),
    registration date, first/last visit dates, follow-up visit count, the
    latest-dated kmc_status/child_alive, and the chronological list of
    (date, weight_g) readings — everything the four analyses need.
    """
    by_case: dict[tuple[str, str], dict[str, Any]] = {}
    for row in visit_rows:
        uname = _row_get(row, "username") or ""
        cid = _row_get(row, "beneficiary_case_id")
        if not uname or not cid:
            continue
        key = (uname, str(cid))
        slot = by_case.setdefault(
            key,
            {
                "username": uname,
                "case_id": str(cid),
                "reg_date": None,
                "followup_count": 0,
                "_latest_date": None,
                "latest_status": None,
                "latest_child_alive": None,
                "weights": [],  # list[(date, weight_g)]
                "visit_dates": [],  # every dated visit row (weight or not)
            },
        )

        rd = _parse_date(_row_get(row, "reg_date"))
        if rd and slot["reg_date"] is None:
            slot["reg_date"] = rd

        # Follow-up visits are rows where visit_number is populated
        # (registration-only forms carry no visit_number).
        if _row_get(row, "visit_number") is not None:
            slot["followup_count"] += 1

        vdate = _parse_date(_row_get(row, "visit_date"))
        if vdate is not None:
            slot["visit_dates"].append(vdate)
        wg = _read_weight_g(row)
        if vdate is not None and wg is not None and _WEIGHT_MIN_G <= wg <= _WEIGHT_MAX_G:
            slot["weights"].append((vdate, wg))

        # Latest-dated status/child_alive (mirrors compute_case_metrics rule).
        if vdate is not None and (slot["_latest_date"] is None or vdate > slot["_latest_date"]):
            slot["_latest_date"] = vdate
            status = _row_get(row, "kmc_status")
            if status:
                slot["latest_status"] = str(status).strip().lower() or None
            ca = _row_get(row, "child_alive")
            if ca is not None:
                slot["latest_child_alive"] = str(ca).strip().lower() or None

    summaries: list[dict[str, Any]] = []
    for slot in by_case.values():
        weights = sorted(slot["weights"], key=lambda t: t[0])
        first_date = weights[0][0] if weights else None
        summaries.append(
            {
                "username": slot["username"],
                "case_id": slot["case_id"],
                "reg_date": slot["reg_date"],
                "first_visit_date": first_date,
                "last_visit_date": slot["_latest_date"],
                "visit_dates": sorted(slot["visit_dates"]),
                "followup_count": slot["followup_count"],
                "latest_status": slot["latest_status"],
                "latest_child_alive": slot["latest_child_alive"],
                # Enrollment weight = earliest valid weight reading by date.
                "enrollment_weight_g": weights[0][1] if weights else None,
                "weights": weights,
                "is_discharged": slot["latest_status"] == "discharged",
            }
        )
    return summaries


def _stats(values: list[float]) -> dict[str, Any]:
    """mean/median/min/max/n for a list of numbers (None-safe, empty-safe)."""
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n": len(vals),
        "mean": statistics.fmean(vals),
        "median": statistics.median(vals),
        "min": min(vals),
        "max": max(vals),
    }


# ---------------------------------------------------------------------------
# 1. Weight distribution of enrolled infants
# ---------------------------------------------------------------------------


def weight_distribution(visit_rows: list[Any]) -> dict[str, Any]:
    """Histogram of enrollment weight (earliest valid weight) by weight class.

    Returns program-wide counts/percentages per class plus a per-FLW
    breakdown, so over-focus on one weight category is visible at both
    levels. ``unknown`` counts infants with no valid weight reading.
    """
    summaries = _case_summaries(visit_rows)

    def _empty_counts() -> dict[str, int]:
        return {label: 0 for label, _, _ in WEIGHT_CLASSES} | {"unknown": 0}

    program = _empty_counts()
    per_flw: dict[str, dict[str, int]] = {}
    enrollment_weights: list[float] = []

    for s in summaries:
        cls = classify_weight(s["enrollment_weight_g"]) or "unknown"
        program[cls] += 1
        per_flw.setdefault(s["username"], _empty_counts())[cls] += 1
        if s["enrollment_weight_g"] is not None:
            enrollment_weights.append(s["enrollment_weight_g"])

    total = len(summaries)
    classified = total - program["unknown"]

    def _pct_map(counts: dict[str, int]) -> dict[str, float | None]:
        # Percentage of *classified* infants (excludes unknown) per class.
        denom = sum(v for k, v in counts.items() if k != "unknown")
        return {k: (round(100 * counts[k] / denom, 1) if denom else None) for k, _, _ in WEIGHT_CLASSES}

    return {
        "total_infants": total,
        "classified_infants": classified,
        "program_counts": program,
        "program_pct": _pct_map(program),
        "enrollment_weight_stats_g": _stats(enrollment_weights),
        "per_flw_counts": per_flw,
    }


# ---------------------------------------------------------------------------
# 2. Average days between visits
# ---------------------------------------------------------------------------


def days_between_visits(visit_rows: list[Any]) -> dict[str, Any]:
    """Per-FLW and program gap (days) between consecutive follow-up visits.

    Gaps are computed within each case (consecutive dated visits), then
    pooled. ``per_flw`` gives mean/median per FLW; ``program`` pools every
    gap across all FLWs; ``per_flw_mean_distribution`` summarises the spread
    of per-FLW means (so an outlier FLW stands out).
    """
    summaries = _case_summaries(visit_rows)

    gaps_by_flw: dict[str, list[float]] = {}
    all_gaps: list[float] = []
    for s in summaries:
        # Distinct dated visits for this case (any visit row, weight or not).
        dates = sorted(set(s["visit_dates"]))
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i - 1]).days
            if gap > 0:
                gaps_by_flw.setdefault(s["username"], []).append(gap)
                all_gaps.append(gap)

    per_flw = {u: _stats(g) for u, g in gaps_by_flw.items()}
    per_flw_means = [v["mean"] for v in per_flw.values() if v["mean"] is not None]

    return {
        "program": _stats(all_gaps),
        "per_flw": per_flw,
        "per_flw_mean_distribution": _stats(per_flw_means),
    }


# ---------------------------------------------------------------------------
# 3. Early discharge (two definitions, side by side)
# ---------------------------------------------------------------------------


def early_discharge(visit_rows: list[Any]) -> dict[str, Any]:
    """Rate of cases discharged 'during early visits', two ways.

    A discharged case = latest-dated kmc_status == "discharged".
      * Definition A: (last_visit_date - reg_date) <= EARLY_DISCHARGE_DAYS.
      * Definition B: follow-up visit count <= EARLY_DISCHARGE_MAX_FOLLOWUPS.

    NOTE: there is no explicit program-discharge timestamp in the form, so
    "time to discharge" is approximated by the enrolment→last-visit span
    (reg_date → last_visit_date). reg_date is the program registration date
    (distinct from the hospital discharge_date field). Denominator for the
    rates is discharged cases (with the dates/counts each definition needs).
    """
    summaries = _case_summaries(visit_rows)
    discharged = [s for s in summaries if s["is_discharged"]]

    days_to_discharge: list[float] = []
    early_a = 0
    a_denom = 0
    early_b = 0
    b_denom = 0
    per_flw: dict[str, dict[str, int]] = {}

    for s in discharged:
        u = s["username"]
        pf = per_flw.setdefault(u, {"discharged": 0, "early_a": 0, "early_b": 0})
        pf["discharged"] += 1

        if s["reg_date"] and s["last_visit_date"]:
            span = (s["last_visit_date"] - s["reg_date"]).days
            if span >= 0:
                days_to_discharge.append(span)
                a_denom += 1
                if span <= EARLY_DISCHARGE_DAYS:
                    early_a += 1
                    pf["early_a"] += 1

        b_denom += 1
        if s["followup_count"] <= EARLY_DISCHARGE_MAX_FOLLOWUPS:
            early_b += 1
            pf["early_b"] += 1

    return {
        "total_cases": len(summaries),
        "discharged_cases": len(discharged),
        "definition_a": {
            "label": f"discharged within {EARLY_DISCHARGE_DAYS} days of registration",
            "early": early_a,
            "denom": a_denom,
            "rate_pct": round(100 * early_a / a_denom, 1) if a_denom else None,
        },
        "definition_b": {
            "label": f"discharged with <= {EARLY_DISCHARGE_MAX_FOLLOWUPS} follow-up visits",
            "early": early_b,
            "denom": b_denom,
            "rate_pct": round(100 * early_b / b_denom, 1) if b_denom else None,
        },
        "days_to_discharge_stats": _stats(days_to_discharge),
        "per_flw": per_flw,
    }


# ---------------------------------------------------------------------------
# 4. BONUS — average weight gain per weight class, 0–45 days post-registration
# ---------------------------------------------------------------------------


def weight_gain_by_class_45d(visit_rows: list[Any]) -> dict[str, Any]:
    """Average daily weight gain (g/day) per enrollment weight class, 0–45d.

    For each infant: classify by enrollment weight; keep only weight
    readings within GAIN_WINDOW_DAYS of reg_date; pair successive readings
    (1–30 days apart, both 500–5000 g); average the per-pair daily gains for
    that infant. Then aggregate the per-infant averages within each class
    (mean/median/n). Per-baby averaging matches ``compute_weight_metrics`` so
    a high-visit infant doesn't dominate. Infants without a reg_date are
    skipped (no 45-day window) and counted in ``skipped_no_reg_date``.
    """
    summaries = _case_summaries(visit_rows)

    per_class_baby_gains: dict[str, list[float]] = {label: [] for label, _, _ in WEIGHT_CLASSES}
    skipped_no_reg = 0
    infants_with_gain = 0

    for s in summaries:
        cls = classify_weight(s["enrollment_weight_g"])
        if cls is None:
            continue
        reg = s["reg_date"]
        if reg is None:
            skipped_no_reg += 1
            continue

        in_window = [(d, w) for d, w in s["weights"] if 0 <= (d - reg).days <= GAIN_WINDOW_DAYS]
        in_window.sort(key=lambda t: t[0])

        child_gains: list[float] = []
        for i in range(1, len(in_window)):
            d1, w1 = in_window[i - 1]
            d2, w2 = in_window[i]
            days = (d2 - d1).days
            if days < _PAIR_MIN_DAYS or days > _PAIR_MAX_DAYS:
                continue
            if not (_WEIGHT_MIN_G <= w1 <= _WEIGHT_MAX_G and _WEIGHT_MIN_G <= w2 <= _WEIGHT_MAX_G):
                continue
            diff = w2 - w1
            if diff > 0:
                child_gains.append(diff / days)

        if child_gains:
            per_class_baby_gains[cls].append(sum(child_gains) / len(child_gains))
            infants_with_gain += 1

    return {
        "window_days": GAIN_WINDOW_DAYS,
        "infants_with_gain_data": infants_with_gain,
        "skipped_no_reg_date": skipped_no_reg,
        "by_class": {
            label: {**_stats(per_class_baby_gains[label]), "unit": "g/day"} for label, _, _ in WEIGHT_CLASSES
        },
    }
