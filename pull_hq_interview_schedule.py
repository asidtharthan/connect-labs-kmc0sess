"""pull_hq_interview_schedule.py — pull the per-cohort interview schedule from CommCare HQ.

The bot's interview cadence + topic sequence live in the CommCare HQ **`interview_schedule`
lookup table** (one row per cohort step: cohort_id / next_interview / previous_interview /
frequency_days; frequency_days on a row = days from THAT interview to the NEXT; 9999 = terminal).
This is the runtime source of truth — authoritative over any hardcoded design.

We reconstruct each cohort's ordered topic chain and cumulative release offsets, so the dashboard
build derives SUBGROUP_DESIGN (topics + cadence) and release dates from the bot's real config
(fixes e.g. PANEL = 13 interviews `7,1,2,12,3,4,5,6,C,10,11,8,13`, not the stale hardcoded 11).

Headless (HQ key) → runs in the daily CI. Output: _interview_schedule.json =
  {cohort_id: [{"n": 1, "topic": "7", "offset_days": 0}, ...]}

Usage:
    python pull_hq_interview_schedule.py
    python pull_hq_interview_schedule.py --domain ccc-interview-panel-cowac
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
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
    "connect-int-ng-cowac-2wt",
    "connect-int-ng-eha-2wt",
    "ccc-interview-abtest3-cow",
    "ccc-interview-abtest3-eha",
    # Extension cohorts — separate domains, cohorts 1ECC1 (COWACDI) / 1ECE1 (EHA).
    "connect-int-ng-cowac-ext",
    "connect-int-ng-eha-ext",
]

_creds_file = ROOT / ".hq_creds.json"
if os.environ.get("HQ_API_KEY") and os.environ.get("HQ_USERNAME"):
    CREDS = {"hq_username": os.environ["HQ_USERNAME"], "hq_api_key": os.environ["HQ_API_KEY"]}
elif _creds_file.exists():
    CREDS = json.loads(_creds_file.read_text())
else:
    raise SystemExit("No HQ creds: set env HQ_API_KEY + HQ_USERNAME, or add .hq_creds.json")

_env_dom = os.environ.get("HQ_DOMAINS")
DOMAINS = [d.strip() for d in _env_dom.split(",")] if _env_dom else _DEFAULT_DOMAINS
AUTH = f"ApiKey {CREDS['hq_username']}:{CREDS['hq_api_key']}"
OUT = ROOT / "_interview_schedule.json"
# test/sandbox cohorts that exist in the lookup but aren't real cohorts
_TEST = re.compile(r"_test|^1[ABD]$|te\d{3}", re.I)


def _flat(o):
    f = o.get("fields", {})
    d = {}
    for k, v in f.items():
        if isinstance(v, dict) and v.get("field_list"):
            vals = [x.get("field_value") for x in v["field_list"]]
            d[k] = vals[0] if len(vals) == 1 else vals
        else:
            d[k] = v
    return d


def pull_domain(domain):
    """Return list of flat schedule rows for one domain."""
    base = f"https://www.commcarehq.org/a/{domain}/api/v0.5/fixture/"
    rows, offset = [], 0
    while True:
        r = requests.get(
            base,
            params={"fixture_type": "interview_schedule", "limit": 100, "offset": offset, "format": "json"},
            headers={"Authorization": AUTH},
            timeout=90,
        )
        r.raise_for_status()
        objs = r.json().get("objects", [])
        if not objs:
            break
        rows += [_flat(o) for o in objs]
        if len(objs) < 100:
            break
        offset += 100
    return rows


def build_chain(cohort_rows):
    """Order a cohort's rows into [(topic, offset_days)] following previous->next.
    frequency_days on a row = gap from that row's next_interview to the FOLLOWING interview."""
    by_prev = {}
    for d in cohort_rows:
        by_prev[(d.get("previous_interview") or "").strip()] = d
    seq, prev, offset, seen = [], "", 0, set()
    while prev in by_prev and prev not in seen:
        seen.add(prev)
        d = by_prev[prev]
        topic = (d.get("next_interview") or "").strip()
        if topic in ("--", ""):  # terminal sentinel (e.g. 2WT chain: 14 -> "--"); not a real interview
            break
        seq.append({"n": len(seq) + 1, "topic": topic, "offset_days": offset})
        try:
            f = int(float(d.get("frequency_days")))
        except (TypeError, ValueError):
            f = 0
        if f != 9999:  # 9999 = terminal (no following interview)
            offset += f
        prev = topic
    return seq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", action="append", help="limit to specific domain(s)")
    args = ap.parse_args()
    domains = args.domain or DOMAINS

    by_cohort = defaultdict(list)
    for dom in domains:
        try:
            rows = pull_domain(dom)
        except Exception as e:
            print(f"  {dom}: FAILED {type(e).__name__}: {e}")
            continue
        n = 0
        for d in rows:
            cid = (d.get("cohort_id") or "").strip()
            if not cid or _TEST.search(cid):
                continue
            by_cohort[cid].append(d)
            n += 1
        print(f"  {dom}: {len(rows)} rows, {n} kept")

    schedule = {}
    for cid, rows in by_cohort.items():
        # dedupe identical rows merged across domains
        uniq = {(d.get("previous_interview"), d.get("next_interview"), d.get("frequency_days")): d for d in rows}
        seq = build_chain(list(uniq.values()))
        if seq:
            schedule[cid] = seq
    OUT.write_text(json.dumps(schedule, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(schedule)} cohorts")
    for cid in sorted(schedule)[:3]:
        print(f"  e.g. {cid}: {[s['topic'] for s in schedule[cid]]}")


if __name__ == "__main__":
    main()
