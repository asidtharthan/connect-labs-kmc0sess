"""
kmc_probe_run -- read-only diagnostic for a workflow run's audit sessions.

Answers, for one run: do its sessions exist, which image question was audited,
and did the AI actually record verdicts — or did it skip/stop?

Fetches the same /export/labs_record/ endpoint the app uses, three ways:
  A) opportunity scope only, then filter in Python  -> what the app does today
  B) labs_record_id alone                           -> what the patch would do
  B2) labs_record_id AND opportunity_id             -> what get_records really sends

Findings from the first real use (2026-08-11), so nobody re-derives them:
  * B alone returns 0 every time — the endpoint needs a scope param alongside
    labs_record_id. get_records always adds opportunity_id, so the app makes the
    B2 call and the patch is fine; B on its own is just not a valid query.
  * The "0 sessions" symptom did NOT reproduce as a capped response on any run
    checked. What DOES reproduce is per-opportunity scoping: run 11644 returns
    0 sessions under opp 1487 and 35 under 1488, and the results page is scoped
    to the workflow's home opportunity.
  * An audit whose selected image question carries no reading (equipment / wrap
    photos) gives the AI nothing to do — every image is skipped and the run
    "completes with no results". Run 12615 is entirely this case.

Mutates nothing.

    python manage.py kmc_probe_run --run-id 12615 --opp-id 1487
"""

from __future__ import annotations

import sys

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Read-only: compare audit-session fetches for a workflow run (all-for-opp vs by labs_record_id)."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, required=True)
        parser.add_argument("--opp-id", type=int, required=True)
        parser.add_argument("--access-token")

    def _resolve_token(self) -> str | None:
        # Same resolution eha_pull_raw uses: CLI TokenManager first, then the
        # active dev-server session left behind by /labs/login/.
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

    def _get(self, client, url, params):
        r = client.get(url, params=params)
        r.raise_for_status()
        body = r.json()
        if isinstance(body, dict):
            return body.get("results", body.get("records", [])), body
        return body, {}

    def handle(self, *args, **opts):
        run_id, opp_id = opts["run_id"], opts["opp_id"]
        token = opts.get("access_token") or self._resolve_token()
        if not token:
            self.stderr.write(self.style.ERROR("No token (log in at /labs/login/ on the dev server)."))
            sys.exit(2)

        base = settings.CONNECT_PRODUCTION_URL.rstrip("/")
        url = f"{base}/export/labs_record/"
        with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=120.0) as client:
            # --- B: what the patch does ---
            by_run, raw_b = self._get(
                client, url, {"experiment": "audit", "type": "AuditSession", "labs_record_id": run_id}
            )
            self.stdout.write(self.style.MIGRATE_HEADING("\nB) filtered server-side by labs_record_id=%s" % run_id))
            self.stdout.write("   sessions returned: %d" % len(by_run))
            for k in ("count", "next", "total", "has_more"):
                if isinstance(raw_b, dict) and k in raw_b:
                    self.stdout.write(f"   {k}: {raw_b[k]}")

            # --- A: what the current code does ---
            all_for_opp, raw_a = self._get(
                client, url, {"experiment": "audit", "type": "AuditSession", "opportunity_id": opp_id}
            )
            matching = [r for r in all_for_opp if r.get("labs_record_id") == run_id]
            self.stdout.write(self.style.MIGRATE_HEADING("\nA) all sessions for opp %s, filtered in Python" % opp_id))
            self.stdout.write("   sessions returned by the endpoint: %d" % len(all_for_opp))
            self.stdout.write("   of those, belonging to run %s: %d" % (run_id, len(matching)))
            for k in ("count", "next", "total", "has_more"):
                if isinstance(raw_a, dict) and k in raw_a:
                    self.stdout.write(f"   {k}: {raw_a[k]}")

            # --- does the server-side filter need a scope alongside it? ---
            by_run_scoped, _ = self._get(
                client,
                url,
                {
                    "experiment": "audit",
                    "type": "AuditSession",
                    "labs_record_id": run_id,
                    "opportunity_id": opp_id,
                },
            )
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nB2) labs_record_id={run_id} AND opportunity_id={opp_id}"))
            self.stdout.write("   sessions returned: %d" % len(by_run_scoped))

            # Report the raw response shape once, so a cap/pagination field can't hide.
            self.stdout.write(
                "\n   raw response keys (A): %s" % (sorted(raw_a.keys()) if isinstance(raw_a, dict) else "bare list")
            )

            # --- did the AI actually review anything? Judge on whichever fetch found them. ---
            found = by_run_scoped or by_run or matching
            reviewed = graded = 0
            verdicts: dict[str, int] = {}
            for rec in found:
                data = rec.get("data") or {}
                for vr in (data.get("visit_results") or {}).values():
                    for a in (vr.get("assessments") or {}).values():
                        reviewed += 1
                        ai = a.get("ai_result")
                        if ai:
                            graded += 1
                            verdicts[ai] = verdicts.get(ai, 0) + 1
            self.stdout.write(
                self.style.MIGRATE_HEADING("\nAI review content of run %s (%d sessions)" % (run_id, len(found)))
            )
            self.stdout.write("   assessments: %d  (with an ai_result: %d)" % (reviewed, graded))
            self.stdout.write("   verdicts: %s" % (verdicts or "none"))

            # --- what state is the run itself in, and what do the sessions actually hold? ---
            runs, _ = self._get(client, url, {"experiment": "workflow", "opportunity_id": opp_id})
            run_rec = next((r for r in runs if r.get("id") == run_id), None)
            self.stdout.write(self.style.MIGRATE_HEADING("\nRun record %s" % run_id))
            if not run_rec:
                self.stdout.write("   not found in the workflow records for opp %s" % opp_id)
            else:
                rd = run_rec.get("data") or {}
                self.stdout.write("   type={} status={}".format(run_rec.get("type"), rd.get("status")))
                aj = rd.get("active_job") or {}
                if aj:
                    self.stdout.write(
                        "   active_job: status=%s stage=%s message=%s"
                        % (aj.get("status"), aj.get("stage_name"), str(aj.get("message"))[:120])
                    )
                self.stdout.write("   data keys: %s" % sorted(rd.keys())[:20])

            self.stdout.write(self.style.MIGRATE_HEADING("\nSession anatomy (first 3 of %d)" % len(found)))
            for rec in found[:3]:
                d = rec.get("data") or {}
                vimg = d.get("visit_images") or {}
                n_img = sum(len(v) for v in vimg.values())
                with_reading = 0
                for imgs in vimg.values():
                    for im in imgs:
                        if any(rf.get("value") for rf in (im.get("related_fields") or [])):
                            with_reading += 1
                vres = d.get("visit_results") or {}
                n_ass = sum(len(vr.get("assessments") or {}) for vr in vres.values())
                human = sum(
                    1 for vr in vres.values() for a in (vr.get("assessments") or {}).values() if a.get("result")
                )
                self.stdout.write(
                    "   session %s  status=%s  images=%d (with reading=%d)  assessments=%d (human-marked=%d)"
                    % (rec.get("id"), d.get("status"), n_img, with_reading, n_ass, human)
                )

            # Which image question was audited, across EVERY session — one sample would not be safe
            # to generalise from.
            qcount: dict[str, int] = {}
            rf_empty = rf_valued = 0
            for rec in found:
                for imgs in (rec.get("data") or {}).get("visit_images", {}).values():
                    for im in imgs:
                        q = im.get("question_id") or "(none)"
                        qcount[q] = qcount.get(q, 0) + 1
                        rfs = im.get("related_fields") or []
                        if any(rf.get("value") for rf in rfs):
                            rf_valued += 1
                        else:
                            rf_empty += 1
            self.stdout.write(
                self.style.MIGRATE_HEADING("\nImage questions audited across all %d sessions" % len(found))
            )
            for q, n in sorted(qcount.items(), key=lambda kv: -kv[1]):
                self.stdout.write("   %6d  %s" % (n, q))
            self.stdout.write("   related_fields: %d with a value, %d empty" % (rf_valued, rf_empty))

            # The AI loop skips any image whose related_fields carry no value, so dump one.
            self.stdout.write(self.style.MIGRATE_HEADING("\nrelated_fields on the first image"))
            import json as _json

            for rec in found:
                for imgs in (rec.get("data") or {}).get("visit_images", {}).values():
                    if imgs:
                        im = imgs[0]
                        self.stdout.write("   keys: %s" % sorted(im.keys()))
                        self.stdout.write("   related_fields: %s" % _json.dumps(im.get("related_fields")))
                        self.stdout.write("   question_id: %s" % im.get("question_id"))
                        break
                else:
                    continue
                break

            self.stdout.write(self.style.MIGRATE_HEADING("\nVERDICT"))
            exists = max(len(by_run), len(by_run_scoped), len(matching))
            if exists == 0:
                self.stdout.write(
                    self.style.WARNING(
                        "   No sessions exist for this run by any fetch -> creation produced nothing.\n"
                        "   NOT the listing bug; look at visit selection / sample size."
                    )
                )
            elif len(matching) > max(len(by_run), len(by_run_scoped)):
                self.stdout.write(
                    self.style.ERROR(
                        "   %d sessions exist and the opp-wide fetch DOES surface them, but the\n"
                        "   server-side labs_record_id filter returns %d / %d. The patch's premise\n"
                        "   is WRONG for this run — filtering server-side would HIDE these sessions."
                        % (len(matching), len(by_run), len(by_run_scoped))
                    )
                )
            elif max(len(by_run), len(by_run_scoped)) > len(matching):
                self.stdout.write(
                    self.style.SUCCESS(
                        "   Sessions EXIST (%d) but the opp-wide fetch surfaces only %d.\n"
                        "   -> the listing is the bug; the capped-response theory holds."
                        % (max(len(by_run), len(by_run_scoped)), len(matching))
                    )
                )
            else:
                self.stdout.write("   All fetches agree (%d sessions). This run does not reproduce the bug." % exists)
