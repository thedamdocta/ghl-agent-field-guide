# How to learn GoHighLevel on your own

Everything else here is what was found. This is **how to find the next thing**, so you
are not stuck when you hit something nobody wrote down.

---

## The one structural fact that explains most of the strangeness

**GoHighLevel is a set of separate services wearing one interface.** Each major
feature is its own application on its own host, and the builder UIs are cross-origin
iframes loaded into a shell:

```
services.leadconnectorhq.com                    the public API gateway
backend.leadconnectorhq.com                     internal admin endpoints
client-app-automation-workflows.leadconnectorhq.com   the workflow builder
email-home-prod.leadconnectorhq.com             email marketing
api.leadconnectorhq.com/widget/form/{id}        the form widget document
backend.memberships.apisystem.tech              memberships — a DIFFERENT VENDOR
```

Once you know that, the inconsistencies stop being random:

- Auth differs per host. A PIT works on one and returns `"Unauthorized"` on another.
- Validation differs per host. The public gateway 422s helpfully; the internal host
  accepts an empty body and creates a nameless object.
- A capability missing from one surface may exist on another. "Absent from the MCP
  catalogue" never means "impossible."
- Two things with the same name may be different things. `wait` is two different
  actions. A form on a GHL page and the same form embedded elsewhere render
  differently.

**So when something behaves inconsistently, your first hypothesis should be that you
are talking to a different service — not that the platform is flaky.** That single
reframe resolved more confusion than any other idea here.

---

## The method that actually works: watch it do the thing

Guessing endpoint names failed every time it was tried. What worked, repeatedly, was
**driving the real UI while capturing the traffic it produces**, then reading the
schema off what the application itself sends.

Concretely:

1. Open the feature in a browser you control (see `knowledge/getting-the-token.md` —
   you can do this without a human).
2. Perform the action once, by hand or by driving the UI.
3. Read the requests it made. In the page:
   ```js
   performance.getEntriesByType('resource').map(r => r.name)
   ```
   That alone reveals internal APIs the UI calls and nothing documents.
4. Copy the request shape. Not approximately — exactly, including headers.

A variant worth remembering: **let the platform's own generator produce your
exemplar.** The complete element schema in this repo came from letting GHL's builder
create a page, then reading the object it produced. The vendor writes a perfect
example of their own format for free.

---

## Read errors as documentation

GoHighLevel's validation errors **name the offending field**. This is the cheapest
schema discovery available:

```
422  "property locationId should not exist"
422  "name must be a string"
422  "offset should not be empty"
```

So: send a deliberately minimal request and let the validator tell you what it wants.
Three fields were discovered that way in an afternoon.

**One caveat that cost someone real time:** this works on the **public** host. The
internal host does not validate bodies — `POST backend…/workflow/{loc}` with `{}`
returns 200 and creates a nameless workflow. Probe `services.` freely; never probe
`backend.` with an empty body.

---

## Control-test, or you have learned nothing

Unknown paths on this platform fall through to a generic get-by-id handler and
**return 200 for nonsense**. Before believing an endpoint exists:

```bash
curl ".../thing/zzzznotreal"      # 200? then your "discovery" is meaningless
```

The same discipline applies to your own parsing. `GET /funnels/page` returns a **bare
array**; a parser expecting `{"pages": [...]}` reports zero pages on a funnel with
six, and nothing errors. **Before concluding the platform is wrong, check whether your
reader is.** It usually is.

---

## A 200 is not proof, and neither is existence

Two beliefs to hold permanently:

**Verify at the rendered surface.** Not the API response — the live preview URL, the
stored template, the sent email. Twice a write returned success, the API echoed the
change back, and the live surface never moved.

**Check that it is wired, not that it is present.** Empty stubs deploy cleanly. A
workflow step with `workflow_id: ""` and a condition with `segments: []` both return
201 and do nothing. Every "is it there?" check passes.

---

## Timing is a variable

Reads do not immediately reflect writes. A form id handed to you by `create` is not
resolvable on the write path for a second or two; populating immediately returns
`400 "form does not exist or is deleted"` against an id you just received. The same
call works a minute later.

**Poll for the condition; do not `sleep`.** A fixed sleep is either too short to work
or too long for every subsequent run. And apply the same patience to your
verification — reading back immediately can report an empty result while the write
succeeded, which is a false negative that sends you debugging something that worked.

---

## Distrust your own summary of your own work

The single most expensive error in this repository's history: a note described some
work as *"cloned the field schema"* when the code **hand-wrote** it. Months later that
description — not the code — was used to build a tool, which then refused to run
without a donor form that fresh accounts do not have.

**Descriptions drift from implementations, and the description is what propagates.**
When you write something down, prefer the artifact over the account of the artifact.
When you read your own notes, check them against the code before acting.

---

## Record at the moment of discovery, with the failure attached

You will not remember why a header mattered. Write it down while the pain is fresh,
and keep the incident attached to the rule:

- Weak: *"Use the `token-id` header."*
- Strong: *"`Authorization: Bearer` returns `Unauthorized` on the internal host with a
  perfectly valid token. The error reads as a credentials problem and is a header-name
  problem. Cost a day."*

The second one is retrievable later, because the story is the search handle.
`INHERIT.md` covers how to decompose this into a memory system: **one note per fact**,
one-line description, indexed, unverified things marked unverified.

---

## Expect it to move

`PUT /customValues/bulk` worked in November 2025 and was gone by August 2026 — no
announcement, and a 422 blaming the request body. Date anything time-sensitive so it
can be re-tested rather than silently rotting, and build tools that **probe once and
fall back** rather than assuming last year's route still exists.

---

## The disposition, in one paragraph

Assume the platform is stranger than it looks and that the documentation is a subset
of the truth. Prefer watching over guessing, errors over assumptions, and the rendered
surface over the response body. Control-test everything, including yourself. Treat
inconsistency as evidence of a second system rather than of chaos. Write the artifact
down, not the story of the artifact. And when something you were sure of turns out
wrong, fix the note in place and say what it cost — that correction is worth more to
whoever comes next than the thing you originally got right.

Related: [`discovery.md`](discovery.md) · [`verification.md`](verification.md) ·
[`failure-modes.md`](failure-modes.md) ·
[`../knowledge/known-unknowns.md`](../knowledge/known-unknowns.md)
