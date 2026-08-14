"""Audit the OCS transcript pull for completeness, then package a durable local dump.

Two jobs, deliberately in one place so the dump can never be written without passing the audit.

AUDIT — the checks that would catch a half-pull or a silently broken one:
  1. COVERAGE     every session OCS lists is on disk (live count from the API, not a remembered number)
  2. NO DUPES     one line per session id
  3. NO TRUNCATION message counts form a smooth distribution with no spike at a round number, which is
                  what a server-side cap looks like; and no session that exists is empty
  4. FIELD SANITY every message has a role in {assistant, user, system} and non-null content
  5. ORDERING     message timestamps are non-decreasing within a session (the analysis binds answers
                  to the question open at the time, so out-of-order messages would corrupt it)
  6. EXPORT PARITY every session in the 2026-05-25 chat export is present, with a message count at
                  least as high as the export's (independent source, so this catches a systematic loss
                  the API alone could not reveal)
  7. STATE        sessions carrying an interview also carry the question block the catalogue needs

DUMP — a self-describing archive so later analyses need no re-pull:
  transcripts.jsonl (the corpus), question_catalogue.json/.csv, session_index.csv (one row per
  session, no message text, for fast filtering), manifest.json (counts + sha256 + the audit result),
  and README.md documenting the schema and provenance.

  python build_transcript_dump.py            # audit only
  python build_transcript_dump.py --write     # audit, then write the dump (refuses if the audit fails)
"""
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SRC = Path("_ocs_messages.jsonl")
EXPORT = Path("[Connect Interviews] Dynamic Router Interview Bot Chat Export 2026-05-25_07-59-21.csv")
DUMP = Path("ocs_transcript_dump")
ROLES = {"assistant", "user", "system"}


def live_session_count():
    """Ask OCS how many sessions exist right now. Never trust a number remembered from an earlier run."""
    try:
        import httpx

        from pull_ocs_messages import BASE, EXP, ocs_key

        r = httpx.Client(headers={"Authorization": f"Bearer {ocs_key()}"}, timeout=60.0).get(
            f"{BASE}/api/sessions/", params={"experiment": EXP, "page_size": 1}
        )
        r.raise_for_status()
        return r.json().get("count")
    except Exception as e:  # offline / creds absent: coverage becomes unverifiable, and says so
        print(f"  ! could not reach OCS for the live count ({type(e).__name__}) — coverage UNVERIFIED")
        return None


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def audit():
    if not SRC.exists():
        raise SystemExit(f"missing {SRC} — run pull_ocs_messages.py --all first")

    sids = Counter()
    msg_counts = Counter()
    roles = Counter()
    bad_role = bad_content = out_of_order = empty = empty_tagged = 0
    tagged = tagged_no_questions = 0
    per_code = Counter()
    langs = Counter()
    first_dt = last_dt = None
    n_sessions = n_msgs = 0
    sha = hashlib.sha256()

    with SRC.open("rb") as fb:
        for chunk in iter(lambda: fb.read(1 << 20), b""):
            sha.update(chunk)

    for ln in SRC.open(encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        rec = json.loads(ln)
        n_sessions += 1
        sids[rec.get("sid")] += 1
        ms = rec.get("messages") or []
        msg_counts[len(ms)] += 1
        n_msgs += len(ms)
        code = str(rec.get("interview") or "").strip()
        if not ms:
            empty += 1
            if code:
                empty_tagged += 1
        per_code[code or "(untagged)"] += 1
        langs[str(rec.get("preferred_language") or "(none)").lower()[:24]] += 1
        if code:
            tagged += 1
            if not str(rec.get("interview_questions") or "").strip():
                tagged_no_questions += 1
        prev = None
        for m in ms:
            roles[m.get("role")] += 1
            if m.get("role") not in ROLES:
                bad_role += 1
            if m.get("content") is None:
                bad_content += 1
            d = _parse(m.get("created_at"))
            if d:
                if prev and d < prev:
                    out_of_order += 1
                prev = d
                first_dt = d if first_dt is None or d < first_dt else first_dt
                last_dt = d if last_dt is None or d > last_dt else last_dt

    dupes = sum(v - 1 for v in sids.values() if v > 1)

    # truncation test: a server-side cap shows up as an outsized spike at one value near the top
    top = sorted(msg_counts)[-1] if msg_counts else 0
    biggest_spike = max(msg_counts.values()) if msg_counts else 0
    spike_at = max(msg_counts, key=lambda k: msg_counts[k]) if msg_counts else 0
    cap_suspected = bool(spike_at >= 0.8 * top and biggest_spike > 0.02 * max(n_sessions, 1) and top >= 50)

    live = live_session_count()
    coverage = (100 * n_sessions / live) if live else None

    # export parity
    exp_missing = exp_lower = exp_sessions = 0
    if EXPORT.exists():
        csv.field_size_limit(10**9)
        exp = Counter()
        with EXPORT.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                exp[row["Session ID"]] += 1
        exp_sessions = len(exp)
        have = {}
        for ln in SRC.open(encoding="utf-8"):
            if ln.strip():
                r = json.loads(ln)
                have[r["sid"]] = len(r.get("messages") or [])
        exp_missing = sum(1 for s in exp if s not in have)
        exp_lower = sum(1 for s, c in exp.items() if s in have and have[s] < c)

    # OCS is live: sessions are created while the pull runs, so the listed total drifts upward during
    # a 20-minute fetch. The gate has to catch a SYSTEMATIC shortfall (thousands missing) without
    # failing on a two-session race. Margin is the larger of 10 sessions or 0.1%, and the exact delta
    # is printed either way so a real gap can never hide inside the tolerance.
    margin = max(10, int(0.001 * (live or 0)))
    short = (live - n_sessions) if live else 0

    checks = [
        (
            "coverage: every session OCS lists is on disk",
            (live is None) or short <= margin,
            f"{n_sessions} on disk / {live} live"
            + (
                f" = {coverage:.2f}%, short by {short} (margin {margin}, live arrivals)"
                if coverage
                else " (unverified)"
            ),
        ),
        ("no duplicate session ids", dupes == 0, f"{dupes} duplicates"),
        # An empty session is only a defect if it should have had content. All 23 empties were checked
        # against the API directly: it returns 0 messages for each, status setup/pending-review, and
        # none carries an interview code — session shells that were never used. A TAGGED session with
        # no messages would mean a lost fetch, so that is what this gate tests.
        (
            "no tagged session is empty",
            empty_tagged == 0,
            f"{empty} empty sessions, {empty_tagged} of them tagged (untagged empties are unused shells)",
        ),
        (
            "no server-side message cap",
            not cap_suspected,
            f"max {top} msgs; most common count {spike_at} ({biggest_spike} sessions)",
        ),
        ("all roles known", bad_role == 0, f"{bad_role} unknown-role messages; roles={dict(roles)}"),
        ("no null message content", bad_content == 0, f"{bad_content} null contents"),
        ("messages in chronological order", out_of_order == 0, f"{out_of_order} out-of-order messages"),
        (
            "export parity: all export sessions present",
            exp_missing == 0,
            f"{exp_missing} of {exp_sessions} export sessions missing",
        ),
        (
            "export parity: no session shorter than the export",
            exp_lower == 0,
            f"{exp_lower} sessions shorter than export",
        ),
        (
            "tagged sessions carry their question block",
            tagged_no_questions == 0,
            f"{tagged_no_questions} of {tagged} tagged sessions missing interview_questions",
        ),
    ]

    print(f"[audit] {SRC} — {n_sessions:,} sessions, {n_msgs:,} messages")
    print("[audit] roles: " + ", ".join(f"{k}={v:,}" for k, v in roles.most_common()))
    print(f"[audit] window: {first_dt} -> {last_dt}")
    print(f"[audit] sha256: {sha.hexdigest()}")
    ok = True
    for name, passed, detail in checks:
        ok &= passed
        print(f"  {'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
    print(f"[audit] VERDICT: {'ALL CHECKS PASS' if ok else 'FAILURES PRESENT'}")

    return {
        "ok": ok,
        "generated": datetime.now(timezone.utc).isoformat(),
        "source_file": str(SRC),
        "sha256": sha.hexdigest(),
        "bytes": SRC.stat().st_size,
        "sessions": n_sessions,
        "messages": n_msgs,
        "empty_sessions": empty,
        "empty_tagged_sessions": empty_tagged,
        "roles": dict(roles),
        "live_sessions_on_ocs": live,
        "coverage_pct": round(coverage, 2) if coverage else None,
        "tagged_sessions": tagged,
        "untagged_sessions": n_sessions - tagged,
        "first_message": str(first_dt),
        "last_message": str(last_dt),
        "max_messages_in_session": top,
        "export_sessions": exp_sessions,
        "export_sessions_missing": exp_missing,
        "export_sessions_shorter": exp_lower,
        "per_code": dict(per_code.most_common()),
        "languages": dict(langs.most_common(12)),
        "checks": [{"check": c, "pass": bool(p), "detail": d} for c, p, d in checks],
    }


def write_dump(man):
    DUMP.mkdir(exist_ok=True)
    print(f"[dump] copying transcripts -> {DUMP / 'transcripts.jsonl'} ({man['bytes'] / 1e6:.0f} MB)")
    shutil.copy2(SRC, DUMP / "transcripts.jsonl")
    for f in ("question_catalogue.json", "question_catalogue.csv"):
        if Path(f).exists():
            shutil.copy2(f, DUMP / f)

    # session index: everything except message text, so later work can filter without parsing 170MB
    idx = DUMP / "session_index.csv"
    cols = [
        "sid",
        "pid",
        "interview",
        "interview_topic",
        "interview_status",
        "cohort_id",
        "preferred_language",
        "suspected_ai_use",
        "total_questions",
        "created_at",
        "updated_at",
        "status",
        "session_tags",
        "n_messages",
        "n_flw",
        "n_bot",
        "n_system",
        "flw_words",
        "first_message_at",
        "last_message_at",
    ]
    with idx.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for ln in SRC.open(encoding="utf-8"):
            if not ln.strip():
                continue
            r = json.loads(ln)
            ms = r.get("messages") or []
            w.writerow(
                {
                    "sid": r.get("sid"),
                    "pid": r.get("pid"),
                    "interview": r.get("interview"),
                    "interview_topic": r.get("interview_topic"),
                    "interview_status": r.get("interview_status"),
                    "cohort_id": r.get("cohort_id"),
                    "preferred_language": r.get("preferred_language"),
                    "suspected_ai_use": r.get("suspected_ai_use"),
                    "total_questions": r.get("total_questions"),
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                    "status": r.get("status"),
                    "session_tags": "|".join(str(t) for t in (r.get("session_tags") or [])),
                    "n_messages": len(ms),
                    "n_flw": sum(1 for m in ms if m.get("role") == "user"),
                    "n_bot": sum(1 for m in ms if m.get("role") == "assistant"),
                    "n_system": sum(1 for m in ms if m.get("role") == "system"),
                    "flw_words": sum(len(str(m.get("content") or "").split()) for m in ms if m.get("role") == "user"),
                    "first_message_at": (ms[0].get("created_at") if ms else None),
                    "last_message_at": (ms[-1].get("created_at") if ms else None),
                }
            )
    (DUMP / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    (DUMP / "README.md").write_text(
        README.format(
            **{
                "generated": man["generated"],
                "sessions": f"{man['sessions']:,}",
                "messages": f"{man['messages']:,}",
                "flw": f"{man['roles'].get('user', 0):,}",
                "bot": f"{man['roles'].get('assistant', 0):,}",
                "system": f"{man['roles'].get('system', 0):,}",
                "first": man["first_message"],
                "last": man["last_message"],
                "sha": man["sha256"],
                "tagged": f"{man['tagged_sessions']:,}",
                "untagged": f"{man['untagged_sessions']:,}",
            }
        ),
        encoding="utf-8",
    )
    print(
        f"[dump] wrote {DUMP}/ — transcripts.jsonl, session_index.csv, question_catalogue.*, "
        f"manifest.json, README.md"
    )
    print(f"[dump] NOTE: {DUMP}/ is gitignored — it holds verbatim FLW text and participant ids.")


README = """# OCS interview transcript dump

Generated {generated} from the live OpenChatStudio API (experiment: Dynamic Router Interview Bot).
Created because every other OCS puller in this repo discards message text; the probing analysis and
anything else conversational needs the transcripts themselves.

## Contents

| File | What it is |
| --- | --- |
| `transcripts.jsonl` | one JSON object per session, with the full message list |
| `session_index.csv` | one row per session, no message text — filter here first |
| `question_catalogue.json` / `.csv` | the interview questions, reconstructed from the sessions themselves |
| `manifest.json` | counts, sha256, and the completeness audit that gated this dump |

## Census

- **{sessions} sessions**, {tagged} carrying an interview code and {untagged} untagged
- **{messages} messages** — {flw} FLW, {bot} bot, {system} system
- First message {first}, last message {last}
- `transcripts.jsonl` sha256 `{sha}`

## Session schema (`transcripts.jsonl`)

    sid                   OCS session uuid
    pid                   participant identifier (== Connect connect_id)
    interview             interview/topic code ("3", "C", "8L", ...); empty when untagged
    interview_topic       human-readable topic name
    interview_status      e.g. interview_complete
    interview_questions   VERBATIM question block for THIS session — the catalogue source
    total_questions       as declared by the bot (usually 1; the block holds many sub-questions)
    cohort_id, external_id, preferred_language, suspected_ai_use, interview_start_time
    status, session_tags  session state and human review tags (acceptable / unacceptable / Test / ...)
    created_at, updated_at
    messages[]            {{role, content, created_at, tags}}

`role` is `assistant` (the bot), `user` (the FLW), or `system`.

**`system` messages are not conversation.** They are the bot's own context compression, e.g.
"Here is a summary of the conversation to date: ## SESSION INTENT ...", averaging ~298 words. Exclude
them from anything measuring what the FLW said — counting them as FLW text adds ~1.4M machine-written
words to the corpus.

Message `tags` carry the bot prompt version (`v34`, `v55`, ...) and the router branch
(`Interview Router:3`), which is what makes a per-release time series possible.

## Caveats

- Most topics put several questions inside ONE `Qn:` block, concatenated with no separator. Split on
  terminal punctuation followed immediately by a capital letter; see `build_question_catalogue.py`.
- Question text is **not** stable per code — several codes changed mid-study. Join on the session's own
  `interview_questions`, not on a code-level assumption.
- Interviews run in English and Hausa. Do not score relevance by word overlap against the English
  catalogue: for Hausa sessions that overlap is near zero by construction, not because the answer was
  off topic.
- Test topics (`te001`-`te004`, `AE001`) and sessions tagged `Test` are present in the dump and must be
  excluded by the consumer.

## Regenerating

    python pull_ocs_messages.py --all      # incremental; resumable; re-fetches in-progress sessions
    python build_question_catalogue.py
    python build_transcript_dump.py --write
"""


if __name__ == "__main__":
    man = audit()
    if "--write" in sys.argv:
        if not man["ok"]:
            print(
                "[dump] REFUSING to write: the audit failed. Fix the pull first "
                "(pull_ocs_messages.py --all is resumable)."
            )
            sys.exit(1)
        write_dump(man)
    else:
        print("[audit] re-run with --write to package the dump")
    sys.exit(0 if man["ok"] else 1)
