#!/usr/bin/env python3
"""
capture_funnel.py — read ANY public GHL funnel page back into its full definition.

WHY THIS EXISTS
---------------
This is the entire READ side of working with GoHighLevel funnels, and it is the
tool that makes the write side tractable. Every other tool here builds or mutates
a `pageData` tree; this one is where you get a REAL, KNOWN-GOOD tree to learn from
and to clone exemplars out of.

A public GHL funnel page is a server-rendered Nuxt 3 app. The complete page
definition — every element, style, layout value, button wiring and responsive
flag — ships inside the HTML:

    <script type="application/json" id="__NUXT_DATA__" data-ssr="true">[...]</script>

That payload is `devalue`-serialized: a FLAT JSON ARRAY where index 0 is the root
and **any integer appearing inside an object or array is a POINTER (an index) back
into that same array**, not a literal number. Resolving it means walking the array
and substituting pointers recursively. Until you do that, the payload looks like
meaningless integer soup and people conclude the page definition is not there.

Consequence, verified: any publicly reachable GHL funnel page leaks its complete
definition to anyone who fetches the HTML. That is the read half of funnel
hacking, and it is also the fastest way to learn GHL's authoring schema — you do
not have to guess what a valid `button` element looks like when you can read a
working one off a live page.

THREE THINGS THAT COST TIME IF YOU DO NOT KNOW THEM
----------------------------------------------------
1. CURL, NOT urllib. Cloudflare 403s Python's default User-Agent on GHL hosts.
   Every request here goes through the system `curl` with a browser UA. This is
   not superstition — swapping it back reintroduces the 403.

2. THE GRAPH SELF-REFERENCES. devalue payloads contain cycles. An unbounded
   recursive resolve does not error, it hangs or blows the stack. Both a depth
   bound and a visited-set are required; neither alone is enough.

3. DESKTOP AND MOBILE PAYLOADS ARE BYTE-IDENTICAL (verified across six pages).
   GHL serves ONE definition and does the responsive work with per-element flags
   and breakpoint style blocks. Do not fetch twice expecting two layouts. `--ua`
   exists to prove that for yourself, not because you need both.

EXEMPLARS — WHY `--exemplars` MATTERS MORE THAN THE FULL DUMP
---------------------------------------------------------------
GHL elements carry dozens of required keys and every value is wrapped as
`{"value": X}`. Hand-writing them produces schema-invalid nodes that fail in ways
that do not name the missing key. The reliable technique is to CLONE a verified
exemplar and mutate only text, colour and layout. `--exemplars` writes exactly
that file, and `ghl_generator.py` consumes it.

THE EXEMPLAR ROLE TRAP (verified, cost a full rebuild): an exemplar carries its
original ROLE, not just its schema. Cloning `sections[0]` off a page whose first
section was a sticky navigation bar produced seven sticky-nav sections stacked on
each other — schema valid, CSS valid, semantics wrong, and a key-set diff showed
ZERO differences. When a type has several occurrences this tool tells you so and
`--pick type=N` lets you choose a role-matched one. Look at `extra.sticky`,
`title`, `class.width` and padding magnitude before adopting.

IDS: what you read here is the RENDERED namespace (ids carry a leading `c`).
Authoring ids — what you WRITE — have no `c`. `ghl_generator.py` mints fresh ids
on clone, so this does not bite you there; it bites you when you copy an id by
hand off a capture.

USAGE
-----
    python3 capture_funnel.py https://funnel.example.com/optin
    python3 capture_funnel.py <url> --out optin.json --html optin.html
    python3 capture_funnel.py <url> --exemplars exemplars.json
    python3 capture_funnel.py <url> --exemplars exemplars.json --pick section=2
    python3 capture_funnel.py <url> --summary          # analysis only, no files
    python3 capture_funnel.py <url> --ua mobile

No urls, ids or accounts are baked in. The page must be PUBLIC — this fetches it
the way any visitor would, with no credentials of any kind.

PRIVACY NOTE ON THE OUTPUT: a resolved capture contains the source account's real
locationId / funnelId / pageId and its copy. Gitignore what you capture. Run
`scrub_secrets.py` before publishing anything derived from it.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import subprocess
import sys
import urllib.parse

# Cloudflare 403s python-urllib on GHL hosts. Browser UAs, via system curl.
USER_AGENTS = {
    "desktop": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "mobile": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
               "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
               "Mobile/15E148 Safari/604.1"),
}

NUXT_RE = re.compile(
    r'<script type="application/json"[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>',
    re.S)

# The devalue graph self-references. This bound plus the visited-set in resolve()
# is what stops a cycle from becoming a hang. 60 clears real GHL pages with room
# to spare; raise it only if you see "<maxdepth>" markers in your output.
MAXDEPTH = 60

# Keys worth surfacing in the summary because they identify the captured page.
ID_KEYS = ("locationId", "funnelId", "pageId", "stepId", "pageName",
           "funnelName", "funnelDomain")


def fetch(url: str, ua: str, timeout: int = 45) -> str:
    """GET a page with curl and a browser UA.

    urllib is not an option here: Cloudflare returns 403 to Python's default
    User-Agent on every GHL host. --compressed because GHL serves gzip and the
    payload is large.
    """
    proc = subprocess.run(
        ["curl", "-sS", "--compressed", "--max-time", str(timeout), "-A", ua, url],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"FATAL: curl failed for {url} (exit {proc.returncode}): "
                         f"{proc.stderr.strip()[:300]}")
    if not proc.stdout.strip():
        raise SystemExit(f"FATAL: {url} returned an empty body. If this is a gated "
                         f"page it may need query parameters to render its real "
                         f"state — open it in a browser and copy the full URL.")
    return proc.stdout


def resolve_payload(html: str):
    """Extract and resolve __NUXT_DATA__. Returns (resolved_root, flat_length).

    devalue flat format: index 0 is the root; an integer INSIDE an object or list
    is an index back into the same array. Anything that is not a valid index is a
    literal and passes through untouched (that is how negative sentinels and real
    numbers survive).
    """
    match = NUXT_RE.search(html)
    if not match:
        return None
    try:
        flat = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FATAL: found a __NUXT_DATA__ block but it is not valid "
                         f"JSON: {exc}")
    if not isinstance(flat, list) or not flat:
        raise SystemExit("FATAL: __NUXT_DATA__ is not a non-empty array — this is "
                         "not a devalue payload.")

    def walk(idx, depth=0, seen=frozenset()):
        if depth > MAXDEPTH:
            return "<maxdepth>"
        # bool is a subclass of int in Python; treating True as index 1 would
        # silently corrupt the tree. Check it first.
        if isinstance(idx, bool):
            return idx
        if not isinstance(idx, int) or not (0 <= idx < len(flat)):
            return idx
        if idx in seen:
            return f"<cycle:{idx}>"
        seen = seen | {idx}
        node = flat[idx]
        if isinstance(node, dict):
            return {k: walk(p, depth + 1, seen) for k, p in node.items()}
        if isinstance(node, list):
            return [walk(p, depth + 1, seen) for p in node]
        return node

    return walk(0), len(flat)


def analyse(resolved) -> dict:
    """Summarise a resolved capture without dumping the whole tree.

    This is what you read first. The element-type histogram tells you what the
    page is made of, `merge_tags` tells you which custom values it depends on
    (every one of those must exist in your account or it renders as an EMPTY
    STRING, silently), and `colors` is a usable palette inventory.
    """
    types: collections.Counter = collections.Counter()
    node_prefixes: collections.Counter = collections.Counter()
    keys: collections.Counter = collections.Counter()
    ids: dict = {}

    def walk(obj, depth=0):
        if depth > 40:
            return
        if isinstance(obj, dict):
            t = obj.get("type")
            if isinstance(t, str):
                types[t] += 1
            n = obj.get("nodeId")
            if isinstance(n, str):
                node_prefixes[n.split("-")[0]] += 1
            for k, v in obj.items():
                keys[k] += 1
                if k in ID_KEYS and isinstance(v, str):
                    ids.setdefault(k, v)
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, depth + 1)

    walk(resolved)
    raw = json.dumps(resolved, ensure_ascii=False)
    return {
        "ids": ids,
        "element_types": dict(types.most_common()),
        "node_prefixes": dict(node_prefixes.most_common()),
        "merge_tags": dict(collections.Counter(
            re.findall(r"\{\{[^}]{1,60}\}\}", raw)).most_common()),
        "colors": dict(collections.Counter(
            c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}\b", raw)).most_common(25)),
        "responsive_keys": {
            k: keys[k] for k in
            ("forceColumnLayoutForMobile", "hideElements", "showElements",
             "mobileBgColor", "columnLayout", "mobileStyles")
            if k in keys
        },
    }


def collect_candidates(resolved) -> dict:
    """Group every styleable node in the capture by its `type`.

    An exemplar candidate is a dict carrying a string `type`, a string `id` and an
    `extra` dict — that is the shape of a GHL element, row, column or section.
    Order is document order, so index 0 is the topmost occurrence.
    """
    found: dict = collections.OrderedDict()
    seen_ids = set()

    def walk(obj, depth=0):
        if depth > 60:
            return
        if isinstance(obj, dict):
            t, i = obj.get("type"), obj.get("id")
            if (isinstance(t, str) and isinstance(i, str)
                    and isinstance(obj.get("extra"), dict) and i not in seen_ids):
                seen_ids.add(i)
                found.setdefault(t, []).append(obj)
            for v in obj.values():
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, depth + 1)

    walk(resolved)
    return found


def build_exemplars(candidates: dict, picks: dict) -> tuple:
    """Choose one exemplar per type. Returns (exemplars, ambiguous_types)."""
    exemplars, ambiguous = {}, []
    for type_name, nodes in candidates.items():
        index = picks.get(type_name, 0)
        if index >= len(nodes):
            raise SystemExit(
                f"FATAL: --pick {type_name}={index} but only {len(nodes)} "
                f"'{type_name}' node(s) were captured (valid: 0..{len(nodes) - 1}).")
        exemplars[type_name] = nodes[index]
        if len(nodes) > 1:
            ambiguous.append((type_name, len(nodes), index))
    return exemplars, ambiguous


def slug_for(url: str) -> str:
    """A filename from the URL path — `/optin` -> `optin`, `/` -> `index`."""
    path = urllib.parse.urlparse(url).path.strip("/")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", path.split("?")[0]).strip("-")
    return slug or "index"


def write_once(path: pathlib.Path, text: str, force: bool, label: str) -> None:
    """Write, refusing to clobber an existing file unless --force.

    A capture is expensive to re-take on a page that has since changed. Silently
    overwriting one is a data-loss bug, so it needs an explicit flag.
    """
    if path.exists() and not force:
        raise SystemExit(f"FATAL: {path} already exists ({label}). Pass --force to "
                         f"overwrite, or choose another path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Decode __NUXT_DATA__ off a PUBLIC GHL funnel page and write "
                    "the complete resolved page definition as JSON.",
        epilog="No credentials are used or required — this fetches the page the "
               "way any visitor would. Output contains the source account's real "
               "ids: gitignore it.")
    ap.add_argument("url", help="Full public URL of the funnel page. Include any "
                                "query parameters a gated page needs to render.")
    ap.add_argument("--out", help="Write the resolved definition here "
                                  "(default: <url-slug>.json).")
    ap.add_argument("--html", help="Also save the raw HTML here (useful when the "
                                   "payload will not parse).")
    ap.add_argument("--report", help="Write the analysis summary here as JSON.")
    ap.add_argument("--exemplars",
                    help="Write one clonable exemplar per element type here. This "
                         "is the file ghl_generator.py --templates consumes.")
    ap.add_argument("--pick", action="append", default=[], metavar="TYPE=N",
                    help="Choose the Nth occurrence (0-based) as the exemplar for "
                         "TYPE, e.g. --pick section=2. Repeatable. Use it to avoid "
                         "the role trap — see the module docstring.")
    ap.add_argument("--ua", choices=sorted(USER_AGENTS), default="desktop",
                    help="Which browser UA to send (default desktop). Desktop and "
                         "mobile payloads are byte-identical; this exists so you "
                         "can verify that, not because you need both.")
    ap.add_argument("--summary", action="store_true",
                    help="Print the analysis to stdout and write NO files.")
    ap.add_argument("--indent", type=int, default=2,
                    help="Indent for the written JSON (default 2; 0 = compact).")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing output files.")
    args = ap.parse_args()

    if not args.url.lower().startswith(("http://", "https://")):
        raise SystemExit(f"FATAL: --url must be absolute, got {args.url!r}. "
                         f"Pass the full https:// URL of the public page.")

    picks = {}
    for item in args.pick:
        if "=" not in item:
            raise SystemExit(f"FATAL: --pick wants TYPE=N, got {item!r}.")
        type_name, _, index = item.partition("=")
        if not index.isdigit():
            raise SystemExit(f"FATAL: --pick index must be a number, got {item!r}.")
        picks[type_name.strip()] = int(index)

    html = fetch(args.url, USER_AGENTS[args.ua])
    result = resolve_payload(html)
    if not result:
        raise SystemExit(
            f"FATAL: no __NUXT_DATA__ block in {args.url}\n"
            f"  fetched {len(html):,} bytes.\n"
            f"  usual causes: the URL is not a GHL-hosted funnel page; the page is\n"
            f"  unpublished or password-gated; or you were served an interstitial.\n"
            f"  fix: re-run with --html page.html and read what actually came back.")
    resolved, flat_len = result

    info = analyse(resolved)
    info["source_url"] = args.url
    info["html_bytes"] = len(html)
    info["flat_entries"] = flat_len
    typed = sum(info["element_types"].values())

    print(f"  fetched:       {len(html):,} bytes ({args.ua} UA)")
    print(f"  flat entries:  {flat_len:,}")
    print(f"  typed nodes:   {typed}")
    if info["ids"]:
        print(f"  ids found:     {', '.join(sorted(info['ids']))}")
    if info["element_types"]:
        top = list(info["element_types"].items())[:8]
        print("  element types: " + ", ".join(f"{k}×{v}" for k, v in top))
    if info["merge_tags"]:
        print(f"  merge tags:    {len(info['merge_tags'])} distinct "
              f"(each one must exist as a custom value or it renders EMPTY)")

    if args.summary:
        print()
        json.dump(info, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    dump = (lambda o: json.dumps(o, ensure_ascii=False,
                                 **({"indent": args.indent} if args.indent
                                    else {"separators": (",", ":")})))

    out = pathlib.Path(args.out) if args.out else pathlib.Path(f"{slug_for(args.url)}.json")
    write_once(out, dump(resolved), args.force, "resolved definition")
    print(f"  -> {out}")

    if args.html:
        write_once(pathlib.Path(args.html), html, args.force, "raw html")
        print(f"  -> {args.html}")

    if args.report:
        write_once(pathlib.Path(args.report), dump(info), args.force, "report")
        print(f"  -> {args.report}")

    if args.exemplars:
        candidates = collect_candidates(resolved)
        if not candidates:
            raise SystemExit(
                "FATAL: no clonable exemplars found. The payload resolved, but no "
                "node carried a type + id + extra. Either this is not a funnel "
                "page, or the schema moved — inspect the resolved JSON by hand.")
        exemplars, ambiguous = build_exemplars(candidates, picks)
        write_once(pathlib.Path(args.exemplars), dump(exemplars), args.force,
                   "exemplars")
        print(f"  -> {args.exemplars}  ({len(exemplars)} type(s): "
              f"{', '.join(sorted(exemplars))})")
        if ambiguous:
            print("  note: several occurrences exist for these types. An exemplar "
                  "carries its ROLE, not just its schema — a sticky nav section "
                  "clones as a sticky nav section. Inspect extra.sticky, title, "
                  "class.width and padding, then re-run with --pick TYPE=N:")
            for type_name, count, index in ambiguous:
                print(f"      {type_name:<16} {count} occurrence(s), using #{index}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
