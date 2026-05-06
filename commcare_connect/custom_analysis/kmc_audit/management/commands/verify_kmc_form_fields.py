"""
Verify which KMC form fields actually exist in the live CommCare HQ apps.

Pulls the most recent labs OAuth token from django_session, uses it to
fetch each KMC opportunity's deliver-app cc_domain + cc_app_id from the
Connect API, then queries CommCare HQ's application API and walks every
form's question tree looking for the fields the secondary KMC flags
need (heart_rate, temperature, spo2_level, gestational_age_lmp,
gps_lat, gps_lon, gps_accuracy_m, child_referred, child_alive).

Reports one line per (opportunity, field) so you can see at a glance
which secondary flags are wirable.

Usage:
    python manage.py verify_kmc_form_fields
"""

from __future__ import annotations

import asyncio
import re

import httpx
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.utils import timezone

from commcare_connect.custom_analysis.kmc_audit.constants import KMC_OPPORTUNITIES

# Field names the secondary flags would need. Searched as substrings of
# question_id / json_path so we catch close variants too.
TARGET_FIELDS = [
    "heart_rate",
    "temperature",
    "temp",
    "spo2",
    "oxygen",
    "gestational",
    "gestation",
    "gps_lat",
    "gps_lon",
    "gps_accuracy",
    "latitude",
    "longitude",
    "child_referred",
    "child_alive",
    "danger_sign",
    "weight",
]


def _walk_questions(node, path_parts=None, hits=None):
    """Recursively walk a CommCare question tree and collect every
    (question_id, full_path, type) tuple."""
    if path_parts is None:
        path_parts = []
    if hits is None:
        hits = []
    if isinstance(node, dict):
        # CommCare question nodes typically have "type", "question_id" and
        # for groups, a "children" or "questions" list.
        qid = node.get("question_id") or node.get("name") or ""
        qtype = node.get("type", "")
        if qid:
            full = ".".join(path_parts + [qid]) if path_parts else qid
            hits.append({"question_id": qid, "path": full, "type": qtype, "label": node.get("label", "")})
            sub_path = path_parts + [qid] if qtype in ("Group", "Repeat") else path_parts
        else:
            sub_path = path_parts
        for key in ("children", "questions", "tree"):
            child = node.get(key)
            if isinstance(child, list):
                for c in child:
                    _walk_questions(c, sub_path, hits)
    elif isinstance(node, list):
        for c in node:
            _walk_questions(c, path_parts, hits)
    return hits


def _walk_app_for_form_paths(app_def):
    """Walk a full CommCare HQ app definition and return a list of
    {form_name, xmlns, paths: [json_path, ...]} dicts.

    Uses a simple text walk: anything that looks like a question_id in
    the app's modules/forms tree gets emitted. CommCare's HQ API returns
    deeply nested module → form → question structures.
    """
    forms_seen = []
    for module in app_def.get("modules", []) or []:
        m_name = module.get("name", "")
        for form in module.get("forms", []) or []:
            f_name = form.get("name") or m_name
            xmlns = form.get("xmlns", "")
            # Some forms expose questions directly; others embed an XForm we'd
            # have to parse. Prefer the API's 'questions' summary if present.
            qs = form.get("questions")
            paths: list[str] = []
            if qs:
                for q in qs:
                    p = q.get("value") or q.get("question_id") or q.get("name") or ""
                    # Strip the leading /data/ prefix that some forms include
                    # so paths line up with submitted form_json's "form.X.Y".
                    p = re.sub(r"^/data/?", "", p).strip("/")
                    if p:
                        paths.append(p.replace("/", "."))
            else:
                # Fall back to walking children
                for h in _walk_questions(form):
                    if h["path"]:
                        paths.append(h["path"])
            forms_seen.append({"form": f_name, "xmlns": xmlns, "paths": paths})
    return forms_seen


def _find_target_fields(forms_seen):
    """For each TARGET_FIELDS substring, find every (form, path) match across
    the given forms list."""
    matches: dict[str, list[dict]] = {f: [] for f in TARGET_FIELDS}
    for f in forms_seen:
        for p in f["paths"]:
            p_lower = p.lower()
            for t in TARGET_FIELDS:
                if t.lower() in p_lower:
                    matches[t].append({"form": f["form"], "xmlns": f["xmlns"], "path": p})
    return matches


def _newest_labs_oauth_token() -> str | None:
    """Find the most recently active Django session that contains a
    labs_oauth.access_token, decode it, and return the access token.

    Iterates active (non-expired) sessions newest-first."""
    now = timezone.now()
    sessions = Session.objects.filter(expire_date__gt=now).order_by("-expire_date")
    for s in sessions:
        try:
            decoded = SessionStore().decode(s.session_data)
        except Exception:
            continue
        oauth = decoded.get("labs_oauth") or {}
        access_token = oauth.get("access_token")
        if access_token:
            return access_token
    return None


async def _resolve_opp_app(token: str, opp_id: int) -> dict | None:
    """Call Connect's /export/opportunity/{id}/ to get cc_domain + cc_app_id."""
    base = settings.CONNECT_PRODUCTION_URL.rstrip("/")
    url = f"{base}/export/opportunity/{opp_id}/"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code >= 400:
            return None
        data = resp.json()
    deliver = data.get("deliver_app") or {}
    return {
        "name": data.get("name", ""),
        "cc_domain": deliver.get("cc_domain", ""),
        "cc_app_id": deliver.get("cc_app_id", ""),
    }


async def _fetch_app_definition(domain: str, app_id: str) -> dict | None:
    """Fetch a single application definition from CommCare HQ."""
    import os

    username = os.environ.get("COMMCARE_USERNAME", "")
    api_key = os.environ.get("COMMCARE_API_KEY", "")
    if not username or not api_key:
        return None
    url = f"https://www.commcarehq.org/a/{domain}/api/v0.5/application/{app_id}/"  # noqa: E231
    async with httpx.AsyncClient(
        timeout=120.0,
        headers={"Authorization": f"ApiKey {username}:{api_key}"},  # noqa: E231
    ) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            return {"_error": f"HTTP {resp.status_code}: {resp.text[:200]}"}  # noqa: E231
        return resp.json()


class Command(BaseCommand):
    help = "Verify which KMC form fields actually exist in CommCare HQ for each KMC opportunity."

    def handle(self, *args, **options):
        token = _newest_labs_oauth_token()
        if not token:
            self.stderr.write(self.style.ERROR("No active labs_oauth session found. Log into the dashboard first."))
            return

        async def run():
            for opp_id, meta in KMC_OPPORTUNITIES.items():
                self.stdout.write(
                    self.style.MIGRATE_HEADING(f"\n=== Opp {opp_id} — {meta['name']} ({meta['llo']}) ===")
                )
                resolved = await _resolve_opp_app(token, opp_id)
                if not resolved or not resolved["cc_domain"] or not resolved["cc_app_id"]:
                    self.stdout.write("  (no deliver app — skipped)")
                    continue
                self.stdout.write(f"  domain={resolved['cc_domain']} app_id={resolved['cc_app_id']}")
                app = await _fetch_app_definition(resolved["cc_domain"], resolved["cc_app_id"])
                if not app or "_error" in (app or {}):
                    err = (app or {}).get("_error", "no app returned")
                    self.stdout.write(self.style.ERROR(f"  HQ fetch failed: {err}"))
                    continue
                forms = _walk_app_for_form_paths(app)
                self.stdout.write(f"  {len(forms)} forms scanned")
                matches = _find_target_fields(forms)
                for field, hits in matches.items():
                    if hits:
                        first = hits[0]
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ {field:18s} found at: {first['path']}"  # noqa: E231
                                + (f"  (+{len(hits) - 1} more)" if len(hits) > 1 else "")
                            )
                        )
                    else:
                        self.stdout.write(self.style.WARNING(f"  ✗ {field:18s} NOT FOUND"))  # noqa: E231

        asyncio.run(run())
