"""
verify_kmc_doc — production-data verification command.

Loads the KMC audit dashboard (all 5 opportunities, V1+V2 merged) and
compares the computed values for specific named FLWs against the
"Overview of KMC flags [March 2026]" document's example data tables
(Tables 1-16 in the Follow-on Analysis [April 2026] section).

The doc's examples reference FLWs by integer ID (e.g. "FLW 2328"). We
do not have a stable name-to-ID mapping in this codebase — the dashboard
operates on usernames — so this command:

  1) Builds the dashboard once.
  2) For every FLW row, prints `username | llo | total_cases | closed |
     mortality_rate | avg_visits | flagged_flags`.
  3) Lets the user manually cross-reference the printed values against
     the doc's tables.

If a name-to-FLW-ID mapping becomes available later (e.g. via a
production export), this command can be extended to do automatic
PASS/FAIL diffing against doc-expected values per row.

Usage:

    # Local dev (uses session OAuth token if you've logged in via /labs/login/)
    python manage.py verify_kmc_doc

    # CSV output
    python manage.py verify_kmc_doc --csv > /tmp/kmc_audit_dump.csv

    # Filter to one LLO
    python manage.py verify_kmc_doc --llo PIPN

    # Compare against the doc's known FLW IDs (when name-to-id mapping
    # exists). Doc-expected values for a few highlighted FLWs are stored
    # in DOC_EXPECTATIONS below — add more as your team identifies them.
    python manage.py verify_kmc_doc --check-known
"""

from __future__ import annotations

import csv
import sys
from typing import Any

from django.core.management.base import BaseCommand
from django.test import RequestFactory

from commcare_connect.custom_analysis.kmc_audit.constants import KMC_OPPORTUNITY_IDS
from commcare_connect.custom_analysis.kmc_audit.data_access import KMCAuditDataAccess

# Doc-expected values for specific FLWs from the April Follow-on tables.
# Keys are FLW IDs as printed in the doc; values are the metrics the doc
# claims. Add username mapping when known. None = "not yet mapped to a
# username, can't auto-verify".
#
# Source: Tables 1-16 of the April Follow-on Analysis section.
DOC_EXPECTATIONS: dict[str, dict[str, Any]] = {
    # Flag 1 — Low avg visits per case
    "2208": {"username": None, "llo": "Nama", "closed_cases": 14, "avg_visits": 1.07},
    "2198": {"username": None, "llo": "Nama", "closed_cases": 26, "avg_visits": 1.58},
    "2172": {"username": None, "llo": "Nama", "closed_cases": 15, "avg_visits": 1.80},
    # Flag 2 — Low mortality (zero deaths)
    "2274": {"username": None, "llo": "PIPN", "closed_cases": 47, "mort_rate": 0.0},
    "2252": {"username": None, "llo": "PIPN", "closed_cases": 40, "mort_rate": 0.0},
    "2190": {"username": None, "llo": "Nama", "closed_cases": 28, "mort_rate": 0.0},
    # Flag 3 — High mortality
    "2328": {"username": None, "llo": "PIPN", "closed_cases": 108, "deaths": 35, "mort_rate": 0.324},
    "5030": {"username": None, "llo": "PIPN", "closed_cases": 113, "deaths": 24, "mort_rate": 0.212},
    "4193": {"username": None, "llo": "PIPN", "closed_cases": 67, "deaths": 14, "mort_rate": 0.209},
    # Flag 4 — Late enrollment (>10% per April canonical; we use 35% per user pref)
    "2262": {"username": None, "llo": "PIPN", "cases_with_dates": 28, "pct_late_enroll": 0.821},
    # Flag 5 — High danger sign rate
    "4841": {"username": None, "llo": "PIPN", "danger_visit_count": 69, "danger_rate": 0.884},
    # Flag 9 — Zero weight change
    # 2208 already in flag_1; add zero_change_pairs
    # Flag 13 — Round weights 100%
    "2283": {"username": None, "llo": "PIPN", "weight_pairs": 98, "round_weight_pct": 1.0},
    # Flag 14 — DS no referral
    "2251": {"username": None, "llo": "PIPN", "ds_positive_visits": 672, "ds_no_referral_pct": 0.0},
}


class Command(BaseCommand):
    help = (
        "Print the KMC audit dashboard rows so values can be"
        " cross-referenced with the March/April KMC flags doc tables."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--llo",
            choices=("NAMA", "PIPN", "GHI"),
            help="Filter to a single LLO.",
        )
        parser.add_argument(
            "--csv",
            action="store_true",
            help="Print as CSV (suitable for redirecting to a file).",
        )
        parser.add_argument(
            "--check-known",
            action="store_true",
            help="Auto-compare against DOC_EXPECTATIONS for any FLW with a known username mapping.",
        )
        parser.add_argument(
            "--access-token",
            help="Override the session OAuth token (if running outside an authenticated session).",
        )
        parser.add_argument(
            "--opp-ids",
            help="Comma-separated KMC opportunity IDs to load (default: all 5).",
        )

    def handle(self, *args, **opts):
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}

        if opts.get("access_token"):
            request.session["labs_oauth"] = {"access_token": opts["access_token"]}
        else:
            self.stderr.write(
                self.style.WARNING(
                    "No --access-token provided. The pipeline call will fail unless this command "
                    "runs with a valid session OAuth token (e.g. via /labs/login/ in the same shell)."
                )
            )
            request.session["labs_oauth"] = {}

        if opts.get("opp_ids"):
            try:
                opp_ids = [int(x) for x in opts["opp_ids"].split(",")]
            except ValueError:
                self.stderr.write(self.style.ERROR("--opp-ids must be a comma-separated list of integers."))
                sys.exit(2)
        else:
            opp_ids = list(KMC_OPPORTUNITY_IDS)

        self.stderr.write(f"Loading dashboard for opportunities: {opp_ids}")
        try:
            data_access = KMCAuditDataAccess(request, opportunity_ids=opp_ids)
            summary = data_access.build_dashboard()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"build_dashboard failed: {e}"))
            sys.exit(3)

        rows = summary.rows
        if opts.get("llo"):
            rows = [r for r in rows if r["llo"] == opts["llo"]]
        rows.sort(key=lambda r: (-r.get("flag_count", 0), (r.get("flw_name") or r["username"]).lower()))

        # Print summary header
        self.stderr.write(
            self.style.SUCCESS(
                f"\nLoaded {len(rows)} rows. "
                f"Total FLWs: {summary.total_flws}, "
                f"with ≥1 flag: {summary.flws_with_any_flag}, "
                f"total cases: {summary.total_cases_all}, "
                f"total visits: {summary.total_kmc_visits}\n"
            )
        )

        if opts.get("csv"):
            self._print_csv(rows)
        else:
            self._print_table(rows)

        if opts.get("check_known"):
            self._check_known(rows)

    def _print_table(self, rows: list[dict]):
        cols = [
            ("LLO", "llo", 5),
            ("Username", "username", 24),
            ("FLW Name", "flw_name", 28),
            ("TotalCases", "total_cases", 11),
            ("ClosedCases", "closed_cases", 12),
            ("Deaths", "deaths", 7),
            ("AvgVisits", "avg_visits", 10),
            ("Mort%", "mort_rate", 8),
            ("Danger%", "danger_rate", 9),
            ("LateEnr%", "pct_late_enroll", 9),
            ("Excluded", "excluded", 9),
            ("FlagCount", "flag_count", 10),
            ("Flags", "_flags_str", 60),
        ]
        header = "  ".join(f"{c[0]:<{c[2]}}" for c in cols)
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for row in rows:
            row["_flags_str"] = ",".join(k for k, v in (row.get("flags") or {}).items() if v is True) or "—"
            line = "  ".join(self._fmt_cell(row.get(c[1]), c[1], c[2]) for c in cols)
            self.stdout.write(line)

    def _print_csv(self, rows: list[dict]):
        writer = csv.writer(self.stdout)
        writer.writerow(
            [
                "username",
                "flw_name",
                "llo",
                "opp_ids",
                "total_cases",
                "closed_cases",
                "non_mort_closed",
                "deaths",
                "avg_visits",
                "mort_rate",
                "danger_rate",
                "pct_late_enroll",
                "pct_wt_loss",
                "mean_daily_gain",
                "pct_wt_zero",
                "weight_pairs",
                "round_weight_pct",
                "temp_copycat_pct",
                "ds_no_referral_pct",
                "excluded",
                "flag_count",
                "priority_flag_count",
                "flags_fired",
            ]
        )
        for r in rows:
            metrics = r.get("metrics", {})
            flags = r.get("flags") or {}
            writer.writerow(
                [
                    r["username"],
                    r.get("flw_name"),
                    r["llo"],
                    "+".join(str(o) for o in r.get("opportunity_ids") or []),
                    r.get("total_cases"),
                    r.get("closed_cases"),
                    r.get("non_mort_closed"),
                    r.get("deaths"),
                    r.get("avg_visits"),
                    r.get("mort_rate"),
                    r.get("danger_rate"),
                    r.get("pct_late_enroll"),
                    r.get("pct_wt_loss"),
                    r.get("mean_daily_gain"),
                    r.get("pct_wt_zero"),
                    r.get("weight_pairs"),
                    metrics.get("round_weight_pct"),
                    metrics.get("temp_copycat_pct"),
                    metrics.get("ds_no_referral_pct"),
                    r.get("excluded"),
                    r.get("flag_count"),
                    r.get("priority_flag_count"),
                    ",".join(k for k, v in flags.items() if v is True),
                ]
            )

    def _check_known(self, rows: list[dict]):
        self.stdout.write("\n=== Known FLW comparisons against doc expectations ===\n")
        index = {(r.get("flw_name") or r["username"]).lower(): r for r in rows}
        index.update({r["username"].lower(): r for r in rows})

        passed = 0
        failed = 0
        skipped = 0

        for flw_id, expected in DOC_EXPECTATIONS.items():
            uname = expected.get("username")
            if not uname:
                self.stdout.write(
                    f"FLW {flw_id} ({expected.get('llo', '?')}): username mapping not yet known — SKIPPED"
                )
                skipped += 1
                continue
            row = index.get(uname.lower())
            if not row:
                self.stdout.write(f"FLW {flw_id} ({uname}): NOT FOUND in dashboard rows — FAIL")
                failed += 1
                continue
            diffs = []
            for k, v in expected.items():
                if k in {"username", "llo"}:
                    if k == "llo" and row.get("llo") != v:
                        diffs.append(f"llo expected {v}, got {row.get('llo')}")
                    continue
                actual = row.get(k)
                if actual is None:
                    diffs.append(f"{k} is None (insufficient data?)")
                    continue
                if isinstance(v, float):
                    if abs(actual - v) > 0.01:
                        diffs.append(f"{k}: expected ≈{v}, got {actual:.3f}")
                else:
                    if actual != v:
                        diffs.append(f"{k}: expected {v}, got {actual}")
            if diffs:
                self.stdout.write(self.style.ERROR(f"FLW {flw_id} ({uname}): FAIL"))
                for d in diffs:
                    self.stdout.write(f"  - {d}")
                failed += 1
            else:
                self.stdout.write(self.style.SUCCESS(f"FLW {flw_id} ({uname}): PASS"))
                passed += 1

        total = passed + failed + skipped
        self.stdout.write(
            f"\nSummary: {passed} pass, {failed} fail, {skipped} skipped (mapping unknown). Total: {total}"
        )

    @staticmethod
    def _fmt_cell(value, key: str, width: int) -> str:
        if value is None:
            s = "—"
        elif isinstance(value, bool):
            s = "yes" if value else "no"
        elif isinstance(value, float):
            if key in {
                "mort_rate",
                "danger_rate",
                "pct_late_enroll",
                "pct_wt_loss",
                "pct_wt_zero",
                "round_weight_pct",
                "temp_copycat_pct",
                "ds_no_referral_pct",
            }:
                s = f"{value*100:.1f}%"
            else:
                s = f"{value:.2f}"
        else:
            s = str(value)
        if len(s) > width:
            s = s[: width - 1] + "…"
        return f"{s:<{width}}"
