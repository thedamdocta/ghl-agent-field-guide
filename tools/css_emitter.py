#!/usr/bin/env python3
"""
css_emitter.py — the missing half of arbitrary-design injection into GHL.

THE CORE DISCOVERY
------------------
GHL does NOT compile an element's `styles` dict into CSS at render time.

Read that again, because it is the single fact that separates "I can tweak a page
GHL's own AI generated" from "I can inject any design I want". You can set every
style property on every element in a pageData tree, POST it successfully, and get
back a completely unstyled page.

What actually happens: the GHL builder generates a single CSS STRING per section
and stores it at `section.general.sectionStyles`, with every rule scoped to a
specific element id. It looks like this (ids here are illustrative):

    .hl_page-preview--content .section-AbCdEf1234{box-shadow:none;padding-top:12px}
    @media screen and (min-width:0px) and (max-width:480px){
        .hl_page-preview--content .section-AbCdEf1234{padding-top:10px!important} }

The `styles` dict is the builder's own editing state. `sectionStyles` is what the
browser sees. A from-scratch generator must emit that string for ITS OWN ids or
nothing is styled.

This module does that. It is what turns "modify an AI-generated page" into
"inject any design".

THE TWO ID NAMESPACES — THE PART THAT COSTS PEOPLE A DAY
---------------------------------------------------------
Every node carries TWO ids and they are not interchangeable:

  * `node.id`                — the AUTHORING id. Section-level layout keys off it.
  * `node.extra.nodeId`      — the RENDERED id (conventionally 'c'-prefixed).
                               Element-level styling — button fills, nav
                               typography, anything inside a section — keys off
                               THIS one.

GHL's own builder emits rules for BOTH. If you emit only the authoring id, your
sections lay out correctly and every button, heading and nav item renders in
default styling, which reads as "my CSS is being ignored" when in fact half of it
landed on a selector nothing matches. So: emit a grouped selector covering both.

MAPPING RULES (decoded from a real builder-generated page)
-----------------------------------------------------------
  camelCase key             -> kebab-case property
  {"value":X,"unit":"px"}   -> "Xpx"        {"value":"none"} -> "none"
  mobileStyles              -> inside the max-width:480px media block, !important
  extra.desktopFontSize     -> font-size          (type lives on `extra`, not
  extra.mobileFontSize      -> font-size, mobile   `styles` — easy to miss)
  extra.typography          -> font-family
  empty-string values       -> skipped entirely

SPECIFICITY: GHL's own stylesheet outranks a plain rule of ours for a handful of
properties. Background-color is the loud one — without !important every section
renders transparent and the whole page flattens to a single background colour.
See FORCE below; add to it if a property of yours is being visibly overridden.

USAGE — CLI
-----------
    python3 css_emitter.py page.json                  # -> page.styled.json
    python3 css_emitter.py page.json --out out.json
    python3 css_emitter.py page.json --root-vars '{"--ink":"#111","--bg":"#fff"}'
    python3 css_emitter.py page.json --stdout         # print, write nothing

Then inject the styled file with `inject_page.py`.

USAGE — AS A LIBRARY
--------------------
    from css_emitter import apply_css
    apply_css(page_data, root_vars={"--ink": "#111111"})

No ids, brands, colours or fonts are baked in. Everything comes from the pageData
you pass and the root vars you choose.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# The wrapper class GHL renders funnel content inside. Every rule is scoped under
# it, exactly as the builder does, so our rules sit at the same specificity as
# GHL's own instead of fighting them from a different level.
SEL_PREFIX = ".hl_page-preview--content ."

# Verbatim from the builder's output. Do not "improve" it to a plain max-width
# query — matching the builder's own string is what keeps the two stylesheets from
# interleaving in a surprising order.
MOBILE_MQ = "@media screen and (min-width:0px) and (max-width:480px)"

# Keys that are GHL-internal layout hints, not real CSS. Emitting them produces
# invalid declarations that can invalidate a whole rule in some parsers.
SKIP = {
    "forceColumnLayoutForMobile", "justifyContentColumnLayout",
    "alignContentColumnLayout", "colWidth", "rowWidth", "alignRow",
    "nestedColumn", "allowRowMaxWidth", "hideElements", "showElements",
    "elementScreenshot", "customClass", "inlineColors", "inlineTypographies",
    "entranceAnimation", "animationScale", "animationDuration",
    "animationDelay", "animationEasing", "visibility", "sticky", "bgImage",
}

# Style keys whose CSS property name differs from a naive kebab-case conversion,
# plus the common ones spelled out so the conversion is inspectable rather than
# implicit.
RENAME = {
    "backgroundColor": "background-color",
    "backgroundImage": "background-image",
    "backgroundSize": "background-size",
    "backgroundPosition": "background-position",
    "backgroundRepeat": "background-repeat",
    "backdropFilter": "backdrop-filter",
    "boxShadow": "box-shadow",
    "borderColor": "border-color",
    "borderWidth": "border-width",
    "borderStyle": "border-style",
    "borderRadius": "border-radius",
    "fontFamily": "font-family",
    "fontWeight": "font-weight",
    "fontStyle": "font-style",
    "textAlign": "text-align",
    "textDecoration": "text-decoration",
    "lineHeight": "line-height",
    "letterSpacing": "letter-spacing",
    "textTransform": "text-transform",
    "justifyContent": "justify-content",
    "alignItems": "align-items",
    "maxWidth": "max-width",
    "minHeight": "min-height",
}

# GHL's own stylesheet outranks a plain rule for these, so they must be forced.
# background-color is the one that visibly breaks a design: without !important
# every section renders transparent and the page flattens to one colour.
FORCE = {"background-color", "color", "padding-top", "padding-bottom"}


def kebab(key: str) -> str:
    if key in RENAME:
        return RENAME[key]
    return re.sub(r"(?<!^)(?=[A-Z])", "-", key).lower()


def value_of(v):
    """Turn {"value": X[, "unit": "px"]} into a CSS value string, or None.

    None means "emit nothing". Empty strings, nested objects and booleans are all
    builder state rather than CSS, and emitting them produces broken declarations.
    """
    if not isinstance(v, dict) or "value" not in v:
        return None
    val = v["value"]
    if val is None or val == "" or isinstance(val, (dict, list)):
        return None
    if isinstance(val, bool):
        return None
    unit = v.get("unit")
    if unit and isinstance(val, (int, float)):
        return f"{val}{unit}"
    return str(val)


def decls(styles: dict, important: bool = False) -> str:
    out = []
    for k, v in (styles or {}).items():
        if k in SKIP:
            continue
        cv = value_of(v)
        if cv is None:
            continue
        prop = kebab(k)
        bang = "!important" if (important or prop in FORCE) else ""
        out.append(f"{prop}:{cv}{bang}")
    return ";".join(out)


def typography_decls(extra: dict, mobile: bool = False) -> str:
    """GHL keeps type on `extra`, not `styles`. Emit it as real CSS.

    This is a genuine trap: you can set fontSize inside `styles` all day and see
    no change, because the builder reads type from `extra`.

        extra.desktopFontSize {value,unit} -> font-size
        extra.mobileFontSize  {value,unit} -> font-size (inside the media block)
        extra.typography                   -> font-family
    """
    if not isinstance(extra, dict):
        return ""
    out = []
    fs = extra.get("mobileFontSize" if mobile else "desktopFontSize")
    v = value_of(fs) if isinstance(fs, dict) else None
    if v:
        out.append(f"font-size:{v}{'!important' if mobile else ''}")
    if not mobile:
        typ = extra.get("typography")
        fam = value_of(typ) if isinstance(typ, dict) else None
        if fam:
            out.append(f"font-family:{fam}")
    return ";".join(out)


def _walk_nodes(section: dict):
    """Yield every styleable node in a section: its metaData plus all elements."""
    md = section.get("metaData")
    if isinstance(md, dict) and md.get("id"):
        yield md
    for el in section.get("elements") or []:
        if isinstance(el, dict) and el.get("id"):
            yield el


def emit_section_css(section: dict, root_vars=None) -> str:
    """Build the complete `sectionStyles` string for ONE section."""
    parts = []

    if root_vars:
        # Custom properties are the clean way to carry a palette across sections.
        # They are emitted once per section, which is harmless — last one wins and
        # they are identical.
        rv = ";".join(f"{k}:{v}" for k, v in root_vars.items())
        parts.append(f":root{{{rv}}}")

    mobile = []
    for node in _walk_nodes(section):
        nid = node["id"]
        sel = f"{SEL_PREFIX}{nid}"
        extra = node.get("extra") or {}

        # THE TWO ID NAMESPACES (see module docstring). GHL emits rules for BOTH
        # the authoring id and the rendered nodeId. Element-level styling — button
        # fills, nav type — is keyed off the rendered id, so both are required or
        # half your CSS lands on a selector that matches nothing.
        rendered = extra.get("nodeId") if isinstance(extra, dict) else None
        sels = sel if not rendered else f"{sel},{SEL_PREFIX}{rendered}"

        base = decls(node.get("styles") or {})
        typ = typography_decls(extra)
        both = ";".join(x for x in (base, typ) if x)
        if both:
            parts.append(f"{sels}{{{both}}}")

        mtyp = typography_decls(extra, mobile=True)
        if mtyp:
            mobile.append(f"{sels}{{{mtyp}}}")

        # Column width lives on class.colWidth as a percentage, not in `styles`.
        cw = (node.get("class") or {}).get("colWidth")
        cwv = value_of(cw) if isinstance(cw, dict) else None
        if cwv:
            parts.append(f"{sel}{{width:{cwv}%}}")

        # mobileStyles is scoped to the AUTHORING id only — that is what the
        # builder emits and what was verified in production. Deliberately NOT
        # widened to `sels`; if a mobile override is not taking effect on an inner
        # element, that asymmetry is the first place to look.
        m = decls(node.get("mobileStyles") or {}, important=True)
        if m:
            mobile.append(f"{sel}{{{m}}}")

        # Responsive visibility flags are builder state; turn them into real CSS
        # or a "hidden on mobile" element is visible to every visitor.
        vis = (extra.get("visibility") or {}).get("value") or {}
        if isinstance(vis, dict):
            if vis.get("hideDesktop"):
                parts.append(f"@media screen and (min-width:481px)"
                             f"{{{sel}{{display:none!important}}}}")
            if vis.get("hideMobile"):
                mobile.append(f"{sel}{{display:none!important}}")

    if mobile:
        parts.append(f"{MOBILE_MQ}{{{''.join(mobile)}}}")

    return "".join(parts)


def apply_css(page_data: dict, root_vars=None) -> dict:
    """Emit and attach `sectionStyles` for every section of a pageData document.

    Mutates and returns `page_data`. Existing sectionStyles are REPLACED — this
    tool is the source of truth for styling, so a stale hand-edit does not survive
    and silently fight the generated rules.
    """
    sections = page_data.get("sections")
    if not isinstance(sections, list):
        raise ValueError(
            "pageData has no 'sections' list. If you saved a whole page record, "
            "pass its .pageData sub-object instead.")
    for sec in sections:
        gen = sec.setdefault("general", {})
        gen["sectionStyles"] = emit_section_css(sec, root_vars)
    return page_data


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Emit GHL sectionStyles CSS for every section of a pageData "
                    "document. Run this BEFORE inject_page.py.",
        epilog="Without this step your styles dict is ignored and the page "
               "renders unstyled.")
    ap.add_argument("page_data", help="Path to a pageData JSON file.")
    ap.add_argument("--out", help="Output path (default: <input>.styled.json).")
    ap.add_argument("--stdout", action="store_true",
                    help="Print the styled document and write no file.")
    ap.add_argument("--root-vars",
                    help='JSON object of CSS custom properties to emit at :root, '
                         'e.g. \'{"--ink":"#111111","--bg":"#ffffff"}\'. '
                         'Optional; nothing is assumed about your palette.')
    ap.add_argument("--indent", type=int, default=0,
                    help="Pretty-print with this indent (default 0 = compact). "
                         "Compact keeps the payload small for autosave.")
    args = ap.parse_args()

    src = pathlib.Path(args.page_data).expanduser()
    if not src.is_file():
        raise SystemExit(f"FATAL: no such file: {src}")
    try:
        doc = json.loads(src.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FATAL: {src} is not valid JSON: {exc}")

    root_vars = None
    if args.root_vars:
        try:
            root_vars = json.loads(args.root_vars)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"FATAL: --root-vars is not valid JSON: {exc}")
        if not isinstance(root_vars, dict):
            raise SystemExit("FATAL: --root-vars must be a JSON object.")

    try:
        apply_css(doc, root_vars)
    except ValueError as exc:
        raise SystemExit(f"FATAL: {exc}")

    dumped = json.dumps(doc, separators=(",", ":")) if not args.indent \
        else json.dumps(doc, indent=args.indent)

    if args.stdout:
        print(dumped)
        return 0

    out = pathlib.Path(args.out) if args.out else src.with_suffix(".styled.json")
    out.write_text(dumped)

    total = sum(len(s.get("general", {}).get("sectionStyles", ""))
                for s in doc["sections"])
    print(f"  sections styled:   {len(doc['sections'])}")
    print(f"  total CSS emitted: {total:,} chars")
    print(f"  -> {out}")
    if total == 0:
        print("  warn: zero CSS emitted. Either the nodes carry no styles, or the "
              "document is not a pageData tree.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
