"""Save the render that is LIVE on Labs right now, plus its embedded DATA, for a before/after comparison.

Writes, under .render_snapshots/ (gitignored, the payload carries participant-level rows):
  live_v<N>.js          the exact render code Labs is serving, byte for byte
  live_data_v<N>.json   the DATA literal recovered from it

It also proves the live render is what git says it is: the comment-stripped template at HEAD with that
DATA injected must reproduce the live render exactly. If it does not, someone published from a different
template and any comparison against HEAD would be measuring the wrong baseline.

    python pull_live_render.py

Then follow the snapshot procedure in PROJECT_LEARNINGS.md section 0 (render_snapshot.js).
"""

import os
import subprocess
import sys
import tempfile

from pull_live_payload import extract_data_literal
from refresh_interviews_dashboard import OWNER_OPP, WORKFLOW_ID, _mcp_call, _mcp_creds

OUT = ".render_snapshots"
TEMPLATE = os.path.join("docs", "interviews_render_template.js")


def main():
    url, auth = _mcp_creds()
    if not (url and auth):
        sys.exit("no MCP creds")
    wf = _mcp_call(
        url,
        auth,
        "workflow_get",
        {"workflow_id": WORKFLOW_ID, "opportunity_id": OWNER_OPP, "include_render_code": True},
        {"v": None},
    )
    code, ver = wf["render_code"], wf["render_code_version"]
    data = extract_data_literal(code)
    if not isinstance(data, str):
        import json

        data = json.dumps(data, separators=(",", ":"))
    os.makedirs(OUT, exist_ok=True)
    # newline="" so Windows does not rewrite every \n as \r\n and change the bytes being compared
    with open(os.path.join(OUT, "live_v%s.js" % ver), "w", encoding="utf-8", newline="") as f:
        f.write(code)
    with open(os.path.join(OUT, "live_data_v%s.json" % ver), "w", encoding="utf-8", newline="") as f:
        f.write(data)

    # HEAD, not the working copy: the point is to compare against what is committed, and the working
    # copy is usually already carrying the change about to be measured
    head_src = os.path.join(tempfile.gettempdir(), "pull_live_render_head_src.js")
    stripped = os.path.join(tempfile.gettempdir(), "pull_live_render_head.js")
    with open(head_src, "wb") as f:
        f.write(
            subprocess.run(
                ["git", "show", "HEAD:" + TEMPLATE.replace(os.sep, "/")], check=True, capture_output=True
            ).stdout
        )
    subprocess.run(["node", "strip_render_comments.js", head_src, stripped], check=True, capture_output=True)
    with open(stripped, encoding="utf-8") as f:
        rebuilt = f.read().replace("/*__DATA__*/", data)
    same = rebuilt == code
    print("live render v%s | %d bytes | DATA %d chars" % (ver, len(code.encode("utf-8")), len(data)))
    print("HEAD template + live DATA reproduces the live render exactly: %s" % ("YES" if same else "NO"))
    if not same:
        print("WARNING: live was NOT published from this template. Compare against the live file, not HEAD.")
    print(f"next: node render_snapshot.js {OUT}/live_v{ver}.js {OUT}/before.json")


if __name__ == "__main__":
    main()
