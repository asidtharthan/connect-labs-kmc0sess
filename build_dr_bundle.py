"""Bundle the source legs that CANNOT be re-pulled later, for off-machine backup.

The frozen report set under docs/report_freeze/ is derived data. It is enough to defend a number in
review; it is NOT enough to rebuild the pipeline. Every upstream source lives in exactly one place -
this machine - and none of it is in git.

What can be re-pulled from upstream, so is NOT bundled:
  hq_pull_full/            105 MB. Append-only forms, and pull_hq_full_payloads.py is resumable.
  ocs_transcript_dump/     186 MB. Re-derivable, and it holds FLW answers, so it should not be
                           copied around casually.

What CANNOT be re-pulled, and so is:
  _ocs_state_cache.json    session state INCLUDING interview_status. OCS has no as-of query, so a
                           historical status is gone the moment it changes.
  _ocs_tags_cache.json     review verdicts. These arrive weeks after completion and get revised,
                           so today's verdict state is unrecoverable tomorrow.
  _ocs_words_cache.json    per-session word counts, derived from message content we do not keep.
  connect_user_data_snapshot.csv  a point-in-time enrolment snapshot. Connect exposes current
                           state only; yesterday's funnel cannot be re-pulled.
  _interview_schedule.json the CCHQ lookup. Changes when a cohort is reconfigured.
  master_4src.csv          the built master, with REAL ids. The bridge back to the pipeline.
  dashboard_data.json      the built payload.
  .report_freeze_salt      without it the re-keying is irreversible FOREVER.
  docs/report_freeze/.id_map_*.csv  the only link from FLW_xxxxxxxx back to a Connect id.

⚠ This bundle contains REAL participant identifiers. It is written OUTSIDE the repo and must never
be committed or shared. Its purpose is to be copied to access-controlled storage so that one laptop
failing does not make the re-keying permanently irreversible.

    python build_dr_bundle.py                 # writes ../connect-labs-dr-backup/<date>/
    python build_dr_bundle.py D:/backups       # or a location you choose
"""

import hashlib
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
DEST_BASE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "connect-labs-dr-backup"
STAMP = sys.argv[2] if len(sys.argv) > 2 else str(date.today())
DEST = DEST_BASE / STAMP

IRREPLACEABLE = [
    ("_ocs_state_cache.json", "OCS session state incl. interview_status; no as-of query upstream"),
    ("_ocs_tags_cache.json", "review verdicts; arrive late and get revised"),
    ("_ocs_words_cache.json", "per-session word counts, from content we do not keep"),
    ("connect_user_data_snapshot.csv", "point-in-time Connect enrolment; only current state upstream"),
    ("_interview_schedule.json", "CCHQ schedule lookup; changes when a cohort is reconfigured"),
    ("master_4src.csv", "the built master WITH REAL IDS - the bridge back to the pipeline"),
    ("dashboard_data.json", "the built payload"),
    ("_run_history.json", "regression-guard history; the stall check reads it"),
    (".report_freeze_salt", "WITHOUT THIS THE RE-KEYING IS IRREVERSIBLE FOREVER"),
]


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


DEST.mkdir(parents=True, exist_ok=True)
copied, missing = [], []

for rel, why in IRREPLACEABLE:
    src = ROOT / rel
    if not src.exists():
        missing.append((rel, why))
        continue
    dst = DEST / src.name
    shutil.copy2(src, dst)
    copied.append((src.name, dst.stat().st_size, sha(dst), why))

# the id maps live inside the freeze folder and are gitignored
for m in sorted((ROOT / "docs/report_freeze").glob(".id_map_*.csv")):
    dst = DEST / m.name
    shutil.copy2(m, dst)
    copied.append((m.name, dst.stat().st_size, sha(dst), "the ONLY link from FLW_xxxxxxxx back to a Connect id"))

# the whole shareable freeze folder too, so one bundle restores both halves
fz = DEST / "report_freeze"
fz.mkdir(exist_ok=True)
nf = 0
for p in sorted((ROOT / "docs/report_freeze").iterdir()):
    if p.is_file() and not p.name.startswith("."):
        shutil.copy2(p, fz / p.name)
        nf += 1

head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
branch = subprocess.run(
    ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, capture_output=True, text=True
).stdout.strip()

L = [
    "DISASTER RECOVERY BUNDLE",
    "=" * 78,
    "",
    "taken            %s" % STAMP,
    f"repo commit      {head}  ({branch})",
    "",
    "*** THIS BUNDLE CONTAINS REAL PARTICIPANT IDENTIFIERS ***",
    "Never commit it and never share it. Store it in access-controlled storage. Its whole purpose",
    "is that one laptop failing must not make the re-keying permanently irreversible.",
    "",
    "WHY THESE FILES AND NOT OTHERS",
    "-" * 78,
    "Everything here is a source that CANNOT be re-pulled as it was. OCS has no as-of query, so a",
    "historical interview_status or review verdict is gone the moment it changes. Connect exposes",
    "current state only, so yesterday's funnel cannot be recovered. The salt and the id map have no",
    "upstream at all - they exist only where they were generated.",
    "",
    "Deliberately NOT bundled, because upstream can still supply them:",
    "  hq_pull_full/         105 MB, append-only forms; pull_hq_full_payloads.py is resumable",
    "  ocs_transcript_dump/  186 MB, re-derivable, and it holds FLW answers",
    "",
    "CONTENTS",
    "-" * 78,
]
for name, size, h, why in copied:
    L.append("%-34s %11d bytes  %s" % (name, size, h[:16]))
    L.append("%-34s %s" % ("", why))
L += [
    "",
    "report_freeze/                     %d shareable files, copied verbatim" % nf,
    "",
    "RESTORE ORDER",
    "-" * 78,
    "1. git clone the repo and check out %s" % head[:12],
    "2. copy every loose file in this bundle back into the repo root",
    "3. copy .id_map_*.csv back into docs/report_freeze/",
    "4. python verify_freeze.py            -> expect 18 passed, 0 failed",
    "5. python preflight.py                -> expect all checks green",
    "",
    "If step 4 fails on checksums, the bundle is damaged; use an older one. If it fails on the",
    "aggregate checks, the data is damaged in a way checksums cannot see, which is worse - the",
    "figures no longer reproduce and nothing published from that set can be defended.",
    "",
    "WHAT THIS BUNDLE STILL CANNOT DO",
    "-" * 78,
    "It cannot recover data upstream has deleted, and it cannot reconstruct a state older than the",
    "oldest bundle. That is the argument for taking one on every change that moves a number rather",
    "than once.",
]
if missing:
    L += ["", "ABSENT WHEN THIS BUNDLE WAS TAKEN", "-" * 78]
    for rel, why in missing:
        L.append("%-34s %s" % (rel, why))
    L.append("")
    L.append("An absent file is not automatically a problem - _run_history.json only exists after a")
    L.append("CI run - but check the list before relying on this bundle to restore anything.")

(DEST / "DR_MANIFEST.txt").write_text("\n".join(L) + "\n", encoding="utf-8")

total = sum(s for _, s, _, _ in copied) + sum(
    (fz / p.name).stat().st_size
    for p in (ROOT / "docs/report_freeze").iterdir()
    if p.is_file() and not p.name.startswith(".")
)
print("wrote %s" % DEST)
print("  %d irreplaceable source files + %d freeze files = %.1f MB" % (len(copied), nf, total / 1048576))
if missing:
    print("  ABSENT: %s" % ", ".join(r for r, _ in missing))
print("  DR_MANIFEST.txt records checksums and the restore order")
print()
print("  *** contains REAL identifiers - copy to access-controlled storage, never commit ***")
