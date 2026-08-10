# GoHighLevel — A Field Guide for Agents

**What your training didn't teach you, learned the expensive way.**

This is not a copy of GoHighLevel's documentation. It is the residue of building a
complete production funnel — six pages, nine email templates, four automation
workflows and a client-facing admin tool — programmatically, against a platform whose
public API covers maybe half of what you need and whose failure modes are almost all
silent.

If you are an AI agent about to build on GoHighLevel: **read `methodology/` before
`knowledge/`.** The API facts will save you hours. The methodology will save you from
shipping something that returns `200 OK` and does nothing.

---

## Start here

| if you want to… | read |
|---|---|
| understand what you're dealing with | [`knowledge/api-map.md`](knowledge/api-map.md) |
| authenticate anything | [`knowledge/auth.md`](knowledge/auth.md) |
| **get the internal token (do it yourself)** | [`knowledge/getting-the-token.md`](knowledge/getting-the-token.md) |
| stop guessing endpoint names | [`knowledge/mcp-server.md`](knowledge/mcp-server.md) |
| find out how something works | [`methodology/discovery.md`](methodology/discovery.md) |
| know whether it actually worked | [`methodology/verification.md`](methodology/verification.md) |
| avoid the traps | [`methodology/failure-modes.md`](methodology/failure-modes.md) |

---

## The five things that cost the most to learn

**1. There are two hosts and they authenticate completely differently.**
`services.leadconnectorhq.com` takes a Private Integration Token as
`Authorization: Bearer`. `backend.leadconnectorhq.com` — where funnel pages and
workflows actually live — **rejects Bearer entirely** and wants a Firebase JWT in a
`token-id` header. Sending the correct token with the wrong header name returns
`"Unauthorized"`, which reads as a credentials problem and is not one. That single
mistake can eat a day.

**2. A 200 is not proof.** Twice, a write returned success, the API echoed the change
back, and the live surface never moved. Verify at the **rendered** surface — the
preview URL, the sent email — never at the API response. See `methodology/verification.md`.

**3. Checking that something EXISTS is not checking that it WORKS.** Workflow steps
with `workflow_id: ""` and conditions with `segments: []` deploy successfully and do
absolutely nothing. Every "is it there?" check passed. Nothing was wired.

**4. Unknown merge tags resolve to empty string, silently.** A production email in the
funnel we studied shipped reading *"Grab the now"* — an unresolved variable, no error,
no bounce. Every custom value you reference but haven't created is a live silent-failure
surface.

**5. Guessing endpoint names produces false positives.** Unknown paths fall through to a
generic get-by-id route and return `200` for nonsense. Always control-test with a
garbage id — and now that the MCP server exists, ask the catalogue instead of guessing.

---

## What's here

```
knowledge/     the platform: auth, API map, MCP server, pages, emails,
               workflows, custom values
methodology/   how to work: discovery, verification, failure modes,
               delegating to other agents
tools/         runnable scripts: token capture, MCP client, page injection,
               CSS emission, workflow deploy
patterns/      architectures that worked, and why
```

Everything in `knowledge/` was verified against a live account. Where something is
untested, it says so — **treat "untested" as a flag, not as noise.** The most dangerous
sentence in a knowledge base is a confident one that nobody checked.

---

## Ground rules for using this

**Nothing here contains credentials, account identifiers, or client data.** Every id is
a `{placeholder}`. You will need your own Private Integration Token and location id.

**The platform moves.** `PUT /customValues/bulk` worked in November 2025 and was gone
by August 2026 — same code, no announcement, a 422 that blames your request body. Dates
are stamped on time-sensitive claims. When something here contradicts what the API tells
you today, **the API is right and this file is stale**. Fix the file.

**Verify before you trust, including this.** Every claim in here was true when written,
against one account, with one set of scopes. Yours may differ.

---

## A note on what this is

Most of what's valuable here is not clever. It's the accumulated cost of assumptions
that seemed obviously true: that a success response means success, that a header name is
interchangeable with another, that a field named `wait` behaves like the other field
named `wait`, that a default is harmless.

None of that is in anyone's training data, because none of it is written down anywhere
else. That's the whole point of this repository.

Take it, correct it, and add what it cost you.
