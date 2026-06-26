"""
verify_kmc_flw -- exhaustive per-FLW deep-dive against the live data.

Default behaviour (zero-arg): auto-pulls your OAuth token from the most
recent Django session, auto-picks 6-8 FLWs covering every interesting
flag scenario (mortality high/low, late enrollment, danger high/zero,
no referral, plus a control with zero flags), prints exhaustive
breakdowns to stdout, AND writes the same to ``kmc_verify_output.txt``
in the repo root for easy copy-paste.

Usage:

    # Just run it. Make sure you've logged in via /labs/login/ first.
    python manage.py verify_kmc_flw

    # Optional: target specific FLWs.
    python manage.py verify_kmc_flw --username flw_a,flw_b

    # Optional: override token discovery.
    python manage.py verify_kmc_flw --access-token <token>
"""

from __future__ import annotations

import os
import sys
from io import StringIO
from typing import Any

from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.test import RequestFactory
from django.utils import timezone

from commcare_connect.custom_analysis.kmc_audit.constants import KMC_OPPORTUNITY_IDS
from commcare_connect.custom_analysis.kmc_audit.data_access import KMCAuditDataAccess
from commcare_connect.custom_analysis.kmc_audit.flag_logic import (
    MIN_CASES,
    THRESHOLDS,
    _parse_date,
    _row_get,
    compute_case_metrics,
    compute_ds_no_referral_pct,
    compute_enrollment_metrics,
    compute_round_weight_pct,
    compute_temp_copycat_pct,
    compute_weight_metrics,
)

# Order matters: we present output in this order. Each tuple is
# (scenario label shown in output, flag key to look for as True).
AUTO_PICK_SCENARIOS = [
    ("High mortality firing", "flag_mort_high"),
    ("Low mortality firing", "flag_mort_low"),
    ("Late enrollment firing", "flag_enroll"),
    ("High danger sign rate firing", "flag_danger_high"),
    ("Zero danger signs firing", "flag_danger_zero"),
    ("No-referral firing", "flag_ds_no_referral"),
    ("Low avg visits/case firing", "flag_visits"),
    ("Round-weight firing", "flag_round_weight"),
    ("Temp copy-paste firing", "flag_temp_copycat"),
]


class Command(BaseCommand):
    help = "Auto-deep-dive verification of the KMC audit dashboard against live data."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Comma-separated FLW usernames (skip auto-pick).")
        parser.add_argument("--access-token", help="OAuth token (skip auto-discovery).")
        parser.add_argument("--opp-ids", help="Comma-separated KMC opp IDs (default: all 5).")
        parser.add_argument(
            "--output-file",
            default="kmc_verify_output.txt",
            help="File to also write the dump to (default: kmc_verify_output.txt in cwd).",
        )

    def handle(self, *args, **opts):
        # -- Output capture ------------------------------------------------
        # Tee stdout to a file so the user can attach it without re-running.
        captured = StringIO()

        def _w(line: str = ""):
            self.stdout.write(line)
            captured.write(line + "\n")

        self._w = _w

        # -- 1. Resolve OAuth token ----------------------------------------
        token = opts.get("access_token") or self._auto_discover_token()
        if not token:
            self.stderr.write(
                self.style.ERROR(
                    "No OAuth token found. Either:\n"
                    "  - Log in at http://localhost:8001/labs/login/ then re-run, or\n"
                    "  - Pass --access-token <token> explicitly.\n"
                )
            )
            sys.exit(2)
        self.stderr.write(f"OAuth token resolved (last 6 chars: ...{token[-6:]})")

        # -- 2. Resolve opp IDs --------------------------------------------
        if opts.get("opp_ids"):
            try:
                opp_ids = [int(x) for x in opts["opp_ids"].split(",")]
            except ValueError:
                self.stderr.write(self.style.ERROR("--opp-ids must be a comma-separated list of integers."))
                sys.exit(2)
        else:
            opp_ids = list(KMC_OPPORTUNITY_IDS)

        # -- 3. Build the dashboard ----------------------------------------
        self.stderr.write(f"Loading dashboard for opps {opp_ids} (this can take 30-60s) ...")
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {"labs_oauth": {"access_token": token}}
        try:
            data_access = KMCAuditDataAccess(request, opportunity_ids=opp_ids)
            summary = data_access.build_dashboard()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"build_dashboard failed: {e}"))
            sys.exit(3)

        rows = summary.rows
        self.stderr.write(f"Loaded {len(rows)} merged FLW rows.\n")

        # -- 4. Print summary header ---------------------------------------
        _w("=" * 80)
        _w("KMC FLW Audit Dashboard -- Live Data Verification")
        _w("=" * 80)
        _w(f"Generated: {timezone.now().isoformat()}")
        _w(f"Opportunities loaded: {summary.opportunities_loaded}")
        if summary.opportunities_failed:
            _w(f"Opportunities FAILED: {summary.opportunities_failed}")
        _w(f"Total FLWs (merged):    {summary.total_flws}")
        _w(f"FLWs with >=1 flag:     {summary.flws_with_any_flag}")
        _w(f"FLWs with priority:     {summary.flws_with_priority_flag}")
        _w(f"FLWs excluded:          {summary.flws_excluded}")
        _w(f"Total cases (sum):      {summary.total_cases_all}")
        _w(f"Total KMC visits (sum): {summary.total_kmc_visits}")
        _w("")

        # -- 5. Pick FLWs --------------------------------------------------
        if opts.get("username"):
            usernames = [u.strip() for u in opts["username"].split(",") if u.strip()]
            picks = []
            for u in usernames:
                matching = [r for r in rows if r["username"].lower() == u.lower()]
                if not matching:
                    matching = [r for r in rows if u.lower() in (r.get("flw_name") or "").lower()]
                for r in matching:
                    picks.append(("Manual pick", r))
        else:
            picks = self._auto_pick(rows)

        if not picks:
            _w("No FLWs picked. Either no scenarios fired or the auto-pick found nothing.")
            self._save_output(captured.getvalue(), opts["output_file"])
            return

        _w(f"Auto-picked {len(picks)} FLW(s) for deep-dive:\n")
        for label, r in picks:
            _w(f"  * [{label}] {r.get('flw_name') or r['username']} ({r['username']}) -- {r.get('llo')}")
        _w("")

        # -- 5b. DIAGNOSTIC: dump raw visit-row attributes for the first FLW
        # so we can see exactly what fields the SQL pipeline produced. This
        # is what reveals path mismatches (e.g. `weight` is None even though
        # there's a child_weight_visit value buried in the form somewhere).
        if picks:
            self._dump_visit_diagnostic(picks[0][1], data_access)

        # -- 6. Deep-dive each ---------------------------------------------
        for label, row in picks:
            self._dump_flw(label, row, data_access)

        # -- 7. Write file + final note ------------------------------------
        self._save_output(captured.getvalue(), opts["output_file"])

    # ---------------------------------------------------------------------
    # OAuth token auto-discovery
    # ---------------------------------------------------------------------

    def _auto_discover_token(self) -> str | None:
        """Pull the most recent unexpired session that has labs_oauth.access_token."""
        try:
            sessions = Session.objects.filter(expire_date__gte=timezone.now()).order_by("-expire_date")[:20]
        except Exception:
            return None
        for s in sessions:
            try:
                data = s.get_decoded()
            except Exception:
                continue
            tok = (data.get("labs_oauth") or {}).get("access_token")
            if tok:
                return tok
        return None

    # ---------------------------------------------------------------------
    # Auto-pick
    # ---------------------------------------------------------------------

    def _auto_pick(self, rows: list[dict]) -> list[tuple[str, dict]]:
        """Pick one FLW per scenario, plus a zero-flag control."""
        picks: list[tuple[str, dict]] = []
        seen_keys: set[tuple[str, str]] = set()

        for label, flag_key in AUTO_PICK_SCENARIOS:
            candidates = [r for r in rows if (r.get("flags") or {}).get(flag_key) is True]
            # Prefer the FLW with the most cases (more data = better signal)
            candidates.sort(key=lambda r: -(r.get("total_cases") or 0))
            for c in candidates:
                key = (c["username"], c.get("llo") or "")
                if key in seen_keys:
                    continue
                picks.append((label, c))
                seen_keys.add(key)
                break  # one per scenario

        # Add 1 control: an FLW with 0 flags and a healthy case count.
        controls = [
            r
            for r in rows
            if not r.get("excluded") and (r.get("flag_count") or 0) == 0 and (r.get("total_cases") or 0) >= 30
        ]
        controls.sort(key=lambda r: -(r.get("total_cases") or 0))
        for c in controls:
            key = (c["username"], c.get("llo") or "")
            if key not in seen_keys:
                picks.append(("Zero-flag control (sanity check)", c))
                seen_keys.add(key)
                break

        return picks

    # ---------------------------------------------------------------------
    # Visit-row diagnostic — print raw attributes for the first 3 visits of
    # one FLW so we can see what the SQL pipeline is actually producing.
    # ---------------------------------------------------------------------

    def _dump_visit_diagnostic(self, row: dict, data_access: KMCAuditDataAccess):
        u = row["username"]
        visit_rows = self._collect_visits_for_flw(data_access, u)
        if not visit_rows:
            return

        self._w("=" * 80)
        self._w(f"DIAGNOSTIC -- Sample raw visit rows for {row.get('flw_name') or u}")
        self._w(f"(Total visit rows for this FLW across all opps: {len(visit_rows)})")
        self._w("=" * 80)

        # Aggregate stats: how often does each tracked field have a value?
        # If `weight` is None for every row we'll see it here.
        field_keys = [
            "username",
            "beneficiary_case_id",
            "visit_date",
            "visit_number",
            "weight",
            "kmc_status",
            "child_alive",
            "reg_date",
            "discharge_date",
            "danger_sign_positive",
            "child_referred",
            "temperature",
        ]
        non_null_counts: dict[str, int] = {k: 0 for k in field_keys}
        for v in visit_rows:
            for k in field_keys:
                val = _row_get(v, k)
                if val is not None and val != "":
                    non_null_counts[k] += 1

        self._w("\n  Field population (non-null count / total rows):")
        for k in field_keys:
            count = non_null_counts[k]
            pct = (count / len(visit_rows) * 100) if visit_rows else 0
            warn = "  <-- 0% populated, broken path?" if count == 0 and len(visit_rows) > 5 else ""
            self._w(f"    {k:<25} {count:>6} / {len(visit_rows):<6}  ({pct:5.1f}%){warn}")

        # Show first 3 visit rows with all attribute values + any
        # secondary dicts (custom_fields / computed) the row might carry.
        self._w("\n  First 3 visit rows (raw attributes):")
        for i, v in enumerate(visit_rows[:3]):
            self._w(f"\n  --- Visit row {i} ---")
            for k in field_keys:
                val = _row_get(v, k)
                self._w(f"    {k:<25} {val!r}")
            # Surface any dict-shaped extra fields the SQL backend may use.
            if hasattr(v, "computed") and isinstance(v.computed, dict):
                self._w(f"    (computed dict): {dict(list(v.computed.items())[:8])!r}")
            if hasattr(v, "custom_fields") and isinstance(v.custom_fields, dict):
                self._w(f"    (custom_fields): {dict(list(v.custom_fields.items())[:8])!r}")
            # Also list ALL public attributes on the row object so we can spot
            # an alternate name (e.g. child_weight_visit instead of weight).
            attrs = [a for a in dir(v) if not a.startswith("_") and not callable(getattr(v, a, None))]
            attrs_with_values = []
            for a in attrs:
                try:
                    val = getattr(v, a)
                    if isinstance(val, (str, int, float, type(None))) and val not in (None, ""):
                        attrs_with_values.append(f"{a}={val!r}")
                except Exception:
                    pass
            if attrs_with_values:
                self._w(f"    (all public attrs with values): {attrs_with_values[:15]}")

        self._w("")

    # ---------------------------------------------------------------------
    # Per-FLW deep dump
    # ---------------------------------------------------------------------

    def _dump_flw(self, scenario: str, row: dict, data_access: KMCAuditDataAccess):
        u = row["username"]
        name = row.get("flw_name") or u
        llo = row.get("llo") or "?"

        self._w("\n" + "=" * 80)
        self._w(f"  [{scenario}]  {name}  ({u})")
        self._w(f"  LLO: {llo}    Primary opp: {row.get('opportunity_id')}")
        self._w("=" * 80)

        breakdown = row.get("opportunity_breakdown") or []
        if breakdown:
            self._w("\nContributing opportunities:")
            for b in breakdown:
                self._w(
                    f"  opp {b['opportunity_id']:>4} ({b.get('opportunity_name', '?')[:40]}): "
                    f"{b.get('cases', 0)} cases, {b.get('visits', 0)} visits"
                )

        self._w("\nMerged totals:")
        self._kv("total_cases", row.get("total_cases"))
        self._kv("total_visits (kmc_visit_count)", row.get("total_visits"))
        self._kv("closed_cases", row.get("closed_cases"))
        self._kv("deaths", row.get("deaths"))
        self._kv("non_mort_closed", row.get("non_mort_closed"))
        self._kv("excluded?", f"{row.get('excluded')}  (excluded if total_cases < {MIN_CASES['exclude']})")

        visit_rows = self._collect_visits_for_flw(data_access, u)
        if not visit_rows:
            self._w("  (no visit rows available -- drilldown impossible)\n")
            return

        # Flag 1 -- Visits/Case
        cm = compute_case_metrics(visit_rows)
        non_mort_closed = [c for c in cm["cases"] if cm["is_closed"](c) and not cm["is_mortality"](c)]
        sum_visits = sum(c["visit_count"] for c in non_mort_closed)
        avg = sum_visits / len(non_mort_closed) if non_mort_closed else None
        self._section("Flag 1 -- Visits / Case (avg follow-up visits per closed non-mort case)")
        self._kv("Threshold", f"< {THRESHOLDS['visits']}")
        self._kv("Min data", f"{MIN_CASES['visits']} closed non-mortality cases")
        self._kv("Closed non-mort cases", len(non_mort_closed))
        self._kv("Sum follow-up visits", sum_visits)
        if avg is not None:
            self._kv("Avg = sum / count", f"{sum_visits} / {len(non_mort_closed)} = {avg:.3f}")
        self._flag_result("flag_visits", row.get("flags") or {})

        # Flags 2/3 -- Mortality
        deaths = row.get("deaths") or 0
        closed = row.get("closed_cases") or 0
        rate = (deaths / closed) if closed > 0 else None
        self._section("Flags 2 & 3 -- Mortality (deaths / closed_cases)")
        self._kv(
            "Thresholds", f"<{THRESHOLDS['mort_low']*100:.0f}% (low) or >{THRESHOLDS['mort_high']*100:.0f}% (high)"
        )
        self._kv("Min data", f"{MIN_CASES['mort']} closed cases")
        self._kv("Rate", f"{deaths} / {closed} = {(rate*100):.2f}%" if rate is not None else "N/A")
        self._flag_result("flag_mort_low", row.get("flags") or {})
        self._flag_result("flag_mort_high", row.get("flags") or {})
        self._flag_result("flag_mort (synthetic)", row.get("flags") or {}, key="flag_mort")

        # Flag 4 -- Late Enrollment
        compute_enrollment_metrics(visit_rows)  # side-effect only; result used below
        by_case: dict[str, dict] = {}
        for v in visit_rows:
            cid = _row_get(v, "beneficiary_case_id")
            if not cid:
                continue
            cid = str(cid)
            slot = by_case.setdefault(cid, {"reg_date": None, "discharge_date": None})
            rd = _parse_date(_row_get(v, "reg_date"))
            dd = _parse_date(_row_get(v, "discharge_date"))
            if rd and not slot["reg_date"]:
                slot["reg_date"] = rd
            if dd and not slot["discharge_date"]:
                slot["discharge_date"] = dd
        cases_with_dates = [
            (cid, s["reg_date"], s["discharge_date"], (s["reg_date"] - s["discharge_date"]).days)
            for cid, s in by_case.items()
            if s["reg_date"] and s["discharge_date"]
        ]
        late = [c for c in cases_with_dates if c[3] >= 8]
        self._section("Flag 4 -- Late Enrollment (>=8 days between discharge and reg)")
        self._kv("Threshold", f"> {THRESHOLDS['enroll']*100:.0f}%  (user kept March 35%; April canonical 10%)")
        self._kv("Min data", f"{MIN_CASES['enroll']} cases with both dates")
        self._kv("Cases with both dates", len(cases_with_dates))
        self._kv("Late cases (>=8 days)", len(late))
        if cases_with_dates:
            self._kv("Rate", f"{len(late)} / {len(cases_with_dates)} = {len(late)/len(cases_with_dates)*100:.2f}%")
        if cases_with_dates:
            self._w("  Sample first 5 cases:")
            for cid, rd, dd, days in cases_with_dates[:5]:
                tag = "[LATE]" if days >= 8 else "[on-time]"
                self._w(f"    {cid[:14]:<14} discharge={dd} reg={rd} diff={days:>3}d {tag}")
        self._flag_result("flag_enroll", row.get("flags") or {})

        # Flags 5/6 -- Danger Signs
        ds_present = [v for v in visit_rows if _row_get(v, "danger_sign_positive") in ("yes", "no")]
        ds_positive = [v for v in visit_rows if _row_get(v, "danger_sign_positive") == "yes"]
        danger_rate = (row.get("metrics") or {}).get("danger_rate")
        self._section("Flags 5 & 6 -- Danger Sign Rate")
        self._kv(
            "Thresholds", f"high >{THRESHOLDS['danger_high']*100:.0f}%, zero ={THRESHOLDS['danger_zero']*100:.0f}%"
        )
        self._kv("Min data", f"{MIN_CASES['danger_high']} (high) / {MIN_CASES['danger_zero']} (zero) visits")
        self._kv("Visits with field populated", len(ds_present))
        self._kv("Of which 'yes'", len(ds_positive))
        if danger_rate is not None:
            self._kv("Rate (from agg)", f"{danger_rate*100:.2f}%")
        self._flag_result("flag_danger_high", row.get("flags") or {})
        self._flag_result("flag_danger_zero", row.get("flags") or {})

        # Flags 7/8/9 -- Weight Pairs
        wm = compute_weight_metrics(visit_rows)
        self._section("Flags 7, 8, 9 -- Weight Pairs (loss / gain / zero)")
        self._kv("Pair eligibility", "same case, 1-30 days apart, both 500-5000g")
        self._kv("Total valid pairs", wm.get("weight_pairs", 0))
        self._kv("Gain pairs (positive diff)", wm.get("gain_pairs", 0))
        if wm.get("pct_wt_loss") is not None:
            self._kv("Loss rate", f"{wm['pct_wt_loss']*100:.2f}%  (threshold > {THRESHOLDS['wt_loss']*100:.0f}%)")
        if wm.get("mean_daily_gain") is not None:
            self._kv(
                "Mean daily gain", f"{wm['mean_daily_gain']:.2f} g/day  (threshold > {THRESHOLDS['wt_gain']:.0f})"
            )
        if wm.get("pct_wt_zero") is not None:
            self._kv(
                "Zero-change rate", f"{wm['pct_wt_zero']*100:.2f}%  (threshold > {THRESHOLDS['wt_zero']*100:.0f}%)"
            )
        self._flag_result("flag_wt_loss", row.get("flags") or {})
        self._flag_result("flag_wt_gain", row.get("flags") or {})
        self._flag_result("flag_wt_zero", row.get("flags") or {})

        # Flag 13 -- Round Weights
        rw_pct, rw_n = compute_round_weight_pct(visit_rows)
        self._section("Flag 13 -- Round Weights (follow-up only, multiples of 100g)")
        self._kv("Threshold", f">= {THRESHOLDS['round_weight']*100:.0f}%")
        self._kv("Min data", f"{MIN_CASES['round_weight']} valid follow-up weights")
        self._kv("Valid follow-up weights", rw_n)
        if rw_pct is not None:
            self._kv("Rate", f"{rw_pct*100:.2f}%")
        self._flag_result("flag_round_weight", row.get("flags") or {})

        # Flag 12 -- Temp Copy-Paste
        tc_pct, tc_n = compute_temp_copycat_pct(visit_rows)
        self._section("Flag 12 -- Temp Copy-Paste")
        self._kv("Threshold", f"> {THRESHOLDS['temp_copycat']*100:.0f}%")
        self._kv("Min data", f"{MIN_CASES['temp_copycat']} visits with temp")
        self._kv("Visits with temp", tc_n)
        if tc_pct is not None:
            self._kv("Most-common-value rate", f"{tc_pct*100:.2f}%")
        self._flag_result("flag_temp_copycat", row.get("flags") or {})

        # Flag 14 -- DS no referral
        ref_pct, ref_n = compute_ds_no_referral_pct(visit_rows)
        self._section("Flag 14 -- DS+ without referral")
        self._kv("Threshold", f"= {THRESHOLDS['ds_no_referral']*100:.0f}% exactly (i.e. zero referrals)")
        self._kv("Min data", f"{MIN_CASES['ds_no_referral']} DS+ visits")
        self._kv("DS+ visits", ref_n)
        if ref_pct is not None:
            self._kv("Referral rate", f"{ref_pct*100:.2f}%")
        self._flag_result("flag_ds_no_referral", row.get("flags") or {})

        # Data quality flags (now individual, no composite)
        self._section("Data Quality Flags")
        for k in ("flag_round_weight", "flag_hr_copycat", "flag_temp_copycat", "flag_spo2_implausible"):
            self._flag_result(k, row.get("flags") or {})

        # Pending
        self._section("Pending Flags (form path not yet wired -- expect insufficient data)")
        for k in ("flag_ga_fullterm",):
            self._flag_result(k, row.get("flags") or {})

        # Sanity checks
        self._section("Internal Sanity Checks")
        problems = []
        if (row.get("deaths") or 0) > (row.get("closed_cases") or 0):
            problems.append(f"deaths ({row.get('deaths')}) > closed_cases ({row.get('closed_cases')}) -- IMPOSSIBLE")
        if (row.get("non_mort_closed") or 0) + (row.get("deaths") or 0) != (row.get("closed_cases") or 0):
            problems.append(
                f"non_mort_closed ({row.get('non_mort_closed')}) + deaths ({row.get('deaths')}) "
                f"!= closed_cases ({row.get('closed_cases')})"
            )
        if (row.get("total_cases") or 0) < (row.get("closed_cases") or 0):
            problems.append(
                f"total_cases ({row.get('total_cases')}) < closed_cases ({row.get('closed_cases')}) -- IMPOSSIBLE"
            )
        if not problems:
            self._w("  OK: All checks pass.")
        else:
            for p in problems:
                self._w(f"  FAIL: {p}")

        # Final summary
        flags = row.get("flags") or {}
        fired = [k for k, v in flags.items() if v is True]
        passed = [k for k, v in flags.items() if v is False]
        none_flags = [k for k, v in flags.items() if v is None]
        self._section("Final summary for this FLW")
        self._w(f"  Fired ({len(fired)}): {', '.join(fired) or '--'}")
        self._w(f"  Passed ({len(passed)}): {', '.join(passed) or '--'}")
        self._w(f"  Insufficient data ({len(none_flags)}): {', '.join(none_flags) or '--'}")
        self._w(f"  Priority flag count: {row.get('priority_flag_count')}")
        self._w(f"  Total flag count:    {row.get('flag_count')}")
        self._w("")

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _collect_visits_for_flw(self, data_access: KMCAuditDataAccess, username: str) -> list[Any]:
        last = getattr(data_access, "_last_results", {}) or {}
        out = []
        for opp_result in last.values():
            if opp_result.error or not opp_result.visit_result:
                continue
            for v in opp_result.visit_result.rows:
                if (getattr(v, "username", None) or "") == username:
                    out.append(v)
        return out

    def _section(self, title: str):
        self._w("")
        self._w(f"--- {title} ---")

    def _kv(self, key: str, value):
        self._w(f"  {key:<35} {value}")

    def _flag_result(self, label: str, flags: dict, key: str | None = None):
        k = key or label.split(" ")[0]
        v = flags.get(k)
        if v is True:
            tag = "*** FIRED ***"
        elif v is False:
            tag = "pass"
        elif v is None:
            tag = "(insufficient data)"
        else:
            tag = str(v)
        self._w(f"  {label:<35} => {tag}")

    def _save_output(self, content: str, path: str):
        try:
            abspath = os.path.abspath(path)
            with open(abspath, "w", encoding="utf-8") as f:
                f.write(content)
            self.stderr.write(self.style.SUCCESS(f"\n=> Output written to {abspath}"))
            self.stderr.write("Paste the contents back to verify the values.")
        except Exception as e:
            self.stderr.write(self.style.WARNING(f"Could not write output file: {e}"))
