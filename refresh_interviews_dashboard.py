"""Connect Interviews dashboard — DAILY AUTO-REBUILD orchestrator.

Chains the existing build steps into one hands-off run for the scheduler (Celery beat / GH Actions cron):

  1. (--pull-hq)      pull_hq_full_payloads.py   -> hq_pull_full/*.jsonl     [HQ API key, headless OK]
  2. (--pull-ocs)     reconcile_live_ocs.py      -> _ocs_state_cache.json    [OCS bearer key, headless OK]
  3. (--pull-connect) fetch_all_cohorts.py       -> <cohort>_audit/user_data.csv  [needs CONNECT_TOKEN/PAT]
  4. build_payload_agg.py        -> payload_agg.json        (imports build_master_4src)
  5. build_dashboard_data.py     -> dashboard_data.json
  6. audit_e2e.py + build_dashboard_data_audit.py   (ABORTS the run if any check fails)
  7. inject dashboard_data.json into docs/interviews_render_template.js -> docs/interviews_master_v3_render.js
  7b. brutal_verify.py   independent re-derivation from RAW sources + cross-place + render-binding gate (ABORTS on mismatch)
  8. (--push)         update workflow 3962 render_code on Labs   [needs CONNECT_TOKEN/PAT]

Defaults: steps 1-3 are SKIPPED (uses existing local source files) so the build+audit+inject
chain runs anywhere with no credentials. The scheduler turns on the pull/push flags + token.

Connect note: step 3 needs a headless Connect credential (PAT). Until that's wired, run WITHOUT
--pull-connect and the Connect-funnel columns reuse the last local user_data snapshot (static),
while HQ+OCS-derived numbers refresh live. See docs for the PAT setup.

AUTO-LOAD (cohorts/subgroups appearing over time):
  * HQ + OCS legs auto-load every cohort whose id maps to a known subgroup (cohort_to_sg in
    build_master_4src.py: TRS/TRE/ABT1/ABT2/ABT3/PANEL). A NEW program type whose id matches none
    is collected into bm.unmapped_cohorts and surfaced on the dashboard (amber notice) rather than
    dropped — add a SUBGROUP_DESIGN entry + a cohort_to_sg branch to fold it in fully.
  * A subgroup only appears once it has data (build_payload_agg present-only emit), so PANEL/ABT3
    stay hidden until their first cohort launches.
  * CONNECT FUNNEL is the one leg that does NOT auto-refresh: it comes from the static
    connect_user_data_snapshot.csv (Connect has no headless auth — CORS + key secrecy). New cohorts'
    Invited/Accepted/Claimed numbers update only when the snapshot is regenerated. To refresh it:
      1. Re-pull Connect user_data into the per-cohort folders:
           python fetch_all_cohorts.py            # needs a Connect PAT/token (browser-derived)
         -> writes <cohort>_audit/user_data.csv for every cohort (new cohorts get new folders).
      2. Consolidate the folders into the snapshot CSV (one row per FLW, prefixed with cohort_id =
         folder name minus the "_audit" suffix). Columns: cohort_id, username, invited_date,
         user_invite_status, date_learn_started, completed_learn_date, date_claimed.
      3. Re-set the gzip+base64 GitHub secrets the daily CI reassembles (CONNECT_SNAP_1/2/3):
           python setup_dashboard_secrets.py --repo <owner>/<name>
         The snapshot CSV is NOT committed (participant ids); the daily job rebuilds it from the secrets.
    (Run build locally with INTERVIEWS_CONNECT_SNAPSHOT=1 to force the snapshot path even when folders exist.)

Usage:
  python refresh_interviews_dashboard.py                          # build + audit + inject (no creds)
  python refresh_interviews_dashboard.py --pull-hq --pull-ocs     # + live HQ/OCS pull
  python refresh_interviews_dashboard.py --pull-hq --pull-ocs --pull-connect --push   # full daily run
"""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
WORKFLOW_ID = 3962
OWNER_OPP = 1251
TEMPLATE = os.path.join("docs", "interviews_render_template.js")
RENDER_OUT = os.path.join("docs", "interviews_master_v3_render.js")
DATA_JSON = "dashboard_data.json"

# UTF-8 so the audit scripts' unicode (Σ, ÷, —) don't crash on Windows consoles.
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def run(label, cmd, required=True):
    print(f"\n=== {label} ===", flush=True)
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT, env=ENV)
    dt = time.time() - t0
    ok = r.returncode == 0
    print(f"--- {label}: {'OK' if ok else 'FAILED rc=' + str(r.returncode)} ({dt:.0f}s)", flush=True)
    if required and not ok:
        print(f"ABORT: required step failed: {label}", flush=True)
        sys.exit(1)
    return ok


def inject():
    """Inject dashboard_data.json into the render template -> final render JS. Babel-validated separately."""
    print("\n=== 7. inject data into render template ===", flush=True)
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    with open(DATA_JSON, encoding="utf-8") as f:
        data = f.read().strip()
    if "/*__DATA__*/" not in tpl:
        print("ABORT: template missing /*__DATA__*/ placeholder", flush=True)
        sys.exit(1)
    out = tpl.replace("/*__DATA__*/", data)
    with open(RENDER_OUT, "w", encoding="utf-8") as f:
        f.write(out)
    kb = len(out.encode()) / 1024
    print(f"--- wrote {RENDER_OUT} ({kb:.1f} KB)", flush=True)
    if kb > 500:
        print(f"WARNING: render is {kb:.0f} KB, near the 512 KB Labs limit — reduce granular sample.", flush=True)
    return out


def _mcp_creds():
    """MCP endpoint + bearer: prefer env (MCP_URL/MCP_BEARER for CI secrets), else ~/.claude.json."""
    url = os.environ.get("MCP_URL")
    bearer = os.environ.get("MCP_BEARER")
    if url and bearer:
        return url, bearer if bearer.lower().startswith("bearer ") else "Bearer " + bearer
    try:
        import json as _j

        cfg = _j.load(open(os.path.expanduser("~/.claude.json")))
        m = cfg["mcpServers"]["connect_labs"]
        return m["url"], m["headers"]["Authorization"]
    except Exception as e:
        print(f"    no MCP creds (env MCP_URL/MCP_BEARER or ~/.claude.json): {e}", flush=True)
        return None, None


def _mcp_call(url, auth, tool, args, _sid):
    """Invoke one MCP tool over streamable-HTTP JSON-RPC. Returns the unwrapped result dict."""
    import urllib.request

    def rpc(method, params, _id):
        body = json.dumps({"jsonrpc": "2.0", "id": _id, "method": method, "params": params}).encode()
        h = {
            "Authorization": auth,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if _sid["v"]:
            h["Mcp-Session-Id"] = _sid["v"]
        req = urllib.request.Request(url, data=body, method="POST", headers=h)
        with urllib.request.urlopen(req, timeout=180) as r:
            if r.headers.get("Mcp-Session-Id"):
                _sid["v"] = r.headers["Mcp-Session-Id"]
            raw = r.read().decode()
        out = None
        for line in raw.splitlines():
            if line.startswith("data:"):
                out = json.loads(line[5:].strip())
        return out if out is not None else json.loads(raw)

    if not _sid["v"]:
        rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "refresh-job", "version": "1"},
            },
            1,
        )
        try:
            rpc("notifications/initialized", {}, 2)
        except Exception:
            pass
    r = rpc("tools/call", {"name": tool, "arguments": args}, 99)
    res = r.get("result", {})
    content = res.get("content")
    if content:
        v = json.loads(content[0]["text"])
        while isinstance(v, list) and v and isinstance(v[0], dict) and "text" in v[0]:
            v = json.loads(v[0]["text"])
        return v
    return res


def push(render_code):
    """Step 8: update workflow 3962 render_code headless via the connect_labs MCP HTTP endpoint.
    PROVEN working (re-pushed v6->v7 from a plain script). No browser / Option A / Option B needed."""
    url, auth = _mcp_creds()
    if not (url and auth):
        print("\n=== 8. push: SKIPPED — no MCP creds ===", flush=True)
        return False
    print(f"\n=== 8. push render to workflow {WORKFLOW_ID} via MCP ({url}) ===", flush=True)
    sid = {"v": None}
    try:
        wf = _mcp_call(
            url,
            auth,
            "workflow_get",
            {"workflow_id": WORKFLOW_ID, "opportunity_id": OWNER_OPP, "include_render_code": False},
            sid,
        )
        v0 = wf.get("render_code_version")
        res = _mcp_call(
            url,
            auth,
            "workflow_update_render_code",
            {
                "workflow_id": WORKFLOW_ID,
                "opportunity_id": OWNER_OPP,
                "expected_version": v0,
                "component_code": render_code,
            },
            sid,
        )
        new_v = res.get("new_version")
        ok = new_v == (v0 + 1) if isinstance(v0, int) else bool(new_v)
        print(
            f"--- push: render_code_version {v0} -> {new_v}  {'OK' if ok else 'UNEXPECTED: ' + str(res)}", flush=True
        )
        return new_v if ok else False
    except Exception as e:
        print(f"--- push FAILED: {repr(e)[:300]}", flush=True)
        return False


def write_github_summary(pushed_version):
    """Write a clear run summary to GITHUB_STEP_SUMMARY (visible on the Actions run + drives the daily ping)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        d = json.load(open(DATA_JSON, encoding="utf-8"))
        c = d.get("counts", {})
        ok = bool(pushed_version)
        head = "✅ Dashboard updated" if ok else "⚠️ Built but NOT published"
        lines = [
            f"## {head} — Connect Interviews",
            "",
            f"- **Status:** {'published render v' + str(pushed_version) if ok else 'not published'}",
            f"- **Cohorts:** {c.get('cohorts')}  ·  **FLWs:** {c.get('flws')}",
            f"- **Interviews started:** {c.get('started')}  ·  **completed:** {c.get('completed')}",
            f"- **Data as of:** {d.get('today', '')}",
            "",
            f"[Open the dashboard »](https://labs.connect.dimagi.com/labs/workflow/{WORKFLOW_ID}/run/?opportunity_id={OWNER_OPP})",
        ]
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        print(f"  (summary write skipped: {e})", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull-hq", action="store_true", help="live-pull CommCare HQ forms (API key)")
    ap.add_argument("--pull-ocs", action="store_true", help="live-pull OCS sessions (bearer key)")
    ap.add_argument("--pull-words", action="store_true", help="live-pull OCS message word counts (avg-words metric)")
    ap.add_argument("--pull-connect", action="store_true", help="live-pull Connect user_data (needs PAT)")
    ap.add_argument("--push", action="store_true", help="push refreshed render to workflow 3962 (needs PAT)")
    ap.add_argument("--full-resync", action="store_true",
                    help="force a FULL OCS re-scan (state + words) instead of the incremental window (self-heal)")
    args = ap.parse_args()
    ocs_full = ["--full"] if args.full_resync else []

    print(f"Connect Interviews dashboard refresh — workflow {WORKFLOW_ID} (opp {OWNER_OPP})", flush=True)

    # 1-3: live source pulls (optional; default uses existing local snapshot files)
    if args.pull_hq:
        run("1. pull HQ forms", [PY, "pull_hq_full_payloads.py"])
        # untrained_flw lives on the commcare-user usercase (Case API), headless via HQ key.
        # non-critical: if it fails, the build degrades gracefully (everyone defaults to trained).
        run("1b. pull HQ user cases (untrained_flw)", [PY, "pull_hq_user_cases.py"], required=False)
        # interview cadence + topic sequence from the interview_schedule lookup (bot's runtime truth).
        # non-critical: if it fails, the build falls back to the hardcoded design.
        run("1c. pull HQ interview schedule (cadence/topics)", [PY, "pull_hq_interview_schedule.py"], required=False)
    else:
        print("\n=== 1. pull HQ: skipped (using existing hq_pull_full/) ===", flush=True)
    if args.pull_ocs:
        run("2. pull OCS sessions (incremental)", [PY, "pull_ocs_state.py", *ocs_full])
    else:
        print("\n=== 2. pull OCS: skipped (using existing _ocs_state_cache.json) ===", flush=True)
    if args.pull_words:
        run("2b. pull OCS message word counts (incremental)", [PY, "pull_ocs_words.py", *ocs_full])
    else:
        print("\n=== 2b. pull words: skipped (using existing _ocs_words_cache.json) ===", flush=True)
    if args.pull_connect:
        # headless Connect pull (OAuth refresh-token grant) — regenerates connect_user_data_snapshot.csv.
        # non-critical: on failure the build falls back to the existing snapshot / CONNECT_SNAP secrets.
        run("3. pull Connect user_data (headless)", [PY, "fetch_connect_user_data.py"], required=False)
    else:
        print("\n=== 3. pull Connect: skipped (Connect funnel reuses last local user_data snapshot) ===", flush=True)

    # 4-5: build
    run("4. build aggregates (payload_agg)", [PY, "build_payload_agg.py"])
    run("5. build dashboard_data", [PY, "build_dashboard_data.py"])

    # 6: audit — hard gate
    run("6a. end-to-end audit (27/27)", [PY, "audit_e2e.py"])
    run("6b. dashboard_data audit (18/18)", [PY, "build_dashboard_data_audit.py"])

    # 7: inject
    render = inject()

    # 7b: brutal independent re-verification — re-parses RAW sources + re-aggregates from
    # master_4src.csv with its own code (imports no build script), then checks every dashboard
    # number, cross-place consistency, and that the injected render embeds dashboard_data.json
    # verbatim. Hard gate: aborts before publishing if anything is off. Freshness asserts here
    # are enforced only when INTERVIEWS_STRICT_FRESHNESS=1 (set in the daily CI after a live pull).
    run("7b. brutal independent re-verification", [PY, "brutal_verify.py"])

    # 8: push (gated on token)
    pushed_version = None
    if args.push:
        pushed_version = push(render)
    else:
        print("\n=== 8. push: skipped (no --push) ===", flush=True)

    write_github_summary(pushed_version)
    # Fail loudly if a publish was requested but didn't happen (e.g. expired MCP token) — otherwise the
    # job exits green while the dashboard silently stays on the old render. (Root-caused 2026-07-07: an
    # expired MCP_BEARER made push() print "FAILED" and return False, yet the run still reported success.)
    if args.push and not pushed_version:
        print("\nABORT: --push requested but publish FAILED (see step 8) — failing the job so it is not "
              "silently left un-published. Most likely the MCP_BEARER token expired; re-mint it.", flush=True)
        sys.exit(1)
    print("\nDONE.", flush=True)


if __name__ == "__main__":
    main()
