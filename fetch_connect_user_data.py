"""fetch_connect_user_data.py — HEADLESS Connect user_data pull (no browser needed).

The Connect funnel leg (Invited/Accepted/Started-Learn/Completed-Learn/Claimed) used to be a
frozen snapshot because Connect couldn't be pulled headlessly. It CAN: mint a production access
token via the OAuth **refresh-token grant** (the labs app's client id/secret + a refresh token),
then call /export/opportunity/{id}/user_data/ — verified to return scope `export openid` and 200s.

This script mints the token, pulls user_data for every interview cohort (discovered from the opp
catalog by the `[cohort]` name prefix), and writes the consolidated `connect_user_data_snapshot.csv`
that build_master_4src.py already consumes. Runs in the daily CI — closing the last manual leg.

Refresh-token rotation: Connect issues a NEW refresh token on each use (old invalidated). We persist
the new one to a local `.connect_creds.json` AND (in CI, when GH_PAT is set) back to the
`CONNECT_REFRESH_TOKEN` GitHub Actions secret, so the chain survives across runs.

Credentials (env first, else .connect_creds.json):
  CONNECT_REFRESH_TOKEN, CONNECT_OAUTH_CLIENT_ID, CONNECT_OAUTH_CLIENT_SECRET
  GH_PAT (optional; only used to write the rotated token back to the repo secret in CI)

Usage:  python fetch_connect_user_data.py
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8")

BASE = os.environ.get("CONNECT_PRODUCTION_URL", "https://connect.dimagi.com").rstrip("/")
CREDS_FILE = ROOT / ".connect_creds.json"  # local refresh-token store (gitignored)
OUT = ROOT / "connect_user_data_snapshot.csv"
COLS = [
    "cohort_id",
    "username",
    "invited_date",
    "user_invite_status",
    "date_learn_started",
    "completed_learn_date",
    "date_claimed",
]


def _cohort_to_sg(c):
    """Same mapping as build_master_4src.cohort_to_sg (inlined to avoid importing the heavy build)."""
    if not c or c == "1A":
        return None
    c = str(c)
    if "TRS" in c:
        return "TRS"
    if "TRE" in c:
        return "TRE"
    if "ABT1" in c:
        return "ABT1-A" if "A" in c[5:] else "ABT1-B"
    if "ABT2" in c:
        return "ABT2-A" if "A" in c[5:] else "ABT2-B"
    if "ABT3" in c:
        return "ABT3-A" if "A" in c[5:] else "ABT3-B"
    if re.search(r"2WT[CE]\d", c):
        return "2WT"
    if re.search(r"EC[CE]\d", c):  # Extension cohorts: 1ECC1 (COWACDI), 1ECE1 (EHA)
        return "EXT"
    if re.search(r"NPS\d", c):  # NPS cohorts: 1NPS1 (COWACDI only) - before the P[CE]\d Panel pattern
        return "NPS"
    if re.search(r"P[CE]\d", c):
        return "PANEL"
    return None


def _is_test(c):
    return bool(c) and bool(re.search(r"_test", str(c), re.I))


def _creds():
    rt = os.environ.get("CONNECT_REFRESH_TOKEN")
    cid = os.environ.get("CONNECT_OAUTH_CLIENT_ID")
    cs = os.environ.get("CONNECT_OAUTH_CLIENT_SECRET")
    if not (rt and cid and cs) and CREDS_FILE.exists():
        c = json.loads(CREDS_FILE.read_text())
        rt = rt or c.get("refresh_token")
        cid = cid or c.get("client_id")
        cs = cs or c.get("client_secret")
    return rt, cid, cs


def _persist_new_refresh(new_rt):
    """Save the rotated refresh token: local file always; GH secret when GH_PAT is present (CI)."""
    c = json.loads(CREDS_FILE.read_text()) if CREDS_FILE.exists() else {}
    c["refresh_token"] = new_rt
    CREDS_FILE.write_text(json.dumps(c))
    if os.environ.get("GH_PAT"):
        repo = os.environ.get("GITHUB_REPOSITORY", "asidtharthan/connect-labs-AaS")
        try:
            subprocess.run(
                ["gh", "secret", "set", "CONNECT_REFRESH_TOKEN", "--repo", repo],
                input=new_rt,
                text=True,
                check=True,
                env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]},
            )
            print("  rotated refresh token written back to GH secret CONNECT_REFRESH_TOKEN")
        except Exception as e:
            print(f"  WARNING: failed to write rotated refresh token to GH secret: {e}")


def get_access_token():
    rt, cid, cs = _creds()
    if not (rt and cid and cs):
        sys.exit(
            "Missing Connect OAuth creds (CONNECT_REFRESH_TOKEN/CLIENT_ID/CLIENT_SECRET env or .connect_creds.json)"
        )
    r = httpx.post(
        f"{BASE}/o/token/",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "client_id": cid,
            "client_secret": cs,
        },
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    new_rt = j.get("refresh_token")
    if new_rt and new_rt != rt:
        _persist_new_refresh(new_rt)  # rotation — persist before the long pull
    return j["access_token"]


def main():
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(headers=headers, timeout=90.0, follow_redirects=True) as c:
        cat = c.get(f"{BASE}/export/opp_org_program_list/")
        cat.raise_for_status()
        data = cat.json()
        opps = data if isinstance(data, list) else data.get("opportunities", [])
        print(f"opp catalog: {len(opps)} opportunities")
        # Group opps by cohort. Cohort id lives in [brackets] in the opp name — historically
        # at the START ("[1PE1] EHA Interviews"), but newer opps put it at the END
        # ("INT - NG - EHA - 2WT - July26 [2WTE1]"). Scan every bracket group and take the
        # first that maps to a known subgroup — robust to either convention.
        opps_by_cohort = {}
        for opp in opps:
            groups = re.findall(r"\[([^\]]+)\]", opp.get("name", "") or "")
            cohort = next((g.strip() for g in groups if _cohort_to_sg(g.strip()) and not _is_test(g.strip())), None)
            if cohort:
                opps_by_cohort.setdefault(cohort, []).append(opp)
        # A cohort can have MULTIPLE opps (e.g. an empty duplicate + the real one). Pull each and
        # keep the one with the MOST user_data rows so we never bind a cohort to an empty duplicate.
        rows = []
        for cohort, copps in opps_by_cohort.items():
            best, best_opp = [], None
            for opp in copps:
                r = c.get(f"{BASE}/export/opportunity/{opp['id']}/user_data/")
                if r.status_code != 200:
                    print(f"  {cohort} (opp {opp['id']}): user_data {r.status_code} — skipped")
                    continue
                opp_rows = [row for row in csv.DictReader(io.StringIO(r.text)) if (row.get("username") or "").strip()]
                if len(opp_rows) > len(best):
                    best, best_opp = opp_rows, opp["id"]
            for row in best:
                rows.append({col: (cohort if col == "cohort_id" else (row.get(col, "") or "")) for col in COLS})
            suffix = f" (best of {len(copps)} opps)" if len(copps) > 1 else ""
            print(f"  {cohort:10} (opp {best_opp}): +{len(best)} rows{suffix}")
    if not rows:
        sys.exit("No Connect rows pulled — keeping existing snapshot (graceful degrade)")
    seen = {r["cohort_id"] for r in rows}
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT.name}: {len(rows)} rows across {len(seen)} cohorts")


if __name__ == "__main__":
    main()
