"""Fetch OCS message content for TAGGED sessions and count FLW (human) words per session.

Writes incremental cache `_ocs_words_cache.json` = {sid: {human_words, human_msgs}}.
FLW message = message with role == "user"; word = whitespace token in `content`.
(The AI is role == "assistant".) Adapted to the OCS session-detail API
(GET /api/sessions/{id}/ -> messages[]) — one request per session, so keeping this list small
is what protects us against OCS rate limits (Simon's flag).

Incremental fetch rule (reads the session list from `_ocs_state_cache.json`):
  * NEW tagged session (not in the words cache) -> fetch.
  * IN-PROGRESS tagged session (interview_status != "interview_complete") created within
    OCS_LOOKBACK_DAYS (default 30) -> re-fetch, because its message count can still grow.
  * COMPLETED sessions, and older/abandoned in-progress ones, are FROZEN (kept from cache).
So after the first (seeding) run, each day only fetches the small new + recently-active tail.
`--full` re-fetches every tagged session (rebuild). OCS key from env OCS_API_KEY or .ocs_creds.json.
"""
import concurrent.futures
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

BASE = os.environ.get("OCS_BASE_URL", "https://www.openchatstudio.com")
STATE_CACHE = Path("_ocs_state_cache.json")
WORDS_CACHE = Path("_ocs_words_cache.json")
MAX_WORKERS = 16
LOOKBACK_DAYS = int(os.environ.get("OCS_LOOKBACK_DAYS", "30"))
COMPLETE = "interview_complete"
RETRY_STATUS = {429, 500, 502, 503, 504}


def ocs_key():
    k = os.environ.get("OCS_API_KEY")
    if k:
        return k
    p = Path(".ocs_creds.json")
    if p.exists():
        return json.loads(p.read_text()).get("ocs_api_key")
    raise SystemExit('No OCS key: set env OCS_API_KEY or add .ocs_creds.json {"ocs_api_key": "..."}')


_local = threading.local()


def _client(key):
    if not getattr(_local, "client", None):
        _local.client = httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0)
    return _local.client


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_words(key, sid):
    """GET one session's messages and count human words/msgs. Backs off on 429/5xx / network blips."""
    cl = _client(key)
    delay = 2.0
    for attempt in range(1, 6):
        try:
            r = cl.get(f"{BASE}/api/sessions/{sid}/")
            if r.status_code in RETRY_STATUS and attempt < 5:
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            r.raise_for_status()
            msgs = r.json().get("messages") or []
            hw = hm = 0
            for m in msgs:
                if isinstance(m, dict) and str(m.get("role") or "").lower() == "user":
                    hm += 1
                    hw += len(str(m.get("content") or "").split())
            return sid, {"human_words": hw, "human_msgs": hm}
        except (httpx.TransportError, httpx.TimeoutException):
            if attempt >= 5:
                return sid, None
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
        except Exception:
            return sid, None
    return sid, None


def _needs_fetch(s, cache, cutoff, full):
    """Which tagged sessions to (re)fetch — see module docstring."""
    if not (s.get("interview") and str(s.get("interview")).strip()):
        return False  # untagged: no interview content to count
    sid = s.get("sid")
    if not sid:
        return False
    if full or sid not in cache:
        return True  # rebuild, or brand-new session
    # already cached: only re-fetch if still in progress AND recent (message count can still grow)
    if (s.get("interview_status") or "") != COMPLETE:
        created = _parse_dt(s.get("created_at"))
        if created and created >= cutoff:
            return True
    return False


def main(full=False):
    key = ocs_key()
    sessions = json.loads(STATE_CACHE.read_text())
    cache = json.loads(WORDS_CACHE.read_text()) if WORDS_CACHE.exists() else {}
    if not cache:
        full = True  # no prior words cache -> seed everything
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    todo = list(dict.fromkeys(s["sid"] for s in sessions if _needs_fetch(s, cache, cutoff, full)))
    tagged = sum(1 for s in sessions if s.get("interview") and str(s.get("interview")).strip())
    print(f"[ocs-words] mode: {'FULL' if full else f'incremental (new + in-progress<{LOOKBACK_DAYS}d)'}; "
          f"tagged={tagged} cached={len(cache)} to_fetch={len(todo)}", flush=True)
    done = fail = 0
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            for sid, rec in ex.map(lambda s: fetch_words(key, s), todo):
                done += 1
                if rec is None:
                    fail += 1
                else:
                    cache[sid] = rec
                if done % 500 == 0:
                    print(f"  {done}/{len(todo)} (fail={fail})", flush=True)
        WORDS_CACHE.write_text(json.dumps(cache))
    tot_w = sum(v["human_words"] for v in cache.values())
    tot_m = sum(v["human_msgs"] for v in cache.values())
    avg = (tot_w / tot_m) if tot_m else 0
    print(f"[ocs-words] cache: {len(cache)} sessions, {tot_w} words / {tot_m} msgs "
          f"(avg {avg:.2f}/msg) -> {WORDS_CACHE}  [fetched={done} failures={fail}]", flush=True)


if __name__ == "__main__":
    _full = "--full" in sys.argv or "--full-resync" in sys.argv or os.environ.get("OCS_FULL_RESYNC") == "1"
    main(full=_full)
