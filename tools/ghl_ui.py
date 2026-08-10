#!/usr/bin/env python3
"""
ghl_ui.py — the cross-origin iframe plumbing for driving GHL's workflow builder.

WHY THIS EXISTS
---------------
Two things in GoHighLevel have NO API at all: configuring a workflow TRIGGER, and
PUBLISHING a workflow (Draft -> Published). Both are done by driving the real
builder UI, and both need exactly the same awkward plumbing. `publish_workflow.py`
and `configure_trigger.py` are the tools; this is the shared half they both stand
on, so the hard-won rules below live in ONE place and cannot drift apart.

It is a library. `--self-test` runs the offline fixture tests; there is no other
command here.

THE FIVE RULES THAT MAKE OR BREAK THIS
---------------------------------------
1. THE BUILDER IS A CROSS-ORIGIN IFRAME, NOT THE PAGE. Everything you want lives
   inside a frame served from another host. `page.evaluate(...)` runs in the outer
   document and sees none of it. Acquire the FRAME (`builder_frame`) and evaluate
   there.

2. `page.mouse.click()` SENDS PAGE COORDINATES. An element's `getBoundingClientRect`
   read inside the iframe is in FRAME coordinates. Those two agree only when the
   iframe happens to sit at the page origin — which is true in the full-page builder
   view and FALSE in the list view, where the iframe is inset below the app chrome.
   So: prefer `dispatch_click`, which fires the event inside the frame and needs no
   coordinates at all; and when a real mouse click is genuinely needed, translate
   through `frame_box()` (`center_of`) instead of hardcoding an offset. Any pixel
   numbers you find in old notes are examples of a layout, not constants.

3. dispatchEvent REACHES ELEMENTS A MOUSE CANNOT. The trigger picker renders BELOW
   THE FOLD. A synthetic mouse click at those coordinates lands on whatever is
   actually at that point on screen — usually nothing. A dispatched MouseEvent fires
   on the element regardless of where it is. This is not a hack around scrolling; it
   is the only reliable path.

4. FRAME REFERENCES DIE ON VUE ROUTER NAVIGATION. The frame URL does not change —
   the SPA re-renders — but the handle you are holding goes stale and every
   subsequent `evaluate` throws. After ANY click that navigates, throw the handle
   away and re-acquire by POLLING FOR EXPECTED CONTENT (`find_frame`). Never reuse.

5. A DIRECT BUILDER URL DOES NOT CREATE THE IFRAME. Navigating straight to
   `/automation/builder/<id>` renders the shell without the cross-origin frame, so
   there is nothing to drive. You MUST load the workflows LIST and click the row.
   That is also why every operation here starts with a fresh list load.

PREREQUISITE — SAME CHROME AS `get_token.py`
----------------------------------------------
Chrome must ALREADY be running with a remote-debugging port open, on a dedicated
profile you have ALREADY logged into GHL by hand:

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --remote-debugging-port=9222 \
      --user-data-dir="$HOME/.ghl-agent-profile" \
      --disable-blink-features=AutomationControlled

Use a DEDICATED --user-data-dir: Chrome refuses to open a debug port on a profile
another instance already owns, and the failure is quiet. Verify the port really
listens before blaming these tools:

    curl -s http://127.0.0.1:9222/json/version

WHY THE STEALTH FLAG IS IN THAT LINE. These builder iframes do not load in a
browser that advertises itself as automated. When Playwright LAUNCHES a browser it
adds `--enable-automation`, and the fix there is
`ignore_default_args=["--enable-automation"]` plus
`args=["--disable-blink-features=AutomationControlled"]`. These tools sidestep the
whole problem by CONNECTING to a Chrome you launched yourself — which never had the
flag — and the `--disable-blink-features` above is belt and braces. If a frame never
appears, check `navigator.webdriver` in that window's console before suspecting the
selectors; `webdriver_flagged()` reports it in the failure message for you.

DEPENDENCY: Playwright, imported LAZILY so `--help` works without it.

    pip install playwright     # no `playwright install` — we CONNECT to your Chrome
"""
from __future__ import annotations

import argparse
import contextlib
import sys

DEFAULT_APP_BASE = "https://app.gohighlevel.com"
DEFAULT_PORT = 9222

# The automation builder is served from its own host. Matching on this substring is
# how a frame is identified; do NOT match on 'automation' alone, which also matches
# the parent app URL and hands you the outer document.
AUTOMATION_FRAME_HOST = "client-app-automation-workflows"

# The publish toggle. `role="switch"` with `aria-checked` — see read_toggle().
TOGGLE_ID = "cmp-action-bar__tgl--draft-publish-workflow"


class UIError(RuntimeError):
    """A UI step could not be completed, and pressing on would do damage."""


# ── injected JavaScript ──────────────────────────────────────────────────────
#
# All of it runs INSIDE the builder iframe. Selectors are matched on visible text
# wherever possible: GHL ships a generated SPA whose class names churn between
# releases while the button labels do not.

# THE most important read in either tool. `aria-checked` is the ONLY trustworthy
# publish-state signal: `body.innerText.includes('Draft')` returns true even on a
# published workflow, because the word appears elsewhere in the builder chrome
# (save-state labels, history). Believing that string cost hours once already.
TOGGLE_JS = f"""() => {{
    const el = document.getElementById({TOGGLE_ID!r})
            || document.querySelector('[role="switch"]');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {{ariaChecked: el.getAttribute('aria-checked'),
             x: r.x, y: r.y, w: r.width, h: r.height}};
}}"""

CLICK_TOGGLE_JS = f"""() => {{
    const el = document.getElementById({TOGGLE_ID!r})
            || document.querySelector('[role="switch"]');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    el.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
    return {{x: r.x, y: r.y, w: r.width, h: r.height}};
}}"""

# "Save" means there are unsaved changes; the same button reads "Saved" and goes
# disabled once there are none. So an absent Save button is itself information.
FIND_SAVE_JS = """() => {
    for (const b of document.querySelectorAll('button')) {
        const r = b.getBoundingClientRect();
        if ((b.innerText || '').trim() === 'Save' && r.width > 0 && !b.disabled)
            return {x: r.x, y: r.y, w: r.width, h: r.height};
    }
    return null;
}"""

CLICK_SAVE_JS = """() => {
    for (const b of document.querySelectorAll('button')) {
        const r = b.getBoundingClientRect();
        if ((b.innerText || '').trim() === 'Save' && r.width > 0 && !b.disabled) {
            b.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            return {x: r.x, y: r.y, w: r.width, h: r.height};
        }
    }
    return null;
}"""

# The AI-builder modal opens on the FIRST view of every workflow and swallows every
# click underneath it. Dismiss it before anything else or the rest silently no-ops.
DISMISS_MODAL_JS = """() => {
    for (const b of document.querySelectorAll('button')) {
        if ((b.innerText || '').includes('Got it')) {
            b.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            return true;
        }
    }
    return false;
}"""

# Row anchors carry no usable href (Vue Router), so they are matched on text. The
# anchor's innerText can include the row's other columns, so only the FIRST LINE is
# the workflow name.
LIST_NAMES_JS = """() => {
    const vis = [...document.querySelectorAll('a')]
        .filter(a => a.getBoundingClientRect().width > 0);
    // Prefer anchors that sit in a table row — the list is a table and the page
    // chrome has its own links. Fall back to every visible anchor if the markup
    // ever stops using rows, rather than returning nothing at all.
    const rows = vis.filter(a => a.closest('tr,[role="row"]'));
    const use = rows.length ? rows : vis;
    return use.map(a => ((a.innerText || '').trim().split('\\n')[0] || '').trim())
              .filter(Boolean);
}"""

CLICK_ROW_JS = """(name) => {
    const first = a => ((a.innerText || '').trim().split('\\n')[0] || '').trim();
    const vis = [...document.querySelectorAll('a')]
        .filter(a => a.getBoundingClientRect().width > 0);
    const el = vis.find(a => first(a) === name);
    if (!el) return false;
    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
    return true;
}"""

# Best-effort list filter. The list paginates, and a workflow on page 3 cannot be
# clicked from page 1 — typing into the list's own search box is how a human gets
# past that. Inputs here are framework-controlled, so a plain `el.value = x` updates
# the DOM without telling the framework and the list never re-filters; the native
# setter plus input/change events is what makes the change observable.
FILTER_LIST_JS = """(text) => {
    const set = (el, v) => {
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, v);
        el.dispatchEvent(new Event('input',  {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    };
    const label = i => (i.placeholder || i.getAttribute('aria-label') || '');
    const el = [...document.querySelectorAll('input')]
        .filter(i => i.offsetParent !== null)
        .find(i => /search|filter/i.test(label(i)));
    if (!el) return false;
    set(el, text);
    return true;
}"""

# Click by visible text, from inside the frame. Used for picker items that render
# BELOW THE FOLD, where a coordinate click cannot reach.
CLICK_EXACT_TEXT_JS = """(label) => {
    const hits = [...document.querySelectorAll('*')]
        .filter(el => (el.innerText || '').trim() === label);
    if (!hits.length) return null;
    // A wrapper whose only text is the label matches too. Document order visits
    // ancestors first, so the LAST hit is the deepest — the real control.
    const el = hits[hits.length - 1];
    const r = el.getBoundingClientRect();
    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
    return {x: r.x, y: r.y, w: r.width, h: r.height};
}"""

BODY_TEXT_JS = "() => document.body.innerText"

WEBDRIVER_JS = "() => navigator.webdriver === true"


# ── connecting ───────────────────────────────────────────────────────────────

def import_playwright():
    """Import Playwright, or exit with the one-line fix.

    Imported LATE, and deliberately: `--help` must work on a machine that has never
    installed Playwright.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FATAL: Playwright is not installed.\n"
              "  fix: pip install playwright\n"
              "  (no `playwright install` needed — this connects to YOUR Chrome)",
              file=sys.stderr)
        raise SystemExit(1)
    return sync_playwright


@contextlib.contextmanager
def chrome(port: int):
    """Attach to an already-running, already-logged-in Chrome. Yields a page.

    We CONNECT rather than launch. A launched browser carries `--enable-automation`,
    and these iframes do not load in one that does.
    """
    sync_playwright = import_playwright()
    cdp = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(cdp)
        except Exception as exc:  # noqa: BLE001
            raise UIError(
                f"cannot attach to Chrome at {cdp}\n"
                f"  {type(exc).__name__}: {exc}\n"
                f"  checklist:\n"
                f"    1. Is Chrome running with --remote-debugging-port={port}?\n"
                f"    2. Did you give it a DEDICATED --user-data-dir? Chrome will\n"
                f"       not open a debug port on a profile another instance owns.\n"
                f"    3. Does `curl -s {cdp}/json/version` return JSON? If not, the\n"
                f"       browser never opened the port — a Chrome problem, not this\n"
                f"       tool's.")
        if not browser.contexts:
            raise UIError("attached, but Chrome has no browser context. Open a tab "
                          "and try again.")
        ctx = browser.contexts[0]
        yield ctx.pages[0] if ctx.pages else ctx.new_page()


def webdriver_flagged(page) -> bool:
    """True if this window advertises itself as automated.

    When that is true the builder iframes may never load, and the resulting
    'frame not found' looks exactly like a broken selector. Worth reporting.
    """
    try:
        return bool(page.evaluate(WEBDRIVER_JS))
    except Exception:  # noqa: BLE001
        return False


# ── frames ───────────────────────────────────────────────────────────────────

def find_frame(page, probe_js: str, timeout: int = 25, host: str = None):
    """Poll every frame until `probe_js` returns something truthy. Returns the frame.

    This is rule 4 in practice. A frame handle goes stale the moment the SPA routes,
    so nothing here caches: after any navigating click, call this again and take the
    frame it hands back.
    """
    for _ in range(max(1, timeout * 2)):
        for frame in list(page.frames):
            if host and host not in (frame.url or ""):
                continue
            try:
                if frame.evaluate(probe_js):
                    return frame
            except Exception:  # noqa: BLE001 - stale/at-navigation frames throw
                continue
        page.wait_for_timeout(500)
    return None


def list_frame(page, timeout: int = 25):
    """The workflows LIST iframe — the only door into a builder (rule 5)."""
    return find_frame(page, "() => document.querySelectorAll('a').length > 0",
                      timeout, host=AUTOMATION_FRAME_HOST)


def builder_frame(page, timeout: int = 25):
    """The workflow BUILDER iframe, identified by the publish toggle being present.

    Using the toggle as the signal (rather than body text) means the frame this
    returns is by construction one where the publish state is readable.
    """
    probe = f"""() => {{
        const t = document.getElementById({TOGGLE_ID!r})
               || document.querySelector('[role="switch"]');
        return t ? ['true', 'false'].includes(t.getAttribute('aria-checked')) : false;
    }}"""
    return find_frame(page, probe, timeout)


def frame_box(frame) -> dict:
    """The iframe's position in PAGE coordinates. Queried, never hardcoded.

    In the full-page builder view this is (0, 0) and frame coordinates happen to
    equal page coordinates. In the list view the iframe is inset below the app
    chrome and they do not. Asking is the only thing that is true in both.
    """
    try:
        el = frame.frame_element()
        return el.bounding_box() or {"x": 0, "y": 0}
    except Exception:  # noqa: BLE001
        return {"x": 0, "y": 0}


def center_of(box: dict, rect: dict) -> tuple:
    """Translate a rect read INSIDE the frame into page coordinates."""
    return (float(box.get("x") or 0) + float(rect["x"]) + float(rect["w"]) / 2.0,
            float(box.get("y") or 0) + float(rect["y"]) + float(rect["h"]) / 2.0)


# ── interactions ─────────────────────────────────────────────────────────────

def dispatch_click(frame, js: str, arg=None):
    """Fire a click INSIDE the frame. Returns whatever the snippet returns.

    Preferred over a mouse click everywhere: no coordinates, and it reaches elements
    below the fold that a mouse cannot (rule 3).
    """
    try:
        return frame.evaluate(js, arg) if arg is not None else frame.evaluate(js)
    except Exception as exc:  # noqa: BLE001
        raise UIError(f"click failed inside the builder frame: "
                      f"{type(exc).__name__}: {exc}\n"
                      f"  a stale frame throws exactly like this — re-acquire it "
                      f"after every navigating click.")


def mouse_click(page, frame, rect: dict) -> None:
    """Real mouse click at a frame rect, translated to page coordinates.

    The fallback, not the default. Some Vue controls only respond to a trusted
    event; those are the ones this is for. It cannot reach anything off-screen.
    """
    x, y = center_of(frame_box(frame), rect)
    page.mouse.click(x, y)


def dismiss_modal(frame) -> bool:
    """Dismiss the first-view AI-builder modal. Safe and idempotent."""
    try:
        return bool(frame.evaluate(DISMISS_MODAL_JS))
    except Exception:  # noqa: BLE001
        return False


def read_toggle(frame) -> dict:
    """Publish state and toggle geometry, or None. `aria-checked` is the truth."""
    try:
        return frame.evaluate(TOGGLE_JS)
    except Exception:  # noqa: BLE001
        return None


def is_published(state: dict) -> bool:
    return bool(state) and state.get("ariaChecked") == "true"


# ── the list ─────────────────────────────────────────────────────────────────

def workflows_url(app_base: str, location_id: str) -> str:
    return (f"{app_base.rstrip('/')}/v2/location/{location_id}"
            f"/automation/workflows?listTab=all")


def open_list(page, url: str, settle: int = 8, search: str = None):
    """Fresh list load -> list frame. One page load per workflow, every time.

    Iterating the paginated SPA in place loses frame references and starts throwing
    on row 2. Reloading is slower and it is the thing that works.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(settle * 1_000)
    frame = list_frame(page, timeout=max(10, settle * 2))
    if frame is None:
        raise UIError(
            "the workflows list iframe never appeared.\n"
            "  most likely that Chrome profile is not logged in to GHL, or the\n"
            "  location id is wrong. Bring the window to the front and look at it.\n"
            "  if the page looks fine but no frame loads, check navigator.webdriver "
            "— an automation-flagged browser does not load these iframes.")
    if search:
        # Best effort. If the box is not found we carry on with whatever page 1
        # rendered, and the name match below reports honestly if it is not there.
        try:
            if frame.evaluate(FILTER_LIST_JS, search):
                page.wait_for_timeout(2_500)
        except Exception:  # noqa: BLE001
            pass
    return frame


def list_names(frame) -> list:
    """Workflow names on the rendered list page, in order, de-duplicated."""
    try:
        names = frame.evaluate(LIST_NAMES_JS) or []
    except Exception as exc:  # noqa: BLE001
        raise UIError(f"could not read the workflows list: "
                      f"{type(exc).__name__}: {exc}")
    seen, out = set(), []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def pick_by_name(names: list, wanted: str) -> tuple:
    """Match a workflow name the way ghl_ids matches a funnel: never guess.

    Exact (case-insensitive) first, then a UNIQUE prefix, then a UNIQUE substring.
    Prefix matching is not a convenience — list rows are commonly named
    "WF 1 - Something" while a build spec calls the same workflow "WF 1", and an
    exact-only match refuses work it could obviously do. Several matches raises and
    lists them, because picking one is how the wrong workflow gets published.
    """
    wanted_cf = (wanted or "").strip().casefold()
    if not wanted_cf:
        raise UIError("no workflow name given.")
    listing = "\n".join(f'    "{n}"' for n in names) or "    (none)"

    for how, hits in (
            ("matched by name",
             [n for n in names if n.strip().casefold() == wanted_cf]),
            ("matched by name prefix",
             [n for n in names if n.strip().casefold().startswith(wanted_cf)]),
            ("matched inside the name",
             [n for n in names if wanted_cf in n.strip().casefold()])):
        if len(hits) == 1:
            return hits[0], how
        if len(hits) > 1:
            shown = "\n".join(f'    "{n}"' for n in hits)
            raise UIError(
                f'{len(hits)} workflows match "{wanted}" ({how}):\n{shown}\n'
                f'  fix: pass the full name exactly as the list shows it.')

    raise UIError(
        f'no workflow matching "{wanted}" on the list. {len(names)} visible:\n'
        f'{listing}\n'
        f'  the list PAGINATES — if the name is not above, it may be on another\n'
        f'  page. This tool types into the list search box to narrow it; if that\n'
        f'  box has moved, filter the list by hand and re-run.')


def open_workflow(page, url: str, name: str, settle: int = 8,
                  builder_wait: int = 25):
    """List -> click the row -> builder frame. The only way in (rule 5).

    Returns (builder_frame, matched_name). Every call reloads the list: the frame
    reference from a previous workflow is dead, and reusing it fails in ways that
    look like a selector problem.
    """
    frame = open_list(page, url, settle, search=name)
    names = list_names(frame)
    matched, how = pick_by_name(names, name)
    print(f"  resolved workflow \"{matched}\"   ({how})")

    # The frame dies mid-click — Vue Router navigates. That exception is expected,
    # and swallowing it here is correct; the real check is whether the builder frame
    # shows up below.
    try:
        clicked = frame.evaluate(CLICK_ROW_JS, matched)
    except Exception:  # noqa: BLE001
        clicked = True
    if clicked is False:
        raise UIError(f'the row for "{matched}" vanished between reading the list '
                      f'and clicking it. Re-run.')

    builder = builder_frame(page, timeout=builder_wait)
    if builder is None:
        raise UIError(
            f'opened "{matched}" but the builder never rendered a publish toggle.\n'
            f'  the row click may not have navigated, or the workflow is still\n'
            f'  loading — raise --settle first. Note that going straight to a\n'
            f'  /automation/builder/<id> URL does NOT create this iframe; the row\n'
            f'  click is the only route in.')
    dismiss_modal(builder)
    return builder, matched


# ── offline self-test ────────────────────────────────────────────────────────

def _self_test() -> int:
    """Fixture-only. No browser, no network, no account touched."""
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((True, name, ""))
        except AssertionError as exc:
            results.append((False, name, str(exc) or "assertion failed"))
        except Exception as exc:  # noqa: BLE001
            results.append((False, name, f"{type(exc).__name__}: {exc}"))

    NAMES = ["WF 1 - Registered", "WF 2 - Did not attend", "WF 3 - Attended",
             "Closing sequence"]

    def t_exact():
        got, how = pick_by_name(NAMES, "Closing sequence")
        assert got == "Closing sequence", got
        assert how == "matched by name", how
    check("exact name match", t_exact)

    def t_case():
        got, _ = pick_by_name(NAMES, "cLoSiNg SeQuEnCe")
        assert got == "Closing sequence", got
    check("name match is case-insensitive", t_case)

    def t_prefix():
        got, how = pick_by_name(NAMES, "WF 3")
        assert got == "WF 3 - Attended", got
        assert "prefix" in how, how
    check("unique prefix match (list names carry a suffix)", t_prefix)

    def t_substring():
        got, how = pick_by_name(NAMES, "Did not")
        assert got == "WF 2 - Did not attend", got
        assert "inside" in how, how
    check("unique substring match", t_substring)

    def t_ambiguous():
        try:
            pick_by_name(NAMES, "WF")
        except UIError as exc:
            assert "3 workflows match" in str(exc), exc
            assert "WF 1 - Registered" in str(exc), exc
            return
        raise AssertionError("guessed between three real workflows")
    check("ambiguous prefix raises and lists the candidates", t_ambiguous)

    def t_missing():
        try:
            pick_by_name(NAMES, "Nope")
        except UIError as exc:
            assert "no workflow matching" in str(exc), exc
            assert "PAGINATES" in str(exc), exc
            return
        raise AssertionError("invented a workflow that is not on the list")
    check("unknown name raises, lists what IS there, warns about pagination",
          t_missing)

    def t_empty():
        try:
            pick_by_name([], "anything")
        except UIError as exc:
            assert "(none)" in str(exc), exc
            return
        raise AssertionError("matched against an empty list")
    check("empty list raises rather than matching nothing", t_empty)

    # The list-view vs builder-view offset bug, as arithmetic.
    def t_coords_builder():
        # Builder view: the iframe fills the page, so frame coords == page coords.
        x, y = center_of({"x": 0, "y": 0}, {"x": 100, "y": 50, "w": 40, "h": 20})
        assert (x, y) == (120.0, 60.0), (x, y)
    check("full-page builder view: rect translates to itself", t_coords_builder)

    def t_coords_list():
        # List view: the iframe is inset. Same rect, different page point — which
        # is why nothing here hardcodes an offset.
        x, y = center_of({"x": 224, "y": 93}, {"x": 100, "y": 50, "w": 40, "h": 20})
        assert (x, y) == (344.0, 153.0), (x, y)
    check("inset list view: rect translates by the queried box", t_coords_list)

    def t_coords_missing_box():
        # bounding_box() returns None on a detached frame; treat it as the origin
        # rather than crashing on a NoneType subscript.
        x, y = center_of({}, {"x": 10, "y": 10, "w": 10, "h": 10})
        assert (x, y) == (15.0, 15.0), (x, y)
    check("missing box degrades to the origin", t_coords_missing_box)

    def t_published():
        assert is_published({"ariaChecked": "true"})
        assert not is_published({"ariaChecked": "false"})
        assert not is_published(None)
        # The whole point: page text is NOT a signal. Nothing here reads it.
        assert not is_published({"text": "Draft"})
    check("is_published reads aria-checked only", t_published)

    def t_js_never_reads_draft_text():
        # A regression guard with teeth: if someone reintroduces an innerText
        # check for 'Draft', this fails. That mistake reports success on a
        # workflow that is still a draft and never runs.
        for js in (TOGGLE_JS, CLICK_TOGGLE_JS, FIND_SAVE_JS, CLICK_SAVE_JS):
            assert "Draft" not in js, js[:80]
        assert "aria-checked" in TOGGLE_JS
    check("no snippet detects publish state from page text", t_js_never_reads_draft_text)

    def t_urls():
        url = workflows_url("https://app.example.com/", "LOCATION_ID")
        assert url.endswith("/v2/location/LOCATION_ID/automation/workflows"
                            "?listTab=all"), url
        assert "//v2" not in url, url
    check("workflows list URL builds correctly", t_urls)

    failed = [r for r in results if not r[0]]
    for ok, name, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail
                                                         else ""))
    print(f"\n  {len(results) - len(failed)}/{len(results)} passed"
          f"   (fixtures only — no browser, no account touched)")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Shared cross-origin iframe plumbing for the GHL workflow "
                    "builder. This is a LIBRARY — publish_workflow.py and "
                    "configure_trigger.py are the tools.",
        epilog="Read the module docstring: it carries the five rules that make "
               "driving these iframes work at all.")
    ap.add_argument("--self-test", action="store_true",
                    help="Run the offline fixture tests and exit. No browser, no "
                         "credentials, no account touched.")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    print(__doc__.strip().splitlines()[0])
    print("\n  this module is imported by publish_workflow.py and "
          "configure_trigger.py.")
    print("  run `python3 ghl_ui.py --self-test` for the offline tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
