---
name: ghl-triggers-and-publishing-have-no-api
description: Workflow triggers and the Draft-to-Published toggle have no API at all — both are browser-only, and workflows deploy in Draft and do nothing until published.
metadata:
  type: reference
---

A workflow can be created, populated and updated programmatically. **Attaching a trigger
cannot.** No endpoint was found for it; it has been done by driving the builder with
browser automation. Publishing is the same story.

Plan for that before you promise automation. The `trigger` field in a local build spec is
documentation for a human or browser step, not something the API consumes.

Detect publish state via **`aria-checked` on the `[role="switch"]` element** — never via
body text.

Other things in the same category, so you do not spend an afternoon rediscovering the
wall: **creating a funnel** has no public endpoint (a two-minute manual step, once per
project); **pipelines** failed to create on both hosts in a 2026-04-28 test and are worth
re-testing; **snapshots** are agency-level and a sub-account PIT gets 401; and
**memberships** are a different vendor entirely.

Only four things in a whole build genuinely need a human: creating the PIT, the first
browser login on a fresh profile, creating a funnel, and triggers/publishing. If you are
about to ask for anything else, check first — you can probably do it.

See [[ghl-read-aria-checked-not-innertext]], [[ghl-catalogue-gap-is-not-a-platform-limit]],
[[ghl-memberships-are-a-different-vendor]].
