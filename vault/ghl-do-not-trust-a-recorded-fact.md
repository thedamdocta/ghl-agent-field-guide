---
name: ghl-do-not-trust-a-recorded-fact
description: Do not trust a recorded fact over a live test — including anything in these notes. Send one request and confirm before you build on an auth or endpoint claim.
metadata:
  type: feedback
---

A note in one project's own history recorded the auth scheme for the GoHighLevel internal
API. **Both of its claims were false four months later**: the cookie it named no longer
existed, and the header name it named returned `"Unauthorized"`. Building on it cost a full
debugging cycle.

`PUT /customValues/bulk` worked in November 2025 and was gone by August 2026 — same code, no
announcement, and a 422 that blames your request body rather than saying the route is gone.

**The platform ships continuously; your notes do not.**

Practical form:

- Before building on any auth or endpoint fact in any document, send one request and confirm.
- **Date anything time-sensitive**, so a claim can be re-tested rather than silently rotting.
- Prefer probe-once-and-fall-back over assuming last year's route still exists.
- When the API contradicts a note, **the API wins** — then fix the note in place, date the
  correction, and say what the old claim cost. Correct; do not stack. A guide that only
  accretes becomes a guide nobody trusts.
- Mark what is UNVERIFIED as explicitly as what is verified. An unmarked assumption is
  indistinguishable from a checked fact three weeks later, and that is how bad information
  propagates.

See [[ghl-token-id-not-bearer]], [[ghl-customvalues-bulk-is-gone]],
[[ghl-ship-the-artifact-not-its-description]].
