#!/usr/bin/env python3
"""pull_live_payload.py — take the FLW aggregates from the PUBLISHED dashboard, not a local build.

Why this exists: the executive brief must quote the same numbers stakeholders see on Labs. Rebuilding
locally does NOT give you those numbers — `hq_pull_full/` is a patchwork of per-domain pulls, and on
2026-08-07 a local build came out ~39% smaller than live (master_rows 6,221 vs 9,930) because only 4
of 12 domains were current. Every gate passed on it, and that stale build is what mis-calibrated the
regression-guard floors. So the published render is the only trustworthy source for document figures.

Read-only against Labs: calls workflow_get and nothing else.

    python pull_live_payload.py            # -> flw_analysis_payload.json + _flw_today.json
    python pull_live_payload.py --print    # also dump the headline figures

Writes (both gitignored):
  flw_analysis_payload.json   DATA.flwEngagement from the live render — what build_flw_docx.py reads
  _flw_today.json             {"today", "built_at", "render_version"} for the document header stamp
"""
import argparse
import json
import sys

from refresh_interviews_dashboard import OWNER_OPP, WORKFLOW_ID, _mcp_call, _mcp_creds

PAYLOAD_OUT = "flw_analysis_payload.json"
STAMP_OUT = "_flw_today.json"


def extract_data_literal(code):
    """Return the `var DATA = {...}` object from a render. Brace-matched, string-aware — the payload
    contains braces and quotes inside string values, so a regex would truncate it."""
    i = code.index("var DATA =")
    j = code.index("{", i)
    depth, k, instr, esc = 0, j, None, False
    while k < len(code):
        c = code[k]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == instr:
                instr = None
        elif c in "\"'":
            instr = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                k += 1
                break
        k += 1
    return json.loads(code[j:k])


def fetch_live():
    """(flwEngagement, stamp) from the currently-published render."""
    url, auth = _mcp_creds()
    if not (url and auth):
        sys.exit("no MCP creds (set MCP_URL/MCP_BEARER, or configure connect_labs in ~/.claude.json)")
    wf = _mcp_call(
        url,
        auth,
        "workflow_get",
        {"workflow_id": WORKFLOW_ID, "opportunity_id": OWNER_OPP, "include_render_code": True},
        {"v": None},
    )
    code, version = wf["render_code"], wf["render_code_version"]
    data = extract_data_literal(code)
    fe = data.get("flwEngagement")
    if not fe or not fe.get("n_flws"):
        sys.exit(f"live render v{version} has no usable flwEngagement block")
    stamp = {"today": data.get("today", ""), "built_at": data.get("built_at", ""), "render_version": version}
    return fe, stamp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print", dest="show", action="store_true", help="print the headline figures")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    fe, stamp = fetch_live()
    with open(PAYLOAD_OUT, "w", encoding="utf-8") as f:
        json.dump(fe, f, separators=(",", ":"))
    with open(STAMP_OUT, "w", encoding="utf-8") as f:
        json.dump(stamp, f)
    print(
        f"live render v{stamp['render_version']} (built {stamp['built_at']}) -> {PAYLOAD_OUT} "
        f"({len(json.dumps(fe)) / 1024:.1f} KB), stamp -> {STAMP_OUT}"
    )
    print(
        f"  n_flws={fe['n_flws']}  personas={len(fe.get('personas', []))}  micro={'yes' if fe.get('micro') else 'NO'}"
    )

    if args.show:
        cc = fe.get("crossCohort", {})
        ds = fe.get("depthSplit", {})
        print(
            f"  per-cohort finish: single {cc.get('single', {}).get('finished_pc')}% vs "
            f"multi {cc.get('multi', {}).get('finished_pc')}%  (finished>=1: "
            f"{cc.get('single', {}).get('finished')}% vs {cc.get('multi', {}).get('finished')}%)"
        )
        print(
            f"  depth split ({ds.get('basis')}, median {ds.get('median')}): "
            f"{ds.get('hi', {}).get('finished_pc')}% vs {ds.get('lo', {}).get('finished_pc')}%"
        )
        print(f"  at-risk: {fe.get('atRisk', {}).get('n')} of {fe.get('atRisk', {}).get('ofUnfinished')} unfinished")


if __name__ == "__main__":
    main()
