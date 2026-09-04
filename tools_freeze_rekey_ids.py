"""Re-key every worker and session identifier in the frozen citation set.

The repo is a PUBLIC fork and the workflow header states no participant data goes in git, but the
three data files listed one row per worker. This replaces each real identifier with a salted hash of
itself, so:
  - every figure stays recomputable from the files (row counts, gaps, lags are untouched)
  - nobody outside can link a row back to a worker
  - we can still re-link internally, via an UNTRACKED map

The salt lives in .report_freeze_salt and the map in docs/report_freeze/.id_map_v207.csv. Both are
gitignored. Without the salt the mapping cannot be reproduced, which is the point.

Session UUIDs are DROPPED from 2wt_lags rather than hashed: they identify a conversation and add
nothing to auditing a lag.
"""
import csv
import hashlib
import json
import secrets
from pathlib import Path

ROOT = Path(r"C:\Users\Aathithya S\Desktop\connect-labs-AaS")
FREEZE = ROOT / "docs/report_freeze"
VER = "v207"
SALT_F = ROOT / ".report_freeze_salt"

if SALT_F.exists():
    SALT = SALT_F.read_text(encoding="utf-8").strip()
    print("reusing existing salt (so codes stay stable across runs)")
else:
    SALT = secrets.token_hex(32)
    SALT_F.write_text(SALT + "\n", encoding="utf-8")
    print("generated a new 256-bit salt -> .report_freeze_salt (gitignored)")

_seen = {}


def code(real):
    """FLW_xxxxxx, deterministic for a given salt. Truncated to 6 hex = 16.7M space, plenty for 1.5k
    workers and short enough to read, while remaining infeasible to reverse without the salt.

    IDEMPOTENT: an already-keyed value passes straight through. Running this twice used to hash the
    hashes, which silently broke the code->id map while leaving every figure looking correct."""
    r = str(real)
    if r.startswith("FLW_"):
        return r
    if r not in _seen:
        _seen[r] = "FLW_" + hashlib.sha256((SALT + r).encode()).hexdigest()[:6]
    return _seen[r]


# ---------------------------------------------------------------- panel_gaps
p = FREEZE / ("panel_gaps_%s.csv" % VER)
rows = list(csv.reader(p.open(encoding="utf-8")))
out = []
hdr_done = False
for r in rows:
    if r and str(r[0]).startswith("#"):
        out.append(r)
    elif not hdr_done:
        out.append(r)
        hdr_done = True
    elif r:
        out.append([code(r[0])] + r[1:])
with p.open("w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows(out)
print("re-keyed %s (%d data rows)" % (p.name, len(out) - 4))

# ---------------------------------------------------------------- 2wt_lags (drop session_id)
p = FREEZE / ("2wt_lags_%s.csv" % VER)
rows = list(csv.reader(p.open(encoding="utf-8")))
out = []
hdr_done = False
for r in rows:
    if r and str(r[0]).startswith("#"):
        out.append(r)
    elif not hdr_done:
        out.append([r[0]] + r[2:])  # drop the session_id column
        hdr_done = True
    elif r:
        out.append([code(r[0])] + r[2:])
out.insert(2, ["# session_id column removed: it identifies a conversation and adds nothing to a lag audit."])
with p.open("w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows(out)
print("re-keyed %s (%d data rows, session_id dropped)" % (p.name, len(out) - 4))

# ---------------------------------------------------------------- payload
p = FREEZE / ("payload_%s.json" % VER)
D = json.loads(p.read_text(encoding="utf-8"))
n = 0
if isinstance(D.get("flwMatrixV2"), list):
    new = []
    for e in D["flwMatrixV2"]:
        parts = str(e).split("|")
        parts[0] = code(parts[0])
        new.append("|".join(parts))
        n += 1
    D["flwMatrixV2"] = new
for key in ("granular",):
    if isinstance(D.get(key), list):
        for row in D[key]:
            if isinstance(row, dict):
                if row.get("connect_id"):
                    row["connect_id"] = code(row["connect_id"])
                if "session_id" in row:
                    row["session_id"] = "removed"
for key in ("flwEngagement", "flwMatrixOrder", "flwMatrixOrderW"):
    v = D.get(key)
    if isinstance(v, list):
        D[key] = [code(x) if isinstance(x, str) and len(x) == 20 else x for x in v]
    elif isinstance(v, dict):
        D[key] = {(code(k) if len(str(k)) == 20 else k): val for k, val in v.items()}
D["_ids_rekeyed"] = (
    "Worker identifiers are salted hashes, not Connect ids. Every count and "
    "percentage is unchanged. See MANIFEST.txt."
)
p.write_text(json.dumps(D), encoding="utf-8")
print("re-keyed %s (%d matrix rows)" % (p.name, n))

# ---------------------------------------------------------------- the map, untracked
# MERGE, never overwrite. A no-op re-run has an empty _seen, and rewriting from that wiped the map
# entirely - losing the only link back to real ids while leaving every file looking correct.
m = FREEZE / (".id_map_%s.csv" % VER)
merged = {}
if m.exists():
    for row in csv.DictReader(m.open(encoding="utf-8")):
        if row.get("code"):
            merged[row["code"]] = row["connect_id"]
for real, c in _seen.items():
    merged[c] = real
with m.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["code", "connect_id"])
    for c in sorted(merged):
        w.writerow([c, merged[c]])
print(
    "wrote %s (%d ids total, %d new this run) - UNTRACKED, needed to re-link internally"
    % (m.name, len(merged), len(_seen))
)
