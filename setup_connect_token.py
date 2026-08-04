#!/usr/bin/env python3
"""setup_connect_token.py — mint a FRESH Connect refresh token (browser re-auth).

The daily dashboard refresh pulls Connect user_data headlessly via the OAuth
refresh-token grant (fetch_connect_user_data.py). That refresh token rotates on
every use; if the chain breaks, every later run 400s at /o/token/ and the pipeline
silently falls back to the frozen CONNECT_SNAP snapshot — which is how ABT3/2WT/EXT
ended up with 0 Connect funnel + uncounted cohorts.

This reuses the repo's PROVEN OAuth CLI client
(commcare_connect/labs/integrations/connect/cli/client.py) — Authorization-Code +
PKCE, redirect_uri http://localhost:8765/callback (the value registered on the
Connect OAuth app) — to run the one-time browser flow, then saves the resulting
refresh token to .connect_creds.json (same key fetch_connect reads).

Credentials (env first, else .connect_creds.json):
  CONNECT_OAUTH_CLIENT_ID, CONNECT_OAUTH_CLIENT_SECRET

Usage:
  .venv/Scripts/python.exe setup_connect_token.py
  .venv/Scripts/python.exe setup_connect_token.py --port 8765 --scope export
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CREDS_FILE = ROOT / ".connect_creds.json"
BASE = "https://connect.dimagi.com"


def _load_get_oauth_token():
    """Load the standalone CLI OAuth client by file path (avoids importing Django)."""
    p = ROOT / "commcare_connect" / "labs" / "integrations" / "connect" / "cli" / "client.py"
    spec = importlib.util.spec_from_file_location("connect_cli_client", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.get_oauth_token


def _creds():
    c = json.loads(CREDS_FILE.read_text()) if CREDS_FILE.exists() else {}
    cid = os.environ.get("CONNECT_OAUTH_CLIENT_ID") or c.get("client_id")
    cs = os.environ.get("CONNECT_OAUTH_CLIENT_SECRET") or c.get("client_secret")
    return cid, cs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="export", help="OAuth scope (default: export)")
    ap.add_argument(
        "--port", type=int, default=8765, help="localhost callback port (must be registered; default 8765)"
    )
    args = ap.parse_args()

    cid, cs = _creds()
    if not cid:
        print("error: no client_id (env CONNECT_OAUTH_CLIENT_ID or .connect_creds.json)", file=sys.stderr)
        return 2

    get_oauth_token = _load_get_oauth_token()
    tok = get_oauth_token(client_id=cid, production_url=BASE, client_secret=cs, port=args.port, scope=args.scope)
    if not tok:
        print("\nerror: OAuth flow failed (see messages above).", file=sys.stderr)
        print(
            "If it was a redirect-uri mismatch, the registered callback isn't localhost:%d — try another" % args.port,
            file=sys.stderr,
        )
        print("registered localhost port via --port.", file=sys.stderr)
        return 1
    rt = tok.get("refresh_token")
    if not rt:
        print(
            f"\nerror: no refresh_token in the response (scope may not grant one): keys={list(tok)}", file=sys.stderr
        )
        return 1

    creds = json.loads(CREDS_FILE.read_text()) if CREDS_FILE.exists() else {}
    creds["refresh_token"] = rt
    CREDS_FILE.write_text(json.dumps(creds, indent=2))

    print("\n✓ Fresh Connect refresh token saved to .connect_creds.json (key: refresh_token)")
    print("\nNext — push it to the GitHub secret:\n")
    print(
        '  .venv/Scripts/python.exe -c "import json;'
        "print(json.load(open('.connect_creds.json'))['refresh_token'],end='')\""
        " | gh secret set CONNECT_REFRESH_TOKEN --repo asidtharthan/connect-labs-AaS"
    )
    print("\nThen verify the pull sees ABT3/2WT/EXT:  .venv/Scripts/python.exe fetch_connect_user_data.py")
    print("Then publish:  gh workflow run refresh-interviews.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
