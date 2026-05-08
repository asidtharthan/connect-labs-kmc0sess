"""
Data access layer for the KMC Audit Dashboard.

Orchestrates multi-opportunity pipeline execution and per-FLW flag
computation. The dashboard loads up to five KMC opportunities at once
(see ``constants.py``) so the LLO filter is meaningful.

Concurrency
-----------
For each opportunity we run two pipeline configs (aggregated FLW counts
+ visit-level series). With five opps that's ten parallel pipeline
invocations, each of which the SQLBackend caches by opportunity_id —
so first cold load is the slow path; subsequent loads are O(seconds).
ThreadPoolExecutor is the established pattern; see
``commcare_connect.custom_analysis.audit_of_audits.data_access``.

There is **no precedent** in this codebase for streaming multi-opp
loads via SSE — that's a refactor we explicitly defer. If cold-load
latency proves problematic in practice we can switch to per-opp SSE
events; for now a synchronous parallel fetch matches audit_of_audits.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from django.http import HttpRequest

from commcare_connect.labs.analysis import AnalysisPipeline, FLWAnalysisResult, VisitAnalysisResult, fetch_flw_names

from .constants import KMC_OPPORTUNITIES, KMC_OPPORTUNITY_IDS, llo_for_opportunity, opportunity_name
from .flag_logic import (
    ALL_FLAGS,
    DATA_QUALITY_FLAGS,
    FLAG_DESCRIPTIONS,
    FLAG_LABELS,
    FLAG_METRIC_KEY,
    FLAG_THRESHOLD_DISPLAY,
    PRIORITY_FLAGS,
    SECONDARY_FLAGS,
    FLWFlagResult,
    derive_flags,
    visit_flag_sources,
)
from .pipeline_config import KMC_AUDIT_FLW_CONFIG, KMC_AUDIT_VISIT_CONFIG

logger = logging.getLogger(__name__)

# Per audit_of_audits: cap concurrent HTTP/pipeline calls to keep server-side
# rate limits happy while still parallelising 10× pipeline runs.
_MAX_CONCURRENT_OPPS: int = 10


@dataclass
class OpportunityResult:
    """Per-opportunity pipeline output and the flags derived from it."""

    opportunity_id: int
    opportunity_name: str
    llo: str | None
    flw_results: list[FLWFlagResult]
    error: str | None = None
    flw_aggregated: FLWAnalysisResult | None = None
    visit_result: VisitAnalysisResult | None = None
    flw_names: dict[str, str] | None = None


@dataclass
class DashboardSummary:
    """Top-level summary across all loaded opportunities."""

    rows: list[dict[str, Any]]
    total_flws: int
    flws_with_priority_flag: int
    flws_with_any_flag: int
    flws_excluded: int
    total_kmc_visits: int
    total_cases_all: int
    opportunities_loaded: list[int]
    opportunities_failed: list[tuple[int, str]]


class KMCAuditDataAccess:
    """Multi-opportunity loader + flag aggregator for the dashboard."""

    def __init__(
        self,
        request: HttpRequest,
        opportunity_ids: list[int] | None = None,
    ):
        """
        Args:
            request: HttpRequest with ``request.session["labs_oauth"]`` set
                (required by AnalysisPipeline). Same request object is reused
                across worker threads; HttpRequest is thread-safe for read.
            opportunity_ids: Subset of KMC opps to load. Defaults to all five
                KMC opportunities defined in ``constants.KMC_OPPORTUNITY_IDS``.
                The dashboard config screen passes this through query string.
        """
        self.request = request
        self.opportunity_ids: list[int] = list(opportunity_ids or KMC_OPPORTUNITY_IDS)
        # Validate — silently drop unknown IDs to avoid leaking non-KMC data.
        unknown = [oid for oid in self.opportunity_ids if oid not in KMC_OPPORTUNITIES]
        if unknown:
            logger.warning("[KMCAudit] Dropping non-KMC opportunity IDs: %s", unknown)
            self.opportunity_ids = [oid for oid in self.opportunity_ids if oid in KMC_OPPORTUNITIES]

    # ------------------------------------------------------------------------
    # Per-opp pipeline executor (thread-safe — each thread gets its own
    # AnalysisPipeline, which gets its own backend instance).
    # ------------------------------------------------------------------------

    def _run_opp(self, opportunity_id: int) -> OpportunityResult:
        """Run both pipelines for one opportunity and derive flags."""
        opp_name = opportunity_name(opportunity_id)
        llo = llo_for_opportunity(opportunity_id)

        try:
            pipeline = AnalysisPipeline(self.request)
            # Synchronous — ignore SSE events. The dashboard view doesn't
            # stream progress to the browser at this layer; if we add
            # progress later it's a single-place change.
            flw_aggregated: FLWAnalysisResult = pipeline.stream_analysis_ignore_events(
                KMC_AUDIT_FLW_CONFIG,
                opportunity_id=opportunity_id,
            )
            visit_result: VisitAnalysisResult = pipeline.stream_analysis_ignore_events(
                KMC_AUDIT_VISIT_CONFIG,
                opportunity_id=opportunity_id,
            )
            # FLW display-name lookup. Stored on the OpportunityResult so
            # build_dashboard() can attach it to each row without a second pass.
            try:
                flw_names = fetch_flw_names(
                    access_token=self.request.session.get("labs_oauth", {}).get("access_token"),
                    opportunity_id=opportunity_id,
                )
            except Exception:
                logger.warning("[KMCAudit] fetch_flw_names failed for opp %d", opportunity_id)
                flw_names = {}
        except Exception as e:
            logger.exception("[KMCAudit] opp %d pipeline failed", opportunity_id)
            return OpportunityResult(
                opportunity_id=opportunity_id,
                opportunity_name=opp_name,
                llo=llo,
                flw_results=[],
                error=str(e),
            )

        # Group visit rows by FLW once, then per-FLW flag derivation is local.
        visits_by_flw: dict[str, list[Any]] = {}
        for row in visit_result.rows:
            uname = getattr(row, "username", None) or ""
            if uname:
                visits_by_flw.setdefault(uname, []).append(row)

        flw_results: list[FLWFlagResult] = []
        for flw_row in flw_aggregated.rows:
            uname = flw_row.username
            visit_rows = visits_by_flw.get(uname, [])
            result = derive_flags(flw_row, visit_rows)
            # Cross-check: flag if aggregated total_cases diverges from visit-derived count
            if (
                result.total_cases > 0
                and result.total_cases_from_visits > 0
                and result.total_cases != result.total_cases_from_visits
            ):
                logger.warning(
                    "[KMCAudit] opp %d FLW %s: total_cases mismatch — "
                    "aggregated=%d, visit-derived=%d (mortality denominator may be skewed)",
                    opportunity_id,
                    uname,
                    result.total_cases,
                    result.total_cases_from_visits,
                )
            flw_results.append(result)

        return OpportunityResult(
            opportunity_id=opportunity_id,
            opportunity_name=opp_name,
            llo=llo,
            flw_results=flw_results,
            flw_aggregated=flw_aggregated,
            visit_result=visit_result,
            flw_names=flw_names,
        )

    # ------------------------------------------------------------------------
    # Public: load the full dashboard
    # ------------------------------------------------------------------------

    def build_dashboard(self) -> DashboardSummary:
        """Load all selected opportunities in parallel and merge into one
        flat row list ready for table rendering.

        Rows are merged by ``(llo, username)`` so that V1+V2 of the same
        program (e.g. PIPN: 524 + 874) collapse into a single row per FLW.
        Aggregated counts are summed across opportunities and visit rows
        are concatenated; ``derive_flags`` is then re-run once on the
        merged data so flag thresholds apply to the combined sample. The
        underlying per-opp breakdown is preserved on each row so the
        audit modal can still target a single opportunity.
        """
        if not self.opportunity_ids:
            return DashboardSummary([], 0, 0, 0, 0, 0, 0, [], [])

        results: list[OpportunityResult] = []
        max_workers = min(_MAX_CONCURRENT_OPPS, len(self.opportunity_ids))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_to_opp = {ex.submit(self._run_opp, oid): oid for oid in self.opportunity_ids}
            for future in as_completed(future_to_opp):
                results.append(future.result())

        # Cache per-FLW visits for follow-up drill-down requests within the
        # same Django process. AnalysisPipeline already caches in Postgres,
        # but a request-scoped attribute saves a DB roundtrip.
        self._last_results: dict[int, OpportunityResult] = {r.opportunity_id: r for r in results}

        opportunities_loaded: list[int] = []
        opportunities_failed: list[tuple[int, str]] = []

        # ──────────────────────────────────────────────────────────────────
        # Step 1: collect per-(llo, username) buckets across all opps.
        # Each bucket carries summed aggregate counts + concatenated visits.
        # ──────────────────────────────────────────────────────────────────
        from .flag_logic import derive_flags  # local import to avoid cycles in tests

        buckets: dict[tuple[str, str], dict[str, Any]] = {}

        for opp in sorted(results, key=lambda r: r.opportunity_id):
            if opp.error:
                opportunities_failed.append((opp.opportunity_id, opp.error))
                continue
            if opp.flw_aggregated is None or opp.visit_result is None:
                # Defensive: pipeline returned but with no rows. Skip the merge.
                continue
            opportunities_loaded.append(opp.opportunity_id)

            # Group this opp's visit rows by username once.
            visits_by_flw: dict[str, list[Any]] = {}
            for v in opp.visit_result.rows:
                u = getattr(v, "username", None) or ""
                if u:
                    visits_by_flw.setdefault(u, []).append(v)

            # Names map for this opp (display names take precedence over username).
            names_map: dict[str, str] = dict(opp.flw_names or {})
            for r in opp.flw_aggregated.rows:
                if r.username and r.flw_name and r.username not in names_map:
                    names_map[r.username] = r.flw_name

            for agg_row in opp.flw_aggregated.rows:
                uname = agg_row.username
                if not uname:
                    continue
                key = (opp.llo or "", uname)
                bucket = buckets.setdefault(
                    key,
                    {
                        "username": uname,
                        "llo": opp.llo or "",
                        "flw_name": None,
                        # summed aggregate counts (matches FieldComputation names in pipeline_config)
                        "agg_total_cases": 0,
                        "agg_kmc_visit_count": 0,
                        "agg_danger_visit_count": 0,
                        "agg_danger_positive_count": 0,
                        "visit_rows": [],
                        # per-opp breakdown for audit modal / drill-down routing
                        "opportunity_ids": [],
                        "opportunity_breakdown": [],
                    },
                )
                # Prefer the first non-empty display name we see.
                if not bucket["flw_name"]:
                    bucket["flw_name"] = names_map.get(uname) or getattr(agg_row, "flw_name", None)

                # Sum the four aggregate counts from this opp.
                opp_cases = int(getattr(agg_row, "total_cases", 0) or 0)
                opp_visits = int(getattr(agg_row, "kmc_visit_count", 0) or 0)
                opp_danger_visits = int(getattr(agg_row, "danger_visit_count", 0) or 0)
                opp_danger_pos = int(getattr(agg_row, "danger_positive_count", 0) or 0)
                bucket["agg_total_cases"] += opp_cases
                bucket["agg_kmc_visit_count"] += opp_visits
                bucket["agg_danger_visit_count"] += opp_danger_visits
                bucket["agg_danger_positive_count"] += opp_danger_pos

                # Concatenate this opp's visits for this FLW.
                bucket["visit_rows"].extend(visits_by_flw.get(uname, []))

                bucket["opportunity_ids"].append(opp.opportunity_id)
                bucket["opportunity_breakdown"].append(
                    {
                        "opportunity_id": opp.opportunity_id,
                        "opportunity_name": opp.opportunity_name,
                        "cases": opp_cases,
                        "visits": opp_visits,
                    }
                )

        # ──────────────────────────────────────────────────────────────────
        # Step 2: per bucket, build a synthetic aggregated-row dict and run
        # derive_flags on the combined visit history.
        # ──────────────────────────────────────────────────────────────────
        rows: list[dict[str, Any]] = []
        for bucket in buckets.values():
            agg_dict = {
                "username": bucket["username"],
                "flw_name": bucket["flw_name"],
                "total_cases": bucket["agg_total_cases"],
                "kmc_visit_count": bucket["agg_kmc_visit_count"],
                "danger_visit_count": bucket["agg_danger_visit_count"],
                "danger_positive_count": bucket["agg_danger_positive_count"],
            }
            flw = derive_flags(agg_dict, bucket["visit_rows"])

            # Cross-check: warn if aggregated cases diverge from visit-derived
            # case count (would indicate a stale cache or partial data load).
            if (
                flw.total_cases > 0
                and flw.total_cases_from_visits > 0
                and flw.total_cases != flw.total_cases_from_visits
            ):
                logger.warning(
                    "[KMCAudit] merged llo=%s FLW=%s: total_cases mismatch — " "aggregated=%d, visit-derived=%d",
                    bucket["llo"],
                    bucket["username"],
                    flw.total_cases,
                    flw.total_cases_from_visits,
                )

            metrics = {
                "avg_visits": flw.avg_visits,
                "mort_rate": flw.mort_rate,
                "danger_rate": flw.danger_rate,
                "pct_late_enroll": flw.pct_late_enroll,
                "pct_wt_loss": flw.pct_wt_loss,
                "mean_daily_gain": flw.mean_daily_gain,
                "pct_wt_zero": flw.pct_wt_zero,
                "round_weight_pct": flw.round_weight_pct,
                "hr_copycat_pct": flw.hr_copycat_pct,
                "temp_copycat_pct": flw.temp_copycat_pct,
                "spo2_implausible_pct": flw.spo2_implausible_pct,
                "ga_fullterm_pct": flw.ga_fullterm_pct,
                "gps_same_case_far_pct": flw.gps_same_case_far_pct,
                "ds_no_referral_pct": flw.ds_no_referral_pct,
            }

            # Primary opp_id for audit creation: pick the highest ID, which
            # corresponds to the V2 opportunity (874 > 524, 938 > 523).
            # If only one opp contributed, that's the primary.
            primary_opp_id = max(bucket["opportunity_ids"]) if bucket["opportunity_ids"] else 0
            primary_opp_name = next(
                (
                    b["opportunity_name"]
                    for b in bucket["opportunity_breakdown"]
                    if b["opportunity_id"] == primary_opp_id
                ),
                "",
            )

            rows.append(
                {
                    "username": bucket["username"],
                    "flw_name": bucket["flw_name"] or bucket["username"],
                    # Primary opp drives audit creation + drill-down routing.
                    "opportunity_id": primary_opp_id,
                    "opportunity_name": primary_opp_name,
                    # Full breakdown — used for tooltips ("64+163 cases across V1+V2") and
                    # by the audit modal if we add an opp picker later.
                    "opportunity_ids": bucket["opportunity_ids"],
                    "opportunity_breakdown": bucket["opportunity_breakdown"],
                    "llo": bucket["llo"],
                    "total_cases": flw.total_cases,
                    "total_cases_from_visits": flw.total_cases_from_visits,
                    "total_visits": flw.total_visits,
                    "deaths": flw.deaths,
                    "closed_cases": flw.closed_cases,
                    "non_mort_closed": flw.non_mort_closed,
                    "avg_visits": flw.avg_visits,
                    "mort_rate": flw.mort_rate,
                    "danger_rate": flw.danger_rate,
                    "pct_late_enroll": flw.pct_late_enroll,
                    "pct_wt_loss": flw.pct_wt_loss,
                    "mean_daily_gain": flw.mean_daily_gain,
                    "pct_wt_zero": flw.pct_wt_zero,
                    "weight_pairs": flw.weight_pairs,
                    "excluded": flw.excluded,
                    "flag_count": flw.flag_count,
                    "priority_flag_count": flw.priority_flag_count,
                    "flags": flw.flags,
                    "metrics": metrics,
                }
            )

        # Sort alphabetically by FLW name so the dashboard shows a natural
        # mix of flagged and non-flagged FLWs. The "Show flagged only"
        # checkbox filters to concerning cases when needed.
        rows.sort(key=lambda r: (r.get("flw_name") or r["username"]).lower())

        # Headline counts — rows are now per-(llo, FLW) so dedup by username
        # still gives "distinct people across LLOs" (an FLW is rare across LLOs
        # but possible). Cases / visits sums no longer double-count V1+V2
        # because the merge already collapsed them.
        unique_usernames: set[str] = {r["username"] for r in rows}
        total_flws = len(unique_usernames)
        flws_with_priority_flag = len({r["username"] for r in rows if r["priority_flag_count"] >= 1})
        flws_with_any_flag = len({r["username"] for r in rows if r["flag_count"] >= 1})
        excluded_only_users = {u for u in unique_usernames if all(r["excluded"] for r in rows if r["username"] == u)}
        flws_excluded = len(excluded_only_users)

        total_kmc_visits = sum(r.get("total_visits", 0) for r in rows)
        total_cases_all = sum(r.get("total_cases", 0) for r in rows)

        return DashboardSummary(
            rows=rows,
            total_flws=total_flws,
            flws_with_priority_flag=flws_with_priority_flag,
            flws_with_any_flag=flws_with_any_flag,
            flws_excluded=flws_excluded,
            total_kmc_visits=total_kmc_visits,
            total_cases_all=total_cases_all,
            opportunities_loaded=opportunities_loaded,
            opportunities_failed=opportunities_failed,
        )

    # ------------------------------------------------------------------------
    # Public: per-FLW drill-down
    # ------------------------------------------------------------------------

    def _drill_down_lookup_name(self, opportunity_id: int, username: str) -> str:
        """Best-effort FLW display name for the drill-down header."""
        try:
            names = fetch_flw_names(
                access_token=self.request.session.get("labs_oauth", {}).get("access_token"),
                opportunity_id=opportunity_id,
            )
            return names.get(username) or username
        except Exception:
            return username

    def drill_down(self, opportunity_id: int, username: str) -> dict[str, Any]:
        """Return the per-visit list for one FLW, annotated with flag sources.

        Re-runs the visit pipeline for that opportunity (cheap on cached
        opportunities — pulls from the SQLBackend cache). We do NOT reuse
        ``self._last_results`` because drill-down may be requested from a
        different request than the dashboard load (HTMX partial GET).
        """
        if opportunity_id not in KMC_OPPORTUNITIES:
            return {"error": "Unknown KMC opportunity", "visits": []}

        try:
            pipeline = AnalysisPipeline(self.request)
            flw_aggregated: FLWAnalysisResult = pipeline.stream_analysis_ignore_events(
                KMC_AUDIT_FLW_CONFIG,
                opportunity_id=opportunity_id,
            )
            visit_result: VisitAnalysisResult = pipeline.stream_analysis_ignore_events(
                KMC_AUDIT_VISIT_CONFIG,
                opportunity_id=opportunity_id,
            )
        except Exception as e:
            logger.exception("[KMCAudit] drill-down opp %d / %s failed", opportunity_id, username)
            return {"error": str(e), "visits": []}

        # Find this FLW's aggregated row + filter visits to this username
        flw_row = next((r for r in flw_aggregated.rows if r.username == username), None)
        if flw_row is None:
            return {
                "error": f"FLW '{username}' not found in opportunity {opportunity_id}",  # noqa: E713
                "visits": [],
            }
        visit_rows = [r for r in visit_result.rows if getattr(r, "username", "") == username]

        flw_result = derive_flags(flw_row, visit_rows)
        annotated_visits = visit_flag_sources(visit_rows, flw_result)

        return {
            "username": username,
            "opportunity_id": opportunity_id,
            "opportunity_name": opportunity_name(opportunity_id),
            "llo": llo_for_opportunity(opportunity_id),
            "metrics": {
                "total_cases": flw_result.total_cases,
                "total_cases_from_visits": flw_result.total_cases_from_visits,
                "closed_cases": flw_result.closed_cases,
                "deaths": flw_result.deaths,
                "non_mort_closed": flw_result.non_mort_closed,
                "avg_visits": flw_result.avg_visits,
                "mort_rate": flw_result.mort_rate,
                "danger_rate": flw_result.danger_rate,
                "pct_late_enroll": flw_result.pct_late_enroll,
                "cases_with_dates": flw_result.cases_with_dates,
                "weight_pairs": flw_result.weight_pairs,
                "pct_wt_loss": flw_result.pct_wt_loss,
                "mean_daily_gain": flw_result.mean_daily_gain,
                "pct_wt_zero": flw_result.pct_wt_zero,
                "round_weight_pct": flw_result.round_weight_pct,
                "temp_copycat_pct": flw_result.temp_copycat_pct,
                "ds_no_referral_pct": flw_result.ds_no_referral_pct,
            },
            "flags": flw_result.flags,
            "visits": annotated_visits,
            "flag_labels": FLAG_LABELS,
            "flag_descriptions": FLAG_DESCRIPTIONS,
            "flag_thresholds": FLAG_THRESHOLD_DISPLAY,
            "error": None,
        }

    # ------------------------------------------------------------------------
    # Public: helpers used by views to render filter UI / column headers
    # ------------------------------------------------------------------------

    @staticmethod
    def column_definitions() -> dict[str, list[dict[str, str]]]:
        """Column metadata for the priority and secondary tables."""

        def _col(k: str) -> dict[str, str]:
            return {
                "key": k,
                "label": FLAG_LABELS.get(k, k),
                "description": FLAG_DESCRIPTIONS.get(k, ""),
                "threshold": FLAG_THRESHOLD_DISPLAY.get(k, ""),
                "metric_key": FLAG_METRIC_KEY.get(k, ""),
            }

        return {
            "priority": [_col(k) for k in PRIORITY_FLAGS],
            "secondary": [_col(k) for k in SECONDARY_FLAGS],
            "all": [_col(k) for k in ALL_FLAGS],
            "data_quality_sub_flags": [_col(k) for k in DATA_QUALITY_FLAGS],
        }
