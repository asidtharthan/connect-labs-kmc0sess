"""Live census of OCS session `status` and `tags` for the Connect Interviews bot.

Purpose: settle what OCS's 'acceptable / not acceptable' figure actually counts, and whether it is the
same universe as the dashboard's 'completed interviews'. Reads only the session LIST endpoint.
"""
import collections
import json
import os
import sys
import time

import httpx

BASE = "https://www.openchatstudio.com"
EXPERIMENT = "cc01d032-5931-4bdd-a4b2-6f05f4f72f88"


def key():
    k = os.environ.get("OCS_API_KEY")
    if k:
        return k
    j = json.load(open(".ocs_creds.json", encoding="utf-8"))
    return j.get("ocs_api_key")


rows, url = [], f"{BASE}/api/sessions/"
params = {"experiment": EXPERIMENT, "page_size": 200, "ordering": "created_at"}
with httpx.Client(headers={"Authorization": f"Bearer {key()}"}, timeout=90) as c:
    n = 0
    while url:
        for attempt in range(4):
            try:
                r = c.get(url, params=params if n == 0 else None)
                r.raise_for_status()
                break
            except Exception as e:
                if attempt == 3:
                    sys.exit(f"OCS failed after retries: {e}")
                time.sleep(3 * (attempt + 1))
        j = r.json()
        rows.extend(j["results"])
        url = j.get("next")
        n += 1
        if n % 10 == 0:
            print(f"  ...{len(rows)} sessions", flush=True)
json.dump(rows, open("_ocs_tag_census.json", "w", encoding="utf-8"))
print("TOTAL sessions on this experiment:", len(rows))
print("\n`status` (the review-workflow field):")
for k, v in collections.Counter(r.get("status") for r in rows).most_common():
    print(f"  {str(k):22} {v:>6}")
print("\n`tags` (every distinct tag, with how many sessions carry it):")
tg = collections.Counter()
for r in rows:
    for t in (r.get("tags") or []):
        tg[t] += 1
for k, v in tg.most_common(40):
    print(f"  {k:42} {v:>6}")
print("\nsessions with NO tags:", sum(1 for r in rows if not r.get("tags")))
ds = sorted(r["created_at"][:10] for r in rows if r.get("created_at"))
print("created_at range:", ds[0], "->", ds[-1])
