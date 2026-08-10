# What has NOT been figured out

An honest map of the edges. Everything else in this repo was verified against a live
account; this page is the opposite — **the things nobody here has cracked, tested, or
looked at.**

It exists because a knowledge base that only records wins quietly implies the rest is
easy, and the next agent then burns a day discovering that memberships live on a
different vendor's domain.

Three categories, and the distinction matters:

- **BLOCKED** — tried, does not work through any route found so far.
- **UNTESTED** — plausibly works; nobody has checked. Treat as unknown, not as true.
- **UNEXPLORED** — never looked at. No opinion offered.

**"No API" is not "impossible."** Several BLOCKED entries below are blocked *as API
calls* and are perfectly doable by driving the browser — which you can do yourself, no
human required. Each one says so and points at
[`driving-the-ui.md`](driving-the-ui.md), which carries the setup, the cross-origin
iframe rules and the quirks table. Read it before you conclude anything here is a wall.

Two of them now ship a tool rather than only a description —
`tools/configure_trigger.py` and `tools/publish_workflow.py`, the last two steps of a
workflow build. They stay listed as BLOCKED because the *API* is still blocked, and
because **neither tool's browser path has been run against a live account yet.**

---

## BLOCKED — tried, no route found

### Memberships / courses
**A different vendor entirely.** The memberships product runs on
`backend.memberships.apisystem.tech` — not a `leadconnectorhq.com` host — with
different auth that neither the PIT nor the internal browser JWT satisfied. The UI
also loads as a cross-origin iframe that resisted automation.

If you need memberships, assume you are starting from zero and budget accordingly.
Begin by capturing what the UI does (`performance.getEntriesByType('resource')`) and
expect a third auth scheme. If you fall back to driving that iframe,
[`driving-the-ui.md`](driving-the-ui.md) is the starting point — but note this is the
one builder where the iframe rules there were **not** enough on their own.

### Workflow triggers
No API found. A workflow can be created, populated and updated programmatically, but
**attaching a trigger has no endpoint.** Blocked as an API call — **not blocked as
work.** It has been done repeatedly by driving the builder with Playwright.

**There is now a tool for it: `tools/configure_trigger.py`.** It encodes the full
pattern — acquire the iframe, dismiss the first-view modal, `dispatchEvent` the
picker item that renders below the fold, save, then re-read the canvas to verify.

> **Its browser path has NOT been run against a live account.** The tool was built
> from the verified production pattern and checked offline — argument parsing, every
> refusal path, and its state machine against a stubbed browser — but nobody has
> pointed it at a real sub-account since it was written. Treat your first run as the
> test it is: dry-run one workflow (the default) and read the result.

The hand-driven pattern is still written out in
[`driving-the-ui.md`](driving-the-ui.md), and you will want it the first time a
selector moves. Either way: do it yourself; do not hand it back.

### Publishing a workflow
Same — no endpoint, and the same answer: **flip the toggle in the browser.** The
manual path is verified working and written up step-by-step in
[`driving-the-ui.md`](driving-the-ui.md), which is the worked example on that page.

**There is now a tool for it: `tools/publish_workflow.py`** — one workflow, several,
or `--all`, which skips the ones already live and so publishes exactly the drafts.

> **Its browser path has NOT been run against a live account either.** Built from the
> verified pattern, checked offline only. Same caveat, same advice: dry-run one
> workflow before you reach for `--all`.

Two things that cost hours if you improvise, and that the tool and any hand-run both
have to get right: detect state via `aria-checked` on the `[role="switch"]`
(`body.innerText.includes('Draft')` returns true even when published, because the
word appears elsewhere in the builder chrome), and **click Save after toggling** —
the toggle alone only sets local Vue state, and navigating away discards it silently.

### Creating a funnel
No public create-funnel endpoint found. Funnel *steps* and *pages* can be created; the
funnel object itself is a UI step, once per project. **UNVERIFIED** whether the
list → row → iframe pattern in [`driving-the-ui.md`](driving-the-ui.md) automates it —
nobody has tried. It has always been done by hand because it happens once.

### Snapshots
Agency-level only. A sub-account PIT gets 401. Untested from an agency token.

### Form CREATE on the public host
`POST services.leadconnectorhq.com/forms/` returns
`401 "This route is not yet supported by the IAM Service."` Use the internal host.

---

## UNTESTED — plausible, unverified. Do not treat as true.

### Which datetime format `event_start_date` actually parses
The single most consequential unknown in this repo. A workflow's event anchor accepts
a custom value, and it is **unverified** whether it parses ISO 8601 with an offset or
a naive `MM-DD-YYYY HH:MM`. Get it wrong and two scheduled emails silently never send.
Mitigation in use: write both formats to separate slots and point the workflow at one.
**Settle it with a throwaway workflow and a short wait.** It cannot be settled by
reading.

### Whether large CSS survives the API write path
The ~8KB truncation ceiling was measured against the **builder's textarea**, where a
14KB paste silently persisted random partial chunks. Writing `fieldCSS` through the
API bypasses that textarea, and ~2KB persisted cleanly. **Whether 8KB+ survives the
API path is unknown.** Read the stored value back and compare its length.

### Whether `name: null` is API-specific
Reported by a second account: UI-created forms carry a real name, API-created ones may
return null. Plausible and useful if true; not confirmed here.

### Custom values inside the email builder
Templates are created with `{{custom_values.x}}` in the HTML and the tags are expected
to resolve at send time, as they do on funnel pages. **No test send has been made.**
Send one to yourself before trusting a sequence.

### Sub-account timezone effects on naive datetimes
A naive datetime is interpreted in the *account's* timezone. Verified that the account
timezone is readable; **not** verified what happens when a scheduled action's timezone
differs from it. Assume reminders fire at the wrong hour and check.

### `GET /funnels/page` pagination past the first page
Works with `funnelId` + `locationId` + `limit` + `offset`. Only tested on a funnel with
six pages, single page of results. Behaviour at scale unknown.

---

## UNEXPLORED — never looked at

No opinion is offered on any of these. They are listed so you know the map has edges,
not because anything is known to be hard.

| area | note |
|---|---|
| **Calendars & appointments** | reachable in the MCP catalogue; never exercised |
| **Payments, products, store** | never touched |
| **Invoices & estimates** | operations exist in the catalogue; unused |
| **Conversations & messaging** | never sent a message programmatically |
| **Social planner** | never touched |
| **Blogs** | never touched |
| **Opportunities & pipelines** | read during exploration; never created one via API |
| **Chat widget** | configured through the UI only |
| **A2P / 10DLC registration** | done manually; painful, and full of its own rules |
| **Affiliate manager, reputation, reporting** | never opened |
| **Agency-level / multi-location operations** | everything here is single sub-account |
| **Webhooks & inbound automation** | the trigger side is UI-only; inbound webhooks unexplored |
| **Custom objects** | exist in the catalogue; never used |

For any of these, start with `tools/ghl_mcp.py search "<the thing>"` — the catalogue
covers roughly 40 domains and will usually tell you whether a public route exists
before you spend an afternoon.

---

## How to use this page

**Before starting anything, check whether it is listed here.** If it is BLOCKED, do
not spend the afternoon rediscovering that; go straight to the UI-driving approach in
[`driving-the-ui.md`](driving-the-ui.md) — BLOCKED means "no endpoint", and for most of
these it does not mean "cannot be done." If
it is UNTESTED, budget a verification step. If it is UNEXPLORED, you are the first —
which mostly means: expect a different host and a different auth scheme, and read
[`../methodology/how-to-learn-ghl.md`](../methodology/how-to-learn-ghl.md) first.

**And when you crack one, move it.** Delete the entry, write what you found, date it,
and say what it cost. This page shrinking is the clearest evidence the inheritance is
working.
