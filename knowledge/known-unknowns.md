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

---

## BLOCKED — tried, no route found

### Memberships / courses
**A different vendor entirely.** The memberships product runs on
`backend.memberships.apisystem.tech` — not a `leadconnectorhq.com` host — with
different auth that neither the PIT nor the internal browser JWT satisfied. The UI
also loads as a cross-origin iframe that resisted automation.

If you need memberships, assume you are starting from zero and budget accordingly.
Begin by capturing what the UI does (`performance.getEntriesByType('resource')`) and
expect a third auth scheme.

### Workflow triggers
No API found. A workflow can be created, populated and updated programmatically, but
**attaching a trigger is UI-only.** It has been done by driving the builder with
Playwright; there is no endpoint.

### Publishing a workflow
Same. The Draft → Published toggle is UI-only. Detect state via `aria-checked` on the
`[role="switch"]` — `body.innerText.includes('Draft')` returns true even when
published, because the word appears elsewhere in the builder chrome.

### Creating a funnel
No public create-funnel endpoint found. Funnel *steps* and *pages* can be created;
the funnel itself is a manual step, once per project.

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
not spend the afternoon rediscovering that; go straight to the UI-driving approach. If
it is UNTESTED, budget a verification step. If it is UNEXPLORED, you are the first —
which mostly means: expect a different host and a different auth scheme, and read
[`../methodology/how-to-learn-ghl.md`](../methodology/how-to-learn-ghl.md) first.

**And when you crack one, move it.** Delete the entry, write what you found, date it,
and say what it cost. This page shrinking is the clearest evidence the inheritance is
working.
