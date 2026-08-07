"""
eha_scale_audit -- objective weight/scale-photo audit for EHA (Neal + Christie).

For a stratified sample of follow-up visits that have a weight photo:
  1. map the weight-image filename -> its Connect blob_id (from the images column)
  2. download the image from CONNECT  (/export/opportunity/<id>/image/?blob_id=,  Bearer token)
  3. POST image + entered weight to the Scale-Validation ML API -> {"match": bool}
  4. aggregate match rate overall + per FLW

Uses the SAME Connect OAuth token as eha_pull_raw (resolved internally) and the
SCALE_VALIDATION_API_KEY from settings. Ground truth only — writes scale_photo_audit.json.

Usage (run yourself so the network egress is user-initiated):
  python manage.py eha_scale_audit --images-csv .kmc_validation/register/eha_images_20260710.csv --per-flw 10
"""
from __future__ import annotations

import ast
import base64
import csv as csvmod
import json
import sys
import time
from collections import defaultdict

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

csvmod.field_size_limit(10**8)


class Command(BaseCommand):
    help = "Validate entered weights against scale photos via the Scale-Validation ML API."

    def add_arguments(self, parser):
        parser.add_argument("--opp-id", type=int, default=1236)
        parser.add_argument("--images-csv", required=True, help="user_visits export pulled with --images")
        parser.add_argument("--per-flw", type=int, default=10)
        parser.add_argument("--out", default="dashboard_export_eha_20260625/analysis/scale_photo_audit.json")

    def _resolve_token(self):
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

    @staticmethod
    def _dig(d, path):
        cur = d
        for p in path.split("."):
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return None
        return cur if cur not in (None, "", {}) else None

    def handle(self, *args, **opts):
        opp = opts["opp_id"]
        token = self._resolve_token()
        if not token:
            self.stderr.write(self.style.ERROR("No Connect token (log in at /labs/login/)."))
            sys.exit(2)
        sv_key = getattr(settings, "SCALE_VALIDATION_API_KEY", "")
        sv_url = getattr(
            settings, "SCALE_VALIDATION_API_URL", "https://image-pipeline-scale-gw-4pc8jsfa.uc.gateway.dev"
        ).rstrip("/")
        if not sv_key:
            self.stderr.write(self.style.ERROR("SCALE_VALIDATION_API_KEY not configured."))
            sys.exit(2)
        prod = settings.CONNECT_PRODUCTION_URL.rstrip("/")

        # ---- collect follow-up weight photos with blob_ids ----
        by_flw = defaultdict(list)
        for r in csvmod.DictReader(open(opts["images_csv"], encoding="utf-8")):
            try:
                fj = ast.literal_eval(r["form_json"])
                imgs = ast.literal_eval(r["images"]) if r.get("images") else []
            except Exception:
                continue
            fname = self._dig(fj, "form.anthropometric.upload_weight_image")
            wt = self._dig(fj, "form.anthropometric.child_weight_visit")
            if not fname or wt is None or not isinstance(imgs, list):
                continue
            blob = next((im.get("blob_id") for im in imgs if isinstance(im, dict) and im.get("name") == fname), None)
            if not blob:
                continue
            try:
                reading = str(int(float(wt)))
            except (TypeError, ValueError):
                continue
            by_flw[r["username"]].append({"row_id": r["id"], "blob_id": blob, "reading": reading})

        sample = []
        for flw, items in by_flw.items():
            sample.extend([dict(it, flw=flw) for it in items[: opts["per_flw"]]])
        self.stderr.write(f"sample: {len(sample)} photos across {len(by_flw)} FLWs (<= {opts['per_flw']}/FLW)")

        # ---- download (Connect) + validate (Scale API) ----
        dl_headers = {"Authorization": f"Bearer {token}"}
        sv_headers = {"Content-Type": "application/json", "x-api-key": sv_key}
        results = []
        with httpx.Client(timeout=120.0) as client:
            for i, s in enumerate(sample, 1):
                rec = {"flw": s["flw"], "row_id": s["row_id"], "reading": s["reading"], "match": None, "note": ""}
                try:
                    img = client.get(
                        f"{prod}/export/opportunity/{opp}/image/", params={"blob_id": s["blob_id"]}, headers=dl_headers
                    )
                    if img.status_code != 200:
                        rec["note"] = f"download HTTP {img.status_code}"
                        results.append(rec)
                        continue
                    enc = base64.b64encode(img.content).decode()
                    sv = None
                    for attempt in range(4):
                        sv = client.post(
                            f"{sv_url}/predict",
                            headers=sv_headers,
                            json={"image": enc, "reading": s["reading"]},
                            timeout=90.0,
                        )
                        if sv.status_code == 429:
                            time.sleep(5 * (attempt + 1))
                            continue
                        break
                    if sv is not None and sv.status_code == 200:
                        rec["match"] = bool(sv.json().get("match"))
                    else:
                        code = getattr(sv, "status_code", "?")
                        body = getattr(sv, "text", "")[:120]
                        rec["note"] = f"validate HTTP {code}: {body}"
                except Exception as e:
                    rec["note"] = f"error: {repr(e)[:120]}"
                results.append(rec)
                if i % 10 == 0:
                    ok = sum(1 for r in results if r["match"] is True)
                    self.stderr.write(f"  {i}/{len(sample)} done, matches so far: {ok}")

        # ---- aggregate ----
        scored = [r for r in results if r["match"] is not None]
        errored = [r for r in results if r["match"] is None]
        matched = sum(1 for r in scored if r["match"])
        per_flw = defaultdict(lambda: {"n": 0, "match": 0})
        for r in scored:
            per_flw[r["flw"]]["n"] += 1
            per_flw[r["flw"]]["match"] += 1 if r["match"] else 0
        agg = {
            "opp": opp,
            "sample_photos": len(sample),
            "scored": len(scored),
            "errored": len(errored),
            "overall_match_pct": round(100 * matched / len(scored), 1) if scored else None,
            "matched": matched,
            "per_flw": {
                k: {"n": v["n"], "match": v["match"], "match_pct": round(100 * v["match"] / v["n"], 1)}
                for k, v in per_flw.items()
            },
            "error_notes": [r["note"] for r in errored][:20],
        }
        json.dump({"aggregate": agg, "per_visit": results}, open(opts["out"], "w", encoding="utf-8"), indent=1)

        self.stdout.write("=" * 60)
        self.stdout.write("SCALE-PHOTO AUDIT RESULT (EHA)")
        self.stdout.write("=" * 60)
        self.stdout.write(f"scored {len(scored)}/{len(sample)} (errored {len(errored)})")
        self.stdout.write(f"OVERALL MATCH: {agg['overall_match_pct']}% ({matched}/{len(scored)})")
        for k, v in sorted(agg["per_flw"].items()):
            self.stdout.write(f"  {k:22s} {v['match']:2d}/{v['n']:2d} ({v['match_pct']}%)")  # noqa: E231
        if errored:
            self.stdout.write(f"errors ({len(errored)}): {agg['error_notes'][:5]}")
        self.stdout.write(f"wrote {opts['out']}")
