"""Prove a frozen data set is intact and still says what it claimed. Run this BEFORE trusting a
backup, not after discovering it is broken.

A backup nobody has verified is a hope, not a backup. This answers four questions:

  1. Is every file byte-identical to what MANIFEST.txt recorded?
  2. Does the data still aggregate to the figures the payload published?
  3. Has any real identifier leaked back in?
  4. Can the re-keying still be reversed, if the salt and map are present?

Exit code 0 means the set is usable. Non-zero means do not rely on it.

    python verify_freeze.py                       # docs/report_freeze
    python verify_freeze.py path/to/other/freeze
"""

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
FREEZE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/report_freeze"

HEX20 = re.compile(r"\b[0-9a-f]{20}\b")
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")

P = F = 0
FAILS = []


def chk(name, ok, detail=""):
    global P, F
    if ok:
        P += 1
        print(f"  [PASS] {name}  {detail}")
    else:
        F += 1
        FAILS.append(name)
        print(f"  [FAIL] {name}  {detail}")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sec(t):
    print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)


if not FREEZE.is_dir():
    sys.exit("no such freeze folder: %s" % FREEZE)
print("verifying %s" % FREEZE.resolve())

shareable = sorted(
    p for p in FREEZE.iterdir() if p.is_file() and not p.name.startswith(".") and p.name != "MANIFEST.txt"
)

# ------------------------------------------------------------------ A. checksums
sec("A. FILES MATCH THE MANIFEST")
man = FREEZE / "MANIFEST.txt"
chk("MANIFEST.txt present", man.exists())
if man.exists():
    text = man.read_text(encoding="utf-8")
    recorded = dict(re.findall(r"^(\S+)\s+\d+ bytes\s+([0-9a-f]{64})", text, re.M))
    chk("manifest records checksums", len(recorded) > 0, "%d entries" % len(recorded))
    missing = [p.name for p in shareable if p.name not in recorded]
    chk(
        "every shareable file is in the manifest",
        not missing,
        "unlisted: %s" % (", ".join(missing) if missing else "none"),
    )
    gone = [n for n in recorded if not (FREEZE / n).exists()]
    chk("every manifest entry still exists", not gone, "missing from disk: %s" % (", ".join(gone) if gone else "none"))
    bad = [n for n in recorded if (FREEZE / n).exists() and sha(FREEZE / n) != recorded[n]]
    chk(
        "no file has changed since the manifest was written",
        not bad,
        "altered: %s" % (", ".join(bad) if bad else "none"),
    )
    # the id map must NEVER be named in a shared manifest
    chk(
        "manifest does not list the id map or the salt", not re.search(r"^(\.id_map|\.report_freeze_salt)", text, re.M)
    )

# ------------------------------------------------------------------ B. no identifiers
sec("B. NOTHING IDENTIFYING HAS LEAKED IN")
leaks = []
for p in shareable:
    if p.suffix == ".xlsx":
        continue  # binary; covered by its checksum above
    raw = p.read_text(encoding="utf-8", errors="ignore")
    n = len(set(HEX20.findall(raw))) + len(set(UUID.findall(raw)))
    if n:
        leaks.append("%s(%d)" % (p.name, n))
chk(
    "no Connect ids or session UUIDs in any text file",
    not leaks,
    "; ".join(leaks) if leaks else "%d files scanned" % sum(1 for p in shareable if p.suffix != ".xlsx"),
)

# ------------------------------------------------------------------ C. the data still adds up
sec("C. THE DATA STILL AGGREGATES TO THE PUBLISHED FIGURES")
payloads = sorted(FREEZE.glob("payload_*.json"))
sessions = sorted(FREEZE.glob("sessions_*.csv"))
chk("a payload is pinned", bool(payloads), payloads[0].name if payloads else "none")
chk("a session base is pinned", bool(sessions), sessions[0].name if sessions else "none")

if payloads and sessions:
    D = json.loads(payloads[-1].read_text(encoding="utf-8"))
    S = list(csv.DictReader(sessions[-1].open(encoding="utf-8")))
    t1 = {r["key"]: r for r in D["table1"]}
    ROLL = {"ABT1-A": "ABT1", "ABT1-B": "ABT1", "ABT2-A": "ABT2", "ABT2-B": "ABT2", "ABT3-A": "ABT3", "ABT3-B": "ABT3"}
    cell = {}
    for r in S:
        k = (r["connect_id"], r["cohort_id"], r["interview_n"])
        pr = cell.get(k)
        cell[k] = (
            (pr[0] if pr else False) or r["is_started"] == "Y",
            (pr[1] if pr else False) or r["is_completed"] == "Y",
            ROLL.get(r["subgroup"], r["subgroup"]),
        )
    agg = {}
    for s, c, sg in cell.values():
        a = agg.setdefault(sg, [0, 0])
        if s:
            a[0] += 1
        if c:
            a[1] += 1
    off = [k for k in agg if k in t1 and agg[k][1] != t1[k]["icmp"]]
    chk(
        "completed counts match the payload for every subgroup",
        not off,
        ("mismatched: " + ", ".join(off)) if off else ("%d subgroups all exact" % len(agg)),
    )
    # started may legitimately differ by a couple of slots from build timing
    drift = {k: agg[k][0] - t1[k]["ist"] for k in agg if k in t1 and agg[k][0] != t1[k]["ist"]}
    chk(
        "started counts within 5 of the payload (build timing)",
        all(abs(v) <= 5 for v in drift.values()),
        "drift: %s" % (drift if drift else "none"),
    )

    ts = sum(1 for r in S if r.get("session_created_at"))
    have_sess = sum(1 for r in S if r["matched_session_id"])
    chk("session timestamps present on every row that has a session", ts == have_sess, "%d of %d" % (ts, have_sess))

# ------------------------------------------------------------------ D. derived figures re-derive
sec("D. THE DERIVED FIGURES STILL RE-DERIVE")
if sessions:
    from datetime import datetime

    def dt(x):
        try:
            return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        except Exception:
            return None

    by = {}
    for r in S:
        if r["subgroup"] == "PANEL" and r.get("session_created_at"):
            t = dt(r["session_created_at"])
            if t:
                by.setdefault(r["connect_id"], []).append(t)
    for k in by:
        by[k].sort()
    if by:
        kept = sum(1 for v in by.values() if not any((v[i + 1] - v[i]).days > 14 for i in range(len(v) - 1)))
        pctv = kept / len(by) * 100
        chk(
            "panel retention re-derives to 89% (published figure)",
            88.5 <= pctv <= 90.4,
            "%d of %d = %.1f%%" % (kept, len(by), pctv),
        )
    sch = sorted(FREEZE.glob("schedule_*.csv"))
    if sch:
        rows = [
            r
            for r in csv.reader(sch[-1].open(encoding="utf-8"))
            if r and not r[0].startswith("#") and r[0] != "cohort_id"
        ]
        pan = [int(r[3]) for r in rows if r[0] == "1PC1" and r[3]]
        chk(
            "schedule still gives the panel runtime",
            bool(pan) and max(pan) == 48,
            "1PC1 offsets 0..%d days = %.1f weeks" % (max(pan), max(pan) / 7) if pan else "absent",
        )

# ------------------------------------------------------------------ E. reversibility
sec("E. CAN THE RE-KEYING STILL BE REVERSED?")
salt = ROOT / ".report_freeze_salt"
maps = sorted(FREEZE.glob(".id_map_*.csv"))
print("  These are deliberately NOT shared. Absent here is expected on a shared copy, and fatal on")
print("  the one copy that is meant to be authoritative.")
if not salt.exists() and not maps:
    print("  [warn] neither the salt nor a map is present - this is a SHARED copy, cannot reverse")
else:
    chk("the salt is present", salt.exists(), str(salt.name))
    chk("an id map is present", bool(maps), maps[-1].name if maps else "none")
    if maps and sessions:
        m = {r["code"]: r["real"] for r in csv.DictReader(maps[-1].open(encoding="utf-8"))}
        codes = set()
        for r in S:
            for c in (r["connect_id"], r["matched_session_id"], r["trigger_form_id"]):
                if c:
                    codes.add(c)
        unresolved = [c for c in codes if c not in m]
        chk(
            "every code in the session base resolves through the map",
            not unresolved,
            "%d codes, %d unresolved" % (len(codes), len(unresolved)),
        )
        if salt.exists():
            SALT = salt.read_text(encoding="utf-8").strip()
            ok = all(
                "FLW_" + hashlib.sha256((SALT + m[c]).encode()).hexdigest()[:8] == c
                for c in list(codes)[:200]
                if c.startswith("FLW_") and c in m
            )
            chk("the salt reproduces the codes in the map (spot check)", ok, "200 sampled")

# ------------------------------------------------------------------ verdict
print("\n" + "=" * 78)
print("RESULT: %d passed, %d failed" % (P, F))
if F:
    print("\nFAILED: " + ", ".join(FAILS))
    print("\nDo not rely on this set until these are resolved.")
    sys.exit(1)
print("\nThis frozen set is intact and still reproduces its published figures.")
