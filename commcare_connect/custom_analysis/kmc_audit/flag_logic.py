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
    "visits": 3.0,           # Avg visits/closed-non-mort case below this is concerning
    "mort_low": 0.02,        # < 2% mortality is biologically implausible
    "mort_high": 0.20,       # > 20% mortality is a quality concern
    "enroll": 0.35,          # > 35% of cases enrolled 8+ days post-discharge
    "danger_high": 0.30,     # > 30% follow-up visits with danger signs
    "danger_zero": 0.0,      # Exactly 0 danger signs ever (implausible)
    "wt_loss": 0.15,         # > 15% successive weight pairs show loss
    "wt_gain": 60.0,         # Mean daily gain > 60 g/day (fabrication signal)
    "wt_zero": 0.30,         # > 30% successive pairs show no weight change
    # --- 7 secondary, from "Overview of KMC flags [March 2026].docx" ---
    "round_weight": 0.80,    # >= 80% weights as exact multiples of 100g
    "hr_copycat": 0.75,      # > 75% follow-up visits share single HR value
    "temp_copycat": 0.75,    # > 75% follow-up visits share single temp value
    "spo2_implausible": 0.10,  # > 10% SpO2 readings outside 70-100%
    "ga_fullterm": 0.30,     # > 30% registrations with gestational_age >= 37 weeks
    "gps_same_case_far": 0.30,  # > 30% same-case GPS pairs > 1km apart
    "ds_no_referral": 0.0,   # Exactly 0% referral rate across DS-positive visits
}

MIN_CASES: dict[str, int] = {
    "visits": 10,
    "mort": 20,
    "enroll": 10,
    "danger_high": 20,
    "danger_zero": 30,
    "weight": 10,
    "exclude": 20,           # FLWs with fewer total cases are excluded entirely
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

# Neal's six priority indicators surfaced in the top-tier UI table.
# ``flag_mort`` is synthetic — true if either flag_mort_low or flag_mort_high.
PRIORITY_FLAGS: tuple[str, ...] = (
    "flag_visits",
    "flag_mort",
    "flag_round_weight",
    "flag_enroll",
    "flag_danger_high",
    "flag_hr_copycat",
)

# All other flags shown in the collapsible secondary tier.
SECONDARY_FLAGS: tuple[str, ...] = (
    "flag_mort_low",
    "flag_mort_high",
    "flag_danger_zero",
    "flag_wt_loss",
    "flag_wt_gain",
    "flag_wt_zero",
    "flag_temp_copycat",
    "flag_spo2_implausible",
    "flag_ga_fullterm",
    "flag_gps_same_case_far",
    "flag_ds_no_referral",
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
    "flag_visits": "Low Visits/Case",
    "flag_mort": "Mortality (any)",
    "flag_mort_low": "Low Mortality",
    "flag_mort_high": "High Mortality",
    "flag_enroll": "Late Enrollment",
    "flag_danger_high": "High Danger Signs",
    "flag_danger_zero": "Zero Danger Signs",
    "flag_wt_loss": "High Weight Loss",
    "flag_wt_gain": "High Weight Gain",
    "flag_wt_zero": "Zero Weight Change",
    "flag_round_weight": "Rounded Weights",
    "flag_hr_copycat": "Heart Rate",
    "flag_temp_copycat": "Temperature",
    "flag_spo2_implausible": "SpO2",
    "flag_ga_fullterm": "Gestational Age",
    "flag_gps_same_case_far": "GPS Spread",
    "flag_ds_no_referral": "DS w/o Referral",
}

# Closed-case kmc_status values used by ``compute_case_metrics``.
_CLOSED_STATUSES: frozenset[str] = frozenset({"discharged", "lost_to_followup", "deceased"})
_DECEASED_STATUS: str = "deceased"

# Valid weight range (grams) used to filter out fat-finger entries
# in weight-pair analysis. Mirrors kmc_flw_flags.py:315.
_WEIGHT_MIN_G: int = 500
_WEIGHT_MAX_G: int = 5000

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
    excluded: bool = False
    flags: dict[str, bool | None] = field(default_factory=dict)

    @property
    def flag_count(self) -> int:
        """Number of distinct flags currently fired (excludes synthetic flag_mort)."""
        return sum(1 for k in ALL_FLAGS if self.flags.get(k))

    @property
    def priority_flag_count(self) -> int:
        """Number of priority-tier flags fired (uses synthetic flag_mort)."""
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


# =============================================================================
# Visit-level metric computations
# Direct ports of kmc_flw_flags.py:284-403 (JS).
# =============================================================================


def compute_weight_metrics(visit_rows: list[Any]) -> dict[str, Any]:
    """Pair successive weight readings per child and produce loss/gain/zero rates.

    Mirrors ``computeWeightMetrics`` at kmc_flw_flags.py:284-337.
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
    total_daily_gain = 0.0
    gain_pair_count = 0

    for visits in by_child.values():
        eligible = [
            v for v in visits
            if _safe_float(_row_get(v, "weight")) is not None
            and _parse_date(_row_get(v, "visit_date")) is not None
        ]
        eligible.sort(key=lambda v: _parse_date(_row_get(v, "visit_date")))

        for i in range(1, len(eligible)):
            prev_w = _safe_float(_row_get(eligible[i - 1], "weight"))
            curr_w = _safe_float(_row_get(eligible[i], "weight"))
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
            if days_between > 0:
                total_daily_gain += diff / days_between
                gain_pair_count += 1

    return {
        "pct_wt_loss": (loss_pairs / total_pairs) if total_pairs > 0 else None,
        "mean_daily_gain": (total_daily_gain / gain_pair_count) if gain_pair_count > 0 else None,
        "pct_wt_zero": (zero_pairs / total_pairs) if total_pairs > 0 else None,
        "weight_pairs": total_pairs,
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
            if (rd - dd).days > _LATE_ENROLL_DAYS:
                late_cases += 1

    return {
        "pct_late_enroll": (
            (late_cases / cases_with_dates)
            if cases_with_dates >= MIN_CASES["enroll"]
            else None
        ),
        "cases_with_dates": cases_with_dates,
    }


def compute_case_metrics(visit_rows: list[Any]) -> dict[str, int]:
    """Closed-case and non-mortality-closed counts based on latest kmc_status per case.

    Mirrors ``computeCaseMetrics`` at kmc_flw_flags.py:371-403.
    """
    by_case: dict[str, dict[str, Any]] = {}
    for row in visit_rows:
        cid = _row_get(row, "beneficiary_case_id")
        if not cid:
            continue
        cid = str(cid)
        slot = by_case.setdefault(cid, {"kmc_status": None, "visit_date": None})
        vdate = _parse_date(_row_get(row, "visit_date"))
        status = _row_get(row, "kmc_status")
        if status and (slot["visit_date"] is None or (vdate and vdate > slot["visit_date"])):
            slot["kmc_status"] = status
            slot["visit_date"] = vdate

    closed_cases = 0
    non_mort_closed = 0
    for slot in by_case.values():
        status = slot["kmc_status"]
        if status in _CLOSED_STATUSES:
            closed_cases += 1
            if status != _DECEASED_STATUS:
                non_mort_closed += 1

    return {"closed_cases": closed_cases, "non_mort_closed": non_mort_closed}


# =============================================================================
# Secondary flag computations
# 1 implementable from existing visit data (round_weight); the other 6 require
# new fields that pipeline_config.py will add as form paths are discovered via
# MCP. Until then they return None (renders as empty cell — same as a
# non-triggered flag, no special UI labeling per user direction).
# =============================================================================


def compute_round_weight_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of valid weight readings that are exact multiples of 100g.

    Returns (pct_or_None, valid_weight_count). If valid_weight_count is below
    MIN_CASES["round_weight"], pct is None to signal insufficient data.
    """
    valid_weights: list[float] = []
    for row in visit_rows:
        w = _safe_float(_row_get(row, "weight"))
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

    NOT-YET-WIRED: returns (None, 0) until pipeline_config exposes
    ``heart_rate`` and ``visit_type`` per visit (form path TBD via MCP).
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

    NOT-YET-WIRED: returns (None, 0) until ``temperature`` field is added.
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

    NOT-YET-WIRED: needs ``spo2_level`` field via MCP discovery.
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


def compute_gps_same_case_far_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of same-case GPS pairs > 1km apart.

    NOT-YET-WIRED: needs ``gps_lat``, ``gps_lon``, ``gps_accuracy_m`` per visit.
    Stub returns None until those fields are added.
    """
    # Implementation deferred until form paths are confirmed via MCP.
    return None, 0


def compute_ds_no_referral_pct(visit_rows: list[Any]) -> tuple[float | None, int]:
    """Fraction of danger-sign-positive visits that did NOT result in a referral.

    NOT-YET-WIRED: needs ``child_referred`` field per visit. The
    ``danger_sign_positive`` field already exists in the aggregated pipeline.
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
    deaths = _safe_int(_row_get(aggregated_row, "deaths"))
    total_visits = _safe_int(_row_get(aggregated_row, "total_visits"))
    danger_visit_count = _safe_int(_row_get(aggregated_row, "danger_visit_count"))
    danger_positive_count = _safe_int(_row_get(aggregated_row, "danger_positive_count"))

    # Visit-derived metrics
    weight_metrics = compute_weight_metrics(visit_rows)
    enrollment_metrics = compute_enrollment_metrics(visit_rows)
    case_metrics = compute_case_metrics(visit_rows)

    closed_cases = case_metrics["closed_cases"]
    non_mort_closed = case_metrics["non_mort_closed"]
    avg_visits = (total_visits / non_mort_closed) if non_mort_closed > 0 else None
    mort_rate = (deaths / total_cases) if total_cases > 0 else None
    danger_rate = (
        danger_positive_count / danger_visit_count if danger_visit_count > 0 else None
    )

    # Secondary flag inputs
    round_pct, _round_n = compute_round_weight_pct(visit_rows)
    hr_pct, _hr_n = compute_hr_copycat_pct(visit_rows)
    temp_pct, _temp_n = compute_temp_copycat_pct(visit_rows)
    spo2_pct, _spo2_n = compute_spo2_implausible_pct(visit_rows)
    ga_pct, _ga_n = compute_ga_fullterm_pct(visit_rows)
    gps_pct, _gps_n = compute_gps_same_case_far_pct(visit_rows)
    referral_pct, _ref_n = compute_ds_no_referral_pct(visit_rows)

    excluded = total_cases < MIN_CASES["exclude"]
    flags: dict[str, bool | None] = {f: None if excluded else False for f in ALL_FLAGS}

    if not excluded:
        # ---- 9 currently in JS ----
        flags["flag_visits"] = (
            closed_cases >= MIN_CASES["visits"]
            and avg_visits is not None
            and avg_visits < THRESHOLDS["visits"]
        )
        flags["flag_mort_high"] = (
            total_cases >= MIN_CASES["mort"]
            and mort_rate is not None
            and mort_rate > THRESHOLDS["mort_high"]
        )
        flags["flag_mort_low"] = (
            total_cases >= MIN_CASES["mort"]
            and mort_rate is not None
            and mort_rate < THRESHOLDS["mort_low"]
        )
        flags["flag_enroll"] = (
            enrollment_metrics["cases_with_dates"] >= MIN_CASES["enroll"]
            and enrollment_metrics["pct_late_enroll"] is not None
            and enrollment_metrics["pct_late_enroll"] > THRESHOLDS["enroll"]
        )
        flags["flag_danger_high"] = (
            danger_visit_count >= MIN_CASES["danger_high"]
            and danger_rate is not None
            and danger_rate > THRESHOLDS["danger_high"]
        )
        flags["flag_danger_zero"] = (
            danger_visit_count >= MIN_CASES["danger_zero"]
            and danger_rate is not None
            and danger_rate == THRESHOLDS["danger_zero"]
        )
        flags["flag_wt_loss"] = (
            weight_metrics["weight_pairs"] >= MIN_CASES["weight"]
            and weight_metrics["pct_wt_loss"] is not None
            and weight_metrics["pct_wt_loss"] > THRESHOLDS["wt_loss"]
        )
        flags["flag_wt_gain"] = (
            weight_metrics["weight_pairs"] >= MIN_CASES["weight"]
            and weight_metrics["mean_daily_gain"] is not None
            and weight_metrics["mean_daily_gain"] > THRESHOLDS["wt_gain"]
        )
        flags["flag_wt_zero"] = (
            weight_metrics["weight_pairs"] >= MIN_CASES["weight"]
            and weight_metrics["pct_wt_zero"] is not None
            and weight_metrics["pct_wt_zero"] > THRESHOLDS["wt_zero"]
        )

        # ---- 7 secondary (1 live + 6 not-yet-wired returning None) ----
        flags["flag_round_weight"] = (
            round_pct is not None and round_pct >= THRESHOLDS["round_weight"]
        ) if round_pct is not None else None

        flags["flag_hr_copycat"] = (
            hr_pct is not None and hr_pct > THRESHOLDS["hr_copycat"]
        ) if hr_pct is not None else None

        flags["flag_temp_copycat"] = (
            temp_pct is not None and temp_pct > THRESHOLDS["temp_copycat"]
        ) if temp_pct is not None else None

        flags["flag_spo2_implausible"] = (
            spo2_pct is not None and spo2_pct > THRESHOLDS["spo2_implausible"]
        ) if spo2_pct is not None else None

        flags["flag_ga_fullterm"] = (
            ga_pct is not None and ga_pct > THRESHOLDS["ga_fullterm"]
        ) if ga_pct is not None else None

        flags["flag_gps_same_case_far"] = (
            gps_pct is not None and gps_pct > THRESHOLDS["gps_same_case_far"]
        ) if gps_pct is not None else None

        flags["flag_ds_no_referral"] = (
            referral_pct is not None and referral_pct == THRESHOLDS["ds_no_referral"]
        ) if referral_pct is not None else None

    # Synthetic priority-tier mort flag: True if either component is True.
    flags["flag_mort"] = (
        bool(flags.get("flag_mort_low")) or bool(flags.get("flag_mort_high"))
    ) if not excluded else None

    return FLWFlagResult(
        username=username,
        total_cases=total_cases,
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
                [i for i in indices
                 if _safe_float(_row_get(visit_rows[i], "weight")) is not None
                 and _parse_date(_row_get(visit_rows[i], "visit_date")) is not None],
                key=lambda i: _parse_date(_row_get(visit_rows[i], "visit_date")),
            )
            for i in range(1, len(sorted_idx)):
                p, c = sorted_idx[i - 1], sorted_idx[i]
                w1 = _safe_float(_row_get(visit_rows[p], "weight"))
                w2 = _safe_float(_row_get(visit_rows[c], "weight"))
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
            w = _safe_float(_row_get(row, "weight"))
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

        rows.append({
            "visit_date": _row_get(row, "visit_date"),
            "weight": _row_get(row, "weight"),
            "beneficiary_case_id": _row_get(row, "beneficiary_case_id"),
            "visit_number": _row_get(row, "visit_number"),
            "kmc_status": _row_get(row, "kmc_status"),
            "flag_sources": sources,
        })

    rows.sort(key=lambda r: str(r["visit_date"] or ""), reverse=True)
    return rows
