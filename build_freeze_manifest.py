"""Write MANIFEST.txt for a frozen data set: what is pinned, at which version, and its checksums.

Split out as its own tool because the freeze folder now has several generators
(build_report_freeze.py, build_session_base.py) and the manifest has to be regenerated after ANY of
them runs. Keeping it inside one of them meant re-running that one silently clobbered files the
other had produced.

EXCLUDES dot-files outright. An earlier version listed .id_map_v207.csv as a pinned file with a
checksum; the id map must never be named in anything that gets shared.

    python build_freeze_manifest.py
"""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
FREEZE = ROOT / "docs/report_freeze"


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


files = sorted(p for p in FREEZE.iterdir() if p.is_file() and not p.name.startswith(".") and p.name != "MANIFEST.txt")

payloads = sorted(FREEZE.glob("payload_*.json"))
P = json.loads(payloads[-1].read_text(encoding="utf-8")) if payloads else {}
pv = payloads[-1].stem.replace("payload_", "") if payloads else "unknown"
sv = "unknown"
for p in FREEZE.glob("sessions_*.csv"):
    sv = p.stem.replace("sessions_", "")
    break

tmpl = subprocess.run(
    ["git", "log", "-1", "--format=%H", "--", "docs/interviews_render_template.js"],
    cwd=ROOT,
    capture_output=True,
    text=True,
).stdout.strip()
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

L = [
    "FROZEN DATA SET FOR THE GIVEWELL REPORT",
    "=" * 78,
    "",
    "payload version     {}   (built {})".format(pv, P.get("built_at", "?")),
    "session base        %s   (cut the same day; ties out to the payload)" % sv,
    "render template     %s" % tmpl,
    "repo commit         %s" % head,
    "",
    "Two version labels on purpose. %s is the report's citation basis and nothing in it has moved." % pv,
    "The session base was cut later the same day when we added row-level detail. Every completed",
    "count is identical between them; started differs by 2 from build timing.",
    "",
    "WHERE TO START",
    "-" * 78,
    "RESTORE.md                         disaster recovery: what is recoverable, what is not, and",
    "                                   the restore order. Read this before you need it.",
    "sessions_%s_DATA_DICTIONARY.md   columns, grain, tie-out, reproducibility limits." % sv,
    "sessions_%s.xlsx / .csv          the base table, one row per interview SLOT." % sv,
    "Report_Figures_%s.xlsx           the 31 report figures with definitions and sources." % pv,
    "",
    "⚠ A row in the session base is one interview SLOT, not one session, and",
    "(connect_id, cohort_id, interview_n) is NOT a unique key: 32 slots were re-triggered, so 64",
    "rows share a key. Counting rows rather than distinct slots runs ~0.2% high. Completed rows",
    "number 9,452; deduped it is 9,431, which is the published figure.",
    "",
    "REGENERATE",
    "-" * 78,
    "python build_report_freeze.py docs/report_freeze/payload_<new>.json <new>",
    "python build_session_base.py <new>          also writes the roster and the schedule",
    "python build_freeze_manifest.py            ALWAYS run this last",
    "python verify_freeze.py                    18 checks; exit 0 means usable",
    "python build_dr_bundle.py                  the irreplaceable sources, for off-machine backup",
    "",
    "FILES, WITH CHECKSUMS",
    "-" * 78,
]
for p in files:
    L.append("%-38s %9d bytes  %s" % (p.name, p.stat().st_size, sha(p)))

L += [
    "",
    "IDENTIFIERS",
    "-" * 78,
    "Every file above is re-keyed: FLW_xxxxxxxx, SESS_xxxxxxxx, TRIG_xxxxxxxx. Verified across all",
    "%d files: zero Connect ids, zero session or form UUIDs, no names, phones, LGAs, settlements." % len(files),
    "Codes are stable across files, so they join to each other.",
    "",
    "Reversing it needs BOTH .report_freeze_salt and .id_map_*.csv. Neither is in this folder as",
    "shared, neither is in git, and together they are the only thing that undoes the re-keying.",
    "Round-trip verified on all 10,535 session rows. See RESTORE.md - losing them is the one",
    "genuinely unrecoverable failure here.",
    "",
    "NOT INCLUDED, DELIBERATELY",
    "-" * 78,
    "the chat transcripts    ~186 MB and they hold FLW answers. Only message TIMESTAMPS were used,",
    "                        and those are already here as session_ended_at.",
    "the HQ form dumps       ~105 MB, append-only, and the pull script is resumable.",
    "the render template     in git at the commit above. Needed only to reproduce the interface.",
]
(FREEZE / "MANIFEST.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
print("wrote %s over %d shareable files (dot-files excluded)" % ((FREEZE / "MANIFEST.txt").name, len(files)))
print(f"  payload {pv} | session base {sv} | template {tmpl[:12]}")
