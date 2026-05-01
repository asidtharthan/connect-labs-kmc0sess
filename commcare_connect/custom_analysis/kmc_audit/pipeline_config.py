"""
Pipeline configurations for the KMC Audit Dashboard.

Two configs (mirrors the JS template at ``workflow/templates/kmc_flw_flags.py``
PIPELINE_SCHEMAS):

- ``KMC_AUDIT_FLW_CONFIG``: AGGREGATED — one row per FLW, used by the flag
  table for case counts, mortality, and danger-sign rates.
- ``KMC_AUDIT_VISIT_CONFIG``: VISIT_LEVEL — one row per visit, used by
  weight-pair analysis, late-enrollment computation, and the per-FLW
  drill-down panel.

Both configs use ``linking_field="beneficiary_case_id"`` so twins (same
mother, distinct cases) are not collapsed into a single child timeline.

Form-path strategy
------------------
- Fields needed by the **9 currently-implemented flags** all have known
  form paths copied verbatim from kmc_flw_flags.py PIPELINE_SCHEMAS.
- Fields needed by the **6 secondary flags that aren't yet implemented**
  (heart_rate, temperature, spo2_level, gestational_age_lmp, gps_lat/lon,
  child_referred, visit_type) require MCP ``get_form_json_paths``
  discovery against the live KMC CommCare app to find their exact paths.
  Until those paths are confirmed, those FieldComputation entries are
  intentionally omitted — flag_logic.py's compute functions for those
  flags return None gracefully when the data is absent.
- The 7th secondary flag (``flag_round_weight``) is implementable today
  using the existing ``weight`` field, so it works out of the box.
"""

from __future__ import annotations

from commcare_connect.labs.analysis import (
    AnalysisPipelineConfig,
    CacheStage,
    FieldComputation,
)

# Experiment names — kept distinct from the existing ``kmc_flw_flags``
# workflow template so caches don't collide.
_EXPERIMENT_FLW = "kmc_audit_flw_flags"
_EXPERIMENT_VISIT = "kmc_audit_visit_series"

# Linking field — beneficiary_case_id correctly separates twins; entity_id
# (mother_name+phone) would collapse them.
_LINKING_FIELD = "beneficiary_case_id"


# =============================================================================
# AGGREGATED config — one row per FLW
# Mirrors kmc_flw_flags.py PIPELINE_SCHEMAS[0] ("flw_flags").
# =============================================================================

KMC_AUDIT_FLW_CONFIG = AnalysisPipelineConfig(
    grouping_key="username",
    experiment=_EXPERIMENT_FLW,
    terminal_stage=CacheStage.AGGREGATED,
    linking_field=_LINKING_FIELD,
    fields=[
        FieldComputation(
            name="total_cases",
            paths=["form.kmc_beneficiary_case_id", "form.case.@case_id"],
            aggregation="count_distinct",
            description="Distinct beneficiary case IDs handled by this FLW",
        ),
        FieldComputation(
            name="deaths",
            paths=["form.kmc_beneficiary_case_id", "form.case.@case_id"],
            aggregation="count_distinct",
            filter_path="form.child_alive",
            filter_value="no",
            description="Distinct cases that ended in mortality",
        ),
        FieldComputation(
            name="total_visits",
            path="form.grp_kmc_visit.visit_number",
            aggregation="count",
            description="Total follow-up visits performed",
        ),
        FieldComputation(
            name="danger_visit_count",
            paths=[
                "form.danger_signs_checklist.danger_sign_positive",
                "form.child_details.Danger_Signs_Checklist.danger_sign_positive",
            ],
            aggregation="count",
            description="Visits where the danger-sign checklist was filled out",
        ),
        FieldComputation(
            name="danger_positive_count",
            paths=[
                "form.danger_signs_checklist.danger_sign_positive",
                "form.child_details.Danger_Signs_Checklist.danger_sign_positive",
            ],
            aggregation="count",
            filter_path="form.danger_signs_checklist.danger_sign_positive",
            filter_value="yes",
            description="Visits where any danger sign was positive",
        ),
    ],
    histograms=[],
    filters={},
)


# =============================================================================
# VISIT_LEVEL config — one row per visit
# Mirrors kmc_flw_flags.py PIPELINE_SCHEMAS[1] ("weight_series") and is also
# used for drill-down rendering.
# =============================================================================


def _to_float(x):
    """Coerce a value to float; None on failure (matches JS parseFloat semantics)."""
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _to_int(x):
    """Coerce a value to int; None on failure."""
    if x is None or x == "":
        return None
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


KMC_AUDIT_VISIT_CONFIG = AnalysisPipelineConfig(
    grouping_key="username",
    experiment=_EXPERIMENT_VISIT,
    terminal_stage=CacheStage.VISIT_LEVEL,
    linking_field=_LINKING_FIELD,
    fields=[
        FieldComputation(
            name="beneficiary_case_id",
            paths=["form.kmc_beneficiary_case_id", "form.case.@case_id"],
            aggregation="first",
            description="Case ID — used to group successive visits per child",
        ),
        FieldComputation(
            name="visit_date",
            path="form.grp_kmc_visit.visit_date",
            aggregation="first",
            description="Date of this visit (used for pair-eligibility windows)",
        ),
        FieldComputation(
            name="weight",
            paths=[
                "form.anthropometric.child_weight_visit",
                "form.child_details.birth_weight_reg.child_weight_reg",
            ],
            aggregation="first",
            transform=_to_float,
            description="Weight in grams — used by all weight-related flags",
        ),
        FieldComputation(
            name="visit_number",
            path="form.grp_kmc_visit.visit_number",
            aggregation="first",
            transform=_to_int,
            description="Sequential visit number for this case",
        ),
        FieldComputation(
            name="reg_date",
            paths=["form.reg_date", "form.grp_kmc_beneficiary.reg_date"],
            aggregation="first",
            description="Case registration date — used by flag_enroll",
        ),
        FieldComputation(
            name="discharge_date",
            path="form.hosp_lbl.date_hospital_discharge",
            aggregation="first",
            description="Hospital discharge date — used by flag_enroll",
        ),
        FieldComputation(
            name="kmc_status",
            paths=["form.grp_kmc_beneficiary.kmc_status", "form.kmc_status"],
            aggregation="first",
            description="Latest KMC status (discharged/lost_to_followup/deceased)",
        ),
        # Visit-level danger-sign flag — paired with child_referred below
        # for compute_ds_no_referral_pct.
        FieldComputation(
            name="danger_sign_positive",
            paths=[
                "form.danger_signs_checklist.danger_sign_positive",
                "form.child_details.Danger_Signs_Checklist.danger_sign_positive",
            ],
            aggregation="first",
            description="Was any danger sign positive on this visit (yes/no)",
        ),
        # Referral made on this visit. Path verified against the production
        # KMC Superset dashboard SQL ("KMC - Referral Rate within 28 Days"
        # dataset, line: form.case.update.child_referred). Drives
        # flag_ds_no_referral when paired with danger_sign_positive.
        FieldComputation(
            name="child_referred",
            path="form.case.update.child_referred",
            aggregation="first",
            description="Was the child referred for medical attention on this visit (yes/no)",
        ),
        # ----------------------------------------------------------------
        # Five flags from the doc are NOT IMPLEMENTABLE against current KMC
        # data — the underlying form fields are not collected by the KMC
        # program forms. Verified by:
        #   1) zero references to these field names in the production
        #      Superset KMC dashboard SQL queries
        #   2) zero references in the labs codebase workflow templates
        #
        # The flags concerned are:
        #   flag_hr_copycat        (heart_rate)
        #   flag_temp_copycat      (temperature)
        #   flag_spo2_implausible  (spo2_level)
        #   flag_ga_fullterm       (gestational_age_lmp)
        #   flag_gps_same_case_far (gps_lat / gps_lon / gps_accuracy_m)
        #
        # These flag columns will continue to render as "—" in the dashboard,
        # which the transparency footer documents as "not applicable to
        # current KMC forms". If the KMC program adds vitals capture in a
        # future form revision, add FieldComputations here and the existing
        # flag_logic.py compute functions will start returning real values.
        # ----------------------------------------------------------------
    ],
    histograms=[],
    filters={},
)
