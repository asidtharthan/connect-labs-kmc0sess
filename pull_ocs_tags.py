"""Pull OCS session REVIEW TAGS (acceptable / unacceptable / suspected_ai / ...) -> _ocs_tags_cache.json.

Why this is a separate leg from pull_ocs_state.py
-------------------------------------------------
pull_ocs_state.py is incremental on CREATED_AT: it re-scans only sessions created in the last 30 days
and keeps everything older from cache. That is right for interview status, which settles within days of
a session starting. It is WRONG for review tags, because reviewing happens long after creation - the
live census on 2026-08-25 found tagged sessions going back to March, and the tagged total still climbing
day by day (7,737 through July, 8,748 by 25 Aug). Deriving review status from that cache would freeze an
April session's tag forever.

So this does a FULL scan every run. That is affordable precisely because tags come from the session LIST
endpoint: ~112 paginated requests for all 22k sessions, not one request per session. The rate-limit
concern that made the OCS sync incremental was about per-session DETAIL calls, which this never makes.

Writes {sid: [tags]} for every session carrying at least one tag. Sessions with no tags are omitted -
absence IS the "not yet reviewed" signal, and storing thousands of empty lists would only bloat the file.

    python pull_ocs_tags.py            # refresh the cache
    python pull_ocs_tags.py --report   # also print the census (what the 8,6xx-vs-9,4xx question needs)

OCS bearer key from env OCS_API_KEY (CI secret) or untracked .ocs_creds.json locally.
"""

import collections
import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.environ.get("OCS_BASE_URL", "https://www.openchatstudio.com")
EXP = os.environ.get("OCS_EXPERIMENT", "cc01d032-5931-4bdd-a4b2-6f05f4f72f88")
CACHE = Path("_ocs_tags_cache.json")
PAGE = 200
RETRY_STATUS = {429, 500, 502, 503, 504}

# The review verdicts, in the order a reader should think about them. Everything else OCS puts in
# `tags` (Run-on Session, n/a, Test, ...) is bookkeeping, not a verdict, and is deliberately ignored
# here - mixing the two is what makes "how many were acceptable" unanswerable.
VERDICTS = ("acceptable", "unacceptable", "suspected_ai")


def ocs_key():
    k = os.environ.get("OCS_API_KEY")
    if k:
        return k
    p = Path(".ocs_creds.json")
    if p.exists():
        return json.loads(p.read_text()).get("ocs_api_key")
    raise SystemExit('No OCS key: set env OCS_API_KEY or add .ocs_creds.json {"ocs_api_key": "..."}')


def fetch_all(key):
    out, url, params, page = (
        [],
        f"{BASE}/api/sessions/",
        {"experiment": EXP, "page_size": PAGE, "ordering": "created_at"},
        0,
    )
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=90.0) as c:
        while url:
            for attempt in range(4):
                try:
                    r = c.get(url, params=params if page == 0 else None)
                    if r.status_code in RETRY_STATUS:
                        raise httpx.HTTPError(f"HTTP {r.status_code}")
                    r.raise_for_status()
                    break
                except (httpx.HTTPError, httpx.TimeoutException) as e:
                    if attempt == 3:
                        raise SystemExit(f"[ocs-tags] ABORT after retries: {e}")
                    time.sleep(3 * (attempt + 1))
            j = r.json()
            out.extend(j.get("results") or [])
            url, page = j.get("next"), page + 1
    return out


def main():
    rows = fetch_all(ocs_key())
    tags = {s["id"]: s["tags"] for s in rows if s.get("id") and s.get("tags")}
    CACHE.write_text(json.dumps(tags, separators=(",", ":")))
    n_verdict = sum(1 for t in tags.values() if set(t) & set(VERDICTS))
    print(
        f"[ocs-tags] {len(rows):,} sessions scanned, {len(tags):,} carry tags, "
        f"{n_verdict:,} carry a review verdict -> {CACHE}",
        flush=True,
    )

    if "--report" in sys.argv:
        c = collections.Counter(t for ts in tags.values() for t in ts)
        print("[ocs-tags] every tag:")
        for k, v in c.most_common():
            print(f"           {k:26} {v:>6}")
        comp = [s for s in rows if (s.get("state") or {}).get("interview_status") == "interview_complete"]
        rev = collections.Counter()
        for s in comp:
            hit = set(s.get("tags") or []) & {"acceptable", "unacceptable"}
            rev[next(iter(hit)) if hit else "NOT YET REVIEWED"] += 1
        print(f"[ocs-tags] of {len(comp):,} sessions OCS marks interview_complete:")
        for k, v in rev.most_common():
            print(f"           {k:26} {v:>6}  ({round(100 * v / max(len(comp), 1))}%)")


if __name__ == "__main__":
    main()
