#!/usr/bin/env python3
"""
page_shell.py — put a page-level stylesheet ONTO a GHL funnel page.

WHY THIS EXISTS
---------------
`css_emitter.py` writes per-element CSS into `section.general.sectionStyles`.
That is the right home for "this heading is 62px" and the wrong home for a
design SYSTEM — a type scale, a spacing scale, one button treatment, component
classes. Those are page-level, and GHL gives you exactly one place to put them:
a `custom-code` element whose payload is a `<style>` tag.

Nothing in the pipeline built that block, so every agent hand-assembled it and
hit the same three undocumented rules:

  * the payload field is `extra.customCode` — not `code`, `html` or `text`.
    Guessing produces an element that renders and a script that never runs.
  * `<script>` must NOT be nested inside a `<div>` — style, script and link tags
    have to be SIBLINGS at the top level of the payload.
  * the script must wait for GHL's `hydrationDone` event, and page settings must
    have "Optimise JavaScript" OFF, or hydration defers and the script runs
    against a DOM that is not there yet.

This module emits a correct block and attaches it as a final section.

WHAT THE SCRIPT DOES, AND WHY IT HAS TO EXIST
------------------------------------------------
A stylesheet needs to say "the hero breathes more than the footer". GHL gives
you no reliable way to put your own class on a section from the authoring tree:
`extra.customClass` exists in the schema but was `{"value": []}` on all 158
nodes of the captured corpus, so whether it reaches the rendered DOM is
UNVERIFIED. The route that shipped is to tag sections at RUNTIME.

Roles are derived from CONTENT, never from position. A positional list is wrong
the moment a page has a different number of sections — on a 4-section page a
list written for a 9-section page labels section 3 "the date band" and applies a
date band's treatment to whatever happens to be there. Content-derived tagging
needs no per-page configuration.

Roles assigned (all `gp-` prefixed, matching `page-styles.starter.css`):

    gp-tail        last section, or any section containing <style>/<script>
    gp-form-plate  contains a form
    gp-hero        contains an h1
    gp-foot        contains "all rights reserved"
    gp-bar         section 0 with under 90 characters of text
    gp-close       contains .gp-seal
    gp-cols        2+ columns in its last row
    gp-band        everything else

ORDER MATTERS in that list. The tail carries this stylesheet, whose COMMENTS can
match a later text test, so it is identified first and by structure rather than
by words.

USAGE
-----
    # print the block (paste into a custom-code element, or into GHL's
    # page-settings custom-code box)
    python3 page_shell.py --emit

    # your own stylesheet, plus a webfont
    python3 page_shell.py --emit --css my-page.css \\
        --font-css "https://fonts.googleapis.com/css2?family=...&display=swap"

    # attach to a pageData tree as a final section, then style and inject
    python3 page_shell.py --attach page.json --out page.json
    python3 css_emitter.py page.json
    python3 inject_page.py --page-data page.styled.json ...

    # verify the block is wired, not merely present
    python3 page_shell.py --check page.json

VERIFICATION
------------
`--check` is a static check. It proves the block is in the tree exactly once and
that every `gp-*` class the stylesheet targets is one the script actually
assigns. It does NOT prove the page renders — only
`https://sites.leadconnectorhq.com/preview/<pageId>` does that, read as COMPUTED
style. A rule that is present and losing on specificity looks exactly like a
rule that is absent.

No brand, palette, font, id or account is baked in.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_CSS = HERE / "page-styles.starter.css"

# Roles the runtime script can assign. `--check` compares the stylesheet's
# `gp-*` usage against this set, so a class you style but never assign is caught
# before it reaches a page as a rule that quietly matches nothing.
ROLES = ("gp-tail", "gp-form-plate", "gp-hero", "gp-foot", "gp-bar",
         "gp-close", "gp-cols", "gp-band")

# Classes the script sets that are not section roles.
RUNTIME_CLASSES = ("gp-ready", "gp-in", "gp-anim")

# The runtime. Deliberately dependency-free, idempotent, and safe to run twice —
# GHL fires `hydrationDone` unreliably, so there is also a timeout fallback and
# both paths can execute.
SCRIPT = r"""
<script>
(function(){
  if(window.__gpInit) return; window.__gpInit = 1;

  // Role from CONTENT, not position. ORDER MATTERS: the tail carries the
  // stylesheet, whose comments can match a later text test, so it is caught
  // first and by structure.
  function roleOf(s, i, n){
    if(i === n - 1 || s.querySelector('style,script'))      return 'gp-tail';
    if(s.querySelector('.ghl-form-wrap,form,input'))        return 'gp-form-plate';
    if(s.querySelector('h1'))                               return 'gp-hero';
    if(/all rights reserved/i.test(s.textContent || ''))    return 'gp-foot';
    if(i === 0 && (s.textContent || '').trim().length < 90) return 'gp-bar';
    if(s.querySelector('.gp-seal'))                         return 'gp-close';
    // Count the columns of the LAST row, so a full-width headline row above a
    // multi-column band does not skew the total.
    var rows = s.querySelectorAll('[class*=row-]');
    var last = rows[rows.length - 1];
    var cols = last ? last.querySelectorAll('[class*=column-]').length : 0;
    if(cols >= 2) return 'gp-cols';
    return 'gp-band';
  }

  function start(){
    var root = document.querySelector('.hl_page-preview--content');
    if(!root) return;                       // not a rendered GHL page — do nothing
    document.documentElement.classList.add('gp-ready');

    var secs = [].slice.call(root.querySelectorAll('[class*=section-]'));
    // A section can match both `section-<id>` and `csection-<id>`; querying the
    // substring returns the outermost first, which is the one to tag.
    secs.forEach(function(s, i){ s.classList.add(roleOf(s, i, secs.length)); });
    if(secs.length) secs[secs.length - 1].classList.add('gp-tail');

    // Stagger index. nth-child() cannot do this: GHL wraps every element in its
    // own div, so each one is :nth-child(1) and every delay resolves to 0ms.
    secs.forEach(function(s){
      var kids = s.querySelectorAll('h1,h2,h3,p,a,img,button');
      Array.prototype.forEach.call(kids, function(el, i){
        el.classList.add('gp-anim');
        el.style.setProperty('--i', Math.min(i, 7));
      });
    });

    if(!('IntersectionObserver' in window)){
      secs.forEach(function(s){ s.classList.add('gp-in'); });   // reveal everything
      return;
    }
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){
        if(e.isIntersecting){ e.target.classList.add('gp-in'); io.unobserve(e.target); }
      });
    }, {threshold: .18});
    secs.forEach(function(s){ io.observe(s); });

    // The first screen plays immediately instead of waiting for a scroll it may
    // never get.
    if(secs[0]) secs[0].classList.add('gp-in');
    var hero = root.querySelector('.gp-hero');
    if(hero) hero.classList.add('gp-in');
  }

  document.addEventListener('hydrationDone', start);
  setTimeout(start, 1200);        // fallback: the event may already have fired
})();
</script>
""".strip()


def font_links(href: str) -> str:
    """<link> + preconnect, never @import.

    @import serialises the font fetch behind the stylesheet parse and delays
    first paint. On a type-led design that is the entire first impression.
    """
    if not href:
        return ""
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link rel="stylesheet" href="{href}">')


def build_block(css: str, font_css: str = "") -> str:
    """Assemble the custom-code payload.

    The three top-level tags are SIBLINGS. Nesting the <script> inside a <div>
    is the single most common way this block ships inert.
    """
    return f"{font_links(font_css)}<style>\n{css.strip()}\n</style>\n{SCRIPT}"


# ── attach ───────────────────────────────────────────────────────────────────

def _ids_from(doc: dict) -> dict:
    """Lift pageId / funnelId / locationId off any existing section.

    A section carries them as siblings of `elements`. Building the shell section
    without them produces a section GHL accepts and then cannot place.
    """
    for sec in doc.get("sections") or []:
        if isinstance(sec, dict) and sec.get("pageId"):
            return {"page_id": sec.get("pageId", ""),
                    "funnel_id": sec.get("funnelId", ""),
                    "location_id": sec.get("locationId", "")}
    return {"page_id": "", "funnel_id": "", "location_id": ""}


def attach(doc: dict, block: str) -> dict:
    """Append (or replace) the shell section at the end of a pageData document."""
    sys.path.insert(0, str(HERE))
    try:
        from ghl_generator import Generator      # noqa: E402
    except ImportError as exc:                   # pragma: no cover
        raise SystemExit(f"FATAL: page_shell --attach needs ghl_generator.py "
                         f"beside it: {exc}")

    sections = doc.get("sections")
    if not isinstance(sections, list):
        raise SystemExit(
            "FATAL: that JSON has no 'sections' list. If you saved a whole page "
            "RECORD, pass its .pageData sub-object instead.")

    # Drop any shell we wrote before, so re-running does not stack stylesheets.
    # Two copies of this block means two role-tagging scripts; the second exits
    # on the __gpInit guard, but the duplicate <style> still doubles the payload.
    before = len(sections)
    sections[:] = [s for s in sections if "__gpInit" not in json.dumps(s)]
    replaced = before - len(sections)

    gen = Generator(templates={}, base=doc, **_ids_from(doc))
    shell = gen.section([gen.row([gen.column([gen.custom_code(block)])])],
                        sequence=len(sections))
    sections.append(shell)
    doc["sections"] = sections

    print(f"  shell section {'replaced' if replaced else 'appended'} "
          f"({len(block):,} chars of CSS+JS)")
    print(f"  sections now: {len(sections)}")
    return doc


# ── check ────────────────────────────────────────────────────────────────────

def check(doc: dict) -> int:
    """Prove the block is WIRED, not merely present. Returns an exit code."""
    blocks = []

    def walk(node):
        if isinstance(node, dict):
            extra = node.get("extra")
            if isinstance(extra, dict):
                code = extra.get("customCode")
                if isinstance(code, dict):
                    code = code.get("value")
                if isinstance(code, str) and "__gpInit" in code:
                    blocks.append(code)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    problems = []

    if len(blocks) == 0:
        problems.append("no page shell found — run --attach first")
    elif len(blocks) > 1:
        problems.append(f"{len(blocks)} page shells found; there must be exactly 1")
    else:
        block = blocks[0]
        if "<style>" not in block:
            problems.append("shell has no <style> tag — the stylesheet is missing")
        if "hydrationDone" not in block:
            problems.append("shell script does not wait for hydrationDone")
        if re.search(r"<div[^>]*>\s*<script", block):
            problems.append("<script> is nested inside a <div> — it must be a "
                            "sibling or it will not run")
        # Every gp-* class the stylesheet targets must be one the script sets,
        # or it is a rule that matches nothing on a rendered page.
        # Strip CSS comments first: this stylesheet documents its own selectors
        # in prose, and a class named inside a comment is not a rule.
        sheet = re.sub(r"/\*.*?\*/", "", block.split("</style>")[0], flags=re.S)
        styled = set(re.findall(r"\.(gp-[a-z-]+)", sheet))
        known = set(ROLES) | set(RUNTIME_CLASSES)
        # Content classes an author writes into element HTML themselves.
        authored = {"gp-lead", "gp-label", "gp-legal", "gp-seal"}
        orphans = sorted(styled - known - authored)
        if orphans:
            problems.append("styled but never assigned by the script, and not a "
                            "documented authored class: " + ", ".join(orphans))

    sec_count = len(doc.get("sections") or [])
    styles_written = sum(
        1 for s in (doc.get("sections") or [])
        if (s.get("general") or {}).get("sectionStyles"))

    print(f"  sections:                 {sec_count}")
    print(f"  page shells:              {len(blocks)}")
    print(f"  sections with sectionStyles: {styles_written}/{sec_count}")
    if styles_written == 0:
        print("  note: no sectionStyles yet — run css_emitter.py before injecting, "
              "or the per-element styling renders as nothing.")

    if problems:
        for p in problems:
            print(f"  FAIL: {p}", file=sys.stderr)
        return 1

    print("  OK — shell present once, script wired, every styled role assigned.")
    print("  This is a STATIC check. Prove it on "
          "https://sites.leadconnectorhq.com/preview/<pageId>, reading computed "
          "style at a real viewport.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build and attach the page-level stylesheet block for a GHL "
                    "funnel page.",
        epilog="Run --attach BEFORE css_emitter.py, so the shell section gets "
               "sectionStyles emitted for it too.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit", action="store_true",
                      help="Print the custom-code block and write nothing.")
    mode.add_argument("--attach", metavar="PAGE_JSON",
                      help="Append the shell to a pageData document.")
    mode.add_argument("--check", metavar="PAGE_JSON",
                      help="Verify the shell is present once and wired.")
    ap.add_argument("--css", default=str(DEFAULT_CSS),
                    help=f"Stylesheet to embed (default: {DEFAULT_CSS.name}).")
    ap.add_argument("--font-css", default="",
                    help="Webfont stylesheet URL; emitted as <link> with "
                         "preconnect, never @import.")
    ap.add_argument("--out", help="Output path for --attach (default: in place).")
    args = ap.parse_args()

    if args.check:
        src = pathlib.Path(args.check).expanduser()
        if not src.is_file():
            raise SystemExit(f"FATAL: no such file: {src}")
        return check(json.loads(src.read_text()))

    css_path = pathlib.Path(args.css).expanduser()
    if not css_path.is_file():
        raise SystemExit(
            f"FATAL: no stylesheet at {css_path}.\n"
            f"  The starter ships with this repo as tools/page-styles.starter.css.")
    css = css_path.read_text()
    block = build_block(css, args.font_css)

    if args.emit:
        print(block)
        return 0

    src = pathlib.Path(args.attach).expanduser()
    if not src.is_file():
        raise SystemExit(f"FATAL: no such file: {src}")
    try:
        doc = json.loads(src.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FATAL: {src} is not valid JSON: {exc}")

    attach(doc, block)
    out = pathlib.Path(args.out) if args.out else src
    out.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"  -> {out}")
    print("  next: css_emitter.py, then inject_page.py, then verify on the "
          "rendered preview.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
