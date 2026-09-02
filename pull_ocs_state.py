"""Pull LIVE OCS sessions (with Session State) -> _ocs_state_cache.json.

INCREMENTAL by default: OCS only supports `-created_at` ordering (no `updated_at`/date filters —
verified against the live API), so each run re-scans just the RECENT window of sessions
(created within OCS_LOOKBACK_DAYS, default 30) and MERGES them into the existing cache by `sid`.
That window is wider than an interview's whole lifecycle, so it captures BOTH new sessions AND
status/tag changes on recently-created ones, while older sessions (already settled) are kept as-is
from the cache. This avoids re-downloading all ~18k sessions every day (Simon's rate-limit flag).

Full re-scan (seed / self-heal) happens automatically when the cache is missing, or on demand with
`--full` (also prunes sessions deleted upstream, since it replaces rather than merges).

Standalone (no Django) so the daily job can run it headless.
OCS bearer key from env OCS_API_KEY (CI secret) or untracked .ocs_creds.json locally — never hardcoded.
Output shape matches what build_master_4src.py reads: {sid, pid, interview, interview_status,
created_at} (+ updated_at, additive/ignored downstream).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

BASE = os.environ.get("OCS_BASE_URL", "https://www.openchatstudio.com")
EXP = os.environ.get("OCS_EXPERIMENT", "cc01d032-5931-4bdd-a4b2-6f05f4f72f88")
LOOKBACK_DAYS = int(os.environ.get("OCS_LOOKBACK_DAYS", "30"))

# OCS occasionally returns a transient 5xx (e.g. 502 Bad Gateway) or drops the connection mid-pagination.
# A single blip should NOT abort the whole daily refresh, so retry idempotent GETs with exponential backoff.
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 6


def _get_with_retry(client, url, params):
    """GET a page, retrying transient 5xx / network errors with exponential backoff. Raises on 4xx or exhaustion."""
    delay = 2.0
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = client.get(url, params=params)
            if r.status_code in RETRY_STATUS and attempt < MAX_RETRIES:
                print(f"    OCS {r.status_code} on attempt {attempt}/{MAX_RETRIES}; retrying in {delay:.0f}s...", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
                continue
            r.raise_for_status()
            return r
        except (httpx.TransportError, httpx.TimeoutException) as e:  # connection reset, read timeout, etc.
            last_exc = e
            if attempt >= MAX_RETRIES:
                break
            print(f"    OCS network error on attempt {attempt}/{MAX_RETRIES} ({type(e).__name__}); retrying in {delay:.0f}s...", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    if last_exc:
        raise last_exc
    raise SystemExit(f"OCS still failing after {MAX_RETRIES} attempts: {url}")


def _ocs_key():
    k = os.environ.get("OCS_API_KEY")
    if k:
        return k
    p = Path(".ocs_creds.json")
    if p.exists():
        return json.loads(p.read_text()).get("ocs_api_key")
    raise SystemExit('No OCS key: set env OCS_API_KEY or add .ocs_creds.json {"ocs_api_key": "..."}')


KEY = _ocs_key()
CACHE = Path("_ocs_state_cache.json")


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _row(s):
    st = s.get("state") if isinstance(s.get("state"), dict) else {}
    p = s.get("participant") or {}
    return {
        "sid": s.get("id"),
        "pid": p.get("identifier") if isinstance(p, dict) else None,
        "interview": (st or {}).get("interview"),
        "interview_status": (st or {}).get("interview_status"),
        # The cohort the session itself ran under. Sessions are keyed by (pid, interview) only, so
        # when one worker holds the SAME interview number in two cohorts their triggers compete for
        # one session pool and the slot can be filled from the wrong cohort. build_master_4src's
        # pick_best uses this to break that tie. See PROJECT_LEARNINGS 5v.
        "cohort_id": (st or {}).get("cohort_id"),
        "created_at": s.get("created_at"),
        "updated_at": s.get("updated_at"),
    }


def _load_existing():
    """Existing cache as {sid: row}; {} if absent/unreadable (-> triggers a full seed)."""
    if not CACHE.exists():
        return {}
    try:
        data = json.loads(CACHE.read_text())
        if isinstance(data, list):
            return {s["sid"]: s for s in data if isinstance(s, dict) and s.get("sid")}
    except (ValueError, OSError):
        pass
    return {}


def _needs_reseed(existing):
    """True when the cache predates a field the builder now needs.

    The incremental window is keyed on created_at, so a field added to `_row` will NEVER reach
    sessions created before the window - they are kept as-is from the cache forever. A new field is
    therefore a schema change that requires one full scan, not a gradual fill. Without this the
    `cohort_id` tie-break in build_master_4src's pick_best would silently do nothing for exactly the
    old sessions it exists to fix. Declaring the reseed beats degrading quietly.
    """
    if not existing:
        return False  # already a seed; nothing to compare against
    missing = sum(1 for s in existing.values() if "cohort_id" not in s)
    if missing:
        print(
            f"[ocs-state] cache schema is behind: {missing:,} of {len(existing):,} rows have no "
            f"'cohort_id' -> forcing a FULL scan once to backfill it",
            flush=True,
        )
        return True
    return False


def pull(full=False):
    existing = {} if full else _load_existing()
    if not full and _needs_reseed(existing):
        existing, full = {}, True
    seeding = full or not existing  # no prior cache -> must do a full scan to seed
    cutoff = None if seeding else datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    mode = "FULL scan" if seeding else f"INCREMENTAL (created within {LOOKBACK_DAYS}d)"
    print(f"[ocs-state] mode: {mode}; existing cache: {len(existing)} sessions", flush=True)

    c = httpx.Client(headers={"Authorization": f"Bearer {KEY}"}, timeout=90.0)
    fetched = {}
    url = f"{BASE}/api/sessions/"
    params = {"experiment": EXP, "ordering": "-created_at", "page_size": 200}
    page = 0
    stop = False
    while url and not stop:
        page += 1
        r = _get_with_retry(c, url, params if page == 1 else None)
        d = r.json()
        results = d.get("results", [])
        for s in results:
            row = _row(s)
            if row["sid"]:
                fetched[row["sid"]] = row
        # -created_at order: once the OLDEST row on this page predates the cutoff, everything
        # further back is older too -> stop paginating (we've covered the whole recent window).
        if cutoff is not None and results:
            last_created = _parse_dt(results[-1].get("created_at"))
            if last_created and last_created < cutoff:
                stop = True
        url = None if stop else d.get("next")
        if page % 10 == 0:
            print(f"    page {page}, {len(fetched)} fetched...", flush=True)

    if seeding:
        merged = fetched  # fresh full snapshot (replaces cache -> also prunes upstream-deleted sessions)
    else:
        merged = dict(existing)
        merged.update(fetched)  # upsert by sid: new sessions added, changed ones (status/tag) overwritten

    out = list(merged.values())
    CACHE.write_text(json.dumps(out))
    tagged = sum(1 for s in out if s.get("pid") and s.get("interview"))
    print(f"[ocs-state] pages={page} fetched={len(fetched)} merged_total={len(out)} tagged={tagged} -> {CACHE}", flush=True)
    return out


if __name__ == "__main__":
    _full = "--full" in sys.argv or "--full-resync" in sys.argv or os.environ.get("OCS_FULL_RESYNC") == "1"
    pull(full=_full)
