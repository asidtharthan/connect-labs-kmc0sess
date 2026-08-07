#!/usr/bin/env python3
"""checkpoint.py — versioned rollback points for the Connect Interviews dashboard.

WHY: the dashboard rebuilds and republishes itself every morning, so "what was live last Tuesday"
is otherwise unrecoverable. A checkpoint pins a known state — git commit + git tag + the Labs
render_code_version that was live + the gate results and payload sizes at that moment — so any
change can be rolled back to a state we know was good.

WHAT A CHECKPOINT IS NOT: a copy of the data. The render is regenerated from live sources on every
run, and participant-derived payloads are deliberately never committed (see refresh-interviews.yml).
Rolling back means "rebuild today's data with that day's CODE", which is the meaningful rollback —
and it is why every checkpoint records the gate results that code produced.

    python checkpoint.py list                      # the ledger
    python checkpoint.py show cp-0002
    python checkpoint.py create "label" [--sha X] [--verify] [--live] [--note "..."]
        --verify   run the full build + all three gates and record the results (slow, ~2 min)
        --live     query Labs for the currently-published render_code_version
    python checkpoint.py rollback cp-0001          # prints the runbook; never acts on its own

The ledger lives in checkpoints/manifest.json and is mirrored to docs/CHECKPOINTS.md.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
CPDIR = os.path.join(ROOT, "checkpoints")
MANIFEST = os.path.join(CPDIR, "manifest.json")
LEDGER = os.path.join(ROOT, "docs", "CHECKPOINTS.md")
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "INTERVIEWS_CONNECT_SNAPSHOT": "1"}


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def load():
    if not os.path.exists(MANIFEST):
        return {"checkpoints": []}
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def save(m):
    os.makedirs(CPDIR, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)
        f.write("\n")
    write_ledger(m)


def live_version():
    """Read-only: what render_code_version is published on Labs right now."""
    try:
        sys.path.insert(0, ROOT)
        from refresh_interviews_dashboard import OWNER_OPP, WORKFLOW_ID, _mcp_call, _mcp_creds

        url, auth = _mcp_creds()
        if not (url and auth):
            return None
        wf = _mcp_call(
            url,
            auth,
            "workflow_get",
            {"workflow_id": WORKFLOW_ID, "opportunity_id": OWNER_OPP, "include_render_code": False},
            {"v": None},
        )
        return wf.get("render_code_version")
    except Exception as e:  # never let a checkpoint fail because Labs is unreachable
        print(f"    (could not read live version: {repr(e)[:120]})")
        return None


def verify():
    """Run the real pipeline + all three gates; capture their scores and the render sizes."""
    print("    running build + gates (this is the same chain CI runs)...")
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "refresh_interviews_dashboard.py")],
        cwd=ROOT,
        env=ENV,
        capture_output=True,
        text=True,
    )
    out = r.stdout + r.stderr
    scores = re.findall(r"TOTAL:\s*(\d+)\s*/\s*(\d+) checks passed", out)
    brutal = re.search(r"TOTAL:\s*(\d+) passed,\s*(\d+) failed", out)
    size = re.search(r"wrote .*?render\.js \(([\d.]+) KB = ([\d.]+) KB code \+ ([\d.]+) KB data\)", out)
    head = re.search(r"headroom vs the 512 KB Labs limit: ([\d.]+) KB", out)
    v = {
        "pipeline_ok": r.returncode == 0,
        "gate_6a": f"{scores[0][0]}/{scores[0][1]}" if len(scores) > 0 else None,
        "gate_6b": f"{scores[1][0]}/{scores[1][1]}" if len(scores) > 1 else None,
        "gate_brutal": f"{int(brutal.group(1))}/{int(brutal.group(1)) + int(brutal.group(2))}" if brutal else None,
        "render_kb": float(size.group(1)) if size else None,
        "code_kb": float(size.group(2)) if size else None,
        "data_kb": float(size.group(3)) if size else None,
        "headroom_kb": float(head.group(1)) if head else None,
    }
    print(
        f"    {'OK' if v['pipeline_ok'] else 'PIPELINE FAILED'}  6a={v['gate_6a']} 6b={v['gate_6b']} "
        f"brutal={v['gate_brutal']}  render={v['render_kb']}KB"
    )
    return v


def cmd_create(args):
    m = load()
    sha = args.sha or git("rev-parse", "HEAD")
    sha = git("rev-parse", sha)
    n = len(m["checkpoints"]) + 1
    cid = f"cp-{n:04d}"
    slug = re.sub(r"[^a-z0-9]+", "-", args.label.lower()).strip("-")[:40]
    tag = f"{cid}-{slug}"
    cp = {
        "id": cid,
        "label": args.label,
        "tag": tag,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "git_sha": sha,
        "git_subject": git("log", "-1", "--format=%s", sha),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "note": args.note or "",
        "live_render_version": live_version() if args.live else None,
        "verified": verify() if args.verify else None,
    }
    existing = git("tag", "-l", tag)
    if existing:
        print(f"    tag {tag} already exists — reusing")
    else:
        subprocess.run(["git", "tag", "-a", tag, sha, "-m", f"{cid}: {args.label}"], cwd=ROOT, check=True)
        print(f"    tagged {tag} -> {sha[:8]}")
    m["checkpoints"].append(cp)
    save(m)
    print(f"\n{cid} created. Push the tag so it survives this machine:\n    git push origin {tag}")
    return cp


def cmd_list(_args):
    m = load()
    if not m["checkpoints"]:
        print("no checkpoints yet")
        return
    print(f"{'ID':<9} {'CREATED':<18} {'SHA':<9} {'LIVE':<6} {'GATES (6a/6b/brutal)':<26} LABEL")
    for cp in m["checkpoints"]:
        v = cp.get("verified") or {}
        gates = f"{v.get('gate_6a', '-')} {v.get('gate_6b', '-')} {v.get('gate_brutal', '-')}" if v else "-"
        print(
            f"{cp['id']:<9} {cp['created_utc'][:16]:<18} {cp['git_sha'][:8]:<9} "
            f"{str(cp.get('live_render_version') or '-'):<6} {gates:<26} {cp['label']}"
        )


def cmd_show(args):
    m = load()
    cp = next((c for c in m["checkpoints"] if c["id"] == args.id or c["tag"] == args.id), None)
    if not cp:
        sys.exit(f"no such checkpoint: {args.id}")
    print(json.dumps(cp, indent=2))


def cmd_rollback(args):
    m = load()
    cp = next((c for c in m["checkpoints"] if c["id"] == args.id or c["tag"] == args.id), None)
    if not cp:
        sys.exit(f"no such checkpoint: {args.id}")
    v = cp.get("verified") or {}
    print(
        f"""
ROLLBACK RUNBOOK -> {cp['id']}  ({cp['label']})
  commit {cp['git_sha'][:8]}  {cp['git_subject']}
  tag    {cp['tag']}
  live render_code_version when this checkpoint was taken: {cp.get('live_render_version') or 'not recorded'}
  gates at that commit: 6a={v.get('gate_6a', '-')} 6b={v.get('gate_6b', '-')} brutal={v.get('gate_brutal', '-')}

This prints commands; it does NOT run them. Publishing is outward-facing — do it deliberately.

1. Stop the automation first, so the nightly job cannot re-publish the bad code mid-rollback:
       gh workflow disable "Refresh Interviews Dashboard"

2. Roll the CODE back. Prefer a revert on main (keeps history honest) over a force-push:
       git revert --no-commit <bad-sha>..HEAD && git commit -m "revert to {cp['id']}"
   or, to inspect that state without changing main:
       git checkout {cp['tag']}

3. Rebuild and republish from that code. Data is always pulled fresh, so this restores the
   BEHAVIOUR of the checkpoint, not its numbers:
       python refresh_interviews_dashboard.py --pull-connect --pull-hq --pull-ocs --pull-words --push
   The gates run inside that command and abort before publishing if anything fails.

4. Confirm what is live, then re-enable the schedule:
       python checkpoint.py create "post-rollback to {cp['id']}" --live --verify
       gh workflow enable "Refresh Interviews Dashboard"

If you only need to undo the PUBLISHED render and not the code, note that Labs keeps
render_code_version history: the version live at this checkpoint was {cp.get('live_render_version') or 'not recorded'}.
"""
    )


def write_ledger(m):
    lines = [
        "# Dashboard checkpoints",
        "",
        "Rollback points for the Connect Interviews dashboard. Generated by `checkpoint.py` — "
        "edit that, not this file.",
        "",
        "The dashboard republishes itself every morning, so a checkpoint pins the **code** that produced a "
        "known-good dashboard, together with the gate results and payload sizes it produced and the Labs "
        "`render_code_version` that was live at the time. Data is never committed (participant-derived), so a "
        "rollback rebuilds today's data with that day's code.",
        "",
        "```bash",
        "python checkpoint.py list                 # this table",
        'python checkpoint.py create "label" --verify --live',
        "python checkpoint.py rollback cp-0001     # prints the runbook",
        "```",
        "",
        "| ID | Created | Commit | Tag | Live render | 6a | 6b | brutal | Render KB | Headroom | Label |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cp in m["checkpoints"]:
        v = cp.get("verified") or {}
        lines.append(
            f"| **{cp['id']}** | {cp['created_utc'][:16]} | `{cp['git_sha'][:8]}` | `{cp['tag']}` | "
            f"{cp.get('live_render_version') or '—'} | {v.get('gate_6a') or '—'} | {v.get('gate_6b') or '—'} | "
            f"{v.get('gate_brutal') or '—'} | {v.get('render_kb') or '—'} | {v.get('headroom_kb') or '—'} | "
            f"{cp['label']} |"
        )
    lines += ["", "## Notes", ""]
    for cp in m["checkpoints"]:
        if cp.get("note"):
            lines.append(f"- **{cp['id']} — {cp['label']}**: {cp['note']}")
    lines.append("")
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("label")
    c.add_argument("--sha")
    c.add_argument("--note")
    c.add_argument("--verify", action="store_true")
    c.add_argument("--live", action="store_true")
    c.set_defaults(fn=cmd_create)
    ls = sub.add_parser("list")
    ls.set_defaults(fn=cmd_list)
    sh = sub.add_parser("show")
    sh.add_argument("id")
    sh.set_defaults(fn=cmd_show)
    rb = sub.add_parser("rollback")
    rb.add_argument("id")
    rb.set_defaults(fn=cmd_rollback)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
