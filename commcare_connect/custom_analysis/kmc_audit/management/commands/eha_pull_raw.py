"""
eha_pull_raw -- download and save the FULL raw visit export for an opportunity.

Pulls /export/opportunity/<id>/user_visits/ (CSV, each row carries a
`form_json` column with the complete form submission) straight to disk so it
can be the grounded source of truth for the deep EHA analysis. Read-only.

Usage:
    python manage.py eha_pull_raw --opp-id 1236 --out raw_eha/eha_user_visits_raw.csv
"""

from __future__ import annotations

import csv as csvmod
import sys
from pathlib import Path

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Download the full raw user_visits export (CSV w/ form_json) for an opportunity."

    def add_arguments(self, parser):
        parser.add_argument("--opp-id", type=int, default=1236)
        parser.add_argument("--access-token")
        parser.add_argument("--out", default="raw_eha/eha_user_visits_raw.csv")
        parser.add_argument(
            "--images", action="store_true", help="append ?images=true (adds blob_id-bearing images column)"
        )

    def _resolve_token(self) -> str | None:
        try:
            from commcare_connect.labs.integrations.connect.cli import TokenManager

            tok = TokenManager().get_valid_token()
            if tok:
                return tok
        except Exception:
            pass
        try:
            from django.contrib.sessions.models import Session

            for s in Session.objects.filter(expire_date__gte=timezone.now()).order_by("-expire_date")[:20]:
                tok = (s.get_decoded().get("labs_oauth") or {}).get("access_token")
                if tok:
                    return tok
        except Exception:
            pass
        return None

    def handle(self, *args, **opts):
        opp = opts["opp_id"]
        token = opts.get("access_token") or self._resolve_token()
        if not token:
            self.stderr.write(self.style.ERROR("No token (log in at /labs/login/ on the dev server)."))
            sys.exit(2)

        out = Path(opts["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opp}/user_visits/"
        if opts.get("images"):
            url += "?images=true"
        headers = {"Authorization": f"Bearer {token}", "Accept-Encoding": "gzip, deflate"}
        self.stderr.write(f"Downloading {url} ...")

        nbytes = 0
        try:
            with httpx.stream("GET", url, headers=headers, timeout=580.0) as r:
                r.raise_for_status()
                with out.open("wb") as f:
                    for chunk in r.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        nbytes += len(chunk)
        except httpx.HTTPStatusError as e:
            self.stderr.write(
                self.style.ERROR(f"HTTP {e.response.status_code} — token likely expired, re-login at /labs/login/.")
            )
            sys.exit(3)

        # Report shape: row count + columns (header only, cheap).
        with out.open(encoding="utf-8", newline="") as f:
            reader = csvmod.reader(f)
            header = next(reader, [])
            rows = sum(1 for _ in reader)
        self.stderr.write(self.style.SUCCESS(f"Saved {nbytes:,} bytes to {out.resolve()}"))  # noqa: E231
        self.stderr.write(f"Rows: {rows} | Columns ({len(header)}): {header}")
