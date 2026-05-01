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

from commcare_connect.labs.analysis import (
    AnalysisPipeline,
    FLWAnalysisResult,
    VisitAnalysisResult,
)

from .constants import (
    KMC_OPPORTUNITIES,
    KMC_OPPORTUNITY_IDS,
    llo_for_opportunity,
    opportunity_name,
)
from .flag_logic import (
    ALL_FLAGS,
    FLAG_LABELS,
    FLWFlagResult,
    PRIORITY_FLAGS,
    SECONDARY_FLAGS,
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


@dataclass
class DashboardSummary:
    """Top-level summary across all loaded opportunities."""

    rows: list[dict[str, Any]]
    total_flws: int
    flws_with_priority_flag: int
    flws_excluded: int
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
                KMC_AUDIT_FLW_CONFIG, opportunity_id=opportunity_id,
            )
            visit_result: VisitAnalysisResult = pipeline.stream_analysis_ignore_events(
                KMC_AUDIT_VISIT_CONFIG, opportunity_id=opportunity_id,
            )
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
            flw_results.append(result)

        return OpportunityResult(
            opportunity_id=opportunity_id,
            opportunity_name=opp_name,
            llo=llo,
            flw_results=flw_results,
            flw_aggregated=flw_aggregated,
            visit_result=visit_result,
        )

    # ------------------------------------------------------------------------
    # Public: load the full dashboard
    # ------------------------------------------------------------------------

    def build_dashboard(self) -> DashboardSummary:
        """Load all selected opportunities in parallel and merge into one
        flat row list ready for table rendering."""
        if not self.opportunity_ids:
            return DashboardSummary([], 0, 0, 0, [], [])

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

        # Build the merged row list for template rendering. Each row carries
        # everything the table needs so the template stays dumb.
        rows: list[dict[str, Any]] = []
        opportunities_loaded: list[int] = []
        opportunities_failed: list[tuple[int, str]] = []

        for opp in sorted(results, key=lambda r: r.opportunity_id):
            if opp.error:
                opportunities_failed.append((opp.opportunity_id, opp.error))
                continue
            opportunities_loaded.append(opp.opportunity_id)
            # Build a username -> flw_name map from the aggregated pipeline rows
            # so we can show human-readable FLW names in the table.
            flw_name_by_user: dict[str, str] = {}
            if opp.flw_aggregated:
                for r in opp.flw_aggregated.rows:
                    if r.username and r.flw_name:
                        flw_name_by_user[r.username] = r.flw_name

            for flw in opp.flw_results:
                row = {
                    "username": flw.username,
                    "flw_name": flw_name_by_user.get(flw.username, "") or flw.username,
                    "opportunity_id": opp.opportunity_id,
                    "opportunity_name": opp.opportunity_name,
                    "llo": opp.llo or "",
                    "total_cases": flw.total_cases,
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
                }
                rows.append(row)

        # Sort by priority flag count descending so the most concerning
        # FLWs surface at the top.
        rows.sort(
            key=lambda r: (-(r["priority_flag_count"] or 0), -(r["flag_count"] or 0), r["username"])
        )

        total_flws = len(rows)
        flws_with_priority_flag = sum(1 for r in rows if r["priority_flag_count"] >= 1)
        flws_excluded = sum(1 for r in rows if r["excluded"])

        return DashboardSummary(
            rows=rows,
            total_flws=total_flws,
            flws_with_priority_flag=flws_with_priority_flag,
            flws_excluded=flws_excluded,
            opportunities_loaded=opportunities_loaded,
            opportunities_failed=opportunities_failed,
        )

    # ------------------------------------------------------------------------
    # Public: per-FLW drill-down
    # ------------------------------------------------------------------------

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
                KMC_AUDIT_FLW_CONFIG, opportunity_id=opportunity_id,
            )
            visit_result: VisitAnalysisResult = pipeline.stream_analysis_ignore_events(
                KMC_AUDIT_VISIT_CONFIG, opportunity_id=opportunity_id,
            )
        except Exception as e:
            logger.exception("[KMCAudit] drill-down opp %d / %s failed", opportunity_id, username)
            return {"error": str(e), "visits": []}

        # Find this FLW's aggregated row + filter visits to this username
        flw_row = next((r for r in flw_aggregated.rows if r.username == username), None)
        if flw_row is None:
            return {
                "error": f"FLW '{username}' not found in opportunity {opportunity_id}",
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
                "closed_cases": flw_result.closed_cases,
                "deaths": flw_result.deaths,
                "avg_visits": flw_result.avg_visits,
                "mort_rate": flw_result.mort_rate,
                "weight_pairs": flw_result.weight_pairs,
            },
            "flags": flw_result.flags,
            "visits": annotated_visits,
            "error": None,
        }

    # ------------------------------------------------------------------------
    # Public: helpers used by views to render filter UI / column headers
    # ------------------------------------------------------------------------

    @staticmethod
    def column_definitions() -> dict[str, list[dict[str, str]]]:
        """Column metadata for the priority and secondary tables."""
        return {
            "priority": [
                {"key": k, "label": FLAG_LABELS[k]} for k in PRIORITY_FLAGS
            ],
            "secondary": [
                {"key": k, "label": FLAG_LABELS[k]} for k in SECONDARY_FLAGS
            ],
            "all": [
                {"key": k, "label": FLAG_LABELS[k]} for k in ALL_FLAGS
            ],
        }
