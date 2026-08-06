"""Build render_data.json — the PRUNED payload the Labs render actually embeds.

Why this exists
---------------
`refresh_interviews_dashboard.py:inject()` embeds the data payload verbatim into
`docs/interviews_render_template.js`. Labs caps `render_code` at **512 KB** and the artifact was
already at ~466 KB (117 KB code + 349 KB data) — too little headroom for new interactive blocks.

We cannot simply shrink `dashboard_data.json`: `audit_e2e.py`, `build_dashboard_data_audit.py` and
`brutal_verify.py` all assert against it (funnel / flwMatrix / per-cohort dropoff.connect …).
So `dashboard_data.json` stays COMPLETE and this module derives a second, smaller file that is a
faithful, lossless-for-the-UI transform of it:

  1. DROP keys the render provably never reads (verified by grep against the template):
       * top-level  `funnel`, `granular_total`
       * `dropoff.cohorts[sg][].connect`
       * `dropoff.cohorts[sg][].interviews[].pct_completed_base` / `started_di` / `pct_started_di`
     (The SUBGROUP-level `connect` / `pct_completed_base` / `started_di` / `pct_started_di` ARE read
      — `retentionMatrix()`, `ivRow()`, the retention table — and are therefore KEPT.)
  2. RE-ENCODE `flwMatrix` (one row per claimed FLW×cohort, ~180 KB) into three compact keys.

flwMatrix encoding
------------------
  `flwMatrixCohorts`  list of distinct cohort ids, first-appearance order.
  `flwMatrixV2`       one string per UNIQUE FLW, first-appearance order:
                          "<f>|<cohortIdx>:<stateDigits>[u]|<cohortIdx>:<stateDigits>[u]…"
                      cohortIdx = decimal index into flwMatrixCohorts, stateDigits = one digit per
                      topic (state index 0-9), trailing "u" marks the untrained flag.
  `flwMatrixOrder`    parallel to flwMatrixCohorts; each entry is the concatenation of fixed-width
                      base36 indices into `flwMatrixV2` giving the ORIGINAL row order inside that
                      cohort.  `flwMatrixOrderW` is that width.

Why `flwMatrixOrder` is needed (it is not free — ~10 KB — but it is not optional):
the render paginates the FLW×Topic matrix straight off the array (`matFiltered.slice(...)`) and
exports it to CSV in array order, so row ORDER is user-visible. `dashboard_data.json`'s flwMatrix is
COHORT-major, whereas the per-FLW encoding is FLW-major. Measured on live data, no single global FLW
ordering can reproduce every cohort's internal order (the per-cohort orderings contain cycles — a
topological sort over 1470 FLWs fails), so the order has to be carried explicitly. With it the
round-trip is byte-exact, which is what `brutal_verify.py`'s transform-equivalence gate proves.

Written by `build_dashboard_data.py` right after `dashboard_data.json`, so the two can never drift.
"""
import json
import os
import sys

DASH_JSON = "dashboard_data.json"
RENDER_JSON = "render_data.json"

# ---- the ONLY keys this transform is allowed to remove (brutal_verify re-asserts this exact set) ----
DROP_TOP = ("funnel", "granular_total")
DROP_COHORT = ("connect",)
DROP_COHORT_IV = ("pct_completed_base", "started_di", "pct_started_di")

_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"

# Separators used by the flwMatrix encoding. Both are asserted absent from every FLW id and cohort id
# before encoding; if a future id ever contains one the build FAILS LOUDLY rather than silently
# producing a payload the render would mis-decode.
SEP_FLW = "|"
SEP_CELL = ":"


def _b36(n, w):
    s = ""
    while n:
        s = _B36[n % 36] + s
        n //= 36
    return (s or "0").rjust(w, "0")


def encode_flw_matrix(flw_matrix):
    """flwMatrix rows -> (cohorts, v2 strings, order strings, order width). Raises on any violated assumption."""
    cohorts, cidx = [], {}
    flws, fidx = [], {}
    cells = {}          # (fidx, cidx) -> (stateDigits, u)
    order = {}          # cidx -> [fidx, ...] in original row order

    for i, r in enumerate(flw_matrix):
        f, c, s = r["f"], r["c"], r["s"]
        u = r.get("u", 0)
        extra = set(r) - {"f", "c", "s", "u"}
        if extra:
            raise ValueError(f"flwMatrix row {i} has unexpected keys {sorted(extra)} — encoder would drop them")
        if not isinstance(f, str) or not f or SEP_FLW in f or SEP_CELL in f:
            raise ValueError(
                f"flwMatrix row {i}: FLW id {f!r} is empty or contains a separator "
                f"({SEP_FLW!r}/{SEP_CELL!r})"
            )
        if not isinstance(c, str) or not c or SEP_FLW in c or SEP_CELL in c:
            raise ValueError(f"flwMatrix row {i}: cohort id {c!r} is empty or contains a separator")
        if any((not isinstance(v, int)) or isinstance(v, bool) or v < 0 or v > 9 for v in s):
            raise ValueError(f"flwMatrix row {i}: state values {s} are not all single digits 0-9")
        if u not in (0, 1):
            raise ValueError(f"flwMatrix row {i}: untrained flag {u!r} is not 0/1")

        if c not in cidx:
            cidx[c] = len(cohorts)
            cohorts.append(c)
        if f not in fidx:
            fidx[f] = len(flws)
            flws.append(f)
        ci, fi = cidx[c], fidx[f]
        if (fi, ci) in cells:
            raise ValueError(
                f"flwMatrix row {i}: duplicate (FLW, cohort) pair ({f}, {c}) — encoding assumes uniqueness"
            )
        cells[(fi, ci)] = ("".join(str(v) for v in s), u)
        order.setdefault(ci, []).append(fi)

    # cohort refs inside each FLW string keep their original relative order
    per_flw = [[] for _ in flws]
    for i, r in enumerate(flw_matrix):
        fi, ci = fidx[r["f"]], cidx[r["c"]]
        digits, u = cells[(fi, ci)]
        per_flw[fi].append(f"{ci}{SEP_CELL}{digits}{'u' if u else ''}")
    v2 = [f + SEP_FLW + SEP_FLW.join(parts) for f, parts in zip(flws, per_flw)]

    w = 3
    while len(flws) > 36 ** w:
        w += 1
    order_s = ["".join(_b36(fi, w) for fi in order.get(ci, [])) for ci in range(len(cohorts))]
    return cohorts, v2, order_s, w


def decode_flw_matrix(cohorts, v2, order_s, w):
    """Inverse of encode_flw_matrix — mirrors the JS decoder in docs/RENDER_DECODER_PATCH.md."""
    per = []
    for line in v2:
        parts = line.split(SEP_FLW)
        m = {}
        for p in parts[1:]:
            ci, _, body = p.partition(SEP_CELL)
            u = 0
            if body.endswith("u"):
                u, body = 1, body[:-1]
            m[int(ci)] = ([int(ch) for ch in body], u)
        per.append((parts[0], m))
    rows = []
    for ci, cohort in enumerate(cohorts):
        seq = order_s[ci] if ci < len(order_s) else ""
        for off in range(0, len(seq) - w + 1, w):
            fi = int(seq[off:off + w], 36)
            f, m = per[fi]
            s, u = m[ci]
            row = {"f": f, "c": cohort, "s": s}
            if u:
                row["u"] = 1
            rows.append(row)
    return rows


def prune(dd):
    """dashboard_data dict -> render_data dict.

    Does not mutate the input, but retained branches are shared BY REFERENCE (they are serialised
    immediately). Deep-copy the result before mutating it in a test.
    """
    out = {}
    for k, v in dd.items():
        if k in DROP_TOP:
            continue
        if k == "flwMatrix":
            cohorts, v2, order_s, w = encode_flw_matrix(v)
            rt = decode_flw_matrix(cohorts, v2, order_s, w)
            if rt != v:                      # belt-and-braces: never emit an encoding we can't invert
                raise ValueError("flwMatrix encode/decode round-trip mismatch — refusing to write render_data.json")
            out["flwMatrixCohorts"] = cohorts
            out["flwMatrixV2"] = v2
            out["flwMatrixOrder"] = order_s
            out["flwMatrixOrderW"] = w
            continue
        if k == "dropoff":
            # Only the per-COHORT branch is pruned; `subgroups` (and any future sibling key) passes
            # through untouched, in its original key order.
            out[k] = {
                k2: ({
                    sg: [
                        {
                            ck: ([{ik: iv for ik, iv in ivrow.items() if ik not in DROP_COHORT_IV}
                                  for ivrow in cv] if ck == "interviews" else cv)
                            for ck, cv in co.items() if ck not in DROP_COHORT
                        }
                        for co in cos
                    ]
                    for sg, cos in v2b.items()
                } if k2 == "cohorts" else v2b)
                for k2, v2b in v.items()
            }
            continue
        out[k] = v
    return out


def build_and_write(root="."):
    dash_path = os.path.join(root, DASH_JSON)
    render_path = os.path.join(root, RENDER_JSON)
    raw = open(dash_path, encoding="utf-8").read()
    dd = json.loads(raw)
    rd = prune(dd)
    s = json.dumps(rd, separators=(",", ":"))
    open(render_path, "w", encoding="utf-8").write(s)

    before = len(raw.encode())
    after = len(s.encode())
    print(f"{RENDER_JSON}: {after / 1024:.1f} KB  (from {DASH_JSON} {before / 1024:.1f} KB "
          f"— saved {(before - after) / 1024:.1f} KB, {100 * (before - after) / before:.1f}%)")
    print(f"  dropped top-level: {', '.join(DROP_TOP)}")
    print(f"  dropped dropoff.cohorts[].{{{', '.join(DROP_COHORT)}}} and "
          f".interviews[].{{{', '.join(DROP_COHORT_IV)}}}")
    print(f"  flwMatrix: {len(dd.get('flwMatrix', []))} rows -> {len(rd.get('flwMatrixV2', []))} FLW strings "
          f"over {len(rd.get('flwMatrixCohorts', []))} cohorts "
          f"({_kb(dd.get('flwMatrix', [])):.1f} KB -> "
          f"{_kb(rd.get('flwMatrixCohorts')) + _kb(rd.get('flwMatrixV2')) + _kb(rd.get('flwMatrixOrder')):.1f} KB)")
    return rd


def _kb(o):
    return len(json.dumps(o, separators=(",", ":")).encode()) / 1024 if o is not None else 0.0


if __name__ == "__main__":
    try:
        build_and_write(os.path.dirname(os.path.abspath(__file__)))
    except Exception as e:
        print(f"ABORT: render_data build failed: {e}")
        sys.exit(1)
