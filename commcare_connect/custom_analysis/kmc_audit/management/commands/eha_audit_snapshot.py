"""
eha_audit_snapshot -- one-time data-quality snapshot of the EHA KMC program.

Runs the full 16-flag KMC audit engine plus net-new pattern analyses
(weight distribution, days-between-visits, early discharge, 45-day
weight-gain-by-class) against the live EHA opportunity (default 1236) and
writes a Markdown report + backing CSV/JSON to an export folder.

Read-only against production (pulls via the analysis backend's /export/
calls); the only writes are local report files.

Usage:

    # Token auto-resolved from ~/.claude.json connect_labs PAT, else a
    # recent Django session, else pass it explicitly.
    python manage.py eha_audit_snapshot
    python manage.py eha_audit_snapshot --opp-id 1236 --access-token <token>
    python manage.py eha_audit_snapshot --out-dir dashboard_export_eha_20260625
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.test import RequestFactory
from django.utils import timezone

from commcare_connect.custom_analysis.kmc_audit import eha_analysis
from commcare_connect.custom_analysis.kmc_audit.constants import opportunity_name
from commcare_connect.custom_analysis.kmc_audit.data_access import KMCAuditDataAccess
from commcare_connect.custom_analysis.kmc_audit.flag_logic import (
    ALL_FLAGS,
    FLAG_LABELS,
    FLAG_THRESHOLD_DISPLAY,
    MIN_CASES,
    _row_get,
)

# Visit-row fields dumped to visits.csv (matches the pipeline schema).
_VISIT_FIELDS = [
    "username",
    "beneficiary_case_id",
    "visit_date",
    "visit_number",
    "weight",
    "reg_date",
    "discharge_date",
    "kmc_status",
    "child_alive",
    "danger_sign_positive",
    "child_referred",
    "temperature",
    "heart_rate",
    "spo2_level",
    "gps",
]

# Aggregated-row review fields (present on the FLW aggregated pipeline rows).
_AGG_REVIEW_FIELDS = [
    "total_visits",
    "approved_visits",
    "pending_visits",
    "rejected_visits",
    "flagged_visits",
    "first_visit_date",
    "last_visit_date",
    "days_active",
]


class Command(BaseCommand):
    help = "One-time EHA KMC data-quality snapshot (flags + patterns + weight-gain)."

    def add_arguments(self, parser):
        parser.add_argument("--opp-id", type=int, default=1236, help="EHA KMC opportunity id (default 1236).")
        parser.add_argument("--access-token", help="OAuth/PAT token (skip auto-discovery).")
        parser.add_argument("--out-dir", help="Output directory (default dashboard_export_eha_<date>).")
        parser.add_argument(
            "--expect-visits", type=int, default=1199, help="Expected visit-row count (completeness gate; 0=skip)."
        )
        parser.add_argument(
            "--expect-flws", type=int, default=10, help="Expected aggregated FLW-row count (gate; 0=skip)."
        )

    def handle(self, *args, **opts):
        opp_id = opts["opp_id"]
        token = opts.get("access_token") or self._resolve_token()
        if not token:
            self.stderr.write(
                self.style.ERROR(
                    "No token. Pass --access-token, log in at /labs/login/, or ensure the "
                    "connect_labs PAT is in ~/.claude.json."
                )
            )
            raise SystemExit(2)
        self.stderr.write(f"Token resolved (...{token[-6:]}). Loading opp {opp_id} (30-60s cold) ...")

        # -- Run the engine -------------------------------------------------
        request = RequestFactory().get("/")
        request.session = {"labs_oauth": {"access_token": token}}
        da = KMCAuditDataAccess(request, opportunity_ids=[opp_id])
        if opp_id not in da.opportunity_ids:
            self.stderr.write(
                self.style.ERROR(f"Opp {opp_id} was dropped (not in KMC_OPPORTUNITIES). Add it to constants.py.")
            )
            raise SystemExit(2)
        summary = da.build_dashboard()

        opp_result = (getattr(da, "_last_results", {}) or {}).get(opp_id)
        if opp_result is None or opp_result.error:
            err = opp_result.error if opp_result else "no result"
            self.stderr.write(self.style.ERROR(f"Pipeline failed for opp {opp_id}: {err}"))
            raise SystemExit(3)

        visit_rows = list(opp_result.visit_result.rows) if opp_result.visit_result else []
        agg_rows = list(opp_result.flw_aggregated.rows) if opp_result.flw_aggregated else []

        # -- Completeness gates --------------------------------------------
        self.stderr.write(f"Pulled {len(visit_rows)} visit rows, {len(agg_rows)} FLW rows.")
        if opts["expect_visits"] and len(visit_rows) != opts["expect_visits"]:
            self.stderr.write(
                self.style.WARNING(
                    f"Visit-row count {len(visit_rows)} != expected {opts['expect_visits']}. "
                    "Data may have grown since the plan, or the pull is partial. Continuing — verify."
                )
            )
        if opts["expect_flws"] and len(agg_rows) != opts["expect_flws"]:
            self.stderr.write(self.style.WARNING(f"FLW-row count {len(agg_rows)} != expected {opts['expect_flws']}."))

        # -- Net-new analyses ----------------------------------------------
        wdist = eha_analysis.weight_distribution(visit_rows)
        dbv = eha_analysis.days_between_visits(visit_rows)
        edis = eha_analysis.early_discharge(visit_rows)
        wgain = eha_analysis.weight_gain_by_class_45d(visit_rows)

        # -- Output dir -----------------------------------------------------
        out_dir = Path(opts.get("out_dir") or f"dashboard_export_eha_{timezone.now():%Y%m%d}")
        out_dir.mkdir(parents=True, exist_ok=True)

        agg_review = self._agg_review_rollup(agg_rows)
        self._write_visits_csv(out_dir, visit_rows)
        self._write_flws_csv(out_dir, summary.rows, agg_rows)
        self._write_weight_gain_csv(out_dir, wgain)
        self._write_weight_dist_csv(out_dir, wdist)
        report = self._build_report(opp_id, summary, agg_rows, agg_review, wdist, dbv, edis, wgain, len(visit_rows))
        (out_dir / "EHA_KMC_AUDIT_SNAPSHOT.md").write_text(report, encoding="utf-8")
        (out_dir / "summary.json").write_text(
            json.dumps(
                {
                    "opportunity_id": opp_id,
                    "generated": timezone.now().isoformat(),
                    "visit_rows": len(visit_rows),
                    "flw_rows": len(agg_rows),
                    "summary": {
                        "total_flws": summary.total_flws,
                        "flws_with_any_flag": summary.flws_with_any_flag,
                        "flws_with_priority_flag": summary.flws_with_priority_flag,
                        "flws_excluded": summary.flws_excluded,
                        "total_cases_all": summary.total_cases_all,
                        "total_kmc_visits": summary.total_kmc_visits,
                    },
                    "agg_review": agg_review,
                    "weight_distribution": wdist,
                    "days_between_visits": dbv,
                    "early_discharge": edis,
                    "weight_gain_by_class_45d": wgain,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        self.stderr.write(self.style.SUCCESS(f"\n=> Snapshot written to {out_dir.resolve()}"))
        self.stderr.write(
            "Files: EHA_KMC_AUDIT_SNAPSHOT.md, flws.csv, visits.csv, "
            "weight_gain_by_class.csv, weight_distribution.csv, summary.json"
        )

    # ----------------------------------------------------------------------
    # Token resolution
    # ----------------------------------------------------------------------

    def _resolve_token(self) -> str | None:
        """Resolve a Connect OAuth access token valid for the production /export/ API.

        NOTE: the connect_labs MCP PAT in ~/.claude.json authenticates the MCP
        transport only and 401s on /export/ — it is NOT used here. A real
        export-scoped OAuth token is obtained via `manage.py get_cli_token`
        (saved to ~/.commcare-connect/token.json) or a labs web-session login.
        """
        # 1. CLI token file written by `get_cli_token` (real, export-scoped).
        try:
            from commcare_connect.labs.integrations.connect.cli import TokenManager

            tok = TokenManager().get_valid_token()
            if tok:
                return tok
        except Exception:
            pass
        # 2. Most recent unexpired Django session with a labs token.
        try:
            from django.contrib.sessions.models import Session

            for s in Session.objects.filter(expire_date__gte=timezone.now()).order_by("-expire_date")[:20]:
                tok = (s.get_decoded().get("labs_oauth") or {}).get("access_token")
                if tok:
                    return tok
        except Exception:
            pass
        return None

    # ----------------------------------------------------------------------
    # Aggregated review-status rollup (approval/rejection quality signal)
    # ----------------------------------------------------------------------

    def _agg_review_rollup(self, agg_rows: list[Any]) -> dict[str, Any]:
        totals = {
            k: 0 for k in ("total_visits", "approved_visits", "pending_visits", "rejected_visits", "flagged_visits")
        }
        for r in agg_rows:
            for k in totals:
                totals[k] += int(_row_get(r, k) or 0)
        tv = totals["total_visits"] or 0
        return {
            **totals,
            "approved_pct": round(100 * totals["approved_visits"] / tv, 1) if tv else None,
            "rejected_pct": round(100 * totals["rejected_visits"] / tv, 1) if tv else None,
            "flagged_pct": round(100 * totals["flagged_visits"] / tv, 1) if tv else None,
        }

    # ----------------------------------------------------------------------
    # CSV writers
    # ----------------------------------------------------------------------

    def _write_visits_csv(self, out_dir: Path, visit_rows: list[Any]):
        with (out_dir / "visits.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(_VISIT_FIELDS)
            for v in visit_rows:
                w.writerow([_row_get(v, k) for k in _VISIT_FIELDS])

    def _write_flws_csv(self, out_dir: Path, rows: list[dict], agg_rows: list[Any]):
        agg_by_user = {(_row_get(r, "username") or ""): r for r in agg_rows}
        metric_keys = [
            "avg_visits",
            "mort_rate",
            "danger_rate",
            "pct_late_enroll",
            "pct_wt_loss",
            "mean_daily_gain",
            "pct_wt_zero",
            "round_weight_pct",
            "hr_copycat_pct",
            "temp_copycat_pct",
            "spo2_implausible_pct",
            "gps_same_case_far_pct",
            "ds_no_referral_pct",
        ]
        header = (
            [
                "username",
                "flw_name",
                "total_cases",
                "total_visits",
                "closed_cases",
                "deaths",
                "excluded",
                "flag_count",
                "priority_flag_count",
            ]
            + _AGG_REVIEW_FIELDS
            + list(ALL_FLAGS)
            + metric_keys
        )
        with (out_dir / "flws.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            for r in rows:
                flags = r.get("flags") or {}
                metrics = r.get("metrics") or {}
                agg = agg_by_user.get(r["username"])
                w.writerow(
                    [
                        r["username"],
                        r.get("flw_name"),
                        r.get("total_cases"),
                        r.get("total_visits"),
                        r.get("closed_cases"),
                        r.get("deaths"),
                        r.get("excluded"),
                        r.get("flag_count"),
                        r.get("priority_flag_count"),
                    ]
                    + [(_row_get(agg, k) if agg is not None else None) for k in _AGG_REVIEW_FIELDS]
                    + [self._flag_cell(flags.get(fk)) for fk in ALL_FLAGS]
                    + [metrics.get(mk) for mk in metric_keys]
                )

    def _write_weight_gain_csv(self, out_dir: Path, wgain: dict):
        with (out_dir / "weight_gain_by_class.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["weight_class", "n_infants", "mean_g_per_day", "median_g_per_day", "min", "max"])
            for label, st in wgain["by_class"].items():
                w.writerow([label, st["n"], st["mean"], st["median"], st["min"], st["max"]])

    def _write_weight_dist_csv(self, out_dir: Path, wdist: dict):
        with (out_dir / "weight_distribution.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["weight_class", "count", "pct_of_classified"])
            for label, _, _ in eha_analysis.WEIGHT_CLASSES:
                w.writerow([label, wdist["program_counts"][label], wdist["program_pct"][label]])
            w.writerow(["unknown", wdist["program_counts"]["unknown"], None])

    # ----------------------------------------------------------------------
    # Report builder
    # ----------------------------------------------------------------------

    @staticmethod
    def _flag_cell(v: bool | None) -> str:
        return "FIRED" if v is True else ("pass" if v is False else "n/a")

    @staticmethod
    def _fmt(v: Any, pct: bool = False, dp: int = 1) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v*100:.{dp}f}%" if pct else f"{v:.{dp}f}"
        return str(v)

    def _build_report(self, opp_id, summary, agg_rows, agg_review, wdist, dbv, edis, wgain, n_visits) -> str:
        L: list[str] = []
        L.append("# EHA KMC Data-Quality Audit Snapshot")
        L.append("")
        L.append(f"**Opportunity:** {opp_id} — {opportunity_name(opp_id)}  ")
        L.append(f"**Generated:** {timezone.now():%Y-%m-%d %H:%M UTC}  ")
        L.append("**Source:** live Connect/CommCare (domain `connect-kmc-eha`), read-only pull  ")
        L.append("")
        L.append(
            "> **Read this first.** This is a small, young dataset "
            f"({summary.total_flws} FLWs, {n_visits} visits). Many flags require 20–30 events, "
            "so several read **insufficient data** rather than fire/pass — *absence of a flag is "
            "not proof of clean data*. Flags that DO fire are meaningful. FLWs with <20 cases are "
            "excluded by the engine and reported separately."
        )
        L.append("")

        # Program rollup
        L.append("## 1. Program roll-up")
        L.append("")
        L.append(
            f"- FLWs (total): **{summary.total_flws}**, with ≥1 flag: **{summary.flws_with_any_flag}**, "
            f"with a priority flag: **{summary.flws_with_priority_flag}**, excluded (<{MIN_CASES['exclude']} cases): "
            f"**{summary.flws_excluded}**"
        )
        L.append(
            f"- Infant cases (sum): **{summary.total_cases_all}** · KMC follow-up visits (sum): "
            f"**{summary.total_kmc_visits}** · visit rows pulled: **{n_visits}**"
        )
        L.append(
            f"- Visit review status — approved **{agg_review['approved_pct']}%**, "
            f"pending {self._fmt(agg_review.get('pending_visits'))}, "
            f"rejected **{agg_review['rejected_pct']}%**, flagged **{agg_review['flagged_pct']}%** "
            f"(of {agg_review['total_visits']} submitted)"
        )
        L.append("")

        # Per-FLW flag matrix
        L.append("## 2. Per-FLW flag matrix")
        L.append("")
        L.append(
            "Legend: **FIRED** = threshold breached · pass = within range · n/a = insufficient data. "
            "Flag codes below the table."
        )
        L.append("")
        codes = {fk: f"F{i+1}" for i, fk in enumerate(ALL_FLAGS)}
        header = "| FLW | Cases | Vis | Excl | " + " | ".join(codes[fk] for fk in ALL_FLAGS) + " |"
        sep = "|" + "---|" * (4 + len(ALL_FLAGS))
        L.append(header)
        L.append(sep)
        for r in sorted(summary.rows, key=lambda x: -(x.get("total_cases") or 0)):
            flags = r.get("flags") or {}
            cells = " | ".join(self._flag_cell(flags.get(fk)) for fk in ALL_FLAGS)
            name = (r.get("flw_name") or r["username"])[:18]
            L.append(
                f"| {name} | {r.get('total_cases')} | {r.get('total_visits')} | "
                f"{'Y' if r.get('excluded') else ''} | {cells} |"
            )
        L.append("")
        L.append(
            "**Flag codes:** "
            + " · ".join(
                f"{codes[fk]}={FLAG_LABELS.get(fk, fk)} " f"({FLAG_THRESHOLD_DISPLAY.get(fk, '')})" for fk in ALL_FLAGS
            )
        )
        L.append("")

        # Flag firing tally
        L.append("### Flag firing tally (across FLWs)")
        L.append("")
        L.append("| Flag | Fired | Pass | Insufficient |")
        L.append("|---|---|---|---|")
        for fk in ALL_FLAGS:
            fired = sum(1 for r in summary.rows if (r.get("flags") or {}).get(fk) is True)
            passed = sum(1 for r in summary.rows if (r.get("flags") or {}).get(fk) is False)
            na = sum(1 for r in summary.rows if (r.get("flags") or {}).get(fk) is None)
            L.append(f"| {FLAG_LABELS.get(fk, fk)} | {fired} | {passed} | {na} |")
        L.append("")

        # Weight distribution
        L.append("## 3. Enrolled-infant weight distribution")
        L.append("")
        ws = wdist["enrollment_weight_stats_g"]
        L.append(
            f"Enrollment weight (earliest valid reading per infant), n={wdist['classified_infants']} classified "
            f"of {wdist['total_infants']} infants. "
            f"Mean {self._fmt(ws['mean'])} g, median {self._fmt(ws['median'])} g, "
            f"range {self._fmt(ws['min'])}–{self._fmt(ws['max'])} g."
        )
        L.append("")
        L.append("| Weight class | Count | % of classified |")
        L.append("|---|---|---|")
        for label, _, _ in eha_analysis.WEIGHT_CLASSES:
            L.append(f"| {label} g | {wdist['program_counts'][label]} | {self._fmt(wdist['program_pct'][label])}% |")
        L.append(f"| unknown/no weight | {wdist['program_counts']['unknown']} | — |")
        L.append("")

        # Days between visits
        L.append("## 4. Days between visits")
        L.append("")
        p = dbv["program"]
        L.append(
            f"Program-wide gap between consecutive visits: mean **{self._fmt(p['mean'])}** days, "
            f"median **{self._fmt(p['median'])}**, range {self._fmt(p['min'])}–{self._fmt(p['max'])} "
            f"(n={p['n']} gaps)."
        )
        L.append("")
        L.append("| FLW | n gaps | mean days | median days |")
        L.append("|---|---|---|---|")
        for u, st in sorted(dbv["per_flw"].items(), key=lambda kv: (kv[1]["mean"] or 0)):
            L.append(f"| {u[:18]} | {st['n']} | {self._fmt(st['mean'])} | {self._fmt(st['median'])} |")
        L.append("")

        # Early discharge
        L.append("## 5. Early discharge (two definitions)")
        L.append("")
        da_ = edis["definition_a"]
        db_ = edis["definition_b"]
        dd = edis["days_to_discharge_stats"]
        L.append(
            f"Discharged cases: **{edis['discharged_cases']}** of {edis['total_cases']} total cases. "
            f"Days reg→last-visit for discharged cases: "
            f"mean {self._fmt(dd['mean'])}, median {self._fmt(dd['median'])}, "
            f"range {self._fmt(dd['min'])}–{self._fmt(dd['max'])}."
        )
        L.append("")
        L.append(
            f"- **Definition A** ({da_['label']}): **{da_['early']}/{da_['denom']}** = "
            f"**{self._fmt(da_['rate_pct'])}%**"
        )
        L.append(
            f"- **Definition B** ({db_['label']}): **{db_['early']}/{db_['denom']}** = "
            f"**{self._fmt(db_['rate_pct'])}%**"
        )
        L.append("")
        L.append(
            "_Note: there is no explicit program-discharge timestamp in the form; time-to-discharge "
            "is approximated by registration → last-visit span. reg_date is the program registration "
            "date (distinct from the hospital `discharge_date` field used by the late-enrollment flag)._"
        )
        L.append("")

        # Bonus weight gain
        L.append("## 6. BONUS — average weight gain by class (0–45 days post-registration)")
        L.append("")
        L.append(
            f"Per-baby average daily gain over valid pairs (1–30 days apart, both 500–5000 g), within "
            f"{wgain['window_days']} days of registration. Infants with gain data: "
            f"**{wgain['infants_with_gain_data']}** (skipped, no reg_date: {wgain['skipped_no_reg_date']})."
        )
        L.append("")
        L.append("| Weight class | n infants | mean g/day | median g/day | min | max |")
        L.append("|---|---|---|---|---|---|")
        for label, st in wgain["by_class"].items():
            L.append(
                f"| {label} g | {st['n']} | {self._fmt(st['mean'])} | {self._fmt(st['median'])} | "
                f"{self._fmt(st['min'])} | {self._fmt(st['max'])} |"
            )
        L.append("")
        L.append(
            "_Healthy preterm/low-birth-weight gain is roughly 15–30 g/day; very high values (>60 g/day) "
            "feed the `flag_wt_gain` fabrication signal._"
        )
        L.append("")

        # Auto observations
        L.append("## 7. Observations (auto-generated)")
        L.append("")
        for obs in self._auto_observations(summary, agg_review, wdist, dbv, edis, wgain):
            L.append(f"- {obs}")
        L.append("")
        L.append(
            "_A narrative data-quality / fraud-likelihood verdict accompanies this file in the "
            "delivery message; numbers above are the evidence base._"
        )
        return "\n".join(L)

    def _auto_observations(self, summary, agg_review, wdist, dbv, edis, wgain) -> list[str]:
        obs: list[str] = []
        # Flag concentration
        fired_flags = {}
        for r in summary.rows:
            for fk, v in (r.get("flags") or {}).items():
                if v is True and fk in ALL_FLAGS:
                    fired_flags[fk] = fired_flags.get(fk, 0) + 1
        if fired_flags:
            top = sorted(fired_flags.items(), key=lambda kv: -kv[1])
            obs.append("Flags firing across FLWs: " + ", ".join(f"{FLAG_LABELS.get(k, k)} ×{n}" for k, n in top) + ".")
        else:
            obs.append("No flags fired on any FLW (note: small sample — many flags are underpowered here).")
        # Review status
        if agg_review.get("rejected_pct"):
            obs.append(
                f"Reviewers rejected {agg_review['rejected_pct']}% and flagged "
                f"{agg_review['flagged_pct']}% of submitted visits — active QA is happening on the program."
            )
        # Weight distribution skew
        prog = wdist["program_pct"]
        skew = max((p for p in prog.values() if p is not None), default=None)
        if skew is not None and skew >= 60:
            dominant = next(k for k, v in prog.items() if v == skew)
            obs.append(
                f"Enrollment weights concentrate in the {dominant} g class ({skew}% of classified infants) "
                "— check whether FLWs are selectively enrolling one category."
            )
        # Days between visits outliers
        dist = dbv["per_flw_mean_distribution"]
        if (
            dist["n"]
            and dist["max"] is not None
            and dist["min"] is not None
            and dist["max"] >= 2 * max(dist["min"], 1)
        ):
            obs.append(
                f"Per-FLW mean visit gap ranges {self._fmt(dist['min'])}–{self._fmt(dist['max'])} days — "
                "wide spread; the high end may indicate irregular follow-up."
            )
        # Early discharge
        a = edis["definition_a"]["rate_pct"]
        if a is not None and a >= 20:
            obs.append(
                f"{a}% of discharged cases closed within 7 days of registration — investigate premature closure."
            )
        # Weight gain sanity
        for label, st in wgain["by_class"].items():
            if st["mean"] is not None and st["mean"] > 60:
                obs.append(
                    f"Mean daily gain for {label} g class is {self._fmt(st['mean'])} g/day (>60) — "
                    "implausibly high, a fabrication signal."
                )
        return obs
