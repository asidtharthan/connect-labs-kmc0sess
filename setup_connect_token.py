#!/usr/bin/env python3
"""setup_connect_token.py — mint a FRESH Connect refresh token (browser re-auth).

The daily dashboard refresh pulls Connect user_data headlessly via the OAuth
**refresh-token grant** (see fetch_connect_user_data.py). That refresh token rotates
on every use; if the chain ever breaks (a run uses it but fails to persist the new
one), every later run 400s at /o/token/ and the pipeline silently falls back to the
frozen CONNECT_SNAP secret snapshot — which is how ABT3/2WT/EXT ended up with no
Connect-funnel data (Invited/Accepted/Claimed = 0) and uncounted cohorts.

This script does the one-time **authorization_code** flow to mint a brand-new
refresh token, then writes it to .connect_creds.json. After running it, push the
new token to the CONNECT_REFRESH_TOKEN GitHub secret (the script prints the exact
command) and the daily headless pull self-heals — regenerating the full snapshot
with every cohort the account can access.

Credentials (env first, else .connect_creds.json):
  CONNECT_OAUTH_CLIENT_ID, CONNECT_OAUTH_CLIENT_SECRET

Usage:
  python setup_connect_token.py
  python setup_connect_token.py --redirect-uri http://localhost:8910/callback
  python setup_connect_token.py --scope "export openid"

IMPORTANT: the redirect_uri MUST be one registered on the Connect OAuth application
for this client_id. The default (http://localhost:<port>/callback) works only if a
localhost callback is registered. If you get "redirect_uri mismatch", pass the exact
registered value with --redirect-uri (its host must be localhost/127.0.0.1 so this
script can receive the callback).
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

ROOT = Path(__file__).parent
CREDS_FILE = ROOT / ".connect_creds.json"
BASE = "https://connect.dimagi.com"
TIMEOUT_SECONDS = 180


def _creds():
    import os

    c = json.loads(CREDS_FILE.read_text()) if CREDS_FILE.exists() else {}
    # match fetch_connect_user_data.py: env overrides, else .connect_creds.json (client_id/client_secret keys)
    cid = os.environ.get("CONNECT_OAUTH_CLIENT_ID") or c.get("client_id")
    cs = os.environ.get("CONNECT_OAUTH_CLIENT_SECRET") or c.get("client_secret")
    return cid, cs


class _Result:
    code: str | None = None
    error: str | None = None


def _handler(result: _Result, expected_state: str, cb_path: str):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != cb_path:
                self._r(404, "Not found")
                return
            p = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            if p.get("state") != expected_state:
                result.error = "state mismatch (possible CSRF)"
                self._r(400, "State mismatch")
                return
            if p.get("error"):
                result.error = f"{p['error']}: {p.get('error_description', '')}"
                self._r(400, "Auth error")
                return
            if not p.get("code"):
                result.error = "no code in callback"
                self._r(400, "No code")
                return
            result.code = p["code"]
            self._r(
                200,
                "<html><body style='font-family:sans-serif;text-align:center;padding:4rem'>"
                "<h1>Connect authorized ✓</h1><p>You can close this tab and return to your terminal.</p>"
                "</body></html>",
            )

        def _r(self, status, body):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode())))
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *a):
            return

    return H


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--redirect-uri", default=None, help="registered redirect URI (host must be localhost)")
    ap.add_argument("--scope", default="export openid")
    args = ap.parse_args()

    cid, cs = _creds()
    if not cid:
        print("error: no CONNECT_OAUTH_CLIENT_ID (env or .connect_creds.json)", file=sys.stderr)
        return 2

    # default redirect uri: localhost fixed port + /callback
    port = 8910
    redirect_uri = args.redirect_uri or f"http://localhost:{port}/callback"
    ru = urlparse(redirect_uri)
    if ru.hostname not in ("localhost", "127.0.0.1"):
        print(
            f"error: redirect_uri host must be localhost/127.0.0.1 (got {ru.hostname}) — "
            "so this script can catch the callback",
            file=sys.stderr,
        )
        return 2
    port = ru.port or (443 if ru.scheme == "https" else 80)
    cb_path = ru.path or "/callback"

    state = secrets.token_urlsafe(24)
    result = _Result()
    server = HTTPServer(("127.0.0.1", port), _handler(result, state, cb_path))
    server.timeout = 1

    def _wait():
        start = time.monotonic()
        while result.code is None and result.error is None:
            if time.monotonic() - start > TIMEOUT_SECONDS:
                result.error = f"timed out after {TIMEOUT_SECONDS}s"
                return
            server.handle_request()

    threading.Thread(target=_wait, daemon=True).start()

    authorize_url = f"{BASE}/o/authorize/?" + urlencode(
        {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": redirect_uri,
            "scope": args.scope,
            "state": state,
        }
    )
    print("\nOpen this URL in your browser, log in, and approve:\n")
    print(f"    {authorize_url}\n")
    print(f"(redirect_uri = {redirect_uri} — must be registered on the Connect OAuth app for this client)")
    try:
        webbrowser.open(authorize_url)
    except Exception:
        pass
    print(f"\nListening on http://127.0.0.1:{port}{cb_path} for the callback (timeout {TIMEOUT_SECONDS}s) ...")

    while result.code is None and result.error is None:
        time.sleep(0.3)
    if result.error:
        print(f"\nerror: {result.error}", file=sys.stderr)
        print(
            "If this is a redirect_uri mismatch, pass the exact registered value with --redirect-uri.", file=sys.stderr
        )
        return 1

    # exchange code -> tokens
    data = {"grant_type": "authorization_code", "code": result.code, "redirect_uri": redirect_uri, "client_id": cid}
    if cs:
        data["client_secret"] = cs
    r = httpx.post(f"{BASE}/o/token/", data=data, timeout=30)
    if r.status_code != 200:
        print(f"\nerror: token exchange failed {r.status_code}: {r.text[:300]}", file=sys.stderr)
        return 1
    j = r.json()
    rt = j.get("refresh_token")
    if not rt:
        print(f"\nerror: no refresh_token in response: {list(j)}", file=sys.stderr)
        return 1

    # persist to .connect_creds.json under the SAME keys fetch_connect_user_data.py reads
    creds = json.loads(CREDS_FILE.read_text()) if CREDS_FILE.exists() else {}
    creds["refresh_token"] = rt
    CREDS_FILE.write_text(json.dumps(creds, indent=2))

    print("\n✓ Fresh Connect refresh token minted and saved to .connect_creds.json (key: refresh_token)")
    print("\nNow push it to the GitHub secret so the daily run uses it:\n")
    print(
        "  python -c \"import json;print(json.load(open('.connect_creds.json'))['refresh_token'],end='')\""
        " | gh secret set CONNECT_REFRESH_TOKEN --repo asidtharthan/connect-labs-AaS\n"
    )
    print(
        "Then verify locally:  python fetch_connect_user_data.py   "
        "(should print 'opp catalog: N' and per-cohort rows incl. ABT3/2WT/EXT)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
