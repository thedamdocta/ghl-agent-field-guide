#!/usr/bin/env python3
"""
push_emails.py — create/update GHL email templates from local HTML, idempotently.

WHY THIS EXISTS AS A TOOL AND NOT A PARAGRAPH
---------------------------------------------
`ghl_mcp.py execute create-email-template` can do one write. It cannot do the
part that is actually hard: matching what is already in the account so a re-run
updates instead of littering it with duplicates, deriving an idempotency key that
makes a retry safe, recording the template ids that the workflow build depends
on, and proving the markup survived. That is this file.

THE ONE FACT THAT MAKES EMAIL THE EASY SURFACE IN GHL
-----------------------------------------------------
`editorType:"html"` stores `editorContent` VERBATIM. Round-trip byte-identical,
verified — unlike funnel pages, which GHL recompiles at save time so what you
POST is not what is served. Whatever you author is what sends. GHL adds exactly
two things: an `<!-- outlook-fixes-applied -->` comment and MSO font-colour
fallbacks. No MJML recompilation, no re-nesting, no attribute stripping.

RULES LEARNED THE HARD WAY — EACH ONE COST REAL TIME
-----------------------------------------------------
1. WRITES REQUIRE AN `idempotencyKey`. Omit it and you get a 400 that names the
   field. This tool derives the key from a hash of the CONTENT, not the clock: the
   same logical write retries safely, and a genuine edit gets a new key rather
   than being swallowed as a duplicate. A timestamped key defeats the purpose.

2. `locationId` GOES IN THE PATH, NEVER THE QUERY. In the query you get
   422 "property locationId should not exist".

3. THE PIT CAN CREATE AND UPDATE BUT NOT DELETE. Delete returns 401 "token is not
   authorized for this scope". Retire a template with `--archive`, which updates
   it with `archived: true` instead.

4. `dryRun` PROVES SHAPE, NOT PERMISSION. It returns
   `authorizationVerified: false` — it resolves the request without checking
   scopes. A successful dry run is not a successful write.

5. A 200 IS NOT PROOF. The response carries `data.previewUrl`, a Firebase-hosted
   rendering of the STORED template. That is the verification surface. `--verify`
   fetches it and confirms your copy is actually in there.

6. MATCH EXISTING TEMPLATES BY NAME. There is no natural key otherwise, so a
   re-run without matching creates a second "SEQ 01" every time, forever.

7. RECORD THE IDS. Workflow email actions join to templates by `template_id`, so
   the ids written to the results file are a hard dependency of the workflow
   build. Templates must exist before you deploy a workflow that sends them.

USAGE
-----
    python3 push_emails.py --emit-example > emails.manifest.json
    python3 push_emails.py --manifest emails.manifest.json --check    # offline lint
    python3 push_emails.py --manifest emails.manifest.json --dry-run  # no network
    python3 push_emails.py --manifest emails.manifest.json --apply
    python3 push_emails.py --manifest emails.manifest.json --verify
    python3 push_emails.py --archive "SEQ 03" --apply

Nothing is written to the account without `--apply`. `--check`, `--dry-run` and
`--emit-example` touch no network and need no credentials.

Start from `email-template.starter.html`, which is a complete paste-ready
document, and read its header comment for the construction rules `--check`
enforces.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from html.parser import HTMLParser

HERE = pathlib.Path(__file__).resolve().parent
STARTER = HERE / "email-template.starter.html"

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
             "meta", "param", "source", "track", "wbr"}

BODY_COPY_FLOOR = 16   # px — see the starter's header block


# ── manifest ─────────────────────────────────────────────────────────────────

EXAMPLE_MANIFEST = [
    {
        "key": "01-welcome",
        "name": "SEQ 01 - Welcome",
        "subject": "Your seat is saved",
        "preview": "The inbox preview line. Leave it out and the client scrapes "
                   "your first sentence instead.",
        "fromName": "Sender Name",
        "html": "emails/01-welcome.html",
        "expect": "a distinctive phrase from your copy",
    },
    {
        "key": "02-teach",
        "name": "SEQ 02 - The one teaching email",
        "subject": "Tomorrow: what we will actually cover",
        "preview": "Three things worth knowing before we begin.",
        "fromName": "Sender Name",
        "html": "emails/02-teach.html",
        "expect": "another distinctive phrase",
    },
]

REQUIRED_KEYS = ("key", "name", "subject", "html")


class PushError(RuntimeError):
    """Loud by design. A silent skip here ships an email that never got written."""


def load_manifest(path: pathlib.Path) -> list:
    """Read and validate the manifest. Resolves `html` relative to the manifest."""
    if not path.is_file():
        raise PushError(
            f"no manifest at {path}\n"
            f"  fix: python3 push_emails.py --emit-example > {path.name}")
    try:
        rows = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PushError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(rows, list) or not rows:
        raise PushError(f"{path} must be a non-empty JSON array of entries.")

    seen_names, seen_keys = set(), set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PushError(f"entry {i} is not an object.")
        missing = [k for k in REQUIRED_KEYS if not row.get(k)]
        if missing:
            raise PushError(
                f"entry {i} ({row.get('key') or row.get('name') or '?'}) is missing: "
                f"{', '.join(missing)}")
        # Name is the idempotency key against the account (rule 6). Two entries
        # sharing one name means the second silently overwrites the first.
        if row["name"] in seen_names:
            raise PushError(f"duplicate name {row['name']!r} — names must be unique, "
                            f"they are how a re-run finds the existing template.")
        if row["key"] in seen_keys:
            raise PushError(f"duplicate key {row['key']!r}.")
        seen_names.add(row["name"])
        seen_keys.add(row["key"])

        html_path = (path.parent / row["html"]).resolve()
        if not html_path.is_file():
            raise PushError(f"entry {row['key']}: no HTML at {html_path}")
        row["_html_path"] = html_path
        row["_html"] = html_path.read_text()
    return rows


def build_body(row: dict) -> dict:
    """The request body. `editorType:'html'` is what makes storage verbatim."""
    body = {
        "name": row["name"],
        "editorType": "html",
        "editorContent": row["_html"],
        "subjectLine": row["subject"],
    }
    if row.get("preview"):
        body["previewText"] = row["preview"]
    if row.get("fromName"):
        body["fromName"] = row["fromName"]
    return body


def idempotency_key(row: dict) -> str:
    """Content-addressed, not clock-addressed — see rule 1.

    Same name + same content + same subject => same key, so a retry after a
    network blip is the same logical write. Change the content and the key
    changes, so a genuine second edit is not swallowed as a duplicate.
    """
    digest = hashlib.sha1(
        (row["name"] + "\0" + row["subject"] + "\0" + row.get("preview", "")
         + "\0" + row["_html"]).encode("utf-8")).hexdigest()[:16]
    slug = re.sub(r"[^a-z0-9]+", "-", row["key"].lower()).strip("-")
    return f"{slug}-{digest}"


# ── the linter ───────────────────────────────────────────────────────────────

class _Scan(HTMLParser):
    """Collects tags with their attributes and tracks nesting well-formedness."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list = []
        self.structure: list = []
        self.tags: list = []

    def handle_starttag(self, tag, attrs) -> None:
        self.tags.append((tag, dict(attrs), self.getpos()[0]))
        if tag not in VOID_TAGS:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs) -> None:
        self.tags.append((tag, dict(attrs), self.getpos()[0]))

    def handle_endtag(self, tag) -> None:
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.structure.append(f"line {self.getpos()[0]}: </{tag}> with nothing open")
            return
        open_tag, line = self.stack.pop()
        if open_tag != tag:
            self.structure.append(
                f"line {self.getpos()[0]}: </{tag}> closes <{open_tag}> "
                f"opened at line {line}")


def lint(html: str) -> tuple:
    """Return (fails, warns, info). Every rule maps to a real rendering failure."""
    fails: list = []
    warns: list = []
    info: dict = {}

    # Regex checks run against the RENDERING content only. A starter file carries a
    # long documentation comment, and counting the merge tags or hexes named in
    # prose sends you off creating a custom value called "x".
    visible = re.sub(r"<!--.*?-->", "", html, flags=re.S)

    scan = _Scan()
    try:
        scan.feed(html)
        scan.close()
    except Exception as exc:                       # noqa: BLE001 - report, not crash
        fails.append(f"HTML does not parse: {exc}")
        return fails, warns, info

    fails.extend(scan.structure)
    for open_tag, line in scan.stack:
        fails.append(f"<{open_tag}> opened at line {line} is never closed")

    if not re.match(r"\s*<!doctype html>", html, re.I):
        fails.append("no <!doctype html> at the top — clients fall into quirks mode")

    # Outlook's Word engine: layout tables need the belt-and-braces attributes,
    # and a background must be an ATTRIBUTE as well as an inline style.
    for tag, attrs, line in scan.tags:
        style = attrs.get("style", "")

        if tag == "table":
            if attrs.get("role") != "presentation":
                fails.append(f"line {line}: <table> without role=\"presentation\" — "
                             f"screen readers announce it as a data table")
            for attr in ("cellpadding", "cellspacing", "border"):
                if attrs.get(attr) != "0":
                    fails.append(f"line {line}: <table> without {attr}=\"0\"")

        if tag in ("table", "td", "body") and "background-color:" in style:
            if "bgcolor" not in attrs:
                fails.append(f"line {line}: <{tag}> has background-color in style but "
                             f"no bgcolor attribute — Outlook ignores the style")

        if tag == "div" and "background-color:" in style:
            fails.append(f"line {line}: <div> with a background-color — Outlook's Word "
                         f"engine ignores it. Use a <table>/<td>.")

        if tag == "img":
            src = attrs.get("src", "")
            if ".svg" in src.lower():
                fails.append(f"line {line}: <img> points at an SVG — SVG does not "
                             f"render in Gmail. Raster it to PNG.")
            if "alt" not in attrs:
                fails.append(f"line {line}: <img> without alt — Outlook blocks images "
                             f"by default, so alt is what a real share of the list sees")
            for attr in ("width", "height"):
                if attr not in attrs:
                    fails.append(f"line {line}: <img> without a {attr} ATTRIBUTE "
                                 f"(Outlook reads the attribute, not the style)")
            if "display:block" not in style.replace(" ", ""):
                warns.append(f"line {line}: <img> without display:block — leaves a "
                             f"baseline gap under the image")

        if tag in ("p", "a", "h1") and style and "color:" not in style:
            fails.append(f"line {line}: <{tag}> carries no explicit color — on a dark "
                         f"ground an inherited colour is one inversion from invisible")

        for prop in ("float:", "position:absolute", "position:fixed"):
            if prop in style.replace(" ", ""):
                fails.append(f"line {line}: <{tag}> uses {prop} — ignored by Outlook")

    # Head declarations that stop clients rewriting your type.
    for needle, why in (
        ("x-apple-disable-message-reformatting", "Apple Mail resizes your type"),
        ("width=device-width", "no viewport meta — mobile clients rescale"),
    ):
        if needle not in visible:
            fails.append(f"missing {needle} — {why}")

    if "color-scheme" not in visible:
        warns.append("no color-scheme/supported-color-schemes meta — dark-mode-aware "
                     "clients are more likely to force-invert your ground")

    if not re.search(r"display:\s*none[^\"']*max-height:\s*0", visible):
        warns.append("no hidden preheader div found — the client will scrape your "
                     "first visible sentence as the inbox preview instead")

    if "@media" not in visible:
        warns.append("no media query — the only responsive mechanism email gives you")

    if 'width="600"' not in visible:
        warns.append("no 600px sheet — 600 is the durable content width")

    # The 16px floor. Labels and legal legitimately go smaller, so this is a WARN
    # that lists them: the point is that every exception stays deliberate. Sizes
    # under 8px are hidden-element idioms (the preheader is 1px) and not copy.
    sizes = sorted({int(m) for m in re.findall(r"font-size:\s*(\d+)px", visible)})
    info["font_sizes"] = sizes
    small = [s for s in sizes if 8 <= s < BODY_COPY_FLOOR]
    if small:
        warns.append(f"declared sizes below the {BODY_COPY_FLOOR}px body floor: "
                     f"{small} — fine for labels/legal, wrong for copy people read "
                     f"(below 16px iOS Mail zooms the message and your 600px stops "
                     f"being 600px)")
    if len(sizes) < 3:
        warns.append(f"only {len(sizes)} distinct size(s) — a single size for "
                     f"everything is what makes an email read as one grey block")

    # Palette discipline. One accent used twice beats four accents.
    hexes = sorted({h.lower() for h in re.findall(r"#([0-9a-fA-F]{6})\b", visible)})
    info["hexes"] = ["#" + h for h in hexes]
    if len(hexes) > 8:
        warns.append(f"{len(hexes)} distinct colours: {info['hexes']} — the strongest "
                     f"sequences run one ground and one accent used twice")

    # Every merge tag, so slots can be created BEFORE anything references them.
    tags = sorted(set(re.findall(r"\{\{\s*([^}]+?)\s*\}\}", visible)))
    info["merge_tags"] = tags
    info["custom_values"] = [t.split("custom_values.", 1)[1] for t in tags
                             if t.startswith("custom_values.")]

    return fails, warns, info


def run_check(rows: list, verbose: bool) -> int:
    """Offline. No network, no credentials. Exits non-zero on any FAIL."""
    total_fail = 0
    bad_files = 0
    all_slots: set = set()
    for row in rows:
        fails, warns, info = lint(row["_html"])
        total_fail += len(fails)
        bad_files += 1 if fails else 0
        all_slots |= set(info.get("custom_values", []))
        status = "FAIL" if fails else ("WARN" if warns else "OK  ")
        print(f"  {status} {row['key']:24s} {len(row['_html']):>7,}b  {row['name']}")
        for f in fails:
            print(f"         FAIL  {f}")
        for w in warns:
            print(f"         warn  {w}")
        if verbose:
            print(f"         sizes {info.get('font_sizes')}")
            print(f"         hexes {info.get('hexes')}")
            print(f"         tags  {info.get('merge_tags')}")

    if all_slots:
        print(f"\n  {len(all_slots)} custom-value slot(s) referenced:")
        print("    " + " ".join(sorted(all_slots)))
        print("  GHL resolves an unknown slot to EMPTY STRING, silently. Create every")
        print("  one of these first:  create_custom_values.py --scan <your html>")

    print(f"\n  {len(rows)} file(s) checked · {len(rows) - bad_files} clean · "
          f"{total_fail} failure(s) in {bad_files} file(s)")
    return 1 if total_fail else 0


def run_dry(rows: list) -> int:
    """Build every payload exactly as it would be sent. Still no network."""
    for row in rows:
        body = build_body(row)
        key = idempotency_key(row)
        print(f"  [dry] {row['key']:24s} {len(row['_html']):>7,}b  {row['name']}")
        print(f"        editorType   {body['editorType']}  (stores content VERBATIM)")
        print(f"        subjectLine  {body['subjectLine']!r}")
        print(f"        previewText  {body.get('previewText', '(none)')!r}")
        print(f"        fromName     {body.get('fromName', '(none)')!r}")
        print(f"        idempotency  {key}")
    print(f"\n  {len(rows)} payload(s) built. Nothing was sent. "
          f"Re-run with --apply to write.")
    return 0


# ── the account ──────────────────────────────────────────────────────────────

def client(env_file: str, location_id, timeout: int):
    """Imported lazily so --check/--dry-run/--emit-example never need credentials."""
    sys.path.insert(0, str(HERE))
    try:
        from ghl_mcp import GHLMCP, GHLMCPError, load_env
    except ImportError as exc:
        raise PushError(f"could not import ghl_mcp.py from {HERE}: {exc}") from exc
    try:
        pit, loc = load_env(env_file)
    except GHLMCPError as exc:
        raise PushError(str(exc)) from exc
    return GHLMCP(pit, location_id or loc, timeout=timeout), (location_id or loc)


def existing_by_name(ghl, loc: str, prefix: str) -> dict:
    """name -> id for templates matching the prefix. Rule 6: match by name."""
    found = {}
    for row in ghl.paginate("GET-all-or-email-sms-templates",
                            {"path": {"locationId": loc}}, "data.templates"):
        name = row.get("name")
        if name and (not prefix or name.startswith(prefix)):
            found[name] = row.get("id")
    return found


def run_apply(rows: list, ghl, loc: str, prefix: str, out: pathlib.Path) -> int:
    live = existing_by_name(ghl, loc, prefix)
    print(f"  {len(live)} existing template(s) matching prefix {prefix!r}\n")

    results, failed = [], 0
    for row in rows:
        body = build_body(row)
        key = idempotency_key(row)
        name = row["name"]
        if name in live:
            resp = ghl.execute_operation(
                "update-email-template",
                {"path": {"locationId": loc, "templateId": live[name]}, "body": body},
                key)
            verb = "updated"
        else:
            resp = ghl.execute_operation(
                "create-email-template",
                {"path": {"locationId": loc}, "body": body}, key)
            verb = "created"

        data = resp.get("data") or {}
        ok = bool(resp.get("success") and data.get("id"))
        failed += 0 if ok else 1
        print(f"  {'OK  ' if ok else 'FAIL'} {verb:8s} {name}")
        if not ok:
            print(f"         {json.dumps(resp)[:300]}")
        results.append({"key": row["key"], "name": name, "id": data.get("id"),
                        "previewUrl": data.get("previewUrl"),
                        "expect": row.get("expect"), "ok": ok})

    out.write_text(json.dumps(results, indent=1))
    print(f"\n  {len(results) - failed}/{len(results)} live -> {out}")
    print("  Those ids are a hard dependency of the workflow build: an email STEP "
          "references a template by id.")
    print("  A 200 is not proof. Now run --verify.")
    return 1 if failed else 0


def fetch(url: str, timeout: int) -> str:
    """curl, not urllib — Cloudflare 403s the default Python UA on GHL hosts."""
    proc = subprocess.run(
        ["curl", "-sSL", "--max-time", str(timeout), "-A", USER_AGENT, url],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise PushError(f"curl failed on {url}: {proc.stderr.strip()[:200]}")
    return proc.stdout


def run_verify(results_file: pathlib.Path, timeout: int) -> int:
    """Fetch each previewUrl and confirm the copy is really in what GHL serves."""
    if not results_file.is_file():
        raise PushError(f"no results at {results_file} — run --apply first.")
    rows = json.loads(results_file.read_text())
    bad = 0
    for row in rows:
        url = row.get("previewUrl")
        if not url:
            print(f"  FAIL {row['key']:24s} no previewUrl recorded")
            bad += 1
            continue
        served = fetch(url, timeout)
        expect = row.get("expect")
        if not expect:
            print(f"  warn {row['key']:24s} {len(served):>7,}b served, no `expect` "
                  f"in the manifest — only proves the URL responds")
            continue
        if expect in served:
            print(f"  OK   {row['key']:24s} {len(served):>7,}b  found {expect!r}")
        else:
            bad += 1
            print(f"  FAIL {row['key']:24s} {len(served):>7,}b  {expect!r} NOT in the "
                  f"stored template")
    print(f"\n  {len(rows) - bad}/{len(rows)} verified on previewUrl")
    return 1 if bad else 0


def run_archive(ghl, loc: str, name_prefix: str, apply: bool) -> int:
    """DELETE 401s on the PIT (rule 3). Archiving is the supported retirement."""
    live = existing_by_name(ghl, loc, name_prefix)
    if not live:
        print(f"  nothing matches prefix {name_prefix!r}")
        return 0
    for name, tid in sorted(live.items()):
        if not apply:
            print(f"  [dry] would archive {name}")
            continue
        resp = ghl.execute_operation(
            "update-email-template",
            {"path": {"locationId": loc, "templateId": tid},
             "body": {"name": name, "archived": True}},
            f"archive-{tid}")
        ok = bool(resp.get("success"))
        print(f"  {'OK  ' if ok else 'FAIL'} archived {name}")
    if not apply:
        print(f"\n  {len(live)} template(s) matched. Re-run with --apply.")
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create/update GHL email templates from local HTML, "
                    "idempotently. editorType:'html' stores your markup VERBATIM.",
        epilog="Credentials: $GHL_PIT and $GHL_LOCATION_ID, or a .env file "
               "(see .env.example). --check, --dry-run and --emit-example need "
               "neither credentials nor a network.")
    ap.add_argument("--manifest", help="JSON array of email entries. "
                                       "See --emit-example.")
    ap.add_argument("--emit-example", action="store_true",
                    help="Print a starter manifest and exit.")
    ap.add_argument("--check", action="store_true",
                    help="Lint the HTML offline against the email construction "
                         "rules. Exits non-zero on any failure.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build every payload and print it. Sends nothing.")
    ap.add_argument("--apply", action="store_true",
                    help="REQUIRED to write. Creates or updates by name.")
    ap.add_argument("--verify", action="store_true",
                    help="Fetch each recorded previewUrl and confirm the copy "
                         "survived. A 200 on the write is not proof.")
    ap.add_argument("--archive", metavar="NAME_PREFIX",
                    help="Retire templates by prefix via archived:true. The PIT "
                         "cannot DELETE (401 on scope).")
    ap.add_argument("--prefix", default="",
                    help="Name prefix used to find existing templates. Defaults to "
                         "the longest common prefix of the manifest names.")
    ap.add_argument("--results", default="pushed.json",
                    help="Where template ids and previewUrls are recorded "
                         "(default: pushed.json). Workflows need these ids.")
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--location-id", help="Override the location id.")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    try:
        if args.emit_example:
            print(json.dumps(EXAMPLE_MANIFEST, indent=1))
            return 0

        results_path = pathlib.Path(args.results)

        if args.archive:
            ghl, loc = client(args.env_file, args.location_id, args.timeout)
            return run_archive(ghl, loc, args.archive, args.apply)

        if args.verify and not (args.apply or args.check or args.dry_run):
            return run_verify(results_path, args.timeout)

        if not args.manifest:
            ap.error("need --manifest (or --emit-example / --archive / --verify). "
                     "Run --emit-example to see the shape.")

        rows = load_manifest(pathlib.Path(args.manifest))

        # The lint is the gate, not a suggestion: a template that fails these
        # renders wrong in a client you are not looking at.
        if args.check or args.dry_run or args.apply:
            rc = run_check(rows, args.verbose)
            if rc and (args.apply or args.dry_run):
                print("\n  REFUSED: fix the failures above, or run --check alone to "
                      "review them.", file=sys.stderr)
                return rc
            if args.check and not (args.dry_run or args.apply):
                return rc
            print()

        if args.dry_run:
            return run_dry(rows)

        if not args.apply:
            print("  Nothing sent. Add --apply to write, or --dry-run to see the "
                  "payloads.", file=sys.stderr)
            return run_dry(rows)

        prefix = args.prefix
        if not prefix:
            names = [r["name"] for r in rows]
            prefix = names[0]
            for name in names[1:]:
                while prefix and not name.startswith(prefix):
                    prefix = prefix[:-1]
        ghl, loc = client(args.env_file, args.location_id, args.timeout)
        rc = run_apply(rows, ghl, loc, prefix, results_path)
        if rc == 0 and args.verify:
            print()
            rc = run_verify(results_path, args.timeout)
        return rc

    except PushError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
