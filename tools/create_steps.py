#!/usr/bin/env python3
"""
create_steps.py — create funnel steps (pages) so there is something to inject into.

WHY THIS EXISTS
---------------
`inject_page.py` writes INTO an existing page. It cannot conjure one. A fresh
funnel has one step, so every from-scratch build starts by creating the rest — and
this is the one part of the pipeline with NO API.

> **There is no REST route for creating a funnel step. Every probe 404s.**
> `POST backend/funnels/page` -> 404. `PUT services|backend /funnels/page` ->
> 403 "This route is not yet supported by the IAM Service", for BOTH the PIT and
> the internal JWT. That is a platform-side gate, not a scope problem, and no
> amount of retrying changes it.

So this drives the real UI, in a real logged-in Chrome, the way a human would:

    funnel page -> "Add new step or import" -> fill Name + Path -> "Create funnel step"

That is not a workaround, it is the documented-by-observation path. When a system
resists probing, make it perform the action while you watch — and if there is no
API at all, drive the surface that does exist.

PREREQUISITE — SAME CHROME AS `get_token.py`
----------------------------------------------
Chrome must ALREADY be running with a remote-debugging port open, on a dedicated
profile you have ALREADY logged into GHL by hand:

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --remote-debugging-port=9222 \
      --user-data-dir="$HOME/.ghl-agent-profile"

Use a DEDICATED --user-data-dir: Chrome refuses to open a debug port on a profile
another instance already owns, and the failure is quiet. Verify the port is really
listening before blaming this script:

    curl -s http://127.0.0.1:9222/json/version

DEPENDENCY: Playwright (the only other tool here that is not standard-library).

    pip install playwright     # no `playwright install` — we CONNECT to your Chrome

THE ONE NON-OBVIOUS TECHNIQUE
-------------------------------
The step dialog's inputs are React-controlled. Assigning `el.value = "x"` updates
the DOM and NOT React's internal state, so the field looks filled, the Create
button stays disabled, and nothing explains why. You have to call the NATIVE value
setter and then dispatch `input` + `change` so React observes the change. That is
what `set()` does inside the injected script, and it is the difference between
this working and this silently doing nothing.

Selectors are matched on VISIBLE TEXT rather than class names or ids, because GHL
ships a generated SPA whose class names change between releases while the button
labels do not. If a label changes, update the regexes at the top — they are
deliberately in one place.

IDEMPOTENCY: creating a step whose name already exists produces a SECOND step with
the same name. This tool reads the existing step names first and skips matches;
`--force` opts out of that check.

USAGE
-----
    python3 create_steps.py --funnel-id <id> --step "Registration:registration" \
        --step "Confirmation:confirmation"

    python3 create_steps.py --funnel-id <id> --steps-file steps.json --apply

    # steps.json: [{"name": "Registration", "path": "registration"}, ...]

Nothing is created without `--apply`. The funnel id comes from the builder URL:
    app.gohighlevel.com/v2/location/<locationId>/funnels-websites/funnels/<funnelId>
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

DEFAULT_APP_BASE = "https://app.gohighlevel.com"
DEFAULT_PORT = 9222

# Matched on visible text: GHL's generated class names churn between releases,
# the button labels do not. If a label changes, change it HERE.
ADD_STEP_LABEL = r"add new step|add step|add funnel step"
CREATE_STEP_LABEL = r"create funnel step|create step"

# A funnel path is what lands in the public URL. GHL will accept junk here and you
# find out at launch, so validate before typing.
PATH_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Injected into the page. The native-setter dance is required: a plain
# `el.value = x` updates the DOM without telling React, so the Create button
# stays disabled and nothing says why.
FILL_JS = """(args) => {
    const [name, path] = args;
    const set = (el, v) => {
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, v);
        el.dispatchEvent(new Event('input',  {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    };
    const inputs = [...document.querySelectorAll('input[type=text],input:not([type])')]
        .filter(i => i.offsetParent !== null);
    const label = i => (i.placeholder || i.getAttribute('aria-label') || '');
    const nameEl = inputs.find(i => /name/i.test(label(i)));
    const pathEl = inputs.find(i => /path|url|slug/i.test(label(i)));
    if (!nameEl || !pathEl) return {ok: false, seen: inputs.map(label)};
    set(nameEl, name);
    set(pathEl, path);
    return {ok: true};
}"""

CLICK_JS = """(pattern) => {
    const re = new RegExp(pattern, 'i');
    const el = [...document.querySelectorAll('button,[role=button]')]
        .find(e => re.test(e.innerText || '') && !e.disabled);
    if (!el) return false;
    el.click();
    return true;
}"""

TEXT_JS = "() => document.body.innerText"


def parse_steps(step_args: list, steps_file: str) -> list:
    """Build the step list from --step pairs and/or a JSON file."""
    steps = []
    for item in step_args:
        if ":" not in item:
            raise SystemExit(f"FATAL: --step wants \"Name:path\", got {item!r}.")
        name, _, path = item.partition(":")
        steps.append({"name": name.strip(), "path": path.strip()})

    if steps_file:
        file_path = pathlib.Path(steps_file).expanduser()
        if not file_path.is_file():
            raise SystemExit(f"FATAL: no such --steps-file: {file_path}")
        try:
            doc = json.loads(file_path.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(f"FATAL: {file_path} is not valid JSON: {exc}")
        if not isinstance(doc, list):
            raise SystemExit(f"FATAL: {file_path} must hold a JSON LIST of "
                             f"{{\"name\", \"path\"}} objects.")
        for i, entry in enumerate(doc):
            if not isinstance(entry, dict) or not entry.get("name"):
                raise SystemExit(f"FATAL: {file_path}[{i}] needs a 'name'.")
            steps.append({"name": entry["name"].strip(),
                          "path": (entry.get("path") or "").strip()})

    for step in steps:
        if not step["path"]:
            # Derive a sane path rather than letting GHL invent one — the path is
            # the public URL and a surprise slug is a broken link in an email.
            step["path"] = re.sub(r"[^a-z0-9]+", "-",
                                  step["name"].lower()).strip("-")
        if not PATH_RE.match(step["path"]):
            raise SystemExit(
                f"FATAL: step path {step['path']!r} is not URL-safe. Use lowercase "
                f"letters, digits and hyphens, starting with a letter or digit. "
                f"This string becomes the public page URL.")
    seen = set()
    for step in steps:
        key = step["path"]
        if key in seen:
            raise SystemExit(f"FATAL: duplicate step path {key!r} in your input.")
        seen.add(key)
    return steps


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create GHL funnel steps by driving the funnel builder UI in "
                    "an already-logged-in Chrome. There is no API for this.",
        epilog="Needs the same Chrome setup as get_token.py. Nothing is created "
               "without --apply.")
    ap.add_argument("--funnel-id", required=True,
                    help="Funnel id from the builder URL "
                         ".../funnels-websites/funnels/<THIS>")
    ap.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID"),
                    help="Sub-account id (or $GHL_LOCATION_ID).")
    ap.add_argument("--step", action="append", default=[], metavar="NAME:PATH",
                    help="A step to create, e.g. \"Confirmation:confirmation\". "
                         "Repeatable. PATH may be omitted (\"Name:\") to derive it "
                         "from the name.")
    ap.add_argument("--steps-file",
                    help="JSON list of {\"name\", \"path\"} objects.")
    ap.add_argument("--app-base",
                    default=os.environ.get("GHL_APP_BASE", DEFAULT_APP_BASE),
                    help=f"App host (default {DEFAULT_APP_BASE}, or $GHL_APP_BASE). "
                         f"Change it if your agency uses a white-label domain.")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("GHL_CDP_PORT", DEFAULT_PORT)),
                    help=f"Chrome remote-debugging port (default {DEFAULT_PORT}).")
    ap.add_argument("--apply", action="store_true",
                    help="Actually create the steps. Without this the tool only "
                         "reports what it would do.")
    ap.add_argument("--force", action="store_true",
                    help="Create a step even if one with that name already exists. "
                         "GHL allows duplicates, so this really does duplicate.")
    ap.add_argument("--settle", type=int, default=7,
                    help="Seconds to wait for the funnel page to settle after "
                         "navigation (default 7). The SPA is slow; raising this is "
                         "the first fix for 'could not open the dialog'.")
    args = ap.parse_args()

    if not args.location_id:
        ap.error("no location id. Pass --location-id <id> or set GHL_LOCATION_ID "
                 "(the 20-char id in your GHL URL).")

    steps = parse_steps(args.step, args.steps_file)
    if not steps:
        raise SystemExit(
            "FATAL: no steps given. Pass --step \"Name:path\" (repeatable) or "
            "--steps-file <file>. This tool never invents steps.")

    funnel_url = (f"{args.app_base.rstrip('/')}/v2/location/{args.location_id}"
                  f"/funnels-websites/funnels/{args.funnel_id}")

    print(f"  funnel: {funnel_url}")
    for step in steps:
        print(f"    + {step['name']}  ->  /{step['path']}")

    if not args.apply:
        print("\n  (report only — pass --apply to create these in the UI)")
        return 0

    # Imported late, deliberately: `--help` must work on a machine that has never
    # installed Playwright.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FATAL: Playwright is not installed.\n"
              "  fix: pip install playwright\n"
              "  (no `playwright install` needed — this connects to YOUR Chrome)",
              file=sys.stderr)
        return 1

    cdp = f"http://127.0.0.1:{args.port}"
    created, skipped, failed = [], [], []

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(cdp)
        except Exception as exc:  # noqa: BLE001
            print(f"FATAL: cannot attach to Chrome at {cdp}\n"
                  f"  {type(exc).__name__}: {exc}\n"
                  f"  checklist:\n"
                  f"    1. Is Chrome running with --remote-debugging-port={args.port}?\n"
                  f"    2. Did you give it a DEDICATED --user-data-dir?\n"
                  f"    3. Does `curl -s {cdp}/json/version` return JSON? If not,\n"
                  f"       the browser never opened the port — a Chrome problem.",
                  file=sys.stderr)
            return 1

        if not browser.contexts:
            print("FATAL: attached, but Chrome has no browser context. Open a tab "
                  "and try again.", file=sys.stderr)
            return 1
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def load_funnel() -> str:
            page.goto(funnel_url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(args.settle * 1_000)
            return page.evaluate(TEXT_JS) or ""

        existing_text = load_funnel()
        if "funnel" not in existing_text.lower():
            print("FATAL: the funnel page did not render anything recognisable.\n"
                  "  Most likely that Chrome profile is not logged in to GHL, or\n"
                  "  the funnel id belongs to a different location. Bring the\n"
                  "  window to the front and check what is on screen.",
                  file=sys.stderr)
            return 1

        for step in steps:
            name, path = step["name"], step["path"]
            if not args.force and re.search(re.escape(name), existing_text,
                                            re.IGNORECASE):
                print(f"    ·  exists  {name} — skipping (--force to duplicate)")
                skipped.append(name)
                continue

            if not page.evaluate(CLICK_JS, ADD_STEP_LABEL):
                print(f"    !  {name}: could not find the add-step control. The "
                      f"button label may have changed — see ADD_STEP_LABEL.",
                      file=sys.stderr)
                failed.append(name)
                existing_text = load_funnel()
                continue
            page.wait_for_timeout(2_500)

            filled = page.evaluate(FILL_JS, [name, path])
            if not filled.get("ok"):
                print(f"    !  {name}: could not find the Name/Path inputs. "
                      f"Visible input labels were: {filled.get('seen')}",
                      file=sys.stderr)
                failed.append(name)
                existing_text = load_funnel()
                continue
            page.wait_for_timeout(1_500)

            if not page.evaluate(CLICK_JS, CREATE_STEP_LABEL):
                print(f"    !  {name}: the create button never enabled. That "
                      f"usually means React did not see the typed values — see "
                      f"the native-setter note in this file's docstring.",
                      file=sys.stderr)
                failed.append(name)
                existing_text = load_funnel()
                continue
            page.wait_for_timeout(6_000)

            # VERIFY, do not assume. A click that lands is not a step that exists;
            # re-read the funnel and look for the name.
            existing_text = load_funnel()
            if re.search(re.escape(name), existing_text, re.IGNORECASE):
                print(f"    ok created {name}  (/{path})")
                created.append(name)
            else:
                print(f"    !  {name}: clicked create, but the step is not on the "
                      f"funnel afterwards. Do not report this as done.",
                      file=sys.stderr)
                failed.append(name)

    print(f"\n  created {len(created)} · skipped {len(skipped)} · "
          f"failed {len(failed)}")
    if failed:
        print(f"  FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    if created:
        print("  next: open each new step in the builder to read its pageId from "
              "the URL (.../pages/<pageId>/edit) — inject_page.py needs it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
