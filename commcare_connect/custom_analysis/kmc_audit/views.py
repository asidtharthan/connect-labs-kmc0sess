"""
Views for the KMC Audit Dashboard.

The dashboard surfaces 16 KMC quality flags per FLW across the five
KMC opportunities (see ``constants.KMC_OPPORTUNITY_IDS``), lets a
reviewer filter by LLO, drill into a single FLW's visits, and create
audit sessions on flagged FLWs in one POST.

Frontend: server-rendered Django templates with Alpine.js for client-
side LLO / "show only flagged" filtering and HTMX for the drill-down
partial + audit-modal partial.

Auth: stock LoginRequiredMixin. Anyone with a valid labs OAuth session
can view (no Dimagi-only restriction — KMC reviewers across LLOs need
access).
"""

from __future__ import annotations

import json
import logging
import uuid

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, JsonResponse
from django.urls import reverse
from django.views.generic import TemplateView, View

from commcare_connect.audit.data_access import AuditDataAccess

from .constants import KMC_OPPORTUNITIES, KMC_OPPORTUNITY_IDS, LLO_CHOICES, opportunity_name
from .data_access import KMCAuditDataAccess
from .flag_logic import (
    ALL_FLAGS,
    DATA_QUALITY_FLAGS,
    FLAG_DESCRIPTIONS,
    FLAG_LABELS,
    FLAG_METRIC_KEY,
    FLAG_THRESHOLD_DISPLAY,
    MIN_CASES,
    PRIORITY_FLAGS,
    SECONDARY_FLAGS,
    THRESHOLDS,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Main dashboard view
# ─────────────────────────────────────────────────────────────────────────────


class KMCAuditDashboardView(LoginRequiredMixin, TemplateView):
    """Renders the tiered flag table across all selected KMC opportunities."""

    template_name = "custom_analysis/kmc_audit/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Optional URL filter: ?opp_ids=523&opp_ids=874 (defaults to all 5).
        # The LLO/opp filters in the UI are client-side Alpine.js so we don't
        # round-trip — the server always loads the same row set per opp set.
        opp_id_strs = self.request.GET.getlist("opp_ids")
        if opp_id_strs:
            try:
                opp_ids = [int(x) for x in opp_id_strs if x.isdigit()]
            except ValueError:
                opp_ids = list(KMC_OPPORTUNITY_IDS)
        else:
            opp_ids = list(KMC_OPPORTUNITY_IDS)

        # Load. If anything goes wrong the template still renders an
        # informative error pane — never a 500.
        labs_oauth = self.request.session.get("labs_oauth", {})
        if not labs_oauth.get("access_token"):
            context.update(
                {
                    "load_error": "No OAuth token in session. Please log in via /labs/login/.",
                    "summary": None,
                    "rows": [],
                }
            )
            return self._add_static_context(context, opp_ids)

        try:
            data_access = KMCAuditDataAccess(self.request, opportunity_ids=opp_ids)
            summary = data_access.build_dashboard()
        except Exception as e:
            logger.exception("[KMCAudit] dashboard build failed")
            context.update(
                {
                    "load_error": str(e),
                    "summary": None,
                    "rows": [],
                }
            )
            return self._add_static_context(context, opp_ids)

        context.update(
            {
                "load_error": None,
                "summary": summary,
                "rows": summary.rows,
            }
        )
        return self._add_static_context(context, opp_ids)

    def _add_static_context(self, context: dict, opp_ids: list[int]) -> dict:
        """Filter chips, column metadata, and opp catalogue used by the template."""
        cols = KMCAuditDataAccess.column_definitions()
        # Build ALL_FLAGS list with labels for the flag frequency grid
        all_flags_for_template = [{"key": k, "label": FLAG_LABELS.get(k, k)} for k in ALL_FLAGS]
        context.update(
            {
                "selected_opp_ids": opp_ids,
                "all_kmc_opportunities": [
                    {
                        "id": oid,
                        "name": meta["name"],
                        "llo": meta["llo"],
                        "selected": oid in opp_ids,
                    }
                    for oid, meta in KMC_OPPORTUNITIES.items()
                ],
                "llo_choices": list(LLO_CHOICES),
                "priority_columns": cols["priority"],
                "secondary_columns": cols["secondary"],
                "data_quality_sub_flags": cols["data_quality_sub_flags"],
                "all_flags": all_flags_for_template,
                "flag_labels": FLAG_LABELS,
                "flag_descriptions": FLAG_DESCRIPTIONS,
                "flag_thresholds": FLAG_THRESHOLD_DISPLAY,
                "flag_metric_keys": FLAG_METRIC_KEY,
                "thresholds": THRESHOLDS,
                "min_cases": MIN_CASES,
            }
        )
        return context


# ─────────────────────────────────────────────────────────────────────────────
# HTMX partial: per-FLW drill-down
# ─────────────────────────────────────────────────────────────────────────────


class KMCFLWDrilldownView(LoginRequiredMixin, View):
    """HTMX partial — returns one FLW's visit list with flag-source annotations.

    URL: /custom_analysis/kmc_audit/flw/<int:opportunity_id>/<str:username>/
    """

    template_name = "custom_analysis/kmc_audit/drilldown.html"

    def get(self, request: HttpRequest, opportunity_id: int, username: str):
        from django.shortcuts import render

        labs_oauth = request.session.get("labs_oauth", {})
        if not labs_oauth.get("access_token"):
            return render(
                request,
                self.template_name,
                {
                    "error": "Not authenticated. Refresh the page and log in again.",
                    "visits": [],
                },
            )

        data_access = KMCAuditDataAccess(request)
        result = data_access.drill_down(opportunity_id=opportunity_id, username=username)

        return render(
            request,
            self.template_name,
            {
                "username": username,
                "opportunity_id": opportunity_id,
                "opportunity_name": result.get("opportunity_name", ""),
                "llo": result.get("llo", ""),
                "metrics": result.get("metrics", {}),
                "flags": result.get("flags", {}),
                "visits": result.get("visits", []),
                "error": result.get("error"),
                "flag_labels": FLAG_LABELS,
                "flag_descriptions": FLAG_DESCRIPTIONS,
                "flag_thresholds": FLAG_THRESHOLD_DISPLAY,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# HTMX partial: audit-creation modal
# ─────────────────────────────────────────────────────────────────────────────


class KMCAuditModalView(LoginRequiredMixin, View):
    """HTMX partial — renders the audit-creation modal pre-populated with the
    currently selected FLWs (passed as ?usernames=a&usernames=b&opp_id=938)."""

    template_name = "custom_analysis/kmc_audit/_audit_modal.html"

    def get(self, request: HttpRequest):
        from django.shortcuts import render

        usernames = request.GET.getlist("usernames")
        opp_id_str = request.GET.get("opp_id", "")
        try:
            opp_id = int(opp_id_str) if opp_id_str else None
        except ValueError:
            opp_id = None

        return render(
            request,
            self.template_name,
            {
                "usernames": usernames,
                "opp_id": opp_id,
                "opp_name": opportunity_name(opp_id) if opp_id else "",
                "create_url": reverse("kmc_audit:create_audit"),
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Audit creation — POST handler
# ─────────────────────────────────────────────────────────────────────────────


class KMCAuditCreateView(LoginRequiredMixin, View):
    """Creates an audit-creation job + queues the Celery task.

    Mirrors the inner logic of ``audit.views.ExperimentAuditCreateAsyncAPIView``
    but called in-process so we don't make an HTTP roundtrip from one Django
    view to another. The actual Celery task and downstream session creation
    are unchanged — this is purely a thin orchestration wrapper.

    Accepts JSON or form-encoded POST. Required keys:
        opportunity_id (int), usernames (list[str]), start_date (YYYY-MM-DD),
        end_date (YYYY-MM-DD).
    Optional:
        count_per_flw (int, default 10), title (str), ai_agent_id (str|None).
    """

    def post(self, request: HttpRequest):
        labs_oauth = request.session.get("labs_oauth", {})
        access_token = labs_oauth.get("access_token")
        if not access_token:
            return JsonResponse({"error": "Not authenticated."}, status=401)

        # Parse body — accept JSON OR form-encoded so HTMX hx-post works either way.
        try:
            if request.content_type and "application/json" in request.content_type:
                payload = json.loads(request.body or "{}")
            else:
                payload = {
                    "opportunity_id": request.POST.get("opportunity_id"),
                    "usernames": request.POST.getlist("usernames"),
                    "start_date": request.POST.get("start_date"),
                    "end_date": request.POST.get("end_date"),
                    "count_per_flw": request.POST.get("count_per_flw"),
                    "title": request.POST.get("title"),
                    "ai_agent_id": request.POST.get("ai_agent_id") or None,
                }
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)

        opportunity_id = payload.get("opportunity_id")
        usernames = payload.get("usernames") or []
        start_date = payload.get("start_date")
        end_date = payload.get("end_date")
        count_per_flw = payload.get("count_per_flw") or 10
        title = payload.get("title") or ""
        ai_agent_id = payload.get("ai_agent_id")

        try:
            opportunity_id = int(opportunity_id) if opportunity_id else None
            count_per_flw = int(count_per_flw)
        except (TypeError, ValueError):
            return JsonResponse({"error": "opportunity_id and count_per_flw must be integers."}, status=400)

        if not opportunity_id or opportunity_id not in KMC_OPPORTUNITIES:
            return JsonResponse({"error": "Unknown KMC opportunity_id."}, status=400)
        if not usernames:
            return JsonResponse({"error": "Select at least one FLW."}, status=400)
        if not start_date or not end_date:
            return JsonResponse({"error": "start_date and end_date are required."}, status=400)

        opp_meta = KMC_OPPORTUNITIES[opportunity_id]
        opportunity_dicts = [{"id": opportunity_id, "name": opp_meta["name"]}]

        criteria = {
            "audit_type": "date_range",
            "granularity": "per_flw",
            "title": title or f"KMC Audit — {opp_meta['name']}",
            "start_date": start_date,
            "end_date": end_date,
            "count_per_flw": count_per_flw,
            "selected_flw_user_ids": usernames,
            "related_fields": [
                {
                    "image_path": "anthropometric/upload_weight_image",
                    "field_path": "child_weight_visit",
                    "label": "Weight Reading",
                }
            ],
        }

        task_id = str(uuid.uuid4())
        username_for_record = (
            getattr(request.user, "username", None)
            or labs_oauth.get("user_profile", {}).get("username")
            or "anonymous"
        )

        data_access = AuditDataAccess(opportunity_id=opportunity_id, request=request)
        try:
            job = data_access.create_audit_creation_job(
                username=username_for_record,
                task_id=task_id,
                title=criteria["title"],
                criteria=criteria,
                opportunities=opportunity_dicts,
            )
        except Exception as e:
            logger.exception("[KMCAudit] create_audit_creation_job failed")
            return JsonResponse({"error": f"Failed to create job: {e}"}, status=500)
        finally:
            data_access.close()

        # Queue the Celery task with the pre-generated task_id (matches the
        # pattern at audit/views.py:954-967 to avoid the eager-mode race).
        try:
            from commcare_connect.audit.tasks import run_audit_creation

            run_audit_creation.apply_async(
                kwargs={
                    "access_token": access_token,
                    "username": username_for_record,
                    "opportunities": opportunity_dicts,
                    "criteria": criteria,
                    "visit_ids": None,
                    "flw_visit_ids": None,
                    "template_overrides": None,
                    "workflow_run_id": None,
                    "ai_agent_id": ai_agent_id,
                },
                task_id=task_id,
            )
        except Exception as e:
            logger.exception("[KMCAudit] Celery enqueue failed")
            return JsonResponse({"error": f"Failed to queue task: {e}"}, status=500)

        logger.info(
            "[KMCAudit] queued audit task %s for opp %d (%d FLWs) by %s",
            task_id,
            opportunity_id,
            len(usernames),
            username_for_record,
        )

        # Tell the client where to poll. The audit app already exposes a
        # status endpoint — no need for us to wrap it.
        status_url = f"/audit/api/audit/task/{task_id}/status/"

        return JsonResponse(
            {
                "success": True,
                "task_id": task_id,
                "job_id": job["id"],
                "status_url": status_url,
                "message": "Audit creation queued.",
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tiny helper view to surface flag definitions (handy for the secondary "info"
# popovers in the template — saves duplicating the labels there).
# ─────────────────────────────────────────────────────────────────────────────


class KMCFlagCatalogueView(LoginRequiredMixin, View):
    """Returns the flag list + labels + descriptions as JSON. Used by the dashboard JS for tooltips."""

    def get(self, request: HttpRequest):
        return JsonResponse(
            {
                "priority": list(PRIORITY_FLAGS),
                "secondary": list(SECONDARY_FLAGS),
                "all": list(ALL_FLAGS),
                "data_quality": list(DATA_QUALITY_FLAGS),
                "labels": FLAG_LABELS,
                "descriptions": FLAG_DESCRIPTIONS,
                "thresholds": FLAG_THRESHOLD_DISPLAY,
            }
        )
