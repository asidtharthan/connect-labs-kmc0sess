"""
KMC FLW quality-flag computation.

Ports the JavaScript flag math from
``commcare_connect/workflow/templates/kmc_flw_flags.py`` (lines 143-445)
into pure Python so the KMC Audit Dashboard can compute the same flags
without depending on the React workflow template.

Sources of truth:
- JS implementation: ``workflow/templates/kmc_flw_flags.py``
- Methodology design: ``docs/plans/2026-03-08-kmc-flw-flags-v2.md``
- Full 16-flag catalog with thresholds:
  ``Desktop/Dimagi/Projects/KMC/Labs Dashboard/Overview of KMC flags [March 2026].docx``

Inputs are two collections:
- ``aggregated_row``: one row per FLW from the AGGREGATED pipeline. Has
  ``total_cases``, ``deaths``, ``total_visits``, ``danger_visit_count``,
  ``danger_positive_count`` (matches PIPELINE_SCHEMAS in kmc_flw_flags.py).
- ``visit_rows``: list of visit-level rows from the VISIT_LEVEL pipeline
  for the same FLW (filtered upstream by username). Each row carries
  ``beneficiary_case_id``, ``visit_date``, ``weight``, ``visit_number``,
  ``reg_date``, ``discharge_date``, ``kmc_status``.

Outputs ``FLWFlagResult`` per FLW: metrics + the 16 flag dict + the
synthetic ``flag_mort`` priority indicator + which flags fired.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# =============================================================================
# Thresholds and minimum-data requirements
#
# Values mirror ``kmc_flw_flags.py:143-162`` (JS source) and the doc-stated
# thresholds for the 7 flags not yet in JS. A change here must be mirrored
# in the JS source until the JS is retired.
# =============================================================================

THRESHOLDS: dict[str, float] = {
    # --- 9 currently in JS ---
    "visits": 3.0,  # Avg visits/closed-non-mort case below this is concerning
    "mort_low": 0.02,  # < 2% mortality is biologically implausible
    "mort_high": 0.20,  # > 20% mortality is a quality concern
    "enroll": 0.35,  # > 35% of cases enrolled 8+ days post-discharge
    "danger_high": 0.30,  # > 30% follow-up visits with danger signs
    "danger_zero": 0.0,  # Exactly 0 danger signs ever (implausible)
    "wt_loss": 0.15,  # > 15% successive weight pairs show loss
    "wt_gain": 60.0,  # Mean daily gain > 60 g/day (fabrication signal)
    "wt_zero": 0.30,  # > 30% successive pairs show no weight change
    # --- 7 secondary, from "Overview of KMC flags [March 2026].docx" ---
    "round_weight": 0.80,  # >= 80% weights as exact multiples of 100g
    "hr_copycat": 0.75,  # > 75% follow-up visits share single HR value
    "temp_copycat": 0.75,  # > 75% follow-up visits share single temp value
    "spo2_implausible": 0.10,  # > 10% SpO2 readings outside 70-100%
    "ga_fullterm": 0.30,  # > 30% registrations with gestational_age >= 37 weeks
    "gps_same_case_far": 0.30,  # > 30% same-case GPS pairs > 1km apart
    "ds_no_referral": 0.0,  # Exactly 0% referral rate across DS-positive visits
}

MIN_CASES: dict[str, int] = {
    "visits": 10,
    "mort": 20,
    "enroll": 10,
    "danger_high": 20,
    "danger_zero": 30,
    "weight": 10,
    "exclude": 20,  # FLWs with fewer total cases are excluded entirely
    "round_weight": 20,
    "hr_copycat": 20,
    "temp_copycat": 20,
    "spo2_implausible": 20,
    "ga_fullterm": 10,
    "gps_same_case_far": 20,
    "ds_no_referral": 5,
}

# =============================================================================
# Flag display tiers
# =============================================================================

# Priority indicators surfaced in the top-tier UI table.
# ``flag_mort`` is synthetic — true if either flag_mort_low or flag_mort_high.
# The 4 data-quality flags are shown individually (no composite).
PRIORITY_FLAGS: tuple[str, ...] = (
    "flag_visits",
    "flag_mort",
    "flag_enroll",
    "flag_danger_high",
    "flag_ds_no_referral",
    "flag_round_weight",
    "flag_hr_copycat",
    "flag_temp_copycat",
    "flag_spo2_implausible",
    "flag_gps_same_case_far",
)

# All other flags shown in the collapsible secondary tier.
SECONDARY_FLAGS: tuple[str, ...] = (
    "flag_mort_low",
    "flag_mort_high",
    "flag_danger_zero",
    "flag_wt_loss",
    "flag_wt_gain",
    "flag_wt_zero",
    "flag_ga_fullterm",
)

# Distinct flags actually computed (excludes the synthetic flag_mort).
ALL_FLAGS: tuple[str, ...] = (
    "flag_visits",
    "flag_mort_low",
    "flag_mort_high",
    "flag_enroll",
    "flag_danger_high",
    "flag_danger_zero",
    "flag_wt_loss",
    "flag_wt_gain",
    "flag_wt_zero",
    "flag_round_weight",
    "flag_hr_copycat",
    "flag_temp_copycat",
    "flag_spo2_implausible",
    "flag_ga_fullterm",
    "flag_gps_same_case_far",
    "flag_ds_no_referral",
)

FLAG_LABELS: dict[str, str] = {
    "flag_visits": "Visits/Case",
    "flag_mort": "Mortality",
    "flag_mort_low": "Low Mortality",
    "flag_mort_high": "High Mortality",
    "flag_enroll": "Late Enrollment",
    "flag_danger_high": "Danger Signs",
    "flag_danger_zero": "No Danger Signs",
    "flag_wt_loss": "Weight Loss",
    "flag_wt_gain": "Weight Gain",
    "flag_wt_zero": "Weight Stagnant",
    "flag_round_weight": "Rounded Weights",
    "flag_hr_copycat": "HR Copy-Paste",
    "flag_temp_copycat": "Temp Copy-Paste",
    "flag_spo2_implausible": "SpO2 Implausible",
    "flag_ga_fullterm": "Gestational Age",
    "flag_gps_same_case_far": "GPS Spread",
    "flag_ds_no_referral": "No Referral",
}

# Detailed descriptions for info tooltips. Each value is a short sentence
# explaining what the flag measures and its threshold.
FLAG_DESCRIPTIONS: dict[str, str] = {
    "flag_visits": "Avg follow-up visits per closed non-mortality case < 3.0 (min 10 cases, uses 50 most recent).",
    "flag_mort": "Mortality rate < 2% (implausible) or > 20% (quality concern). Min 20 cases.",
    "flag_mort_low": "Mortality rate < 2% — biologically implausible. Min 20 cases.",
    "flag_mort_high": "Mortality rate > 20% — quality concern. Min 20 cases.",
    "flag_enroll": "> 35% of cases enrolled 8+ days after hospital discharge. Min 10 cases with dates.",
    "flag_danger_high": "> 30% of follow-up visits show danger signs. Min 20 visits.",
    "flag_danger_zero": "Exactly 0% danger signs across 30+ visits — implausible.",
    "flag_wt_loss": "> 15% of successive weight pairs show weight loss. Min 10 pairs.",
    "flag_wt_gain": "Avg daily weight gain per baby > 60 g/day — indicates fabrication. "
    "Per-baby averaging, no minimum.",
    "flag_wt_zero": "> 30% of successive weight pairs show no change. Min 10 pairs.",
    "flag_round_weight": ">= 80% of weights are exact multiples of 100g. Min 20 weights.",
    "flag_hr_copycat": "> 75% of heart rate readings are the same value. Min 20 visits.",
    "flag_temp_copycat": "> 75% of temperature readings are the same value. Min 20 visits.",
    "flag_spo2_implausible": "> 10% of SpO2 readings outside 70–100% range. Min 20 visits.",
    "flag_ga_fullterm": "> 30% of registrations with gestational age >= 37 weeks. Min 10.",
    "flag_gps_same_case_far": "> 30% of same-case GPS pairs > 1km apart. Min 20 visits.",
    "flag_ds_no_referral": "0% referral rate for danger-sign-positive visits. Min 5 DS+ visits.",
}

# Mapping from flag key to the metric value to display in the cell,
# the Python format string, and the threshold display text.
FLAG_METRIC_KEY: dict[str, str] = {
    "flag_visits": "avg_visits",
    "flag_mort": "mort_rate",
    "flag_enroll": "pct_late_enroll",
    "flag_danger_high": "danger_rate",
    "flag_danger_zero": "danger_rate",
    "flag_wt_loss": "pct_wt_loss",
    "flag_wt_gain": "mean_daily_gain",
    "flag_wt_zero": "pct_wt_zero",
    "flag_round_weight": "round_weight_pct",
    "flag_hr_copycat": "hr_copycat_pct",
    "flag_temp_copycat": "temp_copycat_pct",
    "flag_spo2_implausible": "spo2_implausible_pct",
    "flag_ga_fullterm": "ga_fullterm_pct",
    "flag_gps_same_case_far": "gps_same_case_far_pct",
    "flag_ds_no_referral": "ds_no_referral_pct",
}

FLAG_THRESHOLD_DISPLAY: dict[str, str] = {
    "flag_visits": "< 3.0",
    "flag_mort": "< 2% or > 20%",
    "flag_mort_low": "< 2%",
    "flag_mort_high": "> 20%",
    "flag_enroll": "> 35%",
    "flag_danger_high": "> 30%",
    "flag_danger_zero": "= 0%",
    "flag_wt_loss": "> 15%",
    "flag_wt_gain": "> 60 g/d",
    "flag_wt_zero": "> 30%",
    "flag_round_weight": ">= 80%",
    "flag_hr_copycat": "> 75%",
    "flag_temp_copycat": "> 75%",
    "flag_spo2_implausible": "> 10%",
    "flag_ga_fullterm": "> 30%",
    "flag_gps_same_case_far": "> 30%",
    "flag_ds_no_referral": "= 0%",
}

# Closed-case kmc_status values used by ``compute_case_metrics``.
_CLOSED_STATUSES: frozenset[str] = frozenset({"discharged", "lost_to_followup", "deceased"})
_DECEASED_STATUS: str = "deceased"

# Valid weight range (grams) used to filter out fat-finger entries
# in weight-pair analysis. Mirrors kmc_flw_flags.py:315.
_WEIGHT_MIN_G: int = 500
_WEIGHT_MAX_G: int = 5000

# CommCare KMC forms store weight in kg. The JS template applies
# ``kg_to_g`` (×1000) during pipeline extraction; our SQL backend
# does not recognise our Python callables, so we convert at read time.
_KG_TO_G: int = 1000

# Days between successive weight visits to be eligible for pair analysis.
_PAIR_MIN_DAYS: int = 1
_PAIR_MAX_DAYS: int = 30

# Days post-discharge after which an enrollment counts as "late".
_LATE_ENROLL_DAYS: int = 8

# SpO2 valid range — values outside this are "implausible".
_SPO2_MIN: int = 70
_SPO2_MAX: int = 100

# Gestational age (weeks) at/above which a baby is considered full-term.
_GA_FULLTERM_WEEKS: int = 37


# =============================================================================
# Result type
# =============================================================================


@dataclass
class FLWFlagResult:
    """Per-FLW flag computation output for one opportunity."""

    username: str
    total_cases: int = 0
    total_cases_from_visits: int = 0  # Distinct case IDs seen in visit rows
    total_visits: int = 0  # Total follow-up visits from aggregated pipeline
    deaths: int = 0
    closed_cases: int = 0
    non_mort_closed: int = 0
    avg_visits: float | None = None
    mort_rate: float | None = None
    danger_rate: float | None = None
    pct_late_enroll: float | None = None
    cases_with_dates: int = 0
    pct_wt_loss: float | None = None
    mean_daily_gain: float | None = None
    pct_wt_zero: float | None = None
    weight_pairs: int = 0
    # Secondary flag metric values (for numeric display in cells)
    round_weight_pct: float | None = None
    hr_copycat_pct: float | None = None
    temp_copycat_pct: float | None = None
    spo2_implausible_pct: float | None = None
    ga_fullterm_pct: float | None = None
    gps_same_case_far_pct: float | None = None
    ds_no_referral_pct: float | None = None
    excluded: bool = False
    flags: dict[str, bool | None] = field(default_factory=dict)

    @property
    def flag_count(self) -> int:
        """Number of distinct flags currently fired (excludes synthetics)."""
        return sum(1 for k in ALL_FLAGS if self.flags.get(k))

    @property
    def priority_flag_count(self) -> int:
        """Number of priority-tier flags fired (includes synthetic flag_mort)."""
        return sum(1 for k in PRIORITY_FLAGS if self.flags.get(k))


# =============================================================================
# Date helpers — accept ISO strings or date/datetime objects
# =============================================================================


def _parse_date(value: Any) -> date | None:
    """Coerce a value to a ``date``. Returns None for falsy / unparseable input."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return None
    return None


def _safe_float(value: Any) -> float | None:
    """Best-effort numeric coercion; returns None on failure."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    """Coerce to int with 0 fallback (matches JS ``parseInt(x) || 0``)."""
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    """Read a field off either a dataclass row (FLWRow / VisitRow) or a plain dict."""
    if hasattr(row, key):
        val = getattr(row, key)
        if val is not None:
            return val
    if hasattr(row, "custom_fields") and isinstance(row.custom_fields, dict):
        if key in row.custom_fields:
            return row.custom_fields[key]
    if hasattr(row, "computed") and isinstance(row.computed, dict):
        if key in row.computed:
            return row.computed[key]
    if isinstance(row, dict):
        return row.get(key, default)
    return default


def _read_weight_g(row: Any) -> float | None:
    """Read weight from a visit row, normalised to grams.

    Unit detection: production CommCare KMC V2 forms store weight in
    *grams* (e.g. ``1345`` = 1.345 kg). Earlier prototypes / kg-input
    test fixtures store weight in *kilograms* (e.g. ``1.5`` = 1500 g).
    Both are common in our codebase, so we auto-detect by magnitude:

      * 0 <  w  < 50         → kilograms; multiply by 1000.
      * 100 <= w <= 10000    → grams; use as-is.
      * Anything else        → reject (implausible for a neonate).

    Returns None on missing / out-of-range / non-numeric input.

    Historical note: the JS template at ``workflow/templates/kmc_flw_flags.py``
    assumes kg-only input and unconditionally multiplies by 1000. That
    bug masked all four weight-based flags (wt_loss / wt_gain / wt_zero
    / round_weight) because real production weights came in as grams
    (e.g. 1345 → 1,345,000g → rejected as out-of-range).
    """
    w = _safe_float(_row_get(row, "weight"))
    if w is None or w <= 0:
        return None
    # Kilograms: typical premature infant 0.5 - 5 kg.
    if w < 50:
        return w * _KG_TO_G
    # Grams: typical premature infant 500 - 5000 g.
    if 100 <= w <= 10000:
        return w
    # Implausible (a baby weighing 80 of *something*, or > 10kg) → drop.
    return None


# =============================================================================
# Visit-level metric computations
# Direct ports of kmc_flw_flags.py:284-403 (JS).
# =============================================================================


def compute_weight_metrics(visit_rows: list[Any]) -> dict[str, Any]:
    """Pair successive weight readings per child and produce loss/gain/zero rates.

    Weight gain uses **per-baby averaging**: each baby's gain pairs are
    averaged independently, then the baby-level averages are averaged
    across the FLW. This gives equal weight to each baby regardless of
    how many visit pairs they have.
    """
    by_child: dict[str, list[Any]] = {}
    for row in visit_rows:
        cid = _row_get(row, "beneficiary_case_id")
        if not cid:
            continue
        by_child.setdefault(str(cid), []).append(row)

    total_pairs = 0
    loss_pairs = 0
    zero_pairs = 0
    gain_pair_count = 0
    baby_avg_gains: list[float] = []  # one entry per baby that has gain pairs

    for visits in by_child.values():
        eligible = [
            v for v in visits if _read_weight_g(v) is not None and _parse_date(_row_get(v, "visit_date")) is not None
        ]
        eligible.sort(key=lambda v: _parse_date(_row_get(v, "visit_date")))

        child_gains: list[float] = []  # daily gains for this baby

        for i in range(1, len(eligible)):
            prev_w = _read_weight_g(eligible[i - 1])
            curr_w = _read_weight_g(eligible[i])
            if prev_w is None or curr_w is None:
                continue
            if not (_WEIGHT_MIN_G <= prev_w <= _WEIGHT_MAX_G):
                continue
            if not (_WEIGHT_MIN_G <= curr_w <= _WEIGHT_MAX_G):
                continue

            d1 = _parse_date(_row_get(eligible[i - 1], "visit_date"))
            d2 = _parse_date(_row_get(eligible[i], "visit_date"))
            days_between = (d2 - d1).days
            if days_between < _PAIR_MIN_DAYS or days_between > _PAIR_MAX_DAYS:
                continue

            total_pairs += 1
            diff = curr_w - prev_w
            if diff < 0:
                loss_pairs += 1
            if abs(diff) < 0.001:
                zero_pairs += 1
            if diff > 0 and days_between > 0:
                child_gains.append(diff / days_between)
                gain_pair_count += 1

        # Per-baby average: this baby contributes one value.
        if child_gains:
            baby_avg_gains.append(sum(child_gains) / len(child_gains))

    return {
        "pct_wt_loss": (loss_pairs / total_pairs) if total_pairs > 0 else None,
        "mean_daily_gain": (sum(baby_avg_gains) / len(baby_avg_gains)) if baby_avg_gains else None,
        "pct_wt_zero": (zero_pairs / total_pairs) if total_pairs > 0 else None,
        "weight_pairs": total_pairs,
        "gain_pairs": gain_pair_count,
    }


def compute_enrollment_metrics(visit_rows: list[Any]) -> dict[str, Any]:
    """Per-case late-enrollment rate based on (reg_date - discharge_date).

    Mirrors ``computeEnrollmentMetrics`` at kmc_flw_flags.py:339-369.
    """
    by_case: dict[str, dict[str, date | None]] = {}
    for row in visit_rows:
        cid = _row_get(row, "beneficiary_case_id")
        if not cid:
            continue
        cid = str(cid)
        slot = by_case.setdefault(cid, {"reg_date": None, "discharge_date": None})
        rd = _parse_date(_row_get(row, "reg_date"))
        dd = _parse_date(_row_get(row, "discharge_date"))
        if rd and slot["reg_date"] is None:
            slot["reg_date"] = rd
        if dd and slot["discharge_date"] is None:
            slot["discharge_date"] = dd

    cases_with_dates = 0
    late_cases = 0
    for slot in by_case.values():
        rd = slot["reg_date"]
        dd = slot["discharge_date"]
        if rd and dd:
            cases_with_dates += 1
            # Doc text: "8 or more days" / "8+ days" → inclusive >= 8.
            # JS template uses strict > 8; we deviate intentionally to match
            # the doc literally (a case at exactly 8 days post-discharge
            # is "late").
            if (rd - dd).days >= _LATE_ENROLL_DAYS:
                late_cases += 1

    return {
        "pct_late_enroll": ((late_cases / cases_with_dates) if cases_with_dates >= MIN_CASES["enroll"] else None),
        "cases_with_dates": cases_with_dates,
    }


def compute_case_metrics(visit_rows: list[Any]) -> dict[str, Any]:
    """Per-case metadata used by mortality and avg-visits calculations.

    Walks visit rows once and produces, for each case_id:
        - latest_visit_date: max(visit_date) seen on the case
        - latest_status:     kmc_status from that latest-dated visit
        - latest_child_alive: child_alive from that latest-dated visit
        - visit_count:       number of visit rows we saw for this case

    The doc (Overview of KMC flags, March 2026) is explicit that mortality
    is defined by the LATEST visit's child_alive value, not by any
    historical "no" record — so we track it at the visit-row granularity
    here and let derive_flags() use that as the authoritative signal.

    The doc also says flag_visits should use only the 50 most recently
    closed cases (by last visit date). compute_avg_visits_top_50() below
    uses this output to do that.
    """
    by_case: dict[str, dict[str, Any]] = {}
    for row in visit_rows:
        cid = _row_get(row, "beneficiary_case_id")
        if not cid:
            continue
        cid = str(cid)
        slot = by_case.setdefault(
            cid,
            {
                "case_id": cid,
                "latest_visit_date": None,
                "latest_status": None,
                "latest_child_alive": None,
                "visit_count": 0,
            },
        )
        # Only count follow-up visits (where visit_number is populated)
        # — registration-only forms should not inflate the visit count.
        # The doc says "average follow-up visits per closed case".
        if _row_get(row, "visit_number") is not None:
            slot["visit_count"] += 1
        vdate = _parse_date(_row_get(row, "visit_date"))
        if vdate is None:
            continue
        if slot["latest_visit_date"] is None or vdate > slot["latest_visit_date"]:
            slot["latest_visit_date"] = vdate
            status = _row_get(row, "kmc_status")
            if status:
                slot["latest_status"] = str(status).strip().lower() or None
            ca = _row_get(row, "child_alive")
            if ca is not None:
                slot["latest_child_alive"] = str(ca).strip().lower() or None

    cases = list(by_case.values())

    # A case is "closed" if the latest-visit kmc_status is one of the
    # closure statuses, OR the latest visit reports child_alive='no'
    # (which the doc treats as a closing event regardless of status).
    def _is_closed(c: dict) -> bool:
        return c["latest_status"] in _CLOSED_STATUSES or c["latest_child_alive"] == "no"

    def _is_mortality(c: dict) -> bool:
        # Doc rule: mortality iff most recent visit records child_alive='no'.
        # Falls back to status='deceased' for cases where child_alive isn't
        # populated (older opportunities or registration-only cases).
        if c["latest_child_alive"] == "no":
            return True
        if c["latest_child_alive"] == "yes":
            return False
        return c["latest_status"] == _DECEASED_STATUS

    closed = [c for c in cases if _is_closed(c)]
    closed_cases = len(closed)
    non_mort_closed = sum(1 for c in closed if not _is_mortality(c))
    deaths = sum(1 for c in cases if _is_mortality(c))

    return {
        "cases": cases,
        "closed_cases": closed_cases,
        "non_mort_closed": non_mort_closed,
        "deaths": deaths,
        "is_closed": _is_closed,
        "is_mortality": _is_mortality,
    }


def compute_avg_visits(case_metrics: dict[str, Any]) -> tuple[float | None, int]:
    """Avg follow-up visits per closed non-mortality case.

    Per April canonical doc Table 0 row 1: "Avg follow-up visits per closed
    case < 3.0", min "10 closed non-mortality cases" — no cap on how many
    closed cases are considered.

    Returns (avg_or_None, non_mort_closed_count). avg is None if fewer than
    MIN_CASES["visits"] non-mortality closed cases exist.

    Note: an earlier version of this function applied a "50 most recent
    cases" cap from the March narrative ("reflect current behavior rather
    than historical patterns"). The April canonical table does not retain
    that cap, so we now use all non-mortality closed cases the FLW has.
    """
    cases = case_metrics["cases"]
    is_closed = case_metrics["is_closed"]
    is_mortality = case_metrics["is_mortality"]

    non_mort_closed = [c for c in cases if is_closed(c) and not is_mortality(c)]

    if len(non_mort_closed) < MIN_CASES["visits"]:
        return None, len(non_mort_closed)

    total_visits = sum(c["visit_count"] for c in non_mort_closed)
    return total_visits / len(non_mort_closed), len(non_mort_closed)


# Backwards-compatible alias for any external callers still using the old name.
compute_avg_visits_top_50 = compute_avg_visits


# =============================================================================
# Secondary flag computations
# round_weight, hr_copycat, temp_copycat, spo2_implausible are all wired.
# ga_fullterm still needs form-path discovery via MCP.
# =============================================================================


def compute_round_weight_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of valid follow-up weight readings that are exact multiples of 100g.

    Per April canonical doc Table 0 row 13: "≥ 80% of *follow-up weights*
    recorded as exact multiples of 100g". Registration birth weights are
    excluded so that an FLW's calculation isn't biased by birth weights
    (which are often estimated as round hundreds at the hospital). A row
    is a follow-up if its ``visit_number`` field is populated.

    Returns (pct_or_None, valid_weight_count). If valid_weight_count is below
    MIN_CASES["round_weight"], pct is None to signal insufficient data.
    """
    valid_weights: list[float] = []
    for row in visit_rows:
        # Follow-up filter: visit_number is populated only for follow-up
        # forms; registration forms leave it null.
        if _row_get(row, "visit_number") is None:
            continue
        w = _read_weight_g(row)
        if w is None:
            continue
        if not (_WEIGHT_MIN_G <= w <= _WEIGHT_MAX_G):
            continue
        valid_weights.append(w)
    if len(valid_weights) < MIN_CASES["round_weight"]:
        return None, len(valid_weights)
    rounded = sum(1 for w in valid_weights if abs(w - round(w / 100) * 100) < 0.001)
    return rounded / len(valid_weights), len(valid_weights)


def compute_hr_copycat_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of follow-up visits sharing the single most-frequent HR value.

    Wired via dual V1/V2 paths in pipeline_config:
    ``form.danger_signs_checklist.child_heart_rate`` and
    ``form.child_details.Danger_Signs_Checklist.child_heart_rate``.
    """
    hrs = [_safe_float(_row_get(r, "heart_rate")) for r in visit_rows]
    hrs = [h for h in hrs if h is not None]
    if len(hrs) < MIN_CASES["hr_copycat"]:
        return None, len(hrs)
    counts: dict[float, int] = {}
    for h in hrs:
        counts[h] = counts.get(h, 0) + 1
    top = max(counts.values())
    return top / len(hrs), len(hrs)


def compute_temp_copycat_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of follow-up visits sharing the single most-frequent temperature.

    Wired via ``form.danger_signs_checklist.svn_temperature`` in pipeline_config.
    """
    temps = [_safe_float(_row_get(r, "temperature")) for r in visit_rows]
    temps = [t for t in temps if t is not None]
    if len(temps) < MIN_CASES["temp_copycat"]:
        return None, len(temps)
    counts: dict[float, int] = {}
    for t in temps:
        counts[t] = counts.get(t, 0) + 1
    top = max(counts.values())
    return top / len(temps), len(temps)


def compute_spo2_implausible_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of SpO2 readings outside the 70-100% physiological range.

    Wired via dual V1/V2 paths in pipeline_config:
    ``form.danger_signs_checklist.spo2_level`` and
    ``form.child_details.Danger_Signs_Checklist.spo2_level``.
    """
    vals = [_safe_float(_row_get(r, "spo2_level")) for r in visit_rows]
    vals = [v for v in vals if v is not None]
    if len(vals) < MIN_CASES["spo2_implausible"]:
        return None, len(vals)
    bad = sum(1 for v in vals if v < _SPO2_MIN or v > _SPO2_MAX)
    return bad / len(vals), len(vals)


def compute_ga_fullterm_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of registrations with gestational_age_lmp >= 37 weeks.

    NOT-YET-WIRED: needs ``gestational_age_lmp`` and registration-visit filter.
    """
    ga_values: list[float] = []
    for row in visit_rows:
        # Only registration visits carry gestational age; falsy means not a reg visit.
        ga = _safe_float(_row_get(row, "gestational_age_lmp"))
        if ga is not None:
            ga_values.append(ga)
    if len(ga_values) < MIN_CASES["ga_fullterm"]:
        return None, len(ga_values)
    fullterm = sum(1 for g in ga_values if g >= _GA_FULLTERM_WEEKS)
    return fullterm / len(ga_values), len(ga_values)


def _parse_gps(raw: Any) -> tuple[float, float] | None:
    """Parse a GPS string "lat lon [alt] [accuracy]" into (lat, lon) or None."""
    if not raw or not isinstance(raw, str):
        return None
    parts = raw.strip().split()
    if len(parts) < 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except (ValueError, TypeError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if lat == 0.0 and lon == 0.0:
        return None  # Null island — device default, not a real reading
    return lat, lon


_EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_gps_same_case_far_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of same-case consecutive GPS pairs > 1 km apart.

    Groups visits by ``beneficiary_case_id``, then for each case computes
    consecutive GPS pairs and checks if distance exceeds 1 km.  Returns
    (fraction_far, total_pairs).  Returns (None, n) when fewer than
    MIN_CASES["gps_same_case_far"] pairs are available.
    """
    # Group (lat, lon) by case, preserving visit order.
    cases: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in visit_rows:
        case_id = _row_get(row, "beneficiary_case_id")
        if not case_id:
            continue
        coords = _parse_gps(_row_get(row, "gps"))
        if coords is None:
            continue
        cases[str(case_id)].append(coords)

    # Build consecutive pairs across all cases.
    total_pairs = 0
    far_pairs = 0
    for points in cases.values():
        if len(points) < 2:
            continue
        for i in range(len(points) - 1):
            total_pairs += 1
            dist = _haversine_km(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
            if dist > 1.0:
                far_pairs += 1

    if total_pairs < MIN_CASES["gps_same_case_far"]:
        return None, total_pairs
    return far_pairs / total_pairs, total_pairs


def compute_ds_no_referral_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of danger-sign-positive visits that did NOT result in a referral.

    Wired via ``form.case.update.child_referred`` in pipeline_config.
    """
    ds_positive: list[bool] = []
    for row in visit_rows:
        ds = _row_get(row, "danger_sign_positive")
        if ds in ("yes", True, 1, "1"):
            referred = _row_get(row, "child_referred")
            ds_positive.append(referred in ("yes", True, 1, "1"))
    if len(ds_positive) < MIN_CASES["ds_no_referral"]:
        return None, len(ds_positive)
    referred_rate = sum(1 for r in ds_positive if r) / len(ds_positive)
    # Flag fires when referral rate is exactly 0
    return referred_rate, len(ds_positive)


def compute_danger_metrics(visit_rows: list[Any]) -> dict[str, Any]:
    """Visit-level danger sign counts.

    The aggregated SQL pipeline has a known bug: ``danger_visit_count``
    counts non-null values across BOTH primary and fallback paths, but
    ``danger_positive_count``'s ``filter_path=primary, filter_value='yes'``
    only matches the PRIMARY path. V1 forms that store ``danger_sign_positive``
    at the fallback path ``form.child_details.Danger_Signs_Checklist.danger_sign_positive``
    contribute to the denominator but not the numerator, depressing the
    danger rate by up to ~50% for FLWs with substantial V1 history.

    This function recomputes the counts from visit-level rows, where the
    ``danger_sign_positive`` field is resolved by the ``aggregation="first"``
    rule (first non-null across both paths) — so V1 fallback values are
    captured correctly in both numerator and denominator.

    Returns a dict with the same shape ``derive_flags`` expects from the
    aggregated row, so the call site can substitute it transparently.

    If ``visit_rows`` contains no danger-sign data at all (e.g. unit-test
    fixtures that pass aggregated counts directly), returns counts of 0
    and the caller falls back to the aggregated values.
    """
    visits_with_field = 0
    positive_visits = 0
    for row in visit_rows:
        ds = _row_get(row, "danger_sign_positive")
        if ds in ("yes", True, 1, "1"):
            visits_with_field += 1
            positive_visits += 1
        elif ds in ("no", False, 0, "0"):
            visits_with_field += 1
    return {
        "danger_visit_count": visits_with_field,
        "danger_positive_count": positive_visits,
    }


# =============================================================================
# Top-level: derive_flags
# =============================================================================


def derive_flags(aggregated_row: Any, visit_rows: list[Any]) -> FLWFlagResult:
    """Compute the full 16-flag dict for a single FLW.

    Args:
        aggregated_row: One row from the AGGREGATED pipeline result (FLWRow
            or dict). Provides total_cases, deaths, total_visits,
            danger_visit_count, danger_positive_count.
        visit_rows: All visit-level rows for this same FLW (already filtered
            upstream by username).

    Returns:
        FLWFlagResult with metrics + 16-flag dict + the synthetic
        priority-tier flag_mort.
    """
    username = str(_row_get(aggregated_row, "username") or "")
    total_cases = _safe_int(_row_get(aggregated_row, "total_cases"))
    total_visits = _safe_int(_row_get(aggregated_row, "kmc_visit_count"))

    # Danger sign counts — prefer visit-level over aggregated. The aggregated
    # ``danger_positive_count`` filter is bound to the primary path only, so
    # V1 fallback-path positives are silently undercounted (see
    # ``compute_danger_metrics`` docstring). Visit-level rows resolve the
    # field across both paths via the visit pipeline's ``aggregation="first"``,
    # so recounting from them is accurate. If ``visit_rows`` carries no
    # danger field at all (e.g. unit-test fixtures that only pass aggregated
    # counts), fall back to the aggregated values to preserve test contracts.
    danger_v = compute_danger_metrics(visit_rows)
    if danger_v["danger_visit_count"] > 0:
        danger_visit_count = danger_v["danger_visit_count"]
        danger_positive_count = danger_v["danger_positive_count"]
    else:
        danger_visit_count = _safe_int(_row_get(aggregated_row, "danger_visit_count"))
        danger_positive_count = _safe_int(_row_get(aggregated_row, "danger_positive_count"))

    # Visit-derived metrics
    weight_metrics = compute_weight_metrics(visit_rows)
    enrollment_metrics = compute_enrollment_metrics(visit_rows)
    case_metrics = compute_case_metrics(visit_rows)

    closed_cases = case_metrics["closed_cases"]
    non_mort_closed = case_metrics["non_mort_closed"]
    deaths = case_metrics["deaths"]
    # April canonical: avg follow-up visits across ALL closed non-mortality
    # cases (no recent-N cap; the March narrative's "50 most recent" rule
    # was dropped in the April table).
    avg_visits, _non_mort_count = compute_avg_visits(case_metrics)
    # Mortality rate denominator is closed_cases, per the doc data
    # tables (e.g. FLW 2328: 35 deaths / 108 closed = 32.4%).
    mort_rate = (deaths / closed_cases) if closed_cases > 0 else None
    danger_rate = danger_positive_count / danger_visit_count if danger_visit_count > 0 else None

    # Secondary flag inputs
    round_pct, _round_n = compute_round_weight_pct(visit_rows)
    hr_pct, _hr_n = compute_hr_copycat_pct(visit_rows)
    temp_pct, _temp_n = compute_temp_copycat_pct(visit_rows)
    spo2_pct, _spo2_n = compute_spo2_implausible_pct(visit_rows)
    ga_pct, _ga_n = compute_ga_fullterm_pct(visit_rows)
    gps_pct, _gps_n = compute_gps_same_case_far_pct(visit_rows)
    referral_pct, _ref_n = compute_ds_no_referral_pct(visit_rows)

    excluded = total_cases < MIN_CASES["exclude"]
    flags: dict[str, bool | None] = {f: None for f in ALL_FLAGS}

    if not excluded:
        # ---- 9 currently in JS ----
        # Each flag returns True (fires), False (passes), or None
        # (insufficient data). The conditional expression ensures that
        # when the minimum-data requirement isn't met the flag is None —
        # not False — so the UI renders "—" with neutral styling instead
        # of an incorrect green "pass" indicator.
        flags["flag_visits"] = (avg_visits < THRESHOLDS["visits"]) if avg_visits is not None else None
        flags["flag_mort_high"] = (
            (mort_rate > THRESHOLDS["mort_high"])
            if closed_cases >= MIN_CASES["mort"] and mort_rate is not None
            else None
        )
        flags["flag_mort_low"] = (
            (mort_rate < THRESHOLDS["mort_low"])
            if closed_cases >= MIN_CASES["mort"] and mort_rate is not None
            else None
        )
        flags["flag_enroll"] = (
            (enrollment_metrics["pct_late_enroll"] > THRESHOLDS["enroll"])
            if enrollment_metrics["cases_with_dates"] >= MIN_CASES["enroll"]
            and enrollment_metrics["pct_late_enroll"] is not None
            else None
        )
        flags["flag_danger_high"] = (
            (danger_rate > THRESHOLDS["danger_high"])
            if danger_visit_count >= MIN_CASES["danger_high"] and danger_rate is not None
            else None
        )
        flags["flag_danger_zero"] = (
            (danger_rate == THRESHOLDS["danger_zero"])
            if danger_visit_count >= MIN_CASES["danger_zero"] and danger_rate is not None
            else None
        )
        flags["flag_wt_loss"] = (
            (weight_metrics["pct_wt_loss"] > THRESHOLDS["wt_loss"])
            if weight_metrics["weight_pairs"] >= MIN_CASES["weight"] and weight_metrics["pct_wt_loss"] is not None
            else None
        )
        # No minimum data gate — evaluates whenever any baby has a gain pair.
        # Uses per-baby averaging (each baby contributes equally).
        flags["flag_wt_gain"] = (
            (weight_metrics["mean_daily_gain"] > THRESHOLDS["wt_gain"])
            if weight_metrics["mean_daily_gain"] is not None
            else None
        )
        flags["flag_wt_zero"] = (
            (weight_metrics["pct_wt_zero"] > THRESHOLDS["wt_zero"])
            if weight_metrics["weight_pairs"] >= MIN_CASES["weight"] and weight_metrics["pct_wt_zero"] is not None
            else None
        )

        # ---- 7 secondary (1 live + 6 not-yet-wired returning None) ----
        flags["flag_round_weight"] = (
            (round_pct is not None and round_pct >= THRESHOLDS["round_weight"]) if round_pct is not None else None
        )

        flags["flag_hr_copycat"] = (
            (hr_pct is not None and hr_pct > THRESHOLDS["hr_copycat"]) if hr_pct is not None else None
        )

        flags["flag_temp_copycat"] = (
            (temp_pct is not None and temp_pct > THRESHOLDS["temp_copycat"]) if temp_pct is not None else None
        )

        flags["flag_spo2_implausible"] = (
            (spo2_pct is not None and spo2_pct > THRESHOLDS["spo2_implausible"]) if spo2_pct is not None else None
        )

        flags["flag_ga_fullterm"] = (
            (ga_pct is not None and ga_pct > THRESHOLDS["ga_fullterm"]) if ga_pct is not None else None
        )

        flags["flag_gps_same_case_far"] = (
            (gps_pct is not None and gps_pct > THRESHOLDS["gps_same_case_far"]) if gps_pct is not None else None
        )

        flags["flag_ds_no_referral"] = (
            (referral_pct is not None and referral_pct == THRESHOLDS["ds_no_referral"])
            if referral_pct is not None
            else None
        )

    # Synthetic priority-tier mort flag: True if either component is True,
    # None if both sub-flags are None (insufficient data).
    mort_low = flags.get("flag_mort_low")
    mort_high = flags.get("flag_mort_high")
    if excluded or (mort_low is None and mort_high is None):
        flags["flag_mort"] = None
    else:
        flags["flag_mort"] = bool(mort_low) or bool(mort_high)

    # Count distinct case IDs from visit rows for mortality denominator cross-check
    visit_case_ids = {
        str(_row_get(r, "beneficiary_case_id")) for r in visit_rows if _row_get(r, "beneficiary_case_id")
    }
    total_cases_from_visits = len(visit_case_ids)

    return FLWFlagResult(
        username=username,
        total_cases=total_cases,
        total_cases_from_visits=total_cases_from_visits,
        total_visits=total_visits,
        deaths=deaths,
        closed_cases=closed_cases,
        non_mort_closed=non_mort_closed,
        avg_visits=avg_visits,
        mort_rate=mort_rate,
        danger_rate=danger_rate,
        pct_late_enroll=enrollment_metrics["pct_late_enroll"],
        cases_with_dates=enrollment_metrics["cases_with_dates"],
        pct_wt_loss=weight_metrics["pct_wt_loss"],
        mean_daily_gain=weight_metrics["mean_daily_gain"],
        pct_wt_zero=weight_metrics["pct_wt_zero"],
        weight_pairs=weight_metrics["weight_pairs"],
        round_weight_pct=round_pct,
        hr_copycat_pct=hr_pct,
        temp_copycat_pct=temp_pct,
        spo2_implausible_pct=spo2_pct,
        ga_fullterm_pct=ga_pct,
        gps_same_case_far_pct=gps_pct,
        ds_no_referral_pct=referral_pct,
        excluded=excluded,
        flags=flags,
    )


def visit_flag_sources(visit_rows: list[Any], flw_result: FLWFlagResult) -> list[dict[str, Any]]:
    """Annotate each visit with which flags it contributed to.

    For aggregate flags (mortality, late enrollment, etc.) we cannot point at
    a single triggering visit — the annotation lives at the FLW level. This
    function only annotates flags that are visit-localized:

    - Weight-pair flags: marks both visits of any anomalous successive pair.
    - Round-weight flag: marks visits whose weight is an exact multiple of 100g.
    - Danger-sign-no-referral: marks DS-positive visits with no referral.
    - HR/Temp copycat: marks visits that share the most-frequent value
      (only when the flag fired AND the value field is present).

    Returns: list of dicts with keys (visit_date, weight, beneficiary_case_id,
    visit_number, kmc_status, flags), one per visit, sorted by visit_date desc.
    """
    rows: list[dict[str, Any]] = []
    flags = flw_result.flags

    # Pre-compute flag-source sets
    pair_flagged_visits: set[int] = set()
    if flags.get("flag_wt_loss") or flags.get("flag_wt_gain") or flags.get("flag_wt_zero"):
        # Recompute pairs to identify which exact visit indices contributed
        by_child: dict[str, list[int]] = {}
        for idx, row in enumerate(visit_rows):
            cid = _row_get(row, "beneficiary_case_id")
            if cid:
                by_child.setdefault(str(cid), []).append(idx)
        for indices in by_child.values():
            sorted_idx = sorted(
                [
                    i
                    for i in indices
                    if _read_weight_g(visit_rows[i]) is not None
                    and _parse_date(_row_get(visit_rows[i], "visit_date")) is not None
                ],
                key=lambda i: _parse_date(_row_get(visit_rows[i], "visit_date")),
            )
            for i in range(1, len(sorted_idx)):
                p, c = sorted_idx[i - 1], sorted_idx[i]
                w1 = _read_weight_g(visit_rows[p])
                w2 = _read_weight_g(visit_rows[c])
                d1 = _parse_date(_row_get(visit_rows[p], "visit_date"))
                d2 = _parse_date(_row_get(visit_rows[c], "visit_date"))
                if w1 is None or w2 is None or d1 is None or d2 is None:
                    continue
                if not (_WEIGHT_MIN_G <= w1 <= _WEIGHT_MAX_G):
                    continue
                if not (_WEIGHT_MIN_G <= w2 <= _WEIGHT_MAX_G):
                    continue
                days = (d2 - d1).days
                if days < _PAIR_MIN_DAYS or days > _PAIR_MAX_DAYS:
                    continue
                # Any pair fitting the eligibility rules contributed to the FLW-level
                # flag — mark both visits.
                pair_flagged_visits.add(p)
                pair_flagged_visits.add(c)

    hr_top_value: float | None = None
    if flags.get("flag_hr_copycat"):
        counts: dict[float, int] = {}
        for r in visit_rows:
            h = _safe_float(_row_get(r, "heart_rate"))
            if h is not None:
                counts[h] = counts.get(h, 0) + 1
        if counts:
            hr_top_value = max(counts, key=counts.get)

    temp_top_value: float | None = None
    if flags.get("flag_temp_copycat"):
        counts = {}
        for r in visit_rows:
            t = _safe_float(_row_get(r, "temperature"))
            if t is not None:
                counts[t] = counts.get(t, 0) + 1
        if counts:
            temp_top_value = max(counts, key=counts.get)

    for idx, row in enumerate(visit_rows):
        sources: list[str] = []

        # Weight-pair flags
        if idx in pair_flagged_visits:
            for k in ("flag_wt_loss", "flag_wt_gain", "flag_wt_zero"):
                if flags.get(k):
                    sources.append(k)

        # Round-weight: any individual visit whose weight is a 100g multiple
        if flags.get("flag_round_weight"):
            w = _read_weight_g(row)
            if w is not None and _WEIGHT_MIN_G <= w <= _WEIGHT_MAX_G:
                if abs(w - round(w / 100) * 100) < 0.001:
                    sources.append("flag_round_weight")

        # HR copycat
        if flags.get("flag_hr_copycat") and hr_top_value is not None:
            h = _safe_float(_row_get(row, "heart_rate"))
            if h is not None and abs(h - hr_top_value) < 0.001:
                sources.append("flag_hr_copycat")

        # Temp copycat
        if flags.get("flag_temp_copycat") and temp_top_value is not None:
            t = _safe_float(_row_get(row, "temperature"))
            if t is not None and abs(t - temp_top_value) < 0.001:
                sources.append("flag_temp_copycat")

        # SpO2 implausible
        if flags.get("flag_spo2_implausible"):
            v = _safe_float(_row_get(row, "spo2_level"))
            if v is not None and (v < _SPO2_MIN or v > _SPO2_MAX):
                sources.append("flag_spo2_implausible")

        # DS without referral
        if flags.get("flag_ds_no_referral"):
            ds = _row_get(row, "danger_sign_positive")
            referred = _row_get(row, "child_referred")
            if ds in ("yes", True, 1, "1") and referred not in ("yes", True, 1, "1"):
                sources.append("flag_ds_no_referral")

        rows.append(
            {
                "visit_date": _row_get(row, "visit_date"),
                "weight": _row_get(row, "weight"),
                "beneficiary_case_id": _row_get(row, "beneficiary_case_id"),
                "visit_number": _row_get(row, "visit_number"),
                "kmc_status": _row_get(row, "kmc_status"),
                "flag_sources": sources,
            }
        )

    rows.sort(key=lambda r: str(r["visit_date"] or ""), reverse=True)
    return rows
