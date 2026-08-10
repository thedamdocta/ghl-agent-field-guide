#!/usr/bin/env python3
"""
ghl_generator.py — build a valid GHL `pageData` authoring tree from a small spec.

WHY THIS EXISTS
---------------
`css_emitter.py` STYLES a tree. `inject_page.py` WRITES a tree. Without this
module there is nothing that BUILDS one, and the pipeline starts from whatever
page GHL's own AI happened to generate for you.

Output of this module is a `pageData` document you can hand straight to
`css_emitter.py` and then to `inject_page.py`.

THE DESIGN DECISION: CLONE EXEMPLARS, DO NOT HAND-WRITE ELEMENTS
------------------------------------------------------------------
A GHL element carries dozens of required keys and EVERY value is wrapped —
`{"value": X}` or `{"value": X, "unit": "px"}`, never a bare scalar. Hand-writing
them produces nodes that fail in ways that do not name the missing key.

So this factory CLONES verified exemplars captured off a real GHL page and
overrides only text, colour and layout. That guarantees schema validity. Get an
exemplar file with:

    python3 capture_funnel.py <any public GHL funnel page url> \
        --exemplars exemplars.json

You can also point `--templates` at exemplars pulled from an AUTHORING tree
(`GET backend.leadconnectorhq.com/funnels/page/<pageId>` -> `.pageData`), which is
higher fidelity than a rendered capture. Either works: every clone gets fresh ids.

THE EXEMPLAR ROLE TRAP — verified, cost a full rebuild
--------------------------------------------------------
An exemplar carries its original ROLE, not just its schema. Cloning the first
section off a page whose section 0 was the sticky navigation bar produced seven
stacked sticky-nav sections. Schema valid, CSS valid, semantics wrong — and a
key-set diff showed ZERO differences. Keep SEPARATE exemplars for nav / hero /
content / footer, and inspect `extra.sticky`, `title`, `class.width` and padding
magnitude before adopting one. `capture_funnel.py --pick TYPE=N` selects a
different occurrence.

THE TWO ID NAMESPACES
---------------------
Authoring ids (what you WRITE) have NO leading `c`. The rendered id lives at
`extra.nodeId` and DOES carry the `c`. Every element minted here sets both, in
that relationship, because `css_emitter.py` emits CSS for both and element-level
styling keys off the rendered one.

MODULARITY
----------
Use `cv("slot")` to emit a `{{custom_values.slot}}` merge tag instead of literal
text — but read `knowledge/custom-values.md` first. The rule that keeps a build
maintainable: a custom value earns its place ONLY when the same string appears on
MORE THAN ONE surface. Everything else should be literal text the client can see
and edit in the WYSIWYG builder. And an unknown merge tag resolves to the EMPTY
STRING, silently — so every slot you emit must be created before launch
(`create_custom_values.py`).

USAGE — CLI
-----------
    python3 ghl_generator.py --emit-example > page-spec.json
    python3 ghl_generator.py --templates exemplars.json --list
    python3 ghl_generator.py --spec page-spec.json --templates exemplars.json \
        --base captured-pagedata.json --out page.json

Then:  css_emitter.py page.json  ->  inject_page.py --page-data page.styled.json

USAGE — AS A LIBRARY
--------------------
    from ghl_generator import Generator
    gen = Generator.from_file("exemplars.json")
    doc = gen.page([gen.section([gen.row([gen.column([
              gen.heading("<h1>Hello</h1>", color="#111111"),
              gen.button("Save my seat"),
          ])])], background="#ffffff")])

Nothing about a brand, palette, font, id or account is baked in. Colours, copy and
sizes come from your spec; structure comes from your exemplars.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import random
import string
import sys

# Top-level blocks a pageData document needs alongside `sections`. GHL populates
# these itself in the builder; cloning them off a real page (--base) is the only
# way to be sure they are shaped correctly.
PAGE_BLOCKS = ("settings", "general", "pageStyles", "trackingCode",
               "fontsForPreview", "popups", "popupsList")

# Conservative empty defaults, used only when no --base is given. UNVERIFIED: a
# page built from these has not been round-tripped through the builder. Prefer
# --base with a real page's pageData.
PAGE_BLOCK_DEFAULTS = {
    "settings": {}, "general": {}, "pageStyles": {}, "trackingCode": {},
    "fontsForPreview": [], "popups": [], "popupsList": [],
}

# One factory can be satisfied by several exemplar key spellings, because a
# rendered capture and a hand-built template file disagree on naming. Order is
# preference order.
ALIASES = {
    "heading": ("heading", "headline", "header"),
    "subheading": ("sub-heading", "sub-headline", "subheading", "subheadline"),
    "paragraph": ("paragraph", "text", "body"),
    "button": ("button", "cta"),
    "image": ("image", "img"),
    "divider": ("divider", "separator", "hr"),
    "form": ("form",),
    "custom-code": ("custom-code", "customCode", "custom_code", "code", "html"),
    "column": ("column", "col"),
    "row": ("row",),
    "section": ("section",),
}

# Button action -> where the target belongs. THESE ARE NOT INTERCHANGEABLE.
# Writing a scroll target into `visitWebsite` is schema-valid, returns 201, and
# produces a button that moves the page 0px — verified: every CTA on a six-page
# funnel was inert that way for exactly this reason.
ACTIONS_NEEDING_TARGET = {"scroll-to-element", "openPopup", "go-to-funnel-step",
                          "open-website", "visit-website"}


def uid(prefix: str) -> str:
    """A GHL-style AUTHORING id: `<type>-<nanoid>`, with NO leading 'c'.

    The rendered counterpart is this id with a 'c' in front, and it goes on
    `extra.nodeId`. Getting that relationship backwards is the single most common
    reason "my CSS is being ignored".
    """
    alphabet = string.ascii_letters + string.digits + "_-"
    return f"{prefix}-{''.join(random.choice(alphabet) for _ in range(10))}"


def cv(slot: str) -> str:
    """A GHL custom-value merge tag. See the module docstring before using it."""
    return f"{{{{custom_values.{slot}}}}}"


def _set(node: dict, path: str, value) -> None:
    """Set a WRAPPED value: _set(el, 'extra.text', '<h1>hi</h1>').

    Every GHL authoring value is `{"value": X}`. Writing a bare scalar where the
    builder expects a wrapper does not error — the property is simply ignored,
    which is far worse than an error.
    """
    cur = node
    parts = path.split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    leaf = parts[-1]
    if isinstance(cur.get(leaf), dict) and "value" in cur[leaf]:
        cur[leaf]["value"] = value
    else:
        cur[leaf] = {"value": value}


def _set_px(node: dict, path: str, value) -> None:
    """Set a `{"value": N, "unit": "px"}` pair. Skips silently on None."""
    if value is None:
        return
    _set(node, path, value)
    cur = node
    for part in path.split(".")[:-1]:
        cur = cur[part]
    cur[path.split(".")[-1]]["unit"] = "px"


class Generator:
    """Element factory bound to one set of exemplars (and optionally a base page)."""

    def __init__(self, templates: dict, base: dict = None,
                 page_id: str = "", funnel_id: str = "", location_id: str = ""):
        if not isinstance(templates, dict) or not templates:
            raise SystemExit(
                "FATAL: no exemplars. Capture some first:\n"
                "  python3 capture_funnel.py <public funnel page url> "
                "--exemplars exemplars.json")
        self.templates = templates
        self.base = base or {}
        self.page_id = page_id
        self.funnel_id = funnel_id
        self.location_id = location_id

    # ── construction ─────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, templates_path: str, base_path: str = None, **kwargs):
        templates = _read_json(templates_path, "exemplars")
        base = _read_json(base_path, "base pageData") if base_path else None
        if base is not None and "sections" not in base:
            # Almost always the whole page RECORD was passed instead of its
            # pageData sub-object. Recover rather than fail — but say so.
            if isinstance(base.get("pageData"), dict):
                print("  note: --base looked like a page record; using its "
                      ".pageData sub-object.", file=sys.stderr)
                base = base["pageData"]
        return cls(templates, base, **kwargs)

    def _clone(self, kind: str, new_id: str) -> dict:
        """Clone an exemplar for `kind` and give it fresh authoring + rendered ids."""
        names = ALIASES.get(kind, (kind,))
        for name in names:
            if name in self.templates:
                element = copy.deepcopy(self.templates[name])
                break
        else:
            raise SystemExit(
                f"FATAL: no exemplar for {kind!r}.\n"
                f"  tried key(s): {', '.join(names)}\n"
                f"  available:    {', '.join(sorted(self.templates)) or '(none)'}\n"
                f"  fix: capture a page that CONTAINS this element type:\n"
                f"       python3 capture_funnel.py <url> --exemplars exemplars.json")
        element["id"] = new_id
        if isinstance(element.get("extra"), dict):
            # The RENDERED id, and it carries the leading 'c'. css_emitter.py
            # emits CSS against both this and the authoring id.
            element["extra"]["nodeId"] = "c" + new_id
        return element

    # ── leaf elements ────────────────────────────────────────────────────────

    def heading(self, html: str, *, color: str = None, desktop_size: int = None,
                mobile_size: int = None) -> dict:
        return self._text("heading", html, color, desktop_size, mobile_size)

    def subheading(self, html: str, *, color: str = None, desktop_size: int = None,
                   mobile_size: int = None) -> dict:
        return self._text("subheading", html, color, desktop_size, mobile_size)

    def paragraph(self, html: str, *, color: str = None, desktop_size: int = None,
                  mobile_size: int = None) -> dict:
        return self._text("paragraph", html, color, desktop_size, mobile_size)

    def _text(self, kind: str, html: str, color, desktop_size, mobile_size) -> dict:
        """Rich text is HTML inside `extra.text.value`.

        Font size lives on `extra`, NOT in `styles` — set fontSize inside `styles`
        all day and nothing changes, because the builder reads type off `extra`.
        `css_emitter.py` translates these into real CSS.
        """
        element = self._clone(kind, uid(kind))
        _set(element, "extra.text", html)
        if color:
            _set(element, "styles.color", color)
        _set_px(element, "extra.desktopFontSize", desktop_size)
        _set_px(element, "extra.mobileFontSize", mobile_size)
        return element

    def button(self, label: str, *, action: str = "go-to-next-funnel-step",
               target: str = "", background: str = None, color: str = None,
               new_tab: bool = False) -> dict:
        """A button, wired with the CORRECT field for its action.

        THE ACTION FIELDS ARE NOT INTERCHANGEABLE — decoded from a real funnel:

            go-to-next-funnel-step  no target; visitWebsite {url:"", newTab:false}
            go-to-funnel-step       needs a funnel step id
            scroll-to-element       extra.scrollToElement.value = target nodeId
            openPopup               extra.popupId.value = popup id (from popupsList)
            open-website            extra.visitWebsite.value = {url, newTab}

        Writing a scroll target into `visitWebsite` is schema-valid and returns
        201, and produces a button that moves the page 0px. That is how every CTA
        on a six-page funnel ended up inert. Default is go-to-next-funnel-step
        because it is what a funnel CTA almost always wants and it needs no id to
        be correct.
        """
        if action in ACTIONS_NEEDING_TARGET and not target:
            raise SystemExit(
                f"FATAL: button action {action!r} requires a target and none was "
                f"given.\n"
                f"  scroll-to-element -> the target element's nodeId\n"
                f"  openPopup         -> a popup id from the page's popupsList\n"
                f"  go-to-funnel-step -> a funnel step id\n"
                f"  open-website      -> a url\n"
                f"  (a targetless action of this kind deploys fine and does "
                f"nothing at all)")

        element = self._clone("button", uid("button"))
        _set(element, "extra.text", label)
        _set(element, "extra.action", action)
        extra = element.setdefault("extra", {})
        # Reset both target carriers so a cloned exemplar cannot leak the wiring
        # of the button it was cloned from.
        extra["visitWebsite"] = {"value": {"url": "", "newTab": bool(new_tab)}}
        extra["scrollToElement"] = {"value": ""}
        if action == "scroll-to-element":
            extra["scrollToElement"] = {"value": target}
        elif action == "openPopup":
            extra["popupId"] = {"value": target}
        elif action == "go-to-funnel-step":
            extra["funnelStepId"] = {"value": target}
        elif action in ("open-website", "visit-website"):
            extra["visitWebsite"] = {"value": {"url": target,
                                               "newTab": bool(new_tab)}}
        if background:
            _set(element, "styles.backgroundColor", background)
        if color:
            _set(element, "styles.color", color)
        return element

    def image(self, url: str = "", alt: str = "", css_class: str = "") -> dict:
        """An image. `css_class` lands in extra.customClass so page CSS can target it.

        Host the asset in the client's OWN GHL media library, not a third-party
        CDN — a third-party generation URL disappears when its owner deletes the
        generation, and the page silently loses its image.
        """
        element = self._clone("image", uid("image"))
        if url:
            props = element.setdefault("extra", {}).setdefault("imageProperties", {})
            value = dict(props.get("value") or {}) \
                if isinstance(props.get("value"), dict) else {}
            value["url"] = url
            value["alt"] = alt
            props["value"] = value
        if css_class:
            element.setdefault("extra", {})["customClass"] = {"value": [css_class]}
        return element

    def divider(self) -> dict:
        return self._clone("divider", uid("divider"))

    def form(self, form_id: str, form_name: str = "", *,
             redirect_url: str = "") -> dict:
        """A NATIVE GHL form element, referencing a real form by id.

        Use this, not a hand-rolled <form> in a custom-code block: the hand-rolled
        one renders perfectly and captures NO leads.

        SUBMIT BEHAVIOUR LIVES HERE, ON THE PAGE ELEMENT — not on the form record.
        Writing `formAction.actionType` / `redirectUrl` onto the form record
        returns 200 and silently does not persist (verified by round-trip).

        UNVERIFIED: only "ThankYouMessage" has been observed in captured
        production pages. "Redirect" is a CANDIDATE value, inferred from the enum,
        not confirmed. Set the option once in the builder UI and re-capture, or do
        one real test submission, before you describe redirect-on-submit as
        working.

        Give every funnel its OWN form (`create_form.py`). Pointing a page at a
        pre-existing generically-named account form imports that form's fields,
        image, header, branding and fixed width — and restyling it changes every
        other place that form is embedded.
        """
        if not form_id:
            raise SystemExit(
                "FATAL: form element needs a formId. Create one first:\n"
                "  python3 create_form.py --name '<name>' --clone-from <formId> --apply")
        element = self._clone("form", uid("form"))
        # formId is {"value": <id>, "text": <display name>} — the builder uses both.
        element.setdefault("extra", {})["formId"] = {"value": form_id,
                                                     "text": form_name}
        if redirect_url:
            element["extra"]["form_submit_type"] = "Redirect"
            element["extra"]["form_submit_redirect_url"] = redirect_url
        else:
            element["extra"]["form_submit_type"] = "ThankYouMessage"
        return element

    def custom_code(self, html: str) -> dict:
        """GHL's custom HTML/JS element.

        The payload field is `extra.customCode` — NOT code / html / text. Guessing
        those silently produces an empty block: the element renders, the script
        never runs, and nothing anywhere reports a problem.

        Mixing native elements with custom-code blocks is sanctioned — GHL's own
        Funnel AI emits both in one page. Prefer native elements for anything the
        client should be able to edit in the builder.
        """
        element = self._clone("custom-code", uid("custom-code"))
        _set(element, "extra.customCode", html)
        return element

    # ── containers ───────────────────────────────────────────────────────────

    def column(self, children: list, width: int = 100) -> tuple:
        """A column. Returns (column, children) — the tree is FLAT, see section()."""
        col = self._clone("column", uid("column"))
        col["child"] = [c["id"] for c in children]
        # Column width lives at class.colWidth as a PERCENTAGE, not in `styles`.
        _set(col, "class.colWidth", width)
        return col, children

    def row(self, columns: list) -> tuple:
        row = self._clone("row", uid("row"))
        row["child"] = [c[0]["id"] for c in columns]
        flat = []
        for col, kids in columns:
            flat.append(col)
            flat.extend(kids)
        return row, flat

    def section(self, rows: list, *, background: str = None,
                sequence: int = 0) -> dict:
        """A section.

        Structure, decoded from real pages: `elements` is a FLAT list of every
        row, column and element in the section, and parent->child is by ID
        REFERENCE inside that flat array. It is not a nested tree, even though the
        hierarchy is section -> row -> col -> element.
        """
        section_id = uid("section")
        meta = copy.deepcopy(self._template_for("section"))
        meta["id"] = section_id
        meta["child"] = [r[0]["id"] for r in rows]
        if isinstance(meta.get("extra"), dict):
            meta["extra"]["nodeId"] = "c" + section_id
        if background and isinstance(meta.get("styles"), dict):
            meta["styles"].setdefault("backgroundColor", {})["value"] = background

        elements = []
        for row, kids in rows:
            elements.append(row)
            elements.extend(kids)

        return {
            "id": section_id,
            "metaData": meta,
            "elements": elements,
            "sequence": sequence,
            "pageId": self.page_id,
            "funnelId": self.funnel_id,
            "locationId": self.location_id,
            # css_emitter.py writes general.sectionStyles here. Inherit the rest
            # of the block from --base when we have one.
            "general": copy.deepcopy(self._base_section_general()),
        }

    def page(self, sections: list) -> dict:
        """Assemble a complete pageData document.

        The seven top-level blocks besides `sections` are builder state. Cloning
        them from a real page (--base) is the reliable path; the empty defaults
        are UNVERIFIED and exist so the tool is usable before you have a base.
        """
        doc = {}
        missing = []
        for key in PAGE_BLOCKS:
            if isinstance(self.base, dict) and key in self.base:
                doc[key] = copy.deepcopy(self.base[key])
            else:
                doc[key] = copy.deepcopy(PAGE_BLOCK_DEFAULTS[key])
                missing.append(key)
        if missing:
            print(f"  warn: no --base for {', '.join(missing)} — using EMPTY "
                  f"defaults (UNVERIFIED). Pass --base with a real page's "
                  f"pageData:\n"
                  f"        curl -sS -H \"token-id: $(cat .jwt)\" -H 'channel: APP' "
                  f"-H 'source: WEB_USER' -H 'Version: 2021-07-28' \\\n"
                  f"             https://backend.leadconnectorhq.com/funnels/page/"
                  f"<pageId> > page-record.json", file=sys.stderr)
        doc["sections"] = sections
        return doc

    # ── internals ────────────────────────────────────────────────────────────

    def _template_for(self, kind: str) -> dict:
        for name in ALIASES.get(kind, (kind,)):
            if name in self.templates:
                return self.templates[name]
        raise SystemExit(
            f"FATAL: no exemplar for {kind!r}. available: "
            f"{', '.join(sorted(self.templates)) or '(none)'}")

    def _base_section_general(self) -> dict:
        sections = self.base.get("sections") if isinstance(self.base, dict) else None
        if isinstance(sections, list) and sections:
            general = sections[0].get("general")
            if isinstance(general, dict):
                return general
        return {"sectionStyles": ""}


# ── spec -> document ─────────────────────────────────────────────────────────

EXAMPLE_SPEC = {
    "sections": [
        {
            "background": "#ffffff",
            "rows": [
                {
                    "columns": [
                        {
                            "width": 100,
                            "elements": [
                                {"kind": "heading",
                                 "html": "<h1>Your headline goes here</h1>",
                                 "color": "#111111",
                                 "desktopSize": 44, "mobileSize": 30},
                                {"kind": "paragraph",
                                 "html": "<p>One sentence of supporting copy.</p>",
                                 "color": "#444444", "desktopSize": 18},
                                {"kind": "button",
                                 "label": "Save my seat",
                                 "action": "go-to-next-funnel-step",
                                 "background": "#111111", "color": "#ffffff"}
                            ]
                        }
                    ]
                }
            ]
        },
        {
            "background": "#f5f5f5",
            "rows": [
                {
                    "columns": [
                        {"width": 50,
                         "elements": [{"kind": "subheading",
                                       "html": "<h2>Left</h2>"}]},
                        {"width": 50,
                         "elements": [{"kind": "form",
                                       "formId": "<a real form id>",
                                       "formName": "Registration",
                                       "_comment": "submit behaviour lives HERE, "
                                                   "not on the form record"}]}
                    ]
                }
            ]
        }
    ]
}


def build_element(gen: Generator, spec: dict, where: str) -> dict:
    """Turn one element spec dict into a GHL element. Fails loudly on unknowns."""
    if not isinstance(spec, dict):
        raise SystemExit(f"FATAL: {where} is not an object.")
    kind = spec.get("kind")
    if not kind:
        raise SystemExit(f"FATAL: {where} has no 'kind'.")

    if kind in ("heading", "subheading", "paragraph"):
        factory = {"heading": gen.heading, "subheading": gen.subheading,
                   "paragraph": gen.paragraph}[kind]
        html = spec.get("html")
        if html is None:
            raise SystemExit(f"FATAL: {where} ({kind}) has no 'html'.")
        return factory(html, color=spec.get("color"),
                       desktop_size=spec.get("desktopSize"),
                       mobile_size=spec.get("mobileSize"))
    if kind == "button":
        label = spec.get("label")
        if label is None:
            raise SystemExit(f"FATAL: {where} (button) has no 'label'.")
        return gen.button(label, action=spec.get("action", "go-to-next-funnel-step"),
                          target=spec.get("target", ""),
                          background=spec.get("background"),
                          color=spec.get("color"),
                          new_tab=bool(spec.get("newTab")))
    if kind == "image":
        return gen.image(spec.get("url", ""), spec.get("alt", ""),
                         spec.get("cssClass", ""))
    if kind == "divider":
        return gen.divider()
    if kind == "form":
        return gen.form(spec.get("formId", ""), spec.get("formName", ""),
                        redirect_url=spec.get("redirectUrl", ""))
    if kind in ("custom-code", "customCode"):
        html = spec.get("html")
        if html is None:
            raise SystemExit(f"FATAL: {where} (custom-code) has no 'html'.")
        return gen.custom_code(html)

    raise SystemExit(
        f"FATAL: {where} has unknown kind {kind!r}. Known kinds: heading, "
        f"subheading, paragraph, button, image, divider, form, custom-code.")


def build_page(gen: Generator, spec: dict) -> dict:
    sections_spec = spec.get("sections")
    if not isinstance(sections_spec, list) or not sections_spec:
        raise SystemExit("FATAL: spec has no non-empty 'sections' list. Run "
                         "--emit-example to see the shape.")
    sections = []
    for s_i, sec in enumerate(sections_spec):
        rows = []
        for r_i, row_spec in enumerate(sec.get("rows") or []):
            columns = []
            for c_i, col_spec in enumerate(row_spec.get("columns") or []):
                where = f"sections[{s_i}].rows[{r_i}].columns[{c_i}]"
                elements = [build_element(gen, e, f"{where}.elements[{e_i}]")
                            for e_i, e in enumerate(col_spec.get("elements") or [])]
                if not elements:
                    raise SystemExit(f"FATAL: {where} has no elements. An empty "
                                     f"column renders as invisible dead layout.")
                columns.append(gen.column(elements, col_spec.get("width", 100)))
            if not columns:
                raise SystemExit(f"FATAL: sections[{s_i}].rows[{r_i}] has no columns.")
            rows.append(gen.row(columns))
        if not rows:
            raise SystemExit(f"FATAL: sections[{s_i}] has no rows.")
        sections.append(gen.section(rows, background=sec.get("background"),
                                    sequence=s_i))
    return gen.page(sections)


def _read_json(path: str, label: str):
    file_path = pathlib.Path(path).expanduser()
    if not file_path.is_file():
        raise SystemExit(f"FATAL: no such {label} file: {file_path}")
    try:
        return json.loads(file_path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FATAL: {file_path} ({label}) is not valid JSON: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a GHL pageData authoring tree by cloning captured "
                    "exemplars. Run css_emitter.py on the output next.",
        epilog="Exemplars come from capture_funnel.py --exemplars. Nothing about "
               "a brand, palette or account is baked in.")
    ap.add_argument("--spec", help="Page spec JSON (see --emit-example).")
    ap.add_argument("--templates",
                    default=os.environ.get("GHL_ELEMENT_TEMPLATES"),
                    help="Exemplar JSON from capture_funnel.py --exemplars "
                         "(or $GHL_ELEMENT_TEMPLATES).")
    ap.add_argument("--base",
                    help="A real page's pageData JSON, used for the seven "
                         "top-level builder blocks and the section `general` "
                         "block. STRONGLY recommended.")
    ap.add_argument("--out", help="Where to write the pageData document "
                                  "(default: stdout).")
    ap.add_argument("--page-id", default="", help="Target funnel page id, stamped "
                                                  "onto each section.")
    ap.add_argument("--funnel-id", default="", help="Target funnel id.")
    ap.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID", ""),
                    help="Sub-account id (or $GHL_LOCATION_ID).")
    ap.add_argument("--emit-example", action="store_true",
                    help="Print a runnable example spec and exit.")
    ap.add_argument("--list", dest="list_exemplars", action="store_true",
                    help="List the exemplars in --templates and exit.")
    ap.add_argument("--indent", type=int, default=0,
                    help="Indent the output (default 0 = compact, which keeps the "
                         "autosave payload small).")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing --out file.")
    args = ap.parse_args()

    if args.emit_example:
        print(json.dumps(EXAMPLE_SPEC, indent=2))
        return 0

    if args.list_exemplars:
        if not args.templates:
            raise SystemExit("FATAL: --list needs --templates (or "
                             "$GHL_ELEMENT_TEMPLATES).")
        templates = _read_json(args.templates, "exemplars")
        print(f"  {len(templates)} exemplar(s) in {args.templates}:")
        for name in sorted(templates):
            node = templates[name] if isinstance(templates[name], dict) else {}
            print(f"    {name:<18} keys={len(node)}  "
                  f"sticky={bool((node.get('extra') or {}).get('sticky'))}")
        print("  reminder: an exemplar carries its ROLE, not just its schema. "
              "Check sticky/title/width before cloning.")
        return 0

    if not args.spec:
        raise SystemExit(
            "FATAL: nothing to do. Pass --spec <file> to build a page, or "
            "--emit-example to see the spec format, or --list to inspect "
            "exemplars. This tool never writes without an explicit --spec.")
    if not args.templates:
        raise SystemExit(
            "FATAL: no exemplars. Pass --templates <file> or set "
            "$GHL_ELEMENT_TEMPLATES.\n"
            "  get one: python3 capture_funnel.py <public funnel url> "
            "--exemplars exemplars.json")

    spec = _read_json(args.spec, "spec")
    gen = Generator.from_file(args.templates, args.base,
                              page_id=args.page_id, funnel_id=args.funnel_id,
                              location_id=args.location_id)
    doc = build_page(gen, spec)

    dumped = json.dumps(doc, indent=args.indent) if args.indent \
        else json.dumps(doc, separators=(",", ":"))

    element_count = sum(len(s["elements"]) for s in doc["sections"])
    if args.out:
        out = pathlib.Path(args.out).expanduser()
        if out.exists() and not args.force:
            raise SystemExit(f"FATAL: {out} already exists. Pass --force to "
                             f"overwrite.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dumped)
        print(f"  sections: {len(doc['sections'])}   nodes: {element_count}")
        print(f"  -> {out}")
        print("  next: python3 css_emitter.py "
              f"{out}   (without it, NOTHING is styled)")
    else:
        print(dumped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
