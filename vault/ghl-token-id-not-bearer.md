---
name: ghl-token-id-not-bearer
description: "The GoHighLevel internal host authenticates on a header literally named token-id, not Authorization: Bearer. — SYMPTOM: HTTP 401 Unauthorized with a token you know is valid"
metadata:
  type: reference
---

`backend.leadconnectorhq.com` — the API the GoHighLevel web app itself calls, and the
only route to funnel page writes, workflow authoring and form writes — reads its
credential from a header named **`token-id`**. `Authorization: Bearer` fails there, for
the Private Integration Token *and* for the browser JWT.

Both forms were sent back to back with the same JWT value: `Authorization: Bearer`
returned `"Unauthorized"`, `token-id` returned **200**. The header name is the entire
difference.

The cost is in the error text. `"Unauthorized"` reads as a credential problem, so every
instinct says the token expired — and you spend a debugging cycle re-capturing a token
that was never broken. **If the internal host says Unauthorized, check the header name
before you touch the token.**

Send the full set the web app sends:

    token-id: <the jwt>
    channel: APP
    source: WEB_USER
    Version: 2021-07-28

Which of `channel` / `source` are individually load-bearing is **UNVERIFIED** — the set
is confirmed working, so do not trim it experimentally in production code.

See [[ghl-two-hosts-two-schemes]], [[ghl-capture-internal-token-yourself]],
[[ghl-do-not-trust-a-recorded-fact]].
