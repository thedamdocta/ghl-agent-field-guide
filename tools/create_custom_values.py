#!/usr/bin/env python3
"""
create_custom_values.py — create or update GHL custom values in bulk, safely.

WHY THIS EXISTS
---------------
Custom values are the modular layer of a GHL build: `{{custom_values.some_key}}`
resolves server-side on funnel pages, in email templates and in workflow action
attributes.

> **GHL resolves an UNKNOWN `{{custom_values.x}}` to the EMPTY STRING. Silently.
> No error, no warning, no log.**

That is the whole reason this tool exists and why it runs BEFORE anything that
references a slot. A misspelled or uncreated key does not fail — it ships a
sentence with a hole in it. A real production email went out reading
"Grab the now" for exactly this reason and nobody noticed, because nothing failed.

So: create every referenced slot first, and create it with REAL copy rather than a
placeholder, so a mis-set slot reads as WRONG rather than as INVISIBLE.

THE FOUR API FACTS THAT SHAPE THIS TOOL (all verified)
-------------------------------------------------------
1. `PUT /locations/{loc}/customValues/bulk` IS GONE. Not renamed — gone.

       PUT .../customValues/bulk  {"customValues":[{"id","value"}]}
         -> 422 "property customValues should not exist / name must be a string"

   That 422 is the PER-VALUE schema talking. Confirmed by sending a per-value body
   to the same URL:

       -> 404 "The custom value id is invalid."

   i.e. `bulk` is being parsed as the `{id}` path segment. Code written against the
   old bulk route (it worked as recently as late 2025) fails today. This tool does
   per-value writes only. Twenty-odd individual calls is perfectly reasonable — the
   fallback is not a compromise.

2. A PER-VALUE PUT REQUIRES `name` AND `value`. Sending only `value` fails. And the
   `name` must be SOURCED FROM THE LIVE RECORD you just read, never from your own
   constant — that way an update can never accidentally rename a key. This tool
   does exactly that.

3. A PUT NEEDS AN EXISTING id. There is nothing to address on a key that does not
   exist yet, so CREATION IS A SEPARATE CALL (POST, no id). Any "just save it"
   design that assumes one write path is wrong: resolve keys -> ids first, then
   POST the missing ones and PUT the rest.

4. `locationId` GOES IN THE PATH. As a query parameter it returns
   `422 "property locationId should not exist"`.

Bonus, verified: read-after-write is consistent here (0/10 stale across a test
run), unlike funnel pages. You can re-read immediately after saving.

`fieldKey` TRAP: the record's `name` is the bare key (`event_date`), while
`fieldKey` is the wrapped form `{{ custom_values.event_date }}` — WITH braces AND
interior spaces. Matching `fieldKey` by string equality against a bare key returns
"all missing". Parse it with a regex; this tool does.

BEFORE YOU CREATE A HUNDRED SLOTS — THE DESIGN RULE
-----------------------------------------------------
A custom value earns its place ONLY when the same string must appear on MORE THAN
ONE surface. Everything else should be literal text the client can read and edit in
the WYSIWYG builder. In one real build, 59 of 75 slots appeared on exactly one
surface — each one a silent-failure risk that bought nothing and made the client's
own copy unreadable to them. The exception is EMAIL copy, because an
`editorType: "html"` template is raw code, so a slot is friendlier than the
alternative. See `knowledge/custom-values.md`.

AUTH: the PIT (public API). No browser JWT needed, unlike funnel pages and
workflows.

USAGE
-----
    # what would happen (default — nothing is written)
    python3 create_custom_values.py --values values.json
    python3 create_custom_values.py --set business_name="Acme" --set tz=ET

    # find every slot your generated pages/emails reference, and report the gaps
    python3 create_custom_values.py --scan page.json --scan emails/*.html

    # create the missing ones
    python3 create_custom_values.py --values values.json --apply

    # also overwrite values that already exist (destructive: it replaces copy the
    # client may have edited by hand)
    python3 create_custom_values.py --values values.json --apply --overwrite

Nothing is written without `--apply`. Existing values are never touched without
`--overwrite`.

`--scan` and `--values` are deliberately different classes of input. A key you
name explicitly is a statement about content, so `--overwrite` may replace it. A
key found only by scanning is a statement about EXISTENCE — the tool creates it if
missing and never rewrites it, because the client may have edited that copy in the
UI and a grep over your generated files is no reason to overwrite them. Exit code
is 1 whenever a scanned key would still resolve to an empty string; that is the
silent failure, and a build should stop on it.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

PUBLIC_API = "https://services.leadconnectorhq.com"

# Cloudflare 403s python-urllib on GHL hosts. Browser UA, via system curl.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# `fieldKey` carries braces AND interior spaces: "{{ custom_values.event_date }}".
# Live page markup and email HTML usually omit the spaces. Both render, the
# spacing is inconsistent in the wild, so never string-match — always regex.
KEY_RE = re.compile(r"\{\{\s*custom_values\.([A-Za-z0-9_]+)\s*\}\}")

# GHL custom-value names in the wild are snake_case, but the API accepts spaces
# and capitals too (older accounts are full of them). We do not rewrite what the
# caller asks for; we only reject what cannot round-trip through a merge tag.
NAME_RE = re.compile(r"^[A-Za-z0-9 _-]+$")


def load_env(env_file: str = ".env") -> tuple:
    """Return (pit, location_id) from the environment or a .env file.

    Real environment variables win over the file. Fails loudly with the exact
    variable names — an empty PIT surfaces much later as an opaque 401.
    """
    values = {}
    path = pathlib.Path(env_file).expanduser()
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip().strip('"').strip("'")

    pit = os.environ.get("GHL_PIT") or values.get("GHL_PIT")
    loc = os.environ.get("GHL_LOCATION_ID") or values.get("GHL_LOCATION_ID")
    missing = [n for n, v in (("GHL_PIT", pit), ("GHL_LOCATION_ID", loc)) if not v]
    if missing:
        raise SystemExit(
            "FATAL: missing credential(s): " + ", ".join(missing) + "\n"
            "  fix: export them, or copy .env.example to .env and fill it in.\n"
            "  GHL_PIT         — sub-account Settings -> Private Integrations\n"
            "  GHL_LOCATION_ID — the 20-char id in your GHL URL:\n"
            "                    app.gohighlevel.com/v2/location/<THIS>/...")
    return pit, loc


def api(method: str, url: str, pit: str, body=None) -> dict:
    """One public-API call.

    curl, not urllib — Cloudflare 403s the default Python UA on GHL hosts.
    Returns the parsed body, or {"_raw": ...} so a non-JSON error page is
    reported rather than swallowed.
    """
    cmd = ["curl", "-sS", "--max-time", "45", "-X", method, url,
           "-H", f"Authorization: Bearer {pit}",
           "-H", "Version: 2021-07-28",
           "-H", "Accept: application/json",
           "-H", "Content-Type: application/json",
           "-A", USER_AGENT]
    if body is not None:
        cmd += ["-d", json.dumps(body)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"FATAL: curl failed (exit {proc.returncode}): "
                         f"{proc.stderr.strip()[:300]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"_raw": proc.stdout[:400]}


def list_values(pit: str, loc: str) -> dict:
    """Read every custom value in the location. Returns {name: record}.

    `locationId` in the PATH — as a query parameter this returns
    422 "property locationId should not exist".
    """
    doc = api("GET", f"{PUBLIC_API}/locations/{loc}/customValues?limit=500", pit)
    records = doc.get("customValues")
    if records is None:
        raise SystemExit(
            f"FATAL: could not list custom values for location {loc}.\n"
            f"  response: {json.dumps(doc)[:300]}\n"
            f"  usual causes: the PIT lacks the custom-values scope, or "
            f"GHL_LOCATION_ID belongs to a different sub-account.")
    out = {}
    for record in records:
        name = record.get("name")
        if not name:
            # Fall back to the wrapped fieldKey. It has braces AND spaces, so it
            # must be regexed, never compared.
            match = KEY_RE.search(record.get("fieldKey") or "")
            name = match.group(1) if match else None
        if name:
            out[name] = record
    return out


def parse_pairs(pairs: list) -> dict:
    out = {}
    for item in pairs:
        if "=" not in item:
            raise SystemExit(f"FATAL: --set wants key=value, got {item!r}.")
        key, _, value = item.partition("=")
        out[key.strip()] = value
    return out


def scan_surfaces(paths: list) -> dict:
    """Map every {{custom_values.x}} reference to the SURFACES it appears on.

    A "surface" is one page or one email template — i.e. one input file. Keeping
    the per-file breakdown (rather than flattening to a set of keys) is what makes
    the design rule measurable: a key on exactly one surface should usually be
    literal text instead. See --surfaces.
    """
    surfaces: dict = {}
    for raw in paths:
        path = pathlib.Path(raw).expanduser()
        if not path.is_file():
            raise SystemExit(f"FATAL: --scan file not found: {path}")
        for key in set(KEY_RE.findall(path.read_text(errors="ignore"))):
            surfaces.setdefault(key, set()).add(path.name)
    return surfaces


def scan_for_keys(paths: list) -> set:
    """Collect every {{custom_values.x}} referenced by the given files.

    Works on anything textual: a generated pageData JSON, email HTML, a workflow
    spec. This is the check that catches the silent failure — every key found
    here must exist in the account, with a non-blank value, before launch.
    """
    return set(scan_surfaces(paths))


def surface_report(surfaces: dict, files: list, as_json: bool = False) -> int:
    """Count distinct surfaces per key and flag the single-surface ones.

    THE DESIGN RULE: a custom value earns its place only when the same string must
    appear on MORE THAN ONE surface. Everything else should be literal text the
    client can read and edit in the WYSIWYG builder, because every slot is a
    silent-failure site — an unknown or emptied key renders as EMPTY STRING with
    no error anywhere.

    The exception the count cannot see: copy that lives only in an email template
    built as raw HTML. There a slot is friendlier than asking someone to edit
    markup. Judge single-surface EMAIL keys by hand; the report marks them.
    """
    by_count: dict = {}
    for key, where in surfaces.items():
        by_count.setdefault(len(where), []).append(key)
    single = sorted(by_count.get(1, []))
    multi = sorted(k for k, w in surfaces.items() if len(w) > 1)

    if as_json:
        json.dump({"surfaces_scanned": len(files),
                   "keys": len(surfaces),
                   "multi_surface": multi,
                   "single_surface": {k: sorted(surfaces[k]) for k in single},
                   "counts": {k: len(v) for k, v in sorted(surfaces.items())}},
                  sys.stdout, indent=2)
        print()
        return 0

    print(f"  surfaces scanned:         {len(files)}")
    print(f"  distinct keys referenced: {len(surfaces)}")
    print(f"  on MORE THAN ONE surface: {len(multi)}   <- these earn their place")
    print(f"  on exactly ONE surface:   {len(single)}   <- inline these as literal text")
    if multi:
        print("\n  multi-surface (keep as custom values):")
        for key in sorted(multi, key=lambda k: -len(surfaces[k])):
            print(f"    {len(surfaces[key]):>3} surfaces  {key}")
    if single:
        print("\n  single-surface (candidates to inline):")
        for key in single:
            print(f"      1 surface   {key:<34} {next(iter(surfaces[key]))}")
        print("\n  Each of these buys nothing and costs a silent-failure site: a typo or "
              "\n  a blank renders as an empty string, and the client cannot read their "
              "\n  own copy in the builder. EXCEPTION: copy that only ever lives in a "
              "\n  raw-HTML email template is better as a slot — judge those by hand.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create or update GHL custom values from a JSON file, "
                    "key=value pairs, or the slots your content references.",
        epilog="Uses the PIT against the public API. Nothing is written without "
               "--apply; existing values are never changed without --overwrite.")
    ap.add_argument("--values", help="JSON object of {\"name\": \"value\", ...}.")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="A single custom value. Repeatable.")
    ap.add_argument("--scan", action="append", default=[], metavar="FILE",
                    help="Scan FILE for {{custom_values.x}} references and include "
                         "every key found. Repeatable. Keys found only by --scan "
                         "are created with --default-value.")
    ap.add_argument("--default-value", default="",
                    help="Value for keys discovered by --scan that have no value "
                         "elsewhere (default: empty). An empty value renders as "
                         "NOTHING on the page — the report calls these out.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually create the missing values. Without this the "
                         "tool only reports.")
    ap.add_argument("--overwrite", action="store_true",
                    help="Also PUT values that already exist. DESTRUCTIVE — it "
                         "replaces copy the client may have edited by hand.")
    ap.add_argument("--env-file", default=".env",
                    help="Where to read GHL_PIT / GHL_LOCATION_ID (default .env). "
                         "Real environment variables win.")
    ap.add_argument("--surfaces", action="store_true",
                    help="Count how many SURFACES (files) reference each "
                         "{{custom_values.x}} key and flag the single-surface ones, "
                         "which should usually be literal text instead. Pure local "
                         "analysis: needs --scan, no credentials, writes nothing.")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="Print a machine-readable report instead of prose.")
    args = ap.parse_args()

    # Offline, credential-free, and never touches the account.
    if args.surfaces:
        if not args.scan:
            ap.error("--surfaces needs --scan FILE (repeatable) — one file per "
                     "surface, e.g. --scan page1.json --scan email1.html")
        return surface_report(scan_surfaces(args.scan), args.scan, args.as_json)

    # `explicit` is what you ASKED for (--values / --set). Keys that only turn up
    # via --scan are a different class: we ensure they EXIST, but we never touch
    # their value, because the client may have edited it in the UI and a scan is
    # not a statement about content.
    explicit = {}
    if args.values:
        path = pathlib.Path(args.values).expanduser()
        if not path.is_file():
            raise SystemExit(f"FATAL: no such --values file: {path}")
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(f"FATAL: {path} is not valid JSON: {exc}")
        if not isinstance(doc, dict):
            raise SystemExit(f"FATAL: {path} must hold a JSON OBJECT of "
                             f"name -> value, got {type(doc).__name__}.")
        explicit.update({k: "" if v is None else str(v) for k, v in doc.items()})
    explicit.update(parse_pairs(args.set))

    scanned = scan_for_keys(args.scan) if args.scan else set()
    wanted = dict(explicit)
    for key in sorted(scanned):
        wanted.setdefault(key, args.default_value)

    if not wanted:
        raise SystemExit(
            "FATAL: nothing to do — no --values, --set or --scan given.\n"
            "  This tool refuses to run against an account without an explicit "
            "input set.")

    bad = [k for k in wanted if not NAME_RE.match(k)]
    if bad:
        raise SystemExit(
            f"FATAL: {len(bad)} name(s) contain characters that cannot round-trip "
            f"through a {{{{custom_values.x}}}} tag: {', '.join(sorted(bad)[:6])}\n"
            f"  allowed: letters, digits, spaces, underscore, hyphen.")

    pit, loc = load_env(args.env_file)
    live = list_values(pit, loc)

    to_create = sorted(k for k in wanted if k not in live)
    # Only EXPLICIT keys are ever updated. Without this split, a --scan run with
    # --overwrite would write the empty default over copy that already exists in
    # the account — i.e. the tool meant to prevent blank slots would create them.
    to_update = sorted(k for k in explicit
                       if k in live and live[k].get("value") != explicit[k])
    unchanged = sorted(k for k in explicit
                       if k in live and live[k].get("value") == explicit[k])
    # Blanks we are about to WRITE, as opposed to blanks that merely exist.
    blank_now = sorted(k for k in to_create if not wanted[k])
    # THE ONE THAT MATTERS: a key your content references that will end up with no
    # value — neither your input nor the account supplies one. Every one of these
    # renders as an empty string on a live surface, silently. Fail the build on it.
    blank_refs = sorted(k for k in scanned
                        if not (wanted.get(k)
                                or (live.get(k) or {}).get("value")))

    report = {
        "account_values": len(live), "requested": len(wanted),
        "create": to_create, "update": to_update, "unchanged": unchanged,
        "blank": blank_now, "referenced_but_empty": blank_refs,
        "applied": bool(args.apply),
    }

    if not args.as_json:
        print(f"  custom values in account: {len(live)}")
        print(f"  requested:                {len(wanted)} "
              f"({len(explicit)} explicit, {len(scanned - set(explicit))} "
              f"found by --scan)")
        print(f"  to create:                {len(to_create)}")
        print(f"  differing (would update): {len(to_update)}"
              f"{'' if args.overwrite else '   [skipped — pass --overwrite]'}")
        print(f"  already correct:          {len(unchanged)}")

    if not args.apply:
        if not args.as_json:
            for key in to_create[:10]:
                print(f"    + {key}")
            if len(to_create) > 10:
                print(f"    … and {len(to_create) - 10} more")
            print("\n  (report only — pass --apply to write)")
            if blank_now:
                print(f"  warn: {len(blank_now)} value(s) would be created BLANK. "
                      f"GHL renders a blank slot as nothing at all: "
                      f"{', '.join(blank_now[:6])}")
            if blank_refs:
                print(f"  !! {len(blank_refs)} key(s) are REFERENCED by your "
                      f"content and would resolve to an empty string: "
                      f"{', '.join(blank_refs[:8])}\n"
                      f"     supply copy for them (--values / --default-value) "
                      f"before launch. This is the silent failure.",
                      file=sys.stderr)
        else:
            json.dump(report, sys.stdout, indent=2)
            print()
        return 1 if blank_refs else 0

    created = updated = failed = 0
    for key in to_create:
        # CREATION IS A SEPARATE CALL — a PUT has no id to address.
        result = api("POST", f"{PUBLIC_API}/locations/{loc}/customValues", pit,
                     {"name": key, "value": wanted[key]})
        record = result.get("customValue") or result
        if record.get("id"):
            created += 1
            live[key] = record
            print(f"  OK   create  {key}"
                  + ("   <- BLANK, must be filled before launch"
                     if not wanted[key] else ""))
        else:
            failed += 1
            print(f"  FAIL create  {key}: {json.dumps(result)[:200]}",
                  file=sys.stderr)

    if args.overwrite:
        for key in to_update:
            record = live[key]
            value_id = record.get("id")
            if not value_id:
                failed += 1
                print(f"  FAIL update  {key}: the live record has no id, so there "
                      f"is nothing to PUT against.", file=sys.stderr)
                continue
            # BOTH name and value are required, and `name` comes from the LIVE
            # record so an update can never silently rename the key.
            result = api("PUT", f"{PUBLIC_API}/locations/{loc}/customValues/{value_id}",
                         pit, {"name": record.get("name") or key,
                               "value": wanted[key]})
            if (result.get("customValue") or result).get("id"):
                updated += 1
                print(f"  OK   update  {key}")
            else:
                failed += 1
                print(f"  FAIL update  {key}: {json.dumps(result)[:200]}",
                      file=sys.stderr)

    report.update({"created": created, "updated": updated, "failed": failed})
    if args.as_json:
        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        print(f"\n  created {created} · updated {updated} · failed {failed}")
        if blank_now:
            print(f"  {len(blank_now)} slot(s) were created BLANK — they render as "
                  f"nothing on every surface that references them. Fill them "
                  f"before launch: {', '.join(blank_now[:8])}")
        if blank_refs:
            print(f"  !! {len(blank_refs)} key(s) your content references still "
                  f"resolve to an empty string: {', '.join(blank_refs[:8])}",
                  file=sys.stderr)

    if failed or blank_refs:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
