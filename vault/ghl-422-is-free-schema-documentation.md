---
name: ghl-422-is-free-schema-documentation
description: A GoHighLevel 422 names the offending property, so deliberately POSTing an empty body to a public-host endpoint buys the whole request contract in one call.
metadata:
  type: reference
---

The body validator runs before authorization and it **names the field**. POST `{}` to
the funnel autosave endpoint and the 422 names `funnelId`, `pageData`, `pageVersion` —
the entire contract, obtained in one throwaway request that changes no state.

It works in the negative direction too. `"property locationId should not exist"` is how
you learn `locationId` belongs in the path or header rather than the query. And a
bulk-shaped body sent to the bulk path answered *in the per-value schema's language*,
which is how the removed bulk route was diagnosed. **Read which validator answered, not
just the status code** — that is the difference between "the route moved" and "the route
is gone".

Two hard limits on the technique:

- **Public host only.** See [[ghl-never-probe-internal-host-with-empty-body]].
- **A 422 proves shape, never permission.** A `401 -> 422` shift means the validator
  engaged with your request; a real payload to the same endpoint can still return
  `403 IAM`. That transition was twice read as "auth unlocked" and walked back both times.

See [[ghl-describe-operation-under-reports-params]], [[ghl-200-is-not-proof]].
