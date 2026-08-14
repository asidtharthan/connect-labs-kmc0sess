"""Pull LIVE OCS sessions WITH full message text -> _ocs_messages.jsonl (one session per line).

Why this exists: every other OCS puller in this repo throws the message text away.
`pull_ocs_words.py` fetches the same endpoint and keeps two integers; `pull_ocs_state.py` keeps six
scalars. The chatbot-probing analysis needs the conversation itself — specifically the AI turns
BETWEEN questions, which are the probes.

Shape (one JSON object per line, so a 20k-session corpus streams instead of loading whole):
  {sid, pid, interview, interview_topic, total_questions, interview_questions, cohort_id,
   preferred_language, suspected_ai_use, status, session_tags, created_at, updated_at,
   messages: [{role, content, created_at, tags}]}

`role` is "assistant" (bot) / "user" (FLW). Message `tags` carry the bot prompt version (e.g. "v49")
and the router branch ("Interview Router:3") — that is what makes the prompt-version time series
possible. `metadata` (trace blobs) and `attachments` are dropped: large and unused.

Two-stage, to protect against OCS rate limits (Simon's flag):
  1. Page the session LIST once (state is included there), and keep only sessions that carry an
     `interview` — untagged sessions have no interview content to analyse.
  2. Fetch the session DETAIL (messages) only for those, one request each, resumable.

Incremental by default — a session already on disk is refetched only if it is still in progress and
recent (its messages can still grow). `--full` refetches everything. `--limit N` is a smoke test.
OCS key from env OCS_API_KEY or untracked .ocs_creds.json — never hardcoded.
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
EXP = os.environ.get("OCS_EXPERIMENT", "cc01d032-5931-4bdd-a4b2-6f05f4f72f88")
OUT = Path("_ocs_messages.jsonl")
MAX_WORKERS = int(os.environ.get("OCS_MSG_WORKERS", "12"))
LOOKBACK_DAYS = int(os.environ.get("OCS_LOOKBACK_DAYS", "30"))
COMPLETE = "interview_complete"
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 6

# State keys worth keeping. `interview_questions` is the whole reason this script can exist without
# Neal's question catalogue: OCS stamps the verbatim question text onto every session.
STATE_KEYS = (
    "interview",
    "interview_status",
    "interview_topic",
    "total_questions",
    "interview_questions",
    "cohort_id",
    "external_id",
    "preferred_language",
    "suspected_ai_use",
    "interview_start_time",
)


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
        _local.client = httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=90.0)
    return _local.client


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


RETRIES = {"n": 0}  # counted and printed, so throttling is visible instead of silently slow


def _get_with_retry(client, url, params=None):
    """Retry transient 5xx / 429 / network blips with exponential backoff. Raises on 4xx or exhaustion."""
    delay, last_exc = 2.0, None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = client.get(url, params=params)
            if r.status_code in RETRY_STATUS and attempt < MAX_RETRIES:
                RETRIES["n"] += 1
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
                continue
            r.raise_for_status()
            return r
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt >= MAX_RETRIES:
                break
            RETRIES["n"] += 1
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    if last_exc:
        raise last_exc
    raise SystemExit(f"OCS still failing after {MAX_RETRIES} attempts: {url}")


def list_sessions(key):
    """Page the session list once. State is returned inline, so tagging is known before any detail fetch."""
    c = httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=90.0)
    url, page, rows = f"{BASE}/api/sessions/", 0, []
    params = {"experiment": EXP, "ordering": "-created_at", "page_size": 200}
    while url:
        page += 1
        d = _get_with_retry(c, url, params if page == 1 else None).json()
        for s in d.get("results", []):
            st = s.get("state") if isinstance(s.get("state"), dict) else {}
            p = s.get("participant") if isinstance(s.get("participant"), dict) else {}
            rows.append(
                {
                    "sid": s.get("id"),
                    "pid": p.get("identifier"),
                    "status": s.get("status"),
                    "session_tags": s.get("tags") or [],
                    "created_at": s.get("created_at"),
                    "updated_at": s.get("updated_at"),
                    **{k: (st or {}).get(k) for k in STATE_KEYS},
                }
            )
        url = d.get("next")
        if page % 20 == 0:
            print(f"    list page {page}, {len(rows)} sessions...", flush=True)
    print(f"[ocs-msgs] listed {len(rows)} sessions over {page} pages", flush=True)
    return [r for r in rows if r["sid"]]


def fetch_messages(key, row):
    """GET one session's detail and keep role/content/created_at/tags per message."""
    try:
        d = _get_with_retry(_client(key), f"{BASE}/api/sessions/{row['sid']}/").json()
    except Exception:
        return None
    st = d.get("state") if isinstance(d.get("state"), dict) else {}
    out = dict(row)
    # detail state is authoritative (the list can lag); keep the list value when detail omits a key
    for k in STATE_KEYS:
        if (st or {}).get(k) is not None:
            out[k] = st[k]
    out["messages"] = [
        {
            "role": m.get("role"),
            "content": m.get("content"),
            "created_at": m.get("created_at"),
            "tags": m.get("tags") or [],
        }
        for m in (d.get("messages") or [])
        if isinstance(m, dict)
    ]
    return out


def _load_done():
    """{sid: interview_status} already on disk. Tolerates a truncated final line from an interrupted run."""
    done = {}
    if not OUT.exists():
        return done
    with OUT.open(encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                continue  # partial last line
            if r.get("sid"):
                done[r["sid"]] = r.get("interview_status")
    return done


def _needs_fetch(row, done, cutoff, full, want_all=False):
    # Untagged sessions carry no interview, so the probing analysis does not use them — but they DO
    # contain real conversation (welcome, language choice, early abandonment) and belong in a complete
    # archive. `--all` includes them; the default keeps the pull small for the analysis path.
    if not want_all and not (row.get("interview") and str(row["interview"]).strip()):
        return False
    if full or row["sid"] not in done:
        return True
    if (done.get(row["sid"]) or "") != COMPLETE:  # still in progress -> messages can still grow
        created = _parse_dt(row.get("created_at"))
        return bool(created and created >= cutoff)
    return False


def main(full=False, limit=None, want_all=False):
    key = ocs_key()
    rows = list_sessions(key)
    done = {} if full else _load_done()
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    tagged = [r for r in rows if r.get("interview") and str(r["interview"]).strip()]
    todo = [r for r in rows if _needs_fetch(r, done, cutoff, full, want_all)]
    if limit:
        todo = todo[:limit]
    print(
        f"[ocs-msgs] mode: {'FULL' if full else 'incremental'}"
        f"{' +ALL(untagged too)' if want_all else ''}; total={len(rows)} tagged={len(tagged)} "
        f"untagged={len(rows) - len(tagged)} on_disk={len(done)} to_fetch={len(todo)} "
        f"workers={MAX_WORKERS}",
        flush=True,
    )

    if todo:
        # Refetched sessions are rewritten, so drop their stale lines first (append-only otherwise).
        refetch = {r["sid"] for r in todo} & set(done)
        if refetch:
            keep = [
                ln
                for ln in OUT.read_text(encoding="utf-8").splitlines()
                if ln.strip() and json.loads(ln).get("sid") not in refetch
            ]
            OUT.write_text("".join(ln + "\n" for ln in keep), encoding="utf-8")
            print(f"[ocs-msgs] rewrote cache without {len(refetch)} stale sessions", flush=True)

        # as_completed, NOT ex.map: map yields in submission order, so a single slow session
        # head-of-line blocks every later write and the run looks stalled.
        n, fail, msgs, t0 = 0, 0, 0, time.time()
        print(f"[ocs-msgs] fetching {len(todo)} session details...", flush=True)
        with OUT.open("a", encoding="utf-8") as fh, concurrent.futures.ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as ex:
            futs = {ex.submit(fetch_messages, key, r): r["sid"] for r in todo}
            for fut in concurrent.futures.as_completed(futs):
                n += 1
                rec = fut.result()
                if rec is None:
                    fail += 1
                else:
                    msgs += len(rec["messages"])
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if n % 50 == 0:
                    fh.flush()
                    rate = n / max(time.time() - t0, 0.01)
                    eta = (len(todo) - n) / max(rate, 0.01) / 60
                    print(
                        f"  {n}/{len(todo)} sessions, {msgs} msgs, {rate:.1f}/s, "
                        f"eta {eta:.0f}m (fail={fail} retries={RETRIES['n']})",
                        flush=True,
                    )
        print(
            f"[ocs-msgs] fetched={n} failures={fail} messages={msgs} "
            f"in {(time.time() - t0) / 60:.1f}m (retries={RETRIES['n']})",
            flush=True,
        )

    # final census straight off disk, so the printed numbers are what downstream will actually read
    tot = tot_m = tot_h = tot_a = tot_s = 0
    codes = {}
    with OUT.open(encoding="utf-8") as fh:
        for ln in fh:
            if not ln.strip():
                continue
            r = json.loads(ln)
            tot += 1
            ms = r.get("messages") or []
            tot_m += len(ms)
            tot_h += sum(1 for m in ms if m.get("role") == "user")
            tot_a += sum(1 for m in ms if m.get("role") == "assistant")
            tot_s += sum(1 for m in ms if m.get("role") == "system")
            codes[str(r.get("interview"))] = codes.get(str(r.get("interview")), 0) + 1
    print(
        f"[ocs-msgs] ON DISK: {tot} sessions, {tot_m} messages "
        f"(FLW {tot_h} / bot {tot_a} / system {tot_s}), {len(codes)} interview codes -> {OUT}",
        flush=True,
    )
    print(
        f"[ocs-msgs] listed on OCS: {len(rows)} sessions -> " f"coverage {100 * tot / max(len(rows), 1):.1f}%",
        flush=True,
    )
    print(
        "[ocs-msgs] per code:",
        ", ".join(f"{k}={v}" for k, v in sorted(codes.items(), key=lambda x: -x[1])),
        flush=True,
    )


if __name__ == "__main__":
    _limit = None
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            _limit = int(a.split("=", 1)[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
    main(full="--full" in sys.argv, limit=_limit, want_all="--all" in sys.argv)
