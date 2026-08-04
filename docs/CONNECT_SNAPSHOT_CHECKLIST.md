# Connect Snapshot — regenerate, version & track checklist

The daily interviews refresh pulls Connect user_data **live**. If that live pull fails, it falls back
to a **frozen** copy stored in the `CONNECT_SNAP_1/2/3` GitHub secrets (gzip+base64 of
`connect_user_data_snapshot.csv`). If that frozen copy is **stale**, the fallback silently
**undercounts** — this is exactly what happened when ABT3/2WT/EXT launched but the fallback still
held the pre-launch 64-cohort snapshot (Invited=0, cohorts uncounted).

So: **whenever a major change lands, re-version the snapshot and (optionally) refresh the fallback.**
Snapshots hold participant usernames, so the CSVs are gitignored — we version them locally and track
**metadata only** in git (`docs/connect_snapshot_manifest.csv`).

## When to make a new snapshot version (triggers)
- ✅ A new cohort / subgroup / domain is onboarded (e.g. 2WT, ABT3, EXT).
- ✅ A Connect OAuth token / app is re-authed (the account's cohort access may change).
- ✅ Before a demo / stakeholder review where the fallback must be trustworthy.
- ✅ A large jump in cohort or row count vs the last version.
- ⬜ NOT needed for render-only tweaks or interview-count changes (those don't touch the Connect leg).

## How (one command)
Run from repo root **after** a successful live pull, using the project venv:

```bash
# 1) get fresh live data (mints/rotates the Connect token as needed)
.venv/Scripts/python.exe fetch_connect_user_data.py          # should print "N cohorts", incl. new ones

# 2) version + track it (metadata -> git; CSV -> gitignored archive). Pass the date explicitly.
.venv/Scripts/python.exe snapshot_connect.py --date YYYY-MM-DD --note "what changed"

# 3) commit the version log (metadata only — safe, no participant data)
git add docs/connect_snapshot_manifest.csv && git commit -m "chore: snapshot vN (<note>)"
```

To ALSO refresh the live fallback secrets in the same step, add `--push-secrets`:
```bash
.venv/Scripts/python.exe snapshot_connect.py --date YYYY-MM-DD --note "..." --push-secrets
```
(Leaving the fallback stale is fine as long as the live pull works — it's only a safety net. Refresh it
when you want the net to be current, e.g. after onboarding cohorts.)

## What gets produced
| Artifact | Location | In git? | Contents |
|---|---|---|---|
| Live snapshot | `connect_user_data_snapshot.csv` | ❌ gitignored | participant rows (usernames) |
| Versioned archive | `connect_snapshots/connect_user_data_snapshot_v<N>_<date>.csv` | ❌ gitignored | archived copy per version |
| **Version log** | `docs/connect_snapshot_manifest.csv` | ✅ tracked | metadata only (version, date, cohorts, rows, sha256, note) |
| Fallback | `CONNECT_SNAP_1/2/3` GitHub secrets | (secrets) | gzip+base64 of the CSV |

## Version log
The authoritative history lives in **`docs/connect_snapshot_manifest.csv`** (one row per version).
`snapshot_connect.py` appends to it automatically. Human-readable summary:

| v | date | cohorts | rows | trigger / note |
|---|------|--------:|-----:|----------------|
| 1 | 2026-06-24 | 64 | 2749 | initial headless Connect pull → CONNECT_SNAP fallback (pre ABT3/2WT/EXT) |
| 2 | 2026-08-04 | 72 | 3961 | onboarded ABT3/2WT/EXT; Connect OAuth app + token re-auth |

> The `connect_snapshots/` archive is gitignored (participant data). Keep it on the machine that runs
> the refresh; the manifest is the durable, shareable record of what each fallback version contained.
