#!/usr/bin/env python3
r"""
get_token.py — capture GoHighLevel's internal `token-id` by PASSIVE OBSERVATION.

WHY THIS EXISTS
---------------
GHL has two separate auth systems and they do not overlap:

  1. The PIT (Private Integration Token). Reaches the PUBLIC API at
     services.leadconnectorhq.com — including the MCP server. Use `ghl_mcp.py`.
  2. The internal `token-id` JWT. Reaches backend.leadconnectorhq.com — funnel
     page autosave, the workflow CRUD API. The PIT does NOT work there
     (verified: returns "Unauthorized"). There is no documented way to mint one.

So anything that writes a funnel page or a workflow needs a token-id, and the
only place a token-id exists is inside a logged-in browser session.

WHAT THIS DOES — AND WHAT IT DOES NOT DO
----------------------------------------
This is PASSIVE OBSERVATION of traffic the GHL app generates by itself.

We attach to a Chrome you already launched and are already logged into, subscribe
to its network request events, navigate to a normal in-app URL, and read the
`token-id` REQUEST HEADER off the calls the app makes on its own behalf. The app
would have made those calls anyway; we are reading its own outbound headers.

It is NOT:
  - storage scraping (we never touch localStorage, cookies, or the profile on disk)
  - credential capture (no password, no login form, no session hijack)
  - a bypass of anything (a human logged in; we borrow that live session)

Practical consequence of that framing: if the human logs out, this stops working,
and it should. There is no offline path.

The token is short-lived (~1 hour), but GHL refreshes it automatically for as long
as the session is alive, so re-running this on demand is cheap and needs no human
step. Do not cache it beyond a single run of a build script.

PREREQUISITE — READ THIS, IT IS THE #1 FAILURE
-----------------------------------------------
Chrome must ALREADY be running with a remote-debugging port open, on a profile
that is ALREADY LOGGED IN to GHL. Launch it yourself, log in by hand once, and
leave it open:

  macOS:
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --remote-debugging-port=9222 \
      --user-data-dir="$HOME/.ghl-agent-profile"

  Linux:
    google-chrome --remote-debugging-port=9222 \
      --user-data-dir="$HOME/.ghl-agent-profile"

  Windows:
    chrome.exe --remote-debugging-port=9222 ^
      --user-data-dir="%USERPROFILE%\.ghl-agent-profile"

Use a DEDICATED --user-data-dir. Chrome refuses to open a debugging port on a
profile that is already running in another Chrome instance, and the failure is
silent-ish: the port never listens and this script reports "cannot connect".

Known trap: on some Chrome builds (144+ was the first we hit) a DevToolsActivePort
file appears but nothing ever listens on the TCP port. Verify before blaming this
script:

    curl -s http://127.0.0.1:9222/json/version

If that returns nothing, the browser is the problem, not this tool.

DEPENDENCY
----------
This is the only tool here that is not standard-library. It needs Playwright:

    pip install playwright
    # no `playwright install` needed — we CONNECT to your Chrome,
    # we do not download or launch a bundled browser.

USAGE
-----
    python3 get_token.py --location-id <id>            # writes ./.jwt
    python3 get_token.py                                # reads GHL_LOCATION_ID
    python3 get_token.py --out /tmp/.jwt --port 9222
    python3 get_token.py --print                        # stdout only, no file

Exit codes: 0 = captured a token with usable lifetime; 1 = failed or the token is
about to expire (treat both as fatal in a build script).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import ghl_ids  # noqa: E402  (sibling module; the path fix above must run first)

DEFAULT_PORT = 9222
DEFAULT_OUT = ".jwt"

# The host the app talks to. Every authenticated in-app XHR carries the token-id
# header to this domain; that is what we listen for.
API_HOST = "leadconnectorhq.com"

# Any authenticated in-app page works. This one is chosen because it loads fast
# and fires several authenticated XHRs immediately. Override with --url if your
# account lands somewhere else.
DEFAULT_PATH = "funnels-websites/funnels"


def jwt_exp(token: str) -> int:
    """Return the `exp` claim, or 0 if the token is not a decodable JWT.

    We do not verify the signature — we are not authenticating anything, we are
    only picking the longest-lived token when the app emitted several, and
    reporting remaining lifetime so a caller can fail early instead of halfway
    through a deploy.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # restore base64url padding
        return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:  # noqa: BLE001 - a malformed token is just a 0-lifetime token
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Capture GHL's internal token-id by observing traffic in an "
                    "already-logged-in Chrome (see module docstring for setup).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--location-id",
                    help="GHL location (sub-account) id. Optional — falls back to "
                         "$GHL_LOCATION_ID, then .env.")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("GHL_CDP_PORT", DEFAULT_PORT)),
                    help=f"Chrome remote-debugging port (default {DEFAULT_PORT}, "
                         f"or $GHL_CDP_PORT).")
    ap.add_argument("--out", default=os.environ.get("GHL_TOKEN_FILE", DEFAULT_OUT),
                    help=f"Where to write the token (default ./{DEFAULT_OUT}). "
                         f"gitignore this file.")
    ap.add_argument("--url",
                    help="Full in-app URL to visit instead of the default funnels list.")
    ap.add_argument("--print", dest="to_stdout", action="store_true",
                    help="Print the token to stdout and do not write any file.")
    ap.add_argument("--min-seconds", type=int, default=300,
                    help="Fail if the captured token expires sooner than this "
                         "(default 300s). A deploy that starts with 40 seconds of "
                         "token left fails halfway, which is worse than not starting.")
    ap.add_argument("--wait", type=int, default=24,
                    help="Seconds to keep listening for an authenticated request "
                         "(default 24).")
    args = ap.parse_args()

    if args.url:
        url = args.url
    else:
        try:
            location_id = ghl_ids.location_id(args.location_id)
        except ghl_ids.ResolveError as exc:
            ap.error(f"{exc}\n  or pass --url with any authenticated in-app URL.")
        url = (f"https://app.gohighlevel.com/v2/location/"
               f"{location_id}/{DEFAULT_PATH}")

    # Imported late, and deliberately: `--help` must work on a machine that has
    # never installed Playwright.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FATAL: Playwright is not installed.\n"
              "  fix: pip install playwright\n"
              "  (no `playwright install` needed — this connects to YOUR Chrome)",
              file=sys.stderr)
        return 1

    cdp = f"http://127.0.0.1:{args.port}"
    found: list = []

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(cdp)
        except Exception as exc:  # noqa: BLE001
            print(f"FATAL: cannot attach to Chrome at {cdp}\n"
                  f"  {type(exc).__name__}: {exc}\n"
                  f"  checklist:\n"
                  f"    1. Is Chrome running with --remote-debugging-port={args.port}?\n"
                  f"    2. Did you give it a DEDICATED --user-data-dir? Chrome will not\n"
                  f"       open a debug port on a profile another instance already owns.\n"
                  f"    3. Does `curl -s {cdp}/json/version` return JSON? If not, the\n"
                  f"       browser never opened the port — that is a Chrome problem.",
                  file=sys.stderr)
            return 1

        if not browser.contexts:
            print("FATAL: attached, but Chrome has no open browser context. "
                  "Open a tab and try again.", file=sys.stderr)
            return 1
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_request(req) -> None:
            # PASSIVE: this is a read-only event subscription on requests the app
            # issues itself. We do not create, modify, or replay any request.
            if API_HOST not in req.url:
                return
            try:
                headers = {k.lower(): v for k, v in req.headers.items()}
            except Exception:  # noqa: BLE001 - request may already be gone
                return
            # Newer builds send `token-id`; some older calls still send the same
            # JWT as a bearer. Accept either; both are the same credential.
            tok = (headers.get("token-id")
                   or headers.get("authorization", "").replace("Bearer ", "").strip())
            if tok.startswith("eyJ") and tok not in found:
                found.append(tok)

        page.on("request", on_request)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        except Exception as exc:  # noqa: BLE001
            # A navigation timeout is not necessarily fatal — the XHRs we care
            # about often fire before the SPA finishes settling.
            print(f"  warn: navigation did not settle ({type(exc).__name__}); "
                  f"still listening…", file=sys.stderr)

        deadline = time.time() + args.wait
        while time.time() < deadline and not found:
            page.wait_for_timeout(1_000)

    if not found:
        print("FATAL: no token-id observed on any request.\n"
              "  most likely: that Chrome profile is not logged in to GHL, or the\n"
              "  session expired. Bring the window to the front, confirm you can see\n"
              "  the sub-account dashboard, then re-run.\n"
              f"  (url tried: {url})", file=sys.stderr)
        return 1

    # Several tokens can be seen during one page load as the app refreshes.
    # Keep the longest-lived one so a slow build does not expire mid-run.
    best, best_exp = found[0], jwt_exp(found[0])
    for tok in found[1:]:
        exp = jwt_exp(tok)
        if exp > best_exp:
            best, best_exp = tok, exp

    remaining = int(best_exp - time.time()) if best_exp else 0

    if args.to_stdout:
        print(best)
    else:
        out = pathlib.Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(best)
        try:
            out.chmod(0o600)  # it is a live credential; do not leave it world-readable
        except OSError:
            pass
        print(f"  captured token-id ({len(best)} chars) -> {out}")

    if best_exp:
        print(f"  valid for {remaining // 60} more minutes")
    else:
        print("  warn: could not decode an exp claim — lifetime unknown")

    if best_exp and remaining < args.min_seconds:
        print(f"FATAL: only {remaining}s of lifetime left (need "
              f"{args.min_seconds}s). Reload the GHL tab to force a refresh, "
              f"then re-run.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
