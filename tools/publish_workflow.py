#!/usr/bin/env python3
"""
publish_workflow.py — flip a workflow from Draft to Published. There is no API.

WHY THIS EXISTS
---------------
`deploy_workflow.py` creates a workflow and installs its steps through the internal
API, and then stops — because publishing has NO endpoint, on either API:

> A workflow deploys in **Draft**. A draft workflow is inert: the trigger never
> fires, no contact ever enters it, and nothing anywhere says so. Everything the
> build did is real and does nothing.

So the last step of a fully automated build used to be "now go and click a toggle in
the browser, 19 times". That is the exact handoff this repo exists to delete. The
toggle is drivable, it has been driven, and this is the tool that drives it.

THE TWO DETAILS THAT COST HOURS
--------------------------------
1. READ THE STATE FROM `aria-checked`, NEVER FROM PAGE TEXT.
   `body.innerText.includes('Draft')` returns TRUE on a workflow that is already
   published — the word survives elsewhere in the builder chrome (save-state
   labels, version history). A tool that believes it reports "still draft" forever,
   or worse, reports success at random. The toggle is `[role="switch"]`;
   `aria-checked="true"` means Published and nothing else does.

2. THE TOGGLE ALONE PERSISTS NOTHING.
   Flipping it sets local Vue state. Navigate away without clicking Save and the
   workflow is a draft again, with no error and no warning — the UI looked right
   the whole time. This tool refuses to report success if it cannot find and click
   Save.

And one structural rule: ONE PAGE LOAD PER WORKFLOW. Walking the paginated list in
place loses frame references and starts throwing on the second row. Reloading the
list for every workflow is slower and it is the thing that works.

VERIFY, DO NOT TRUST THE CLICK. After Save, the state is re-read from a re-acquired
frame. `--verify` goes further and re-opens the workflow from a fresh list load,
which is the only thing that proves Save actually persisted rather than the Vue
state still being warm.

PREREQUISITE — SAME CHROME AS `get_token.py`
----------------------------------------------
Chrome already running with a remote-debugging port, on a dedicated profile you have
already logged into GHL by hand. Full setup, and why the stealth flag matters, in
`ghl_ui.py` and in `knowledge/getting-the-token.md`.

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --remote-debugging-port=9222 \
      --user-data-dir="$HOME/.ghl-agent-profile" \
      --disable-blink-features=AutomationControlled

DEPENDENCY: Playwright, imported LAZILY so `--help` works without it.

    pip install playwright     # no `playwright install` — we CONNECT to your Chrome

USAGE
-----
    python3 publish_workflow.py --workflow "WF 1"                 # dry run (default)
    python3 publish_workflow.py --workflow "WF 1" --apply
    python3 publish_workflow.py --workflow "WF 1" --workflow "WF 2" --apply
    python3 publish_workflow.py --all                             # what is still draft?
    python3 publish_workflow.py --all --apply --verify            # publish every draft

Nothing is toggled without `--apply`. A dry run opens each workflow read-only and
reports its `aria-checked` state, which doubles as "which of these 19 are live?".

Names are matched the way `ghl_ids.py` matches a funnel: exact, then a unique
prefix, then a unique substring, and several matches is an error listing them.
`--workflow-id` is accepted for symmetry with the rest of the repo, but see its help
text — the list rows carry no id, so it is resolved against the row markup and a
NAME is the reliable path.
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

# How long to sit on each state change. The builder is slow and every one of these
# was tuned against a real account; shortening them is the first way to make this
# flaky.
AFTER_TOGGLE_MS = 1_500
AFTER_SAVE_MS = 2_500

# Row markup search for --workflow-id. Rows are Vue Router anchors with no href, so
# this looks for the id anywhere in the row's attributes and is best-effort.
ROW_BY_ID_JS = """(wfid) => {
    const first = a => ((a.innerText || '').trim().split('\\n')[0] || '').trim();
    for (const a of document.querySelectorAll('a')) {
        const row = a.closest('tr,[role="row"]') || a;
        if ((row.outerHTML || '').includes(wfid)) return first(a);
    }
    return null;
}"""


def publish_one(page, url: str, name: str, apply: bool, settle: int,
                verify: bool) -> str:
    """Open one workflow and publish it. Returns a status word.

    'published' | 'already' | 'draft' (dry run only) | raises UIError.
    """
    frame, matched = ghl_ui.open_workflow(page, url, name, settle=settle)

    state = ghl_ui.read_toggle(frame)
    if state is None:
        raise ghl_ui.UIError(
            f'"{matched}": no [role="switch"] in the builder. The action bar did '
            f'not render — raise --settle.')

    if ghl_ui.is_published(state):
        print(f"    ·  already published  {matched}")
        return "already"

    if not apply:
        print(f"    ·  DRAFT  {matched}  (would publish — pass --apply)")
        return "draft"

    # Dispatch first: it fires inside the frame and needs no coordinates. The mouse
    # fallback exists because some Vue controls only answer a trusted event, and it
    # translates through the iframe's queried box rather than any fixed offset.
    ghl_ui.dispatch_click(frame, ghl_ui.CLICK_TOGGLE_JS)
    page.wait_for_timeout(AFTER_TOGGLE_MS)

    frame = ghl_ui.builder_frame(page, timeout=15) or frame
    state = ghl_ui.read_toggle(frame)
    if not ghl_ui.is_published(state):
        rect = state or {}
        if rect.get("w"):
            ghl_ui.mouse_click(page, frame, rect)
            page.wait_for_timeout(AFTER_TOGGLE_MS)
            frame = ghl_ui.builder_frame(page, timeout=15) or frame
            state = ghl_ui.read_toggle(frame)

    if not ghl_ui.is_published(state):
        raise ghl_ui.UIError(
            f'"{matched}": the toggle did not flip (aria-checked is still '
            f'{(state or {}).get("ariaChecked")!r}). Nothing was saved. A modal may '
            f'be covering the action bar — bring the window to the front and look.')

    # THE STEP EVERYONE FORGETS. Without this the flip is local Vue state and dies
    # on the next navigation, silently.
    save_rect = ghl_ui.dispatch_click(frame, ghl_ui.CLICK_SAVE_JS)
    if save_rect is None:
        raise ghl_ui.UIError(
            f'"{matched}": the toggle flipped but there is no enabled Save button, '
            f'so nothing will persist. Do NOT report this as published — reload the '
            f'workflow and check what state it is really in.')
    page.wait_for_timeout(AFTER_SAVE_MS)

    frame = ghl_ui.builder_frame(page, timeout=15) or frame
    state = ghl_ui.read_toggle(frame)
    if not ghl_ui.is_published(state):
        raise ghl_ui.UIError(
            f'"{matched}": saved, but aria-checked went back to '
            f'{(state or {}).get("ariaChecked")!r}. The save was rejected.')

    if verify:
        # The only real proof. A warm Vue state reads 'true' whether or not the save
        # landed; a fresh load reads what the server actually stored.
        frame, _ = ghl_ui.open_workflow(page, url, matched, settle=settle)
        state = ghl_ui.read_toggle(frame)
        if not ghl_ui.is_published(state):
            raise ghl_ui.UIError(
                f'"{matched}": looked published, but after a fresh load '
                f'aria-checked is {(state or {}).get("ariaChecked")!r}. The save did '
                f'not persist.')
        print(f"    ok published  {matched}  (verified on a fresh load)")
    else:
        print(f"    ok published  {matched}")
    return "published"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Publish GHL workflows (Draft -> Published) by driving the "
                    "builder UI in an already-logged-in Chrome. There is no API "
                    "for this.",
        epilog="Needs the same Chrome setup as get_token.py. Nothing is toggled "
               "without --apply. Publish AFTER the trigger is set — see "
               "configure_trigger.py; a published workflow with no trigger is "
               "still inert.")
    ap.add_argument("--workflow", action="append", default=[], metavar="NAME",
                    help="Workflow NAME as the list shows it. Repeatable. Matched "
                         "exact, then unique prefix, then unique substring; several "
                         "matches is an error that lists them.")
    ap.add_argument("--workflow-id", action="append", default=[], metavar="ID",
                    help="Workflow id. Repeatable. Best effort: list rows are Vue "
                         "Router anchors with no href, so the id is searched for in "
                         "the row markup and the row's NAME is what gets clicked. "
                         "If it is not found, pass --workflow instead.")
    ap.add_argument("--all", action="store_true",
                    help="Every workflow on the list. Already-published ones are "
                         "skipped, so this publishes exactly the drafts.")
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
                    help="Actually flip the toggle and save. Without this the tool "
                         "opens each workflow read-only and reports its state.")
    ap.add_argument("--dry-run", action="store_true",
                    help="The default. Accept it explicitly so a script can say "
                         "what it means; it is an error together with --apply.")
    ap.add_argument("--verify", action="store_true",
                    help="After saving, re-open the workflow from a fresh list load "
                         "and re-read aria-checked. Doubles the page loads and is "
                         "the only thing that proves the save persisted.")
    ap.add_argument("--settle", type=int, default=8,
                    help="Seconds to wait for the workflows list to settle after "
                         "each load (default 8). The SPA is slow; raising this is "
                         "the first fix for 'the builder never rendered'.")
    args = ap.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("FATAL: --apply and --dry-run mean opposite things. Pass "
                         "one.")
    if args.all and (args.workflow or args.workflow_id):
        raise SystemExit("FATAL: --all means every workflow on the list; naming one "
                         "as well contradicts it. Pass --all OR --workflow.")
    if not args.all and not args.workflow and not args.workflow_id:
        raise SystemExit(
            "FATAL: no workflow given. Pass --workflow \"<name>\" (repeatable), "
            "--workflow-id <id>, or --all.\n"
            "  This tool never picks a workflow for you — publishing the wrong one "
            "puts a live automation in front of real contacts.")

    try:
        location_id = ghl_ids.location_id(args.location_id, args.env_file)
    except ghl_ids.ResolveError as exc:
        raise SystemExit(f"FATAL: {exc}")

    url = ghl_ui.workflows_url(args.app_base, location_id)
    print(f"  location {location_id}")
    print(f"  list     {url}")
    if not args.apply:
        print("  (dry run — reading state only, nothing will be toggled)")

    counts = {"published": 0, "already": 0, "draft": 0}
    failed = []

    try:
        with ghl_ui.chrome(args.port) as page:
            if ghl_ui.webdriver_flagged(page):
                print("  warn: navigator.webdriver is true in this browser. The "
                      "builder iframes may never load — see ghl_ui.py.",
                      file=sys.stderr)

            targets = list(args.workflow)

            # Ids first: resolve each to the row NAME, then treat it like any name.
            if args.workflow_id:
                frame = ghl_ui.open_list(page, url, args.settle)
                for wfid in args.workflow_id:
                    name = frame.evaluate(ROW_BY_ID_JS, wfid)
                    if not name:
                        print(f"    !  no list row carries the id {wfid}. Rows have "
                              f"no href, so ids are not always in the markup — pass "
                              f"--workflow \"<name>\".", file=sys.stderr)
                        failed.append(wfid)
                        continue
                    print(f"  resolved id {wfid} -> \"{name}\"")
                    targets.append(name)

            if args.all:
                frame = ghl_ui.open_list(page, url, args.settle)
                targets = ghl_ui.list_names(frame)
                if not targets:
                    raise ghl_ui.UIError(
                        "the list rendered no workflow rows. Either the location "
                        "has none, or the list markup changed — see LIST_NAMES_JS "
                        "in ghl_ui.py.")
                print(f"  {len(targets)} workflow(s) on the list:")
                for name in targets:
                    print(f'    "{name}"')

            for name in targets:
                # One FRESH page load per workflow. Iterating the list in place
                # loses the frame reference and fails on the second row.
                try:
                    status = publish_one(page, url, name, args.apply, args.settle,
                                         args.verify)
                    counts[status] = counts.get(status, 0) + 1
                except ghl_ui.UIError as exc:
                    print(f"    !  {exc}", file=sys.stderr)
                    failed.append(name)
    except ghl_ui.UIError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1

    if args.apply:
        print(f"\n  published {counts['published']} · already live "
              f"{counts['already']} · failed {len(failed)}")
        if counts["published"] and not args.verify:
            print("  next: re-run with --verify to prove the save persisted, or "
                  "reload one workflow and check the toggle by eye.")
    else:
        print(f"\n  draft {counts['draft']} · already live {counts['already']} · "
              f"unreadable {len(failed)}")
        print("  (nothing was toggled — pass --apply)")
    if failed:
        print(f"  FAILED: {', '.join(str(f) for f in failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
