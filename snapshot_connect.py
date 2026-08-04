#!/usr/bin/env python3
"""snapshot_connect.py — version + track the Connect fallback snapshot.

The daily refresh normally pulls Connect user_data live; if that ever fails it falls back to the
CONNECT_SNAP_1/2/3 GitHub secrets, which are a frozen copy of connect_user_data_snapshot.csv. When
that frozen copy is stale (e.g. it predates new cohorts) the fallback silently undercounts. To keep
the fallback trustworthy, regenerate + re-version it whenever a MAJOR change lands (see
docs/CONNECT_SNAPSHOT_CHECKLIST.md).

This script makes that a tracked, one-command step. It:
  1. archives the current connect_user_data_snapshot.csv to connect_snapshots/  (gitignored — holds
     participant usernames), named connect_user_data_snapshot_v<N>_<YYYY-MM-DD>.csv
  2. appends a METADATA-ONLY row (version, date, cohorts, rows, sha256, note — NO participant data)
     to docs/connect_snapshot_manifest.csv  (tracked in git — this is the version log)
  3. (with --push-secrets) pushes the snapshot to CONNECT_SNAP_1/2/3 so the fallback is current

Usage:
  python snapshot_connect.py --date 2026-08-04 --note "onboarded ABT3/2WT/EXT; token re-auth"
  python snapshot_connect.py --date 2026-08-04 --note "..." --push-secrets      # also update fallback
"""
import argparse
import base64
import csv
import gzip
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SNAP = ROOT / "connect_user_data_snapshot.csv"
ARCHIVE_DIR = ROOT / "connect_snapshots"
MANIFEST = ROOT / "docs" / "connect_snapshot_manifest.csv"
MANIFEST_COLS = ["version", "date", "cohorts", "rows", "sha256", "archived_file", "note"]
N_CHUNKS = 3
sys.stdout.reconfigure(encoding="utf-8")


def _stats():
    rows = list(csv.DictReader(SNAP.open(encoding="utf-8")))
    cohorts = {(r.get("cohort_id") or "").strip() for r in rows if (r.get("cohort_id") or "").strip()}
    sha = hashlib.sha256(SNAP.read_bytes()).hexdigest()[:16]
    return len(rows), len(cohorts), sha


def _next_version():
    if not MANIFEST.exists():
        return 1
    rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    return max((int(r["version"]) for r in rows), default=0) + 1


def _append_manifest(row):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with MANIFEST.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLS)
        if new:
            w.writeheader()
        w.writerow(row)


def _push_secrets(repo):
    b64 = base64.b64encode(gzip.compress(SNAP.read_bytes(), 9)).decode()
    size = -(-len(b64) // N_CHUNKS)
    for i in range(N_CHUNKS):
        chunk = b64[i * size : (i + 1) * size] or ""
        cmd = ["gh", "secret", "set", f"CONNECT_SNAP_{i+1}"] + (["--repo", repo] if repo else [])
        r = subprocess.run(cmd, input=chunk, text=True)
        if r.returncode != 0:
            sys.exit(f"FAILED to set CONNECT_SNAP_{i+1} (gh authenticated?)")
        print(f"  set CONNECT_SNAP_{i+1} ({len(chunk)} chars)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="snapshot date YYYY-MM-DD (Date.now unavailable in scripts)")
    ap.add_argument("--note", required=True, help="what major change this snapshot captures")
    ap.add_argument("--push-secrets", action="store_true", help="also update CONNECT_SNAP_1/2/3 fallback")
    ap.add_argument("--repo", default="asidtharthan/connect-labs-AaS")
    args = ap.parse_args()

    if not SNAP.exists():
        sys.exit(f"Missing {SNAP.name} — run fetch_connect_user_data.py first.")

    rows, cohorts, sha = _stats()
    ver = _next_version()
    ARCHIVE_DIR.mkdir(exist_ok=True)
    archived = f"connect_user_data_snapshot_v{ver}_{args.date}.csv"
    shutil.copy2(SNAP, ARCHIVE_DIR / archived)

    _append_manifest(
        {
            "version": ver,
            "date": args.date,
            "cohorts": cohorts,
            "rows": rows,
            "sha256": sha,
            "archived_file": archived,
            "note": args.note,
        }
    )
    print(f"✓ snapshot v{ver}: {rows} rows / {cohorts} cohorts / sha {sha}")
    print(f"  archived -> connect_snapshots/{archived}  (gitignored)")
    print("  logged   -> docs/connect_snapshot_manifest.csv  (commit this)")

    if args.push_secrets:
        print("Pushing fallback secrets (CONNECT_SNAP_1/2/3)...")
        _push_secrets(args.repo)
        print("✓ fallback secrets updated to this version")
    else:
        print("Fallback secrets NOT changed (add --push-secrets to update the CONNECT_SNAP_* fallback).")


if __name__ == "__main__":
    main()
