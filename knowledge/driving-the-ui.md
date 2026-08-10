# Driving the UI — you can click the page

**You have a browser. You can open it, you can navigate it, you can click things in
it. That is a normal way to do work on this platform, not a last resort and not an
escalation to a human.**

Read that again, because the sentence this file exists to replace is "this is UI-only"
— and at least one agent read that as a wall and handed the job back. It is not a wall.
It is a different interface with a different set of rules, and every one of those rules
is written down below.

Parts of GoHighLevel have no API at all. Not an undocumented API, not a hard one —
none. Attaching a trigger to a workflow, flipping a workflow from Draft to Published,
creating a funnel, editing the fields inside a form. For those, the browser *is* the
API. The application does the work over HTTP the same as anything else; you are just
driving the client that knows how to make those calls, instead of making them yourself.

The reason this needs a page of its own is not that clicking is hard. It is that GHL's
builder UIs are cross-origin iframes with Vue Router underneath, and almost every
instinct you have about `page.click()` is wrong inside one. Nothing below is guessable.
All of it was paid for.

---

## What actually needs the UI

| task | route |
|---|---|
| workflow **triggers** | **UI only** — no endpoint exists |
| workflow **publish** (Draft → Published) | **UI only** |
| **creating a funnel** (the funnel object itself) | **UI only** — steps and pages have APIs |
| **form field editing** (add/remove/reword fields) | **UI only**, via the form-builder iframe |
| **memberships / courses** | UI, different vendor, different auth — see [`known-unknowns.md`](known-unknowns.md) |
| workflow create / steps / actions | API — [`workflows.md`](workflows.md) |
| funnel **steps** and **pages** | API — [`funnel-pages.md`](funnel-pages.md) |
| email templates, custom values, contacts | API — [`email-templates.md`](email-templates.md), [`custom-values.md`](custom-values.md) |

Rule of thumb: **do it over the API if an API exists**, because API writes are readable
back and verifiable. Reach for the browser for the rows marked UI only. Do not reach for
the browser because an API call was awkward.

---

## Setup

### The profile is the asset

The one thing you need is a Chrome profile that is already logged in, running with a
remote debugging port. **If you followed [`getting-the-token.md`](getting-the-token.md)
you already have exactly that** — same profile, same port, same window. Token capture
and UI driving are the same browser. Do not build a second one.

If it is not running, start it the same way that page tells you to:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.ghl-agent-profile" \
  --no-first-run --no-default-browser-check \
  "https://app.gohighlevel.com/" >/dev/null 2>&1 &
```

A dedicated `--user-data-dir` is not optional — Chrome silently refuses to open a
debugging port on a profile another instance already owns. Verify before you build on
it: `curl -s http://127.0.0.1:9222/json/version`.

A human is needed for exactly one thing, exactly once: the first login. After that the
profile stays authenticated indefinitely and you are on your own.

### Two ways to drive it

**Attach to the running Chrome.** Nothing to authenticate, nothing to smuggle:

```python
browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
context = browser.contexts[0]
page = context.pages[0]
```

**Or launch your own browser with the session handed to it.** This is the path that was
used in production for bulk runs, and it has two requirements that look like
superstition and are not:

```python
browser = await playwright.chromium.launch(
    headless=False,
    ignore_default_args=["--enable-automation"],
    args=["--disable-blink-features=AutomationControlled"],
)
context = await browser.new_context(storage_state="ghl-auth-state.json")
```

- **The two stealth flags are required for the builder iframes to load at all.** Without
  them the page renders, the shell appears, and the cross-origin iframe never arrives.
  You will read that as a slow network and wait forever. It is not a timing problem.
- **`storage_state` persists auth between runs**, so a bulk job does not need a fresh
  login each time. GHL's session lives in localStorage *and* Firebase IndexedDB, so the
  state file has to carry both — if your launched browser lands on a login screen, the
  IndexedDB half did not come across, and attaching over CDP is the reliable fallback.

`headless=True` is **UNVERIFIED** — every production run was `headless=False`. Given
that the anti-automation flags are already load-bearing here, assume headless changes
behaviour until you have proven otherwise.

**Long-lived sessions are more reliable than short ones.** Rapid launch/close cycles
degrade iframe loading — the iframe starts arriving late, then not at all. Open one
browser, do all the work, close it at the end. Do not launch a browser per item.

---

## The one architecture fact everything else follows from

**Every GHL builder UI is a cross-origin iframe inside a shell page. You must acquire
the FRAME, not the page.**

`app.gohighlevel.com` is a thin shell. The thing you actually want to click lives at a
different origin inside it:

| builder | iframe host contains |
|---|---|
| automation / workflows | `client-app-automation-workflows` |
| form builder | `leadgen-apps` |

Consequences, in order of how much time they cost:

1. **`page.query_selector()` does not see anything inside the builder.** Different
   document. You need `frame.evaluate()`, and Playwright gives you full JS access
   inside that frame with no CORS restriction, because it attaches to the frame's own
   execution context rather than reaching across from the parent.
2. **Match the frame by host substring, not by a guess at the path.** Filtering the
   workflows iframe on `'form-builder'` or `'builder'` matches the *parent* URL too and
   hands you the wrong frame.
3. **The iframe takes seconds to appear.** ~6s for the form builder, and the automation
   list wants ~7–8s after `goto`. Poll `page.frames`; do not sleep once and hope.
4. **The DOM element exists before Vue mounts.** Finding `#form-builder-container` is
   not the same as it being ready. Poll for the Vue property you actually need —
   `c.__draggable_component__` — not for the element.
5. **A direct builder URL does not create the iframe.** Navigating straight to
   `/automation/builder/{workflowId}` loads a page with no cross-origin iframe in it.
   **You must load the list and click the row.** This is the single most likely reason
   an agent concludes "the automation UI can't be automated."

---

## Clicking: two mechanisms, and picking the wrong one wastes an hour

There are two ways to click, they fail differently, and the failure is silent both
ways — the call returns, nothing happens.

**`frame.evaluate()` + `dispatchEvent` — the default inside a builder.**

```python
await frame.evaluate("""(label) => {
    for (const el of document.querySelectorAll('*')) {
        if (el.innerText?.trim() === label) {
            el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            return true;
        }
    }
    return false;
}""", "Form Submitted")
```

`page.mouse.click()` sends coordinates to the **main page**. Those coordinates do not
get routed into a cross-origin iframe's element at the same visual position. This is
the number-one cause of "I clicked it and nothing happened."

**`dispatchEvent` also fires on off-screen elements** — and that is not a workaround,
it is the intended tool. GHL's trigger picker renders *below the fold*. A real mouse
click cannot reach it; `dispatchEvent` does not care where the element is. Same for
anything in a long scrolling multi-select.

**`page.mouse.click()` — correct in exactly one situation.** When you open a specific
workflow, the SPA navigates and the automation iframe becomes full-page: origin (0,0).
At that point frame coordinates and page coordinates are the same number, and mouse
clicks land. On the **list** page the same iframe sits at an offset and they do not.

So the rule is not "use mouse" or "use dispatch". It is:

> **Always query `iframe.bounding_box()` (or the frame element's rect) before clicking
> with the mouse, and add that offset.** The offset differs between list view and
> builder view of the same iframe.

Any fixed pixel number you find in this repo or in a previous script — a list-view
offset around (224, 93), a full-page builder box around 1400×900 — is **an example of
the pattern at one window size, not a constant.** Window size, zoom, sidebar state and
GHL's own layout changes all move it. Read the box; never hardcode it.

Two more clicking facts:

- **A modal blocks everything underneath it.** While a GHL dialog is open, clicks on
  background elements silently do not register. Dismiss first, act second.
- **Snapshot-derived element ids are per-snapshot.** If you are using a snapshot tool
  that numbers interactive elements, those numbers change between snapshots. Never
  carry one across a navigation, and never hardcode one into a script.

---

## Worked example: publish a workflow

The shape here — *list → open → dismiss → act → save → verify* — is the shape of every
UI task on this platform. Learn it once.

**1. Load the list.** Not the builder. The list.

```python
await page.goto(f"https://app.gohighlevel.com/v2/location/{LOCATION_ID}"
                f"/automation/workflows?listTab=all")
await asyncio.sleep(8)
```

**2. Acquire the list frame** by host substring.

```python
list_frame = next((f for f in page.frames
                   if 'client-app-automation-workflows' in f.url), None)
```

**3. Click the workflow row from inside the frame.** The `href` is empty — it is Vue
Router, so there is no URL to navigate to. Match by prefix: the name shown in the list
is a display name and will not equal the name in your build spec.

```python
try:
    await list_frame.evaluate("""(prefix) => {
        for (const a of document.querySelectorAll('a')) {
            if (a.innerText?.trim().startsWith(prefix)) {
                a.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                return;
            }
        }
    }""", WORKFLOW_NAME_PREFIX)
except Exception:
    pass  # the frame navigated out from under the call — expected, not an error
```

**4. Re-acquire the frame.** `list_frame` is now dead. **Any Vue Router navigation
invalidates the frame reference**, and the frame URL does *not* change on SPA routing —
so you cannot match on URL to tell whether you arrived. Poll for expected *content*:

```python
async def get_builder_frame(page, timeout=20):
    for _ in range(timeout * 2):
        for f in page.frames:
            try:
                state = await f.evaluate("""() => {
                    const t = document.getElementById(
                                'cmp-action-bar__tgl--draft-publish-workflow')
                           || document.querySelector('[role="switch"]');
                    return t ? t.getAttribute('aria-checked') : null;
                }""")
                if state in ('true', 'false'):
                    return f
            except Exception:
                pass
        await asyncio.sleep(0.5)
    return None

bf = await get_builder_frame(page)
```

Note what that polls for: the element that proves you are in the builder *and* tells you
the state you came to change. One probe, two answers.

**5. Dismiss the modal before anything else.** The AI Builder modal opens on **every**
first view of a workflow and blocks every click behind it.

```python
await bf.evaluate("""() => {
    for (const b of document.querySelectorAll('button'))
        if (b.innerText?.includes('Got it')) { b.click(); return; }
}""")
```

(For a stuck custom-field dialog in the form builder, the blunt equivalent is
`document.querySelector('#ui-modal')?.remove()`.)

**6. Read the state before you change it** — and read it from the attribute:

```python
toggle = await bf.evaluate("""() => {
    const el = document.getElementById('cmp-action-bar__tgl--draft-publish-workflow')
            || document.querySelector('[role="switch"]');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {ariaChecked: el.getAttribute('aria-checked'),
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height)};
}""")
if toggle and toggle['ariaChecked'] == 'true':
    return 'already_published'
```

**`aria-checked="false"` is Draft, `"true"` is Published. Never use
`body.innerText.includes('Draft')`** — the word "Draft" appears elsewhere in the builder
chrome (save-state labels, history UI) and returns a false positive on a workflow that
is already live. Note also that the visible "Publish" text is a `<p>` label, not the
control; clicking the word does nothing.

**7. Click it.** The builder iframe is full-page here, so mouse coordinates line up —
but click the *centre of the measured box*, not a remembered number:

```python
await page.mouse.click(toggle['x'] + toggle['w']//2, toggle['y'] + toggle['h']//2)
await asyncio.sleep(1.5)
```

If the toggle does not flip, fall back to `dispatchEvent` on
`[role="switch"][aria-checked="false"]` from inside the frame.

**8. Save, or you did nothing.** **Toggling only sets local Vue state.** The change is
on screen and not on the server. A Save button appears; click it.

```python
bf = await get_builder_frame(page, timeout=10)      # re-acquire again
save = await bf.evaluate("""() => {
    for (const b of document.querySelectorAll('button')) {
        const r = b.getBoundingClientRect();
        if (b.innerText?.trim() === 'Save' && r.width > 0 && !b.disabled)
            return {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)};
    }
    return null;
}""")
if save:
    await page.mouse.click(save['x'] + save['w']//2, save['y'] + save['h']//2)
    await asyncio.sleep(2)
```

Button text is itself a signal: **"Save" means unsaved changes exist; "Saved" means
there is nothing to persist.** If it already says "Saved" after your toggle, your
toggle did not take.

**9. Verify by re-reading the attribute** — see [Verification](#verification) below.

### Doing this in bulk

**One full page load per item.** Go back to the list URL with `page.goto()` for every
workflow, take the ~7s hit, re-acquire the frame, act.

```python
for prefix in WORKFLOW_PREFIXES:
    await page.goto(WORKFLOWS_URL)
    await asyncio.sleep(7)
    ...
```

It feels wasteful and it is the fast path. Iterating a paginated SPA list in place —
clicking back, paging forward — loses frame references and desynchronises the list from
what you think you are looking at. The reload is cheaper than the debugging.

### The same shape elsewhere

Trigger configuration is the identical loop with more steps: dismiss the modal → click
the `Add New Trigger` node (`.vue-flow__node` whose text matches) → `dispatchEvent` the
trigger type in the picker (**it renders below the fold, so mouse will not reach it**) →
click `Add filters` → open the filter dropdown → select values → click `Save Trigger`.
Every hop re-acquires the frame first and verifies after.

Form field editing goes through the same door with different plumbing: acquire the
`leadgen-apps` frame, poll `#form-builder-container` for `__draggable_component__`, and
mutate `__draggable_component__.realList` directly rather than dragging anything — then
click `#save-action`. Reading and writing the Vue model beats simulating a drag, always.

**UNVERIFIED:** creating a funnel and any memberships work. Both are listed UI-only in
[`known-unknowns.md`](known-unknowns.md); neither has been driven end to end with this
pattern. Expect the list → row → frame shape to hold and budget time to find out.

---

## Quirks

| symptom | cause | fix |
|---|---|---|
| iframe never appears; page looks half-loaded | Playwright's automation flags | launch with `ignore_default_args=["--enable-automation"]` and `--disable-blink-features=AutomationControlled` |
| builder URL loads but there is no iframe | direct `/automation/builder/{id}` does not create the cross-origin iframe | load the list, click the row |
| `page.mouse.click()` returns, nothing happens | coordinates go to the main page, not into the cross-origin iframe | `frame.evaluate(el.dispatchEvent(...))` |
| clicks land in list view, miss in builder view (or vice versa) | the iframe's offset differs per view — list is offset, builder is (0,0) | query `iframe.bounding_box()` every time; never reuse a coordinate |
| the element you need is not clickable | picker renders below the viewport fold | `dispatchEvent` — it fires on off-screen elements |
| `Frame was detached` / stale results after a click | Vue Router navigation invalidates the frame reference | re-acquire by polling frames for expected content after every navigating click |
| frame URL unchanged, so you assume no navigation | SPA routing changes content, not URL | poll content (a known element / attribute), never URL |
| nothing responds after a dialog opened | modal blocks background clicks | dismiss first — `Got it` button, or `#ui-modal`.remove() |
| state reads as Draft after publishing | `body.innerText.includes('Draft')` matches unrelated chrome text | read `aria-checked` on `[role="switch"]` |
| clicking the word "Publish" does nothing | it is a `<p>` label, not the control | click the toggle `[role="switch"]` |
| toggled successfully, reverted on reload | toggle sets local Vue state only | click Save afterwards; "Saved" vs "Save" tells you which state you are in |
| element found but the property is missing | DOM mounts before Vue does | poll for the Vue property (`__draggable_component__`), not the element |
| wrong frame acquired | substring matched the parent URL too | match a host fragment specific to the builder |
| workflow not found by name | list display names differ from build-spec names | match by `startsWith` prefix, not equality |
| bulk run drifts / references go stale | paginated SPA iteration | one `page.goto()` per item |
| iframes load fine at first, then stop | rapid browser launch/close cycles | one long-lived session for the whole job |
| snapshot element id clicks the wrong thing | ids are per-snapshot | re-snapshot after every change; never hardcode |
| everything 401s mid-run | the internal JWT expired (~60 min) | re-capture — [`getting-the-token.md`](getting-the-token.md) |

---

## Verification

**A click that returned is not a change that happened.** UI automation has no status
code, so you have to go and look. The whole failure mode this repo keeps hitting — the
API returns 200 and nothing moved — has an exact browser twin: the click dispatches,
Vue re-renders, nothing persists.

Check in this order:

1. **Re-acquire the frame and re-read the attribute.** Not the variable you set, not the
   text on screen — the attribute, from a freshly acquired frame:
   `aria-checked == "true"`. If you read it from the pre-click frame reference you may
   be reading a detached document.
2. **Reload the page and read it again.** This is what separates persisted state from
   local Vue state, and it is the check that catches a missing Save.
3. **Read it back through the API where one exists.** Triggers and publish state are
   UI-only to *write*; that does not mean the object is invisible to a `GET`. If you can
   fetch the workflow and see the trigger, that is stronger evidence than any pixel.
4. **Check the rendered surface, not the builder.** For a form, load the live embed and
   look at the fields. For a published workflow, the proof is that it fires.
5. **Screenshot to disk for the record** — but do not treat a screenshot as the check. A
   DOM attribute is a fact; an image is an impression. Query the state.

And when something here stops being true — GHL ships UI changes without notice — the
platform is right and this file is stale. Fix it, date it, say what it cost.

---

Related: [`getting-the-token.md`](getting-the-token.md) ·
[`known-unknowns.md`](known-unknowns.md) ·
[`workflows.md`](workflows.md) ·
[`forms-and-external-embeds.md`](forms-and-external-embeds.md) ·
[`../methodology/how-to-learn-ghl.md`](../methodology/how-to-learn-ghl.md) ·
[`../methodology/verification.md`](../methodology/verification.md)
