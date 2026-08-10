---
name: ghl-two-hosts-two-schemes
description: GoHighLevel is two APIs on two hostnames with two different auth schemes, and the credential for one is rejected by the other.
metadata:
  type: reference
---

**Public host `services.leadconnectorhq.com`** takes a Private Integration Token as
`Authorization: Bearer`, with `Version: 2021-07-28` as a *required* header. It covers
contacts, custom values, email templates, media, opportunities and form *reads*, and it
is what GoHighLevel's own MCP server fronts.

**Internal host `backend.leadconnectorhq.com`** is what the web app calls. It covers
funnel page autosave, workflow create/update and form writes, and it takes a short-lived
Firebase JWT in the `token-id` header. The PIT does not reach this host at all.

The most expensive mistake on this platform is assuming a credential that works on one
host works on the other. The failure is a bare `"Unauthorized"`, which reads like a token
problem and is a header problem.

The structural reason: GoHighLevel is a set of microservices, one per feature area, each
on its own subdomain. Auth, validation and failure modes all differ per host. **When
something behaves inconsistently, your first hypothesis should be that you are talking to
a different service — not that the platform is flaky.**

On every GHL host, send a browser-like user agent. Cloudflare 403s Python's default
`urllib` UA; a 403 with an HTML body rather than JSON is the tell.

See [[ghl-token-id-not-bearer]], [[ghl-pit-scopes-are-partial]],
[[ghl-memberships-are-a-different-vendor]].
