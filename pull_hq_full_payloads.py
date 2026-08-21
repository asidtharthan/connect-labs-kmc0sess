"""
Pull FULL form payloads (case_update + form questions + metadata) for all 4 forms
across all 4 domains. Resumable — restart anytime, picks up from last received_on.

Output: hq_pull_full/{domain}__{form_type}.jsonl  (one JSON object per line)

Each line = COMPLETE form record as returned by /api/v0.5/form/.
Includes:
  - id, received_on, server_modified_on, time_start, time_end
  - username, user_id, device_id, app_id, build_id
  - xmlns, form_name
  - form: {full Q/A dict}
  - metadata: {device, deviceID, instanceID, location, ...}
  - case_update: {what gets written to commcare-user case}

Run locally — sandbox can't reach commcarehq.org.

USAGE:
    python pull_hq_full_payloads.py            # all 4 forms x 4 domains
    python pull_hq_full_payloads.py --form trigger_bot
    python pull_hq_full_payloads.py --domain connect-interview-cowacdi
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).parent
_DEFAULT_DOMAINS = [
    "connect-interview-cowacdi",
    "connect-interview-eha",
    "connect-interview-cowac-2",
    "connect-interview-eha-2",
    # Panel (Long-Term Engagement) — separate domains, cohorts 1PC1 (COWACDI) / 1PE1 (EHA).
    "ccc-interview-panel-cowac",
    "ccc-interview-panel-eha",
    # 2WT (2-Week Test) — separate domains, cohorts 2WTC1 (COWACDI) / 2WTE1 (EHA).
    "connect-int-ng-cowac-2wt",
    "connect-int-ng-eha-2wt",
    # ABT3 (Interview Length A/B test) — separate domains, cohorts 3ABT3C* (COWACDI) / 3ABT3E* (EHA).
    "ccc-interview-abtest3-cow",
    "ccc-interview-abtest3-eha",
    # Extension cohorts — separate domains, cohorts 1ECC1 (COWACDI) / 1ECE1 (EHA).
    "connect-int-ng-cowac-ext",
    "connect-int-ng-eha-ext",
    # NPS (Net Promoter Score) - single-interview cohort 1NPS1, COWACDI only (no EHA domain exists).
    "connect-int-ng-cowac-nps",
]
# Creds from env (HQ_API_KEY/HQ_USERNAME[/HQ_DOMAINS]) for CI/server, else .hq_creds.json locally.
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
    CREDS.setdefault("domains", _DEFAULT_DOMAINS)
else:
    raise SystemExit("No HQ creds: set env HQ_API_KEY + HQ_USERNAME (+ optional HQ_DOMAINS), or add .hq_creds.json")
AUTH = f"ApiKey {CREDS['hq_username']}:{CREDS['hq_api_key']}"
OUT_DIR = ROOT / "hq_pull_full"
OUT_DIR.mkdir(exist_ok=True)

FORMS = {
    "flw_registration": "http://openrosa.org/formdesigner/7392F425-F644-4965-AB89-0FE0C1AC445D",
    "welcome_click_start": "http://openrosa.org/formdesigner/FD6A476C-7E97-4639-BF4D-79EAC10CFCE7",
    "trigger_bot": "http://openrosa.org/formdesigner/A9A03039-C562-42E3-AEA6-8D9ADC9314B6",
    "trigger_payment_unit": "http://openrosa.org/formdesigner/3B5E0517-BAD6-4F83-97DA-3C32996BC947",
}

PAGE_SIZE = 100
SLEEP_BETWEEN_PAGES = 0.5


def out_path(domain, form_type):
    return OUT_DIR / f"{domain}__{form_type}.jsonl"


def last_received_on(p):
    """For resumability: find latest received_on already in the file."""
    if not p.exists():
        return None
    latest = None
    for line in p.open():
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        ro = o.get("received_on")
        if ro and (latest is None or ro > latest):
            latest = ro
    return latest


def _clean_dt(s):
    """CC HQ form API rejects received_on_start with microseconds or a trailing
    'Z'/offset (returns 400). Normalize to 'YYYY-MM-DDTHH:MM:SS'."""
    if not s:
        return s
    s = str(s).replace("Z", "").replace("+00:00", "")
    if "." in s:
        s = s.split(".", 1)[0]
    return s


def fetch_page(domain, xmlns, received_on_start=None, offset=0):
    """Hit /form/?xmlns=&received_on_start= with limit=100."""
    base = f"https://www.commcarehq.org/a/{domain}/api/v0.5/form/"
    params = {
        "xmlns": xmlns,
        "limit": PAGE_SIZE,
        "offset": offset,
        "order_by": "received_on",
    }
    if received_on_start:
        params["received_on_start"] = _clean_dt(received_on_start)
    r = requests.get(base, params=params, headers={"Authorization": AUTH}, timeout=120)
    if not r.ok:
        raise requests.HTTPError(
            f"{r.status_code} {r.reason} for {r.url}\n    HQ says: {r.text[:800]}",
            response=r,
        )
    return r.json()


def pull(domain, form_type, xmlns):
    p = out_path(domain, form_type)
    resume = last_received_on(p)
    if resume:
        print(f"  [{domain}/{form_type}] resuming after received_on={resume}")
        received_on_start = resume
    else:
        print(f"  [{domain}/{form_type}] starting fresh")
        received_on_start = None
    offset = 0
    pulled = 0
    seen_ids = set()
    if p.exists():
        for line in p.open():
            try:
                seen_ids.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                pass
    with p.open("a") as out:
        attempts = 0
        while True:
            try:
                data = fetch_page(domain, xmlns, received_on_start, offset)
                attempts = 0
            except requests.HTTPError as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status and 400 <= status < 500:
                    print(f"    CLIENT ERROR {status} - aborting this form (not retrying):\n    {e}")
                    break
                attempts += 1
                if attempts > 5:
                    print(f"    Gave up after {attempts} retries: {e}")
                    break
                print(f"    transient error: {e}. Sleeping 5s then retry {attempts}/5.")
                time.sleep(5)
                continue
            except requests.RequestException as e:
                attempts += 1
                if attempts > 5:
                    print(f"    Gave up after {attempts} network retries: {e}")
                    break
                print(f"    network error: {e}. Sleeping 5s then retry {attempts}/5.")
                time.sleep(5)
                continue
            objects = data.get("objects", [])
            if not objects:
                break
            new_in_page = 0
            for o in objects:
                fid = o.get("id")
                if not fid or fid in seen_ids:
                    continue
                seen_ids.add(fid)
                out.write(json.dumps(o) + "\n")
                new_in_page += 1
                pulled += 1
            out.flush()
            meta = data.get("meta", {})
            total = meta.get("total_count", "unknown")
            next_url = meta.get("next")
            print(
                f"    page offset={offset}: got {len(objects)} objects ({new_in_page} new), total={total}, pulled_this_run={pulled}"
            )
            if not next_url:
                break
            offset += PAGE_SIZE
            time.sleep(SLEEP_BETWEEN_PAGES)
    print(f"  [{domain}/{form_type}] DONE - added {pulled} records this run, file now has {len(seen_ids)} total")
    return pulled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--form", choices=list(FORMS.keys()) + ["all"], default="all")
    ap.add_argument("--domain", default="all")
    args = ap.parse_args()

    domains = CREDS["domains"] if args.domain == "all" else [args.domain]
    forms = list(FORMS.items()) if args.form == "all" else [(args.form, FORMS[args.form])]

    start = time.time()
    grand_total = 0
    for domain in domains:
        print(f"\n=== {domain} ===")
        for form_type, xmlns in forms:
            n = pull(domain, form_type, xmlns)
            grand_total += n
    print(f"\nDone in {time.time()-start:.1f}s - pulled {grand_total} new form records across all domains/forms.")


if __name__ == "__main__":
    main()
