---
name: ghl-memberships-are-a-different-vendor
description: The GoHighLevel memberships and courses product runs on a different vendor's domain with a third auth scheme that neither the PIT nor the internal JWT satisfies.
metadata:
  type: reference
---

It lives on `backend.memberships.apisystem.tech` — not a `leadconnectorhq.com` host at
all. Different auth, and the UI loads as a cross-origin iframe that resisted automation.
**BLOCKED**: tried, no route found.

If you need memberships, **assume you are starting from zero and budget accordingly.**
Begin by capturing what the UI does — `performance.getEntriesByType('resource')` in the
page enumerates every resource the app fetched and is the cheapest way to find the hosts
and paths — and expect a third auth scheme.

This is the clearest instance of the structural fact that explains most of GoHighLevel's
strangeness: it is separate services wearing one interface, and some of those services are
not even the same company's. Different hosts have different auth requirements even inside
the same product, so never assume the credential and header set that worked for one feature
works for the next one.

Check the known-unknowns map before spending an afternoon on a wall someone already hit —
and when you break through one, delete the entry and write what you found.

See [[ghl-two-hosts-two-schemes]], [[ghl-triggers-and-publishing-have-no-api]].
