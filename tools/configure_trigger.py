#!/usr/bin/env python3
"""
configure_trigger.py — attach a trigger to a workflow. There is no API.

WHY THIS EXISTS
---------------
`deploy_workflow.py` builds the whole body of a workflow through the internal API
and then stops, because attaching a TRIGGER has no endpoint on either API. The
`trigger` field in a build spec is a note to a human; nothing consumes it.

> A workflow with no trigger has no way in. Every step is correct, every email
> exists, and not one contact will ever enter it. Nothing in the UI flags this.

That is the last gap between "an agent built the campaign" and "the campaign runs",
and it used to be closed by handing the work back to a person. It does not have to
be. The builder is drivable and this drives it.

THE THREE DETAILS THAT COST HOURS
----------------------------------
1. THE PICKER RENDERS BELOW THE FOLD. The trigger list opens past the bottom of the
   viewport, so a coordinate click lands on whatever is on screen at that point —
   usually nothing at all, silently. A DISPATCHED MouseEvent fires on the element
   wherever it is. That is why every click in the picker goes through
   `dispatch_click` and never through the mouse.

2. THE FIRST-VIEW MODAL BLOCKS EVERYTHING. The AI-builder modal opens the first time
   any workflow is opened and eats every click underneath it. Dismiss it ("Got it")
   before anything else or the rest of the run no-ops while appearing to work.
   `ghl_ui.open_workflow` does this on the way in.

3. FRAME REFERENCES DIE ON NAVIGATION. Opening the trigger panel re-renders the Vue
   app; the handle you were holding throws on the next call. Re-acquire after every
   navigating click — this tool does, and the polling is why it looks slow.

WHAT IS SOLID HERE AND WHAT IS BRITTLE
---------------------------------------
Attaching the trigger itself — open the workflow, click "Add New Trigger", pick the
type by its visible label, save — is the verified path.

FILTERS ARE THE BRITTLE PART. The filter row is a pair of framework-generated
select widgets with no stable ids, located by position in the right-hand panel. If
that layout shifts, this stops finding them. So: when a filter step fails, this tool
SAVES NOTHING and says so, leaving the panel open for you to finish by hand. A
half-configured trigger saved is worse than no trigger, because it looks done.

PREREQUISITE — SAME CHROME AS `get_token.py`
----------------------------------------------
Chrome already running with a remote-debugging port, on a dedicated profile you have
already logged into GHL by hand. Full setup, and why the stealth flag matters, in
`ghl_ui.py` and `knowledge/getting-the-token.md`.

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --remote-debugging-port=9222 \
      --user-data-dir="$HOME/.ghl-agent-profile" \
      --disable-blink-features=AutomationControlled

DEPENDENCY: Playwright, imported LAZILY so `--help` works without it.

    pip install playwright     # no `playwright install` — we CONNECT to your Chrome

USAGE
-----
    python3 configure_trigger.py --workflow "WF 1" --trigger "Form Submitted"
    python3 configure_trigger.py --workflow "WF 1" --trigger "Form Submitted" --apply
    python3 configure_trigger.py --workflow "WF 2" --trigger "Contact Tag" \
        --filter "Tag is:did-not-attend" --apply

`--trigger` is the label EXACTLY as the picker shows it. This tool never guesses a
trigger type: the wrong trigger on a live workflow puts the wrong contacts into a
sequence, which is not a mistake you can take back.

Nothing is changed without `--apply`. A dry run opens the workflow, reports the
trigger nodes already on the canvas, and stops.

AFTERWARDS: the workflow is still a DRAFT. Run `publish_workflow.py`.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import ghl_ids  # noqa: E402  (sibling modules; the path fix above must run first)
import ghl_ui   # noqa: E402

ADD_TRIGGER_LABEL = "Add New Trigger"
ADD_FILTERS_LABEL = "Add filters"

# Waits, tuned against a real account. Shortening them is the first way to make this
# flaky: each one covers a Vue re-render, not a network call.
AFTER_CLICK_MS = 2_000
AFTER_PANEL_MS = 2_500
AFTER_SAVE_MS = 3_000

# Canvas nodes. Reading them is how the trigger is verified afterwards, and how an
# existing trigger is detected before anything is touched.
NODES_JS = """() => [...document.querySelectorAll('.vue-flow__node')].map(n => {
    const r = n.getBoundingClientRect();
    return {text: (n.innerText || '').trim(),
            x: r.x, y: r.y, w: r.width, h: r.height};
})"""

CLICK_NODE_JS = """(needle) => {
    for (const n of document.querySelectorAll('.vue-flow__node')) {
        if ((n.innerText || '').includes(needle)) {
            const r = n.getBoundingClientRect();
            n.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            return {x: r.x, y: r.y, w: r.width, h: r.height};
        }
    }
    return null;
}"""

# The trigger panel's own save. Matched case-insensitively on a CONTAINS, because
# unlike the picker items this label is a button whose exact casing has not been
# pinned down, and an exact match that misses fails silently-looking: the panel
# stays open and the trigger is never attached.
CLICK_SAVE_TRIGGER_JS = """() => {
    for (const b of document.querySelectorAll('button')) {
        if ((b.innerText || '').trim().toLowerCase().includes('save trigger')) {
            const r = b.getBoundingClientRect();
            b.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            return {x: r.x, y: r.y, w: r.width, h: r.height};
        }
    }
    return null;
}"""

# The filter widgets. No stable ids — they are generated select components, found by
# living in the right-hand panel. `side` is a FRACTION of the frame width, not a
# pixel offset: the panel moves with the window and a hardcoded x stops working the
# first time someone resizes. Index 0 is the filter TYPE select; -1 is the value
# select, which only exists once a type has been chosen.
CLICK_SELECT_AT_JS = """(args) => {
    const [side, index] = args;
    const cut = document.documentElement.clientWidth * side;
    const all = [...document.querySelectorAll(
                     '[class*="n-base-selection"],[class*="n-select"]')]
        .filter(el => {
            const r = el.getBoundingClientRect();
            return r.x > cut && r.width > 60;
        })
        .sort((a, b) => a.getBoundingClientRect().y - b.getBoundingClientRect().y);
    const el = all.at(index);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
    return {x: r.x, y: r.y, w: r.width, h: r.height};
}"""

# Which side of the frame the config panel is on, as a fraction of frame width.
PANEL_SIDE = 0.4


def parse_filters(filter_args: list) -> list:
    """Build the filter list from --filter "Key:Value" pairs."""
    filters = []
    for item in filter_args:
        if ":" not in item:
            raise SystemExit(
                f"FATAL: --filter wants \"Key:Value\" — the filter type exactly as "
                f"the dropdown labels it, then the value to pick. Got {item!r}.\n"
                f"  example: --filter \"Form is:Registration\"")
        key, _, value = item.partition(":")
        key, value = key.strip(), value.strip()
        if not key or not value:
            raise SystemExit(f"FATAL: --filter {item!r} has an empty side. Both the "
                             f"type and the value are required.")
        filters.append({"key": key, "value": value})
    return filters


def existing_triggers(frame) -> list:
    """Canvas node labels that are not the empty 'Add New Trigger' placeholder."""
    try:
        nodes = frame.evaluate(NODES_JS) or []
    except Exception as exc:  # noqa: BLE001
        raise ghl_ui.UIError(f"could not read the workflow canvas: "
                             f"{type(exc).__name__}: {exc}")
    return [n["text"] for n in nodes
            if n.get("text") and ADD_TRIGGER_LABEL not in n["text"]]


def click_label(frame, label: str, what: str):
    """Click a control by its visible label, from inside the frame.

    Never via the mouse. Half of these render below the fold, where a coordinate
    click lands on empty screen and reports success.
    """
    rect = ghl_ui.dispatch_click(frame, ghl_ui.CLICK_EXACT_TEXT_JS, label)
    if rect is None:
        raise ghl_ui.UIError(
            f'{what}: nothing on screen is labelled exactly "{label}".\n'
            f'  the match is exact on visible text — check the label in the UI, '
            f'including capitalisation.')
    return rect


def click_node(frame, needle: str, what: str):
    """Click a canvas node by the text it contains.

    Nodes are matched as `.vue-flow__node` containing the text rather than by exact
    label, because the node carries its own chrome (icons, hint lines) around the
    words you can see.
    """
    rect = ghl_ui.dispatch_click(frame, CLICK_NODE_JS, needle)
    if rect is None:
        raise ghl_ui.UIError(
            f'{what}: no canvas node contains "{needle}".\n'
            f'  either the canvas has not finished rendering — raise --settle — or\n'
            f'  this workflow already has a trigger and offers no empty\n'
            f'  "{ADD_TRIGGER_LABEL}" slot. Adding a SECOND trigger alongside an\n'
            f'  existing one is not automated; do that by hand. Nothing changed.')
    return rect


def apply_filter(page, frame, index: int, key: str, value: str) -> None:
    """Add one filter row: open the type select, pick the type, pick the value.

    THE BRITTLE PART. The widgets have no ids; they are found by sitting in the
    right-hand panel. Every failure here raises rather than pressing on, because a
    trigger saved with a half-built filter fires for the wrong contacts.
    """
    click_label(frame, ADD_FILTERS_LABEL, f"filter {index + 1}")
    page.wait_for_timeout(AFTER_CLICK_MS)

    # The type select is the first one in the panel; the value select appears below
    # it only after a type is chosen, which is why it is read as "the last one".
    if ghl_ui.dispatch_click(frame, CLICK_SELECT_AT_JS, [PANEL_SIDE, 0]) is None:
        raise ghl_ui.UIError(
            f'filter {index + 1} ("{key}"): no select widget in the config panel. '
            f'The panel layout has changed — see CLICK_SELECT_AT_JS. Nothing was '
            f'saved.')
    page.wait_for_timeout(AFTER_CLICK_MS)

    click_label(frame, key, f'filter {index + 1} type "{key}"')
    page.wait_for_timeout(AFTER_CLICK_MS)

    if ghl_ui.dispatch_click(frame, CLICK_SELECT_AT_JS, [PANEL_SIDE, -1]) is None:
        raise ghl_ui.UIError(
            f'filter {index + 1} ("{key}"): the value select never appeared after '
            f'choosing the type. Nothing was saved.')
    page.wait_for_timeout(AFTER_CLICK_MS)

    click_label(frame, value, f'filter {index + 1} value "{value}"')
    page.wait_for_timeout(AFTER_CLICK_MS)
    print(f"    ·  filter  {key} -> {value}")


def configure(page, url: str, name: str, trigger: str, filters: list,
              apply: bool, settle: int, force: bool) -> str:
    """Attach one trigger. Returns 'configured' | 'exists' | 'would-configure'."""
    frame, matched = ghl_ui.open_workflow(page, url, name, settle=settle)

    already = existing_triggers(frame)
    if already:
        print(f"    ·  canvas already has: {', '.join(repr(t) for t in already)}")
    # Heuristic, and deliberately conservative: if the label already appears on the
    # canvas, adding it again would give the workflow two ways in and double every
    # contact's journey. --force opts out.
    if any(trigger.casefold() in text.casefold() for text in already) and not force:
        print(f"    ·  \"{trigger}\" is already on this workflow — skipping "
              f"(--force to add a second one)")
        return "exists"

    if not apply:
        print(f"    ·  would add trigger \"{trigger}\"" +
              (f" with {len(filters)} filter(s)" if filters else "") +
              "  (pass --apply)")
        return "would-configure"

    click_node(frame, ADD_TRIGGER_LABEL, "add-trigger node")
    page.wait_for_timeout(AFTER_PANEL_MS)

    # The panel re-renders the app; the handle above is dead from here.
    frame = ghl_ui.builder_frame(page, timeout=15) or frame

    click_label(frame, trigger, f'trigger type "{trigger}"')
    page.wait_for_timeout(AFTER_PANEL_MS)
    frame = ghl_ui.builder_frame(page, timeout=15) or frame

    for i, flt in enumerate(filters):
        apply_filter(page, frame, i, flt["key"], flt["value"])
        frame = ghl_ui.builder_frame(page, timeout=15) or frame

    if ghl_ui.dispatch_click(frame, CLICK_SAVE_TRIGGER_JS) is None:
        raise ghl_ui.UIError(
            f'"{matched}": no "Save Trigger" button in the panel, so the trigger '
            f'was never attached. It is usually disabled until every required field '
            f'is filled — check the panel in the browser. Nothing was saved.')
    page.wait_for_timeout(AFTER_SAVE_MS)
    frame = ghl_ui.builder_frame(page, timeout=15) or frame

    # The trigger panel saves the trigger; the workflow itself can still be holding
    # an unsaved change. Clicking Save when there is nothing to save is a no-op —
    # the button reads "Saved" and is disabled, and this finder skips it.
    if ghl_ui.dispatch_click(frame, ghl_ui.CLICK_SAVE_JS) is not None:
        page.wait_for_timeout(AFTER_SAVE_MS)
        frame = ghl_ui.builder_frame(page, timeout=15) or frame

    # VERIFY. A click that lands is not a trigger that exists.
    now = existing_triggers(frame)
    if not any(trigger.casefold() in text.casefold() for text in now):
        raise ghl_ui.UIError(
            f'"{matched}": clicked through the trigger picker, but "{trigger}" is '
            f'not on the canvas afterwards. Canvas nodes: '
            f'{now or "(none)"}. Do not report this as configured.')

    print(f"    ok trigger \"{trigger}\" on {matched}")
    return "configured"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Attach a trigger to a GHL workflow by driving the builder UI "
                    "in an already-logged-in Chrome. There is no API for this.",
        epilog="Needs the same Chrome setup as get_token.py. Nothing is changed "
               "without --apply. The workflow is still a DRAFT afterwards — run "
               "publish_workflow.py.")
    ap.add_argument("--workflow", metavar="NAME",
                    help="Workflow NAME as the list shows it. Matched exact, then "
                         "unique prefix, then unique substring; several matches is "
                         "an error that lists them.")
    ap.add_argument("--trigger", metavar="TYPE",
                    help="Trigger type EXACTLY as the picker labels it, e.g. "
                         "\"Form Submitted\". Never guessed: the wrong trigger puts "
                         "the wrong contacts into a live sequence.")
    ap.add_argument("--filter", action="append", default=[], metavar="KEY:VALUE",
                    help="A trigger filter, e.g. \"Form is:Registration\". "
                         "Repeatable. Both sides are matched on the visible label. "
                         "This is the brittle part — on failure nothing is saved.")
    ap.add_argument("--location-id",
                    help="Sub-account id (or $GHL_LOCATION_ID, or .env).")
    ap.add_argument("--env-file", default=".env",
                    help="Where to read GHL_LOCATION_ID (default .env).")
    ap.add_argument("--app-base",
                    default=os.environ.get("GHL_APP_BASE",
                                           ghl_ui.DEFAULT_APP_BASE),
                    help=f"App host (default {ghl_ui.DEFAULT_APP_BASE}, or "
                         f"$GHL_APP_BASE). Change it for a white-label domain.")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("GHL_CDP_PORT",
                                               ghl_ui.DEFAULT_PORT)),
                    help=f"Chrome remote-debugging port (default "
                         f"{ghl_ui.DEFAULT_PORT}).")
    ap.add_argument("--apply", action="store_true",
                    help="Actually attach the trigger. Without this the tool opens "
                         "the workflow and reports what is on the canvas.")
    ap.add_argument("--dry-run", action="store_true",
                    help="The default. Accept it explicitly so a script can say "
                         "what it means; it is an error together with --apply.")
    ap.add_argument("--force", action="store_true",
                    help="Add the trigger even if the canvas already shows one with "
                         "that label. Two triggers means two ways in, and every "
                         "contact runs the workflow twice.")
    ap.add_argument("--settle", type=int, default=8,
                    help="Seconds to wait for the workflows list to settle after "
                         "loading (default 8). Raise it first when the builder "
                         "never renders.")
    args = ap.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("FATAL: --apply and --dry-run mean opposite things. Pass "
                         "one.")
    if not args.workflow:
        raise SystemExit(
            "FATAL: no workflow given. Pass --workflow \"<name>\".\n"
            "  This tool never picks a workflow for you.")
    if not args.trigger:
        raise SystemExit(
            "FATAL: no --trigger given. Pass the trigger type exactly as the picker "
            "labels it, e.g. --trigger \"Form Submitted\".\n"
            "  A trigger type is a decision, not a lookup — this tool will not "
            "invent one.")

    filters = parse_filters(args.filter)

    try:
        location_id = ghl_ids.location_id(args.location_id, args.env_file)
    except ghl_ids.ResolveError as exc:
        raise SystemExit(f"FATAL: {exc}")

    url = ghl_ui.workflows_url(args.app_base, location_id)
    print(f"  location {location_id}")
    print(f"  list     {url}")
    print(f"  trigger  \"{args.trigger}\"" +
          (f"  + {len(filters)} filter(s)" if filters else ""))
    if not args.apply:
        print("  (dry run — reading the canvas only, nothing will be changed)")

    try:
        with ghl_ui.chrome(args.port) as page:
            if ghl_ui.webdriver_flagged(page):
                print("  warn: navigator.webdriver is true in this browser. The "
                      "builder iframes may never load — see ghl_ui.py.",
                      file=sys.stderr)
            status = configure(page, url, args.workflow, args.trigger, filters,
                               args.apply, args.settle, args.force)
    except ghl_ui.UIError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1

    if status == "configured":
        print("\n  next: the workflow is still a DRAFT and will not run. "
              "publish_workflow.py --workflow \"<name>\" --apply --verify")
    elif status == "would-configure":
        print("\n  (nothing was changed — pass --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
