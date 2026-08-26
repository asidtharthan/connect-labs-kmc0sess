"""pull_hq_user_cases.py — pull the `untrained_flw` flag per FLW from CommCare HQ.

`untrained_flw` is a property on the **commcare-user usercase** (NOT in form submissions),
so it needs a Case-API pull. The usercase's `username` property IS the Connect `connect_id`
(verified: form.connect_id == form.meta.username == usercase.properties.username), so we key
the flag by connect_id and the dashboard build joins it straight onto the FLW rows.

Headless: uses HQ_API_KEY/HQ_USERNAME (env) or .hq_creds.json — same creds as the form pull,
so this runs in the daily CI with no browser step.

Output: _untrained_flw.json = {connect_id: true, ...} (only the untrained FLWs; everyone else
defaults to trained in the build). build_dashboard_data.py reads this when present.

Usage:
    python pull_hq_user_cases.py                 # all _DEFAULT_DOMAINS
    python pull_hq_user_cases.py --domain ccc-interview-panel-cowac
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8")

_DEFAULT_DOMAINS = [
    "connect-interview-cowacdi",
    "connect-interview-eha",
    "connect-interview-cowac-2",
    "connect-interview-eha-2",
    "ccc-interview-panel-cowac",
    "ccc-interview-panel-eha",
    # Extension cohorts — 1ECC1 (COWACDI) / 1ECE1 (EHA).
    "connect-int-ng-cowac-ext",
    "connect-int-ng-eha-ext",
    # KNOWN GAP: the 2WT and ABT3 domains are deliberately absent here. Backfilling them would change
    # untrained_flw for those existing cohorts and shift already-published numbers, so leave as-is.
]

_creds_file = ROOT / ".hq_creds.json"
if os.environ.get("HQ_API_KEY") and os.environ.get("HQ_USERNAME"):
    _dom = os.environ.get("HQ_DOMAINS")
    CREDS = {
        "hq_username": os.environ["HQ_USERNAME"],
        "hq_api_key": os.environ["HQ_API_KEY"],
        "domains": [d.strip() for d in _dom.split(",")] if _dom else _DEFAULT_DOMAINS,
    }
elif _creds_file.exists():
    CREDS = json.loads(_creds_file.read_text())
else:
    raise SystemExit("No HQ creds: set env HQ_API_KEY + HQ_USERNAME (+ optional HQ_DOMAINS), or add .hq_creds.json")

# Domains: env HQ_DOMAINS override, else the full default set (incl. Panel). We deliberately do NOT
# use any "domains" key in .hq_creds.json — that file's list can be stale and miss Panel.
_env_dom = os.environ.get("HQ_DOMAINS")
DOMAINS = [d.strip() for d in _env_dom.split(",")] if _env_dom else _DEFAULT_DOMAINS
AUTH = f"ApiKey {CREDS['hq_username']}:{CREDS['hq_api_key']}"
OUT = ROOT / "_untrained_flw.json"
PAGE_SIZE = 100
TRUE_VALUES = {"yes", "true", "1", "y"}


def pull_domain(domain):
    """Return {connect_id: True} for untrained FLWs in one domain's commcare-user usercases."""
    base = f"https://www.commcarehq.org/a/{domain}/api/v0.5/case/"
    out, offset, total = {}, 0, 0
    while True:
        r = requests.get(
            base,
            params={"case_type": "commcare-user", "limit": PAGE_SIZE, "offset": offset, "format": "json"},
            headers={"Authorization": AUTH},
            timeout=120,
        )
        r.raise_for_status()
        objs = r.json().get("objects", [])
        if not objs:
            break
        for o in objs:
            p = o.get("properties", {}) or {}
            cid = (p.get("username") or "").strip()  # usercase username == Connect connect_id
            total += 1
            if cid and str(p.get("untrained_flw") or "").strip().lower() in TRUE_VALUES:
                out[cid] = True
        if len(objs) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.3)
    print(f"  {domain}: {total} usercases, {len(out)} untrained")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", action="append", help="limit to specific domain(s)")
    args = ap.parse_args()
    domains = args.domain or DOMAINS

    untrained = {}
    for dom in domains:
        try:
            untrained.update(pull_domain(dom))
        except Exception as e:
            print(f"  {dom}: FAILED {type(e).__name__}: {e}")
    OUT.write_text(json.dumps(untrained, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(untrained)} untrained FLWs across {len(domains)} domain(s)")


if __name__ == "__main__":
    main()
