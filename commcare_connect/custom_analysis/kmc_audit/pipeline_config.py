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
- ``temperature`` is wired — path ``form.danger_signs_checklist.svn_temperature``
  confirmed from kmc_longitudinal.py, kmc_project_metrics.py, and timeline_config.py.
- ``child_referred`` is wired — path ``form.case.update.child_referred`` confirmed
  from Superset "KMC - Referral Rate within 28 Days" SQL.
- ``flag_round_weight`` uses the existing ``weight`` field.
- **Weight unit auto-detection.** Production V2 CommCare forms store weight
  in *grams* (e.g. ``1345`` for a 1.345 kg baby). Earlier prototypes
  and kg-input test fixtures store weight in *kg* (e.g. ``1.5``).
  ``flag_logic._read_weight_g`` auto-detects by magnitude — values
  < 50 are interpreted as kg (and multiplied by 1000), values 100-10000
  as grams (used as-is). The kg-only assumption in the JS template
  (``workflow/templates/kmc_flw_flags.py``) was a latent bug that
  masked all four weight-based flags on production data.
- **heart_rate** is wired — dual paths
  ``form.danger_signs_checklist.child_heart_rate`` (V2) and
  ``form.child_details.Danger_Signs_Checklist.child_heart_rate`` (V1).
- **spo2_level** is wired — dual paths
  ``form.danger_signs_checklist.spo2_level`` (V2) and
  ``form.child_details.Danger_Signs_Checklist.spo2_level`` (V1).
- **1 secondary flag** (gestational_age_lmp) still needs form-path discovery
  via ``python manage.py verify_kmc_form_fields``.
  Until confirmed, flag_logic.py returns None gracefully for it.
- **GPS** is now wired — paths confirmed from kmc_longitudinal.py.

Naming-collision note
---------------------
``build_flw_aggregation_query`` in the SQL backend always emits
``COUNT(*) AS total_visits`` as a built-in column.  That counts ALL form
submissions (registration + follow-up).  To get only KMC visit forms
(where ``visit_number`` is populated), we define ``kmc_visit_count``
with a distinct name that avoids the collision.  ``flag_logic.derive_flags``
reads ``kmc_visit_count`` for the "KMC Visits" column and KPI card.
"""

from __future__ import annotations

from commcare_connect.labs.analysis import AnalysisPipelineConfig, CacheStage, FieldComputation

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
        # KMC visit count — only forms where visit_number is populated
        # (excludes registration-only forms). Named "kmc_visit_count" to
        # avoid collision with the built-in "total_visits" (COUNT(*)) that
        # the SQL backend always emits.
        FieldComputation(
            name="kmc_visit_count",
            path="form.grp_kmc_visit.visit_number",
            aggregation="count",
            description="KMC visits where visit_number is populated (matches JS template total_visits)",
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
            description="Weight in kg (form storage unit) — flag_logic converts to grams via _read_weight_g",
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
        # child_alive recorded on each follow-up visit. Per the KMC flags
        # March-2026 doc: "A case is considered a mortality if the most
        # recent visit records child_alive='no'." Pulled at visit level
        # so flag_logic can resolve mortality from the latest visit
        # rather than counting any historical 'no' record.
        FieldComputation(
            name="child_alive",
            path="form.child_alive",
            aggregation="first",
            description="Was the child alive at this visit (yes/no)",
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
        # Temperature — path confirmed from kmc_longitudinal.py, kmc_project_metrics.py,
        # and timeline_config.py. Drives flag_temp_copycat.
        FieldComputation(
            name="temperature",
            path="form.danger_signs_checklist.svn_temperature",
            aggregation="first",
            transform=_to_float,
            description="SVN temperature reading on this visit",
        ),
        # GPS coordinates — paths confirmed from kmc_longitudinal.py and
        # timeline_config.py. Format: "lat lon alt accuracy". Drives
        # flag_gps_same_case_far (same-case GPS pairs > 1km apart).
        FieldComputation(
            name="gps",
            paths=["form.visit_gps_manual", "form.reg_gps", "metadata.location"],
            aggregation="first",
            description="GPS coordinates (lat lon alt accuracy) for distance analysis",
        ),
        # Heart rate — dual V1/V2 paths (same pattern as danger_sign_positive).
        # Drives flag_hr_copycat (> 75% same value).
        FieldComputation(
            name="heart_rate",
            paths=[
                "form.danger_signs_checklist.child_heart_rate",
                "form.child_details.Danger_Signs_Checklist.child_heart_rate",
            ],
            aggregation="first",
            transform=_to_float,
            description="Heart rate reading on this visit",
        ),
        # SpO2 oxygen saturation — dual V1/V2 paths.
        # Drives flag_spo2_implausible (> 10% outside 70-100% range).
        FieldComputation(
            name="spo2_level",
            paths=[
                "form.danger_signs_checklist.spo2_level",
                "form.child_details.Danger_Signs_Checklist.spo2_level",
            ],
            aggregation="first",
            transform=_to_float,
            description="SpO2 oxygen saturation reading on this visit",
        ),
        # ----------------------------------------------------------------
        # One flag still needs form-path discovery via
        # `python manage.py verify_kmc_form_fields`:
        #   flag_ga_fullterm       (gestational_age_lmp)
        #
        # This flag column renders as "—" until its form path is
        # confirmed and a FieldComputation is added here.
        # ----------------------------------------------------------------
    ],
    histograms=[],
    filters={},
)
