"""
kmc_scale_ai_spike -- GO/NO-GO spike for automated scale-image weight verification.

Answers the one question that gates the "match/no-match in the KMC Audit Dashboard"
feature (Path C): does the scale_validation ML service actually READ our scales --
in particular the ANALOG dials that most KMC LLOs use (Salter 235, KINLee), not just
digital LCDs?

For a per-opp sample of follow-up visits that carry a weight photo, it:
  1. pulls /export/opportunity/<id>/user_visits/?images=true  (form_json + blob_id-bearing images)
  2. downloads each weight photo from Connect (Bearer token)
  3. runs the DEPLOYED scale_validation agent TWICE per photo:
       - with the TRUE typed reading   -> should return "match"
       - with a deliberately WRONG one  -> should return "no_match"
     (the wrong-direction test catches a service that just says "match" to everything)
  4. scores per LLO and per scale-type (analog vs digital).

Read-only. Writes a JSON report; mutates nothing. Uses SCALE_VALIDATION_API_KEY from
settings (already set in ECS) and the same Connect OAuth token resolution as eha_pull_raw.

Usage (in the deployed env, or locally after /labs/login/):
  python manage.py kmc_scale_ai_spike                      # default opps, 12/opp
  python manage.py kmc_scale_ai_spike --opps 1236 1790 1488 874 --per-opp 15
"""
from __future__ import annotations

import ast
import base64
import csv as csvmod
import json
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

csvmod.field_size_limit(10**8)

# LLO scale hardware (see memory kmc-scale-hardware-per-llo): which opps type from an
# ANALOG dial (the risk) vs a DIGITAL LCD (what these services are usually built for).
SCALE_TYPE = {
    1236: "analog",  # EHA  - Salter 235 (NG)
    1790: "analog",  # BERI - Salter 235 (NG)
    523: "analog",
    938: "analog",
    1488: "analog",  # NAMA - KINLee dial (UG)
    524: "digital",
    874: "digital",
    1487: "digital",  # PIPN - digital (UG)
    1234: "other",
    675: "other",
    1739: "other",  # GHI-KE ~10g / GHI-UG reg-only / Kikapu
}
LLO_NAME = {
    1236: "EHA",
    1790: "BERI",
    523: "NAMA-V1",
    938: "NAMA-V2",
    1488: "NAMA-V3",
    524: "PIPN-V1",
    874: "PIPN-V2",
    1487: "PIPN-V3",
    1234: "GHI-KE",
    1739: "Kikapu",
}
DEFAULT_OPPS = [1236, 1790, 1488, 874]  # analog EHA/BERI/NAMA + digital PIPN for contrast


class Command(BaseCommand):
    help = "GO/NO-GO spike: does scale_validation read KMC analog dials? (true->match / wrong->no_match by scale type)"

    def add_arguments(self, parser):
        parser.add_argument("--opps", type=int, nargs="+", default=DEFAULT_OPPS)
        parser.add_argument("--per-opp", type=int, default=12, help="photos sampled per opportunity")
        parser.add_argument("--access-token", help="override; else resolved from TokenManager/session")
        parser.add_argument("--skip-wrong", action="store_true", help="only test true readings (half the calls)")
        parser.add_argument("--out", default="kmc_scale_ai_spike.json")

    def _resolve_token(self, override=None) -> str | None:
        if override:
            return override
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

    @staticmethod
    def _wrong_reading(true_grams: int) -> str:
        return str(true_grams + 500 if true_grams < 4000 else true_grams - 500)

    def _pull_visits(self, opp, token, per_opp):
        """Stream the images-bearing user_visits export to a temp file, collect candidate photos."""
        prod = settings.CONNECT_PRODUCTION_URL.rstrip("/")
        url = f"{prod}/export/opportunity/{opp}/user_visits/?images=true"
        headers = {"Authorization": f"Bearer {token}", "Accept-Encoding": "gzip, deflate"}
        tmp = Path(tempfile.gettempdir()) / f"kmc_spike_opp_{opp}.csv"
        try:
            with httpx.stream("GET", url, headers=headers, timeout=580.0) as r:
                r.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes(chunk_size=65536):
                        f.write(chunk)
        except httpx.HTTPStatusError as e:
            self.stderr.write(
                self.style.ERROR(
                    f"  opp {opp}: pull HTTP {e.response.status_code} (token expired? re-login at /labs/login/)"
                )
            )
            return []

        by_flw = defaultdict(list)
        with tmp.open(encoding="utf-8", newline="") as f:
            for row in csvmod.DictReader(f):
                try:
                    fj = ast.literal_eval(row["form_json"])
                    imgs = ast.literal_eval(row["images"]) if row.get("images") else []
                except Exception:
                    continue
                fname = self._dig(fj, "form.anthropometric.upload_weight_image")
                wt = self._dig(fj, "form.anthropometric.child_weight_visit")
                if not fname or wt is None or not isinstance(imgs, list):
                    continue
                blob = next(
                    (im.get("blob_id") for im in imgs if isinstance(im, dict) and im.get("name") == fname), None
                )
                if not blob:
                    continue
                try:
                    grams = int(round(float(wt)))
                except (TypeError, ValueError):
                    continue
                if not (300 <= grams <= 6000):  # plausible infant grams only
                    continue
                by_flw[row.get("username", "?")].append(
                    {"opp": opp, "blob_id": blob, "true": str(grams), "grams": grams, "flw": row.get("username", "?")}
                )
        try:
            tmp.unlink()
        except OSError:
            pass
        # spread the sample across FLWs (round-robin) so no single FLW dominates
        buckets = list(by_flw.values())
        sample, i = [], 0
        while buckets and len(sample) < per_opp:
            b = buckets[i % len(buckets)]
            if b:
                sample.append(b.pop())
            else:
                buckets.pop(i % len(buckets))
                continue
            i += 1
        return sample

    def _validate(self, agent, image_bytes, reading):
        """Call the deployed agent with 429 backoff; return 'match'/'no_match'/'error'."""
        from commcare_connect.labs.ai_review_agents.types import ReviewContext

        ctx = ReviewContext(images={"scale": image_bytes}, form_data={"reading": reading})
        for attempt in range(4):
            res = agent.review(ctx)
            if res.errors and "Rate limited" in res.errors[0]:
                time.sleep(5 * (attempt + 1))
                continue
            if res.passed:
                return "match"
            if res.failed:
                return "no_match"
            return f"error:{(res.errors or ['?'])[0][:60]}"
        return "error:rate_limited"

    def handle(self, *args, **opts):
        token = self._resolve_token(opts.get("access_token"))
        if not token:
            self.stderr.write(self.style.ERROR("No Connect token (log in at /labs/login/, or pass --access-token)."))
            sys.exit(2)
        if not getattr(settings, "SCALE_VALIDATION_API_KEY", ""):
            self.stderr.write(self.style.ERROR("SCALE_VALIDATION_API_KEY not configured in this environment."))
            sys.exit(2)

        from commcare_connect.labs.ai_review_agents import get_agent

        agent = get_agent("scale_validation")
        prod = settings.CONNECT_PRODUCTION_URL.rstrip("/")
        dl_headers = {"Authorization": f"Bearer {token}"}

        per_type = defaultdict(lambda: {"n": 0, "true_match": 0, "wrong_nomatch": 0, "err": 0})
        per_opp = defaultdict(lambda: {"n": 0, "true_match": 0, "wrong_nomatch": 0, "err": 0})
        per_visit = []

        with httpx.Client(timeout=120.0) as dl:
            for opp in opts["opps"]:
                stype = SCALE_TYPE.get(opp, "other")
                self.stderr.write(f"\n== opp {opp} ({LLO_NAME.get(opp, opp)}, {stype}) — pulling visits ==")
                sample = self._pull_visits(opp, token, opts["per_opp"])
                self.stderr.write(f"   sampled {len(sample)} photos")
                for s in sample:
                    rec = {
                        "opp": opp,
                        "type": stype,
                        "flw": s["flw"],
                        "true": s["true"],
                        "true_result": None,
                        "wrong_result": None,
                        "note": "",
                    }
                    try:
                        img = dl.get(
                            f"{prod}/export/opportunity/{opp}/image/",
                            params={"blob_id": s["blob_id"]},
                            headers=dl_headers,
                        )
                        if img.status_code != 200:
                            rec["note"] = f"download HTTP {img.status_code}"
                            per_type[stype]["err"] += 1
                            per_opp[opp]["err"] += 1
                            per_visit.append(rec)
                            continue
                        rec["true_result"] = self._validate(agent, img.content, s["true"])
                        if not opts["skip_wrong"]:
                            rec["wrong_result"] = self._validate(agent, img.content, self._wrong_reading(s["grams"]))
                    except Exception as e:
                        rec["note"] = f"error: {repr(e)[:100]}"
                    # tally
                    for scope in (per_type[stype], per_opp[opp]):
                        scope["n"] += 1
                        if rec["true_result"] == "match":
                            scope["true_match"] += 1
                        if rec["wrong_result"] == "no_match":
                            scope["wrong_nomatch"] += 1
                        if (rec["true_result"] or "").startswith("error") or rec["note"]:
                            scope["err"] += 1
                    per_visit.append(rec)

        agent.close()

        def pct(a, b):
            return round(100 * a / b, 1) if b else None

        report = {
            "opps": opts["opps"],
            "per_opp_sample": opts["per_opp"],
            "tested_wrong": not opts["skip_wrong"],
            "generated": timezone.now().isoformat(),
            "by_scale_type": {
                t: {
                    **v,
                    "true_match_pct": pct(v["true_match"], v["n"]),
                    "wrong_nomatch_pct": pct(v["wrong_nomatch"], v["n"]),
                }
                for t, v in per_type.items()
            },
            "by_opp": {
                LLO_NAME.get(o, str(o)): {
                    **v,
                    "true_match_pct": pct(v["true_match"], v["n"]),
                    "wrong_nomatch_pct": pct(v["wrong_nomatch"], v["n"]),
                }
                for o, v in per_opp.items()
            },
            "per_visit": per_visit,
        }
        Path(opts["out"]).write_text(json.dumps(report, indent=1), encoding="utf-8")

        self.stdout.write("=" * 68)
        self.stdout.write("KMC SCALE-AI SPIKE — does the service read our scales?")
        self.stdout.write("=" * 68)
        self.stdout.write(f"{'scale type':10} {'n':>4} {'true->match':>13} {'wrong->no_match':>17} {'errs':>6}")
        for t, v in report["by_scale_type"].items():
            self.stdout.write(
                f"{t:10} {v['n']:>4} {str(v['true_match_pct'])+'%':>13} "
                f"{str(v['wrong_nomatch_pct'])+'%':>17} {v['err']:>6}"
            )
        self.stdout.write("-" * 68)
        for name, v in report["by_opp"].items():
            self.stdout.write(
                f"  {name:12} n={v['n']:>3}  true->match {v['true_match_pct']}%  "
                f"wrong->no_match {v['wrong_nomatch_pct']}%  errs {v['err']}"
            )
        self.stdout.write("-" * 68)
        self.stdout.write("GO if ANALOG:  true->match high (~>=70%) AND wrong->no_match high (~>=70%).")
        self.stdout.write("   both high  => reads the dial & detects mismatch => Path C viable for analog LLOs.")
        self.stdout.write("   true high / wrong low => rubber-stamps 'match' => NOT a real check.")
        self.stdout.write("   both low / many errs   => can't read analog => scope C to digital (PIPN) only.")
        self.stdout.write(f"wrote {opts['out']}")
