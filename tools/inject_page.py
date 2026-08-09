#!/usr/bin/env python3
"""
inject_page.py — write a `pageData` tree into a GHL funnel page, then PROVE it.

WHY THIS EXISTS
---------------
GHL's public API (and therefore the MCP server) treats funnel pages as READ-ONLY.
The only write path is the builder's own autosave endpoint on the internal API:

    POST https://backend.leadconnectorhq.com/funnels/builder/autosave/<pageId>
    body: {"funnelId": ..., "pageData": {...}, "pageVersion": <current + 1>}

That endpoint needs the internal `token-id` JWT — the PIT does NOT work here.
Run `get_token.py` first.

THE TWO THINGS THAT GO WRONG
----------------------------
1. pageVersion. Autosave is optimistic-concurrency: send a version that is not
   current+1 and your write is quietly ignored or clobbered. So we GET the page
   first, read `pageVersion`, and increment. Never hardcode a version.

2. READ-AFTER-WRITE LAG IS REAL. A 201 from autosave means "accepted", not
   "rendered". The published/preview surface trails the write by a few seconds.
   During development a single immediate check produced a false "mismatch" and
   sent us hunting a bug that did not exist. So verification retries with a delay,
   and it verifies at the RENDERED preview URL — not by reading the record back.
   Reading your own write back proves the database took it; only the rendered
   surface proves GHL compiled it into something a visitor sees.

   Corollary worth internalising: GHL RECOMPILES page content. What you POST is
   not byte-for-byte what gets served (unlike email templates, which are stored
   verbatim). That is exactly why a rendered check is the honest one — and why
   `--expect` should be a short, distinctive string from your copy rather than a
   chunk of markup, which may legitimately be rewritten.

CURL, NOT urllib — Cloudflare 403s the default Python UA on GHL hosts. The
payload also goes to a temp file and is sent with `--data-binary @file`, because a
full pageData tree on the command line will hit the OS argument-length limit on a
real page.

GETTING THE IDS (no ids are hardcoded anywhere in this repo)
------------------------------------------------------------
Open the page in the GHL funnel builder. The URL carries both:

    app.gohighlevel.com/v2/location/<locationId>/funnels-websites/funnels/
        <funnelId>/pages/<pageId>/edit

To get a page's CURRENT pageData as a starting point (edit-in-place beats
building from scratch):

    curl -sS -H "token-id: $(cat .jwt)" -H "channel: APP" -H "source: WEB_USER" \
         -H "Version: 2021-07-28" \
         https://backend.leadconnectorhq.com/funnels/page/<pageId> > page.json

USAGE
-----
    python3 inject_page.py --page-id <id> --funnel-id <id> \
        --page-data page.json --expect "a distinctive phrase"

    python3 inject_page.py --page-id <id> --funnel-id <id> \
        --page-data page.json --dry-run     # validate + show version, write nothing

The default is a real write, which is why every id is an explicit required flag —
there is no way to run this by accident against the wrong page.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

INTERNAL_API = "https://backend.leadconnectorhq.com"
PREVIEW_BASE = "https://sites.leadconnectorhq.com/preview"

# Cloudflare 403s python-urllib on GHL hosts. Browser UA, via system curl.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def auth_headers(token: str) -> list:
    """The internal API's header set.

    `token-id` — NOT `Authorization: Bearer`. Bearer returns "Unauthorized" here
    for both the PIT and the browser JWT; the internal API wants this header.
    The other three mimic the builder's own calls and are not optional.
    """
    return ["-H", f"token-id: {token}",
            "-H", "channel: APP",
            "-H", "source: WEB_USER",
            "-H", "Version: 2021-07-28"]


def curl(args: list, timeout: int = 90) -> str:
    proc = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), "-A", USER_AGENT, *args],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"FATAL: curl failed (exit {proc.returncode}): "
                         f"{proc.stderr.strip()[:300]}")
    return proc.stdout


def read_token(token_arg, token_file: str) -> str:
    """Token precedence: --token, then $GHL_TOKEN_ID, then the token file.

    Fails loudly. An empty token produces a 401 that reads like a permissions
    problem, which sends you debugging the wrong thing.
    """
    if token_arg:
        return token_arg.strip()
    env_token = os.environ.get("GHL_TOKEN_ID")
    if env_token:
        return env_token.strip()
    path = pathlib.Path(token_file).expanduser()
    if path.is_file():
        token = path.read_text().strip()
        if token:
            return token
    raise SystemExit(
        f"FATAL: no internal token.\n"
        f"  fix: python3 get_token.py --location-id <id>   (writes {token_file})\n"
        f"  or:  --token 'eyJ...'  or  export GHL_TOKEN_ID='eyJ...'\n"
        f"  note: the PIT does NOT work against {INTERNAL_API}.")


def current_version(token: str, page_id: str) -> int:
    """Read the page's current pageVersion.

    Fails loudly on an unreadable page rather than defaulting to 1: defaulting
    would send version 2 to a page on version 47 and silently lose the write.
    """
    out = curl([*auth_headers(token), "-H", "Accept: application/json",
                f"{INTERNAL_API}/funnels/page/{page_id}"])
    try:
        doc = json.loads(out)
    except json.JSONDecodeError:
        raise SystemExit(
            f"FATAL: could not read page {page_id}.\n"
            f"  response: {out[:300]!r}\n"
            f"  usual causes: expired token-id (re-run get_token.py), or a page id "
            f"that belongs to a different location.")
    version = doc.get("pageVersion")
    if version is None:
        raise SystemExit(
            f"FATAL: page {page_id} returned no pageVersion. Response keys: "
            f"{list(doc)[:12]}")
    return int(version)


def verify(page_id: str, expect, attempts: int, delay: int,
           preview_base: str) -> bool:
    """Verify at the RENDERED preview URL, with retries for read-after-write lag.

    A 201 from autosave is 'accepted', not 'rendered'. Checking once, immediately,
    reports a false failure. Cache-Control: no-cache because an edge cache will
    happily serve the previous version and make a good write look broken.
    """
    for attempt in range(1, attempts + 1):
        time.sleep(delay)
        html = curl(["-H", "Cache-Control: no-cache",
                     f"{preview_base}/{page_id}"])
        if expect:
            if expect in html:
                print(f"    verified on preview ({len(html):,} bytes) — "
                      f"found {expect!r}")
                return True
        elif len(html) > 1000:
            # Weak check: the page responds with real content. Prefer --expect.
            print(f"    preview responds ({len(html):,} bytes) — no --expect "
                  f"given, so content was NOT verified")
            return True
        print(f"    attempt {attempt}/{attempts}: not visible yet…")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Inject a pageData tree into a GHL funnel page and verify it "
                    "on the rendered preview.",
        epilog="Needs the internal token-id from get_token.py. The PIT will not work.")
    ap.add_argument("--page-id", required=True,
                    help="Funnel page id (from the builder URL).")
    ap.add_argument("--funnel-id", required=True,
                    help="Funnel id (from the builder URL).")
    ap.add_argument("--page-data", required=True,
                    help="Path to a JSON file holding the pageData tree.")
    ap.add_argument("--expect",
                    help="A short distinctive string from your copy that must "
                         "appear on the rendered preview. STRONGLY recommended — "
                         "without it, verification only proves the page responds.")
    ap.add_argument("--token", help="Internal token-id (eyJ...).")
    ap.add_argument("--token-file",
                    default=os.environ.get("GHL_TOKEN_FILE", ".jwt"),
                    help="File holding the token-id (default ./.jwt).")
    ap.add_argument("--preview-base", default=PREVIEW_BASE,
                    help="Preview host base (override only if GHL moves it).")
    ap.add_argument("--attempts", type=int, default=4,
                    help="Verification attempts (default 4).")
    ap.add_argument("--delay", type=int, default=8,
                    help="Seconds between verification attempts (default 8).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate the JSON, report the version that WOULD be "
                         "written, and send nothing.")
    args = ap.parse_args()

    src = pathlib.Path(args.page_data).expanduser()
    if not src.is_file():
        raise SystemExit(f"FATAL: no such page-data file: {src}")
    try:
        tree = json.loads(src.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FATAL: {src} is not valid JSON: {exc}")
    if not isinstance(tree, dict):
        raise SystemExit(f"FATAL: {src} must contain a pageData OBJECT, "
                         f"got {type(tree).__name__}.")
    if "sections" not in tree:
        # Not fatal — schemas vary — but almost always a sign the wrong file was
        # passed (e.g. the whole page record instead of its `pageData`).
        print("  warn: pageData has no 'sections' key. If you saved the whole page "
              "record, pass its .pageData sub-object instead.", file=sys.stderr)

    token = read_token(args.token, args.token_file)
    version = current_version(token, args.page_id) + 1

    if args.dry_run:
        print(f"  [dry-run] page {args.page_id} in funnel {args.funnel_id}")
        print(f"  [dry-run] would write pageVersion -> {version}")
        print(f"  [dry-run] payload: {len(json.dumps(tree)):,} bytes, "
              f"{len(tree.get('sections') or [])} section(s)")
        return 0

    payload = {"funnelId": args.funnel_id, "pageData": tree,
               "pageVersion": version}

    # Write to a temp file and send with --data-binary @file. A real pageData tree
    # on the command line blows past the OS argument-length limit.
    tmp = pathlib.Path(tempfile.mkdtemp()) / f"payload-{args.page_id}.json"
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    try:
        out = curl([*auth_headers(token), "-H", "Content-Type: application/json",
                    "-X", "POST", "--data-binary", f"@{tmp}",
                    f"{INTERNAL_API}/funnels/builder/autosave/{args.page_id}"])
    finally:
        tmp.unlink(missing_ok=True)
        try:
            tmp.parent.rmdir()
        except OSError:
            pass

    # A successful autosave echoes a pageDataUrl. Its absence is the failure
    # signal; the endpoint does not always use a helpful status code.
    accepted = '"pageDataUrl"' in out
    print(f"  inject page {args.page_id}: "
          f"{'accepted' if accepted else 'FAILED'} (pageVersion -> {version})")
    if not accepted:
        print(f"    response: {out[:400]!r}", file=sys.stderr)
        print("    if this says unauthorized, the token-id expired — re-run "
              "get_token.py.", file=sys.stderr)
        return 1

    if verify(args.page_id, args.expect, args.attempts, args.delay,
              args.preview_base):
        return 0

    print("    !! accepted but NOT verified on the rendered page.\n"
          "       Do not report this as done. Either the write did not compile, or\n"
          "       your --expect string was rewritten by GHL's compiler. Open\n"
          f"       {args.preview_base}/{args.page_id} and look.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
