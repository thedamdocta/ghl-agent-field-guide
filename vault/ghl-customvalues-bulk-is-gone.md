---
name: ghl-customvalues-bulk-is-gone
description: PUT /locations/{locationId}/customValues/bulk no longer exists — bulk is parsed as an id path segment, and per-value PUT is the only write path.
metadata:
  type: reference
---

Tested live 2026-08-06 while porting code that had used the bulk route successfully in
November 2025. It worked for that author then. It does not work now, with no announcement.

    PUT /locations/{loc}/customValues/bulk  body {customValues:[{id,value}]}
      -> 422 "property customValues should not exist / name must be a string"

That 422 is the **per-value** schema talking, which is the tell. Confirmed by sending a
per-value body to the same URL:

    -> 404 "The custom value id is invalid."

So `bulk` is being consumed as the `{id}` path segment. **The route was removed, not
renamed.**

Design consequence: probe bulk once per process, memoise the failure, fall through to
per-value writes. Twenty-odd individual calls is a perfectly reasonable number — the
fallback is not a compromise.

The transferable lesson is about staleness rather than about custom values. **Build tools
that probe once and fall back rather than assuming last year's route still exists**, and
date anything time-sensitive so it can be re-tested instead of silently rotting.

See [[ghl-customvalue-put-needs-name]], [[ghl-do-not-trust-a-recorded-fact]].
