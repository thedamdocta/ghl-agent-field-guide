# Discovery — How to Find Out How GoHighLevel Actually Works

> **Status:** every behaviour described here was observed against live GoHighLevel
> accounts over roughly a year of work. Where a claim was never tested, it is marked
> **UNVERIFIED** inline. Nothing here is inferred from vendor documentation, because
> the vendor documentation does not cover most of it.

---

## The thesis, stated once

**Watching GoHighLevel do the thing beats guessing the API. Decisively, every time,
and by a margin that is embarrassing in retrospect.**

That sentence is the entire methodology. Everything below is either an explanation of
why guessing fails worse than you expect, or a description of the three mechanisms
that let you watch instead.

The reason this needs saying at all is that guessing *feels* productive. You have a
plausible endpoint name, you `curl` it, you get a `200`, and you write it down as a
discovery. On this platform that exact loop produces confidently wrong documentation,
and the section immediately below explains the mechanism that makes it happen.

---

## Why endpoint-name guessing produces FALSE POSITIVES

GoHighLevel's funnel routes accept **any string** as an id and fall through to a
generic get-by-id handler. So probing for feature routes by name returns success for
routes that do not exist:

```
GET  backend.leadconnectorhq.com/funnels/funnel/ai                    -> 200  {"_id":"ai", ...}
GET  backend.leadconnectorhq.com/funnels/funnel/clone                 -> 200  {"_id":"clone", ...}
GET  backend.leadconnectorhq.com/funnels/funnel/import-clickfunnels   -> 200  {"_id":"import-clickfunnels", ...}
```

None of those are AI routes, clone routes, or import routes. There is no such feature
family. Each of those responses is the generic get-by-id route politely echoing your
path segment back at you as an `_id`.

This was believed twice in one session before it was caught. Two "discovered"
endpoints went into notes as real.

### The control test that ends the ambiguity

Before you believe any probe result, **probe a deliberately nonsense id and compare**:

```
GET  backend.leadconnectorhq.com/funnels/funnel/zzzznotreal   -> 200  {"_id":"zzzznotreal", ...}   # identical shape
GET  backend.leadconnectorhq.com/funnels/page/zzzznotreal     -> 400  "Page does not exist or is deleted"
```

If the nonsense id behaves identically to your "discovery," your discovery is
meaningless. This costs one extra request and it should be reflexive — the first
request of any probing session, not the last.

Note the second line: `/funnels/page/{x}` returns `400` for garbage, so *that* route
does discriminate. The control test does not just protect you from false positives, it
tells you which routes are worth probing at all.

### The two probe results that genuinely mean something

| Response | Meaning |
|---|---|
| `403 "This route is not yet supported by the IAM Service."` | A **real** route family behind a genuine wall. Holds for both credential types. Stop probing; go find what the UI calls instead. |
| `401` from a private integration token | A **scope** gap, not necessarily a closed route. Re-test with the browser session credential before concluding anything. |

Everything else — especially a bare `200` — proves nothing until the nonsense-id
control says otherwise.

---

## Try the catalogue FIRST, before any of this

Since GoHighLevel shipped its own MCP server, the correct first move on any "does an
endpoint exist for X?" question is **not** probing at all. The server exposes a small
set of meta-tools over a generated catalogue of the public API:

```
search_operations  ->  describe_operation  ->  execute_operation
```

Ask the catalogue what exists. It answers authoritatively, including with a *negative*
answer, which is the thing probing can never give you. This single change eliminates
the entire false-positive class described above for anything on the public host.

Two things to know before you rely on it:

- **It only covers the public API surface.** The internal host that the web app itself
  calls (funnel autosave, workflow CRUD, form writes) is not in the catalogue. For
  those, you are back to traffic capture.
- **A successful `dryRun` is not a successful call.** `dryRun: true` returns
  `authorizationVerified: false` — it resolves and previews the request shape and does
  **not** check your scopes. A clean dry run proves the shape, never the permission.
  See `verification.md`; this is the same error class as the 422 trap below.

The rule that falls out: **ask the catalogue what exists; probe only what the catalogue
does not cover; capture traffic for everything internal.**

---

## The method that actually works: drive the real UI, capture passively

Every genuinely load-bearing endpoint in this body of work was found the same way —
**by making the GoHighLevel web app perform the action while a passive observer read
the network traffic**, then reading the request schema off what the app itself sent.

The shape:

1. Launch a Chrome instance with a profile that is already logged into GoHighLevel,
   with remote debugging enabled on a dedicated port. Use a *separate* instance from
   the human's own browser so you never disturb their session.
2. Attach over CDP and register a request listener before you navigate.
3. Drive the app to do the thing — click Save, publish the page, submit the form —
   either yourself or by asking the human to click it while you watch.
4. Read the URL, the method, the header set, and the body off the captured request.

This is how the funnel page write path was found. Guessing had produced only the false
positives above and a wall of `403 IAM`. Watching the builder's own Save button
produced the endpoint, the required header names, and the exact body shape in one
capture.

### Two things this method gives you that probing never will

**The header names.** The internal host authenticates on a header literally named
`token-id`, alongside `channel: APP` and `source: WEB_USER`. No amount of endpoint
guessing surfaces a header name. The traffic capture hands it to you because the app
must send it. (Full detail in `../knowledge/auth.md`.)

**The credential itself, with no human step.** The same passive capture that reveals
the endpoints reveals the short-lived session token, because the app attaches it to
every request. Do not ask a human to paste a token out of devtools — you already have
it. And do not sweep `localStorage` looking for JWT-shaped strings: it is fragile
across builds, and some agent harnesses block that *command shape* outright regardless
of your permission configuration. Passive observation is the shape that works and keeps
working.

---

## The strongest variant: let the platform build your exemplar

There is a more powerful version of "watch the UI," and it is worth reaching for
whenever the platform has a feature that generates the artifact you are trying to
construct.

The funnel page authoring schema — dozens of required keys per element, every value
wrapped in a `{"value": ...}` envelope, a four-level `section -> row -> col -> element`
hierarchy — was not reverse-engineered by reading pages. It was obtained by **running
the platform's own AI page generator on a throwaway funnel while a read-only poller
watched the page record**, detected the moment a page-data pointer appeared, and
downloaded the resulting native element tree. That gave a large, complete, guaranteed-
valid document to read the schema off.

The generalisation: **if the platform can produce a valid instance of the thing you
need to write, make it produce one and read it, rather than deriving the format.**
Templates, AI builders, "duplicate this" buttons, and sample imports are all schema
oracles.

The poller that did this touched nothing — it only issued `GET`s on a loop. That is
deliberate and worth copying. A read-only observer can run against a live account with
very little risk; a write-probing script cannot.

### The trap attached to this technique

An exemplar carries its **role**, not just its schema — cloning the wrong sample gives
you a schema-valid document that is semantically wrong. This is catalogued in detail as
the exemplar trap in `failure-modes.md`, and it is the single most expensive bug in
this guide. Read that entry before you build anything on cloned exemplars.

---

## Three more discovery surfaces worth knowing

### `performance.getEntriesByType('resource')` in the browser

When you can execute JavaScript in a GoHighLevel page but cannot see into its iframes,
this single expression enumerates every resource the UI has fetched — which exposes the
internal API hosts and paths the app calls. It unlocked the workflow internal API on
one project when direct iframe inspection was failing.

It is cheap, it is a one-liner, and it does not require a proxy or a CDP attach. Reach
for it early.

Related structural fact it will show you: **GoHighLevel is a set of microservices, one
per feature area, each on its own subdomain** — automation workflows, the page builder,
the form builder, email, memberships all live on different hosts. Different hosts can
have different auth requirements even within the same product. Do not assume the
credential and header set that worked for one feature works for the next one.

### Server-rendered public pages carry their whole definition

Published GoHighLevel funnel pages are server-rendered and embed the complete page
definition in the HTML as a serialised payload (a flat array where integers are
pointers back into the same array). Resolving it yields the full page structure without
any credential at all.

Two consequences, one obvious and one not:

- You can read the structure of any public funnel page — including ones you do not own
  — with a plain HTTP `GET`.
- **Desktop and mobile payloads are byte-identical.** GoHighLevel serves one definition
  and handles responsiveness with per-element flags. If you are capturing a funnel, you
  capture N pages, not 2N. This also means a fidelity check that counts sections will
  overcount, because the source tree contains desktop/mobile twin sections that collapse
  into one responsive element on render.

The same server-rendering fact explains a compliance behaviour documented in
`failure-modes.md`: automated compliance scanners can crawl GoHighLevel-hosted pages
precisely *because* they are genuinely server-rendered, and fail on externally hosted
JS-rendered sites for the same reason.

### Error responses are free schema documentation

GoHighLevel's validators are unusually talkative. Used deliberately, they replace
reading docs:

```
POST  <write endpoint>   {}                      ->  422, and the response NAMES the required fields
POST  /forms/{id}        {..., "locationId": X}  ->  422 "property locationId should not exist"
<write with no idem key>                         ->  400, and the response NAMES idempotencyKey
```

**Post an empty or minimal body first, on purpose, to learn the shape.** It is faster
than any other method and it is current by construction.

The bulk-vs-per-item question was settled the same way. A removed bulk route was
diagnosed not by a 404 but by reading *which validator answered*: sending a bulk-shaped
body to the bulk path returned a 422 written in the **per-item** schema's language,
which meant the path segment `bulk` was being parsed as an item id. Confirming with a
per-item body to the same URL returned `404 "the id is invalid"` — proof the route was
gone, not renamed.

**Read which validator answered, not just the status code.** That is the difference
between "the route moved" and "the route no longer exists."

### The one trap in error-reading

A `401` that becomes a `422` when you attach a payload means **the body validator
accepted you**. It does *not* mean you are authorised. Authorization runs after
validation, and a real payload on the same endpoint can still return `403 IAM-walled`.

This was called "auth confirmed" prematurely and walked back in the same session. It is
covered again in `verification.md` because it is one of the two canonical false
victories, and it is worth encountering twice.

---

## Discovery discipline — the habits that survived the year

**Control-test before you believe.** One nonsense id, every probing session, first
request.

**Do not trust a recorded fact over a live test.** An internal note in this project's
own history recorded the auth header for the internal API. Both of its claims were
false four months later — the cookie it named no longer existed, and the header name it
named returned `"Unauthorized"`. Before you build on any auth or endpoint fact in any
document, *including this one*, send one request and confirm. The platform ships
continuously; your notes do not.

**Check the catalogue before believing a capability is missing.** A capability was once
declared unavailable and hand-built around, when working tooling for it already existed
in the same project's history. One grep of the session log corrected it. Search your own
prior work before you search the API.

**Extract everything from a breakthrough while you are inside it.** When one endpoint
finally opens, do not take the one object you came for. One session that cracked the
workflow internal API pulled every workflow definition and every trigger definition in
the account in the same sitting, and derived the complete action-type and trigger-type
catalogue plus attribute schemas from them. That catalogue then made the next several
sessions possible. Access is the expensive part; reading is cheap once you are in.

**Read is not write.** Extracting a definition proves nothing about your ability to
inject one. Do not describe a write path as working until a round-trip write has been
verified on a throwaway object *and confirmed at the rendered surface*.

**Verify the client's assumptions about their own system before planning around them.**
One project was scoped around a belief that a reference funnel was driven by dynamic
custom values. A single extraction pass showed it had zero. That turned "copy their
modularity" into "build modularity they do not have" — better work, but different work,
and the check took ten minutes.

---

## What remains unknown

Honesty about the edges, so the next agent does not mistake absence for a closed door:

- **OAuth 2.0 marketplace apps.** GoHighLevel supports a full OAuth flow for the public
  host. It was never used here — everything was done with a private integration token.
  **UNVERIFIED.** If you need agency-wide or multi-location reach, evaluate it before
  concluding a capability is missing.
- **Agency-scoped tokens.** Sub-account tokens cannot reach location-search or
  installed-locations routes. Whether an agency-scoped token clears them is
  **UNVERIFIED**.
- **Which of the internal companion headers are individually load-bearing.** The full
  set is confirmed working; `channel` and `source` were never isolated. Do not trim them
  experimentally in production code.
- **The memberships product.** It lives on a different domain entirely with different
  auth and was never cracked. **UNVERIFIED.**
- **Workflow creation via the public catalogue.** Absent as of last check — only read
  operations and contact-membership operations exist. Workflow authoring goes through
  the internal host or the UI. Re-check the catalogue; this is exactly the kind of thing
  that changes.

---

## Related

- `../knowledge/auth.md` — the credential map, the header names, and the status-code
  decoder ring
- `verification.md` — why a `200` from any of the above proves less than you think
- `failure-modes.md` — the catalogue of silent failures, including the exemplar trap
