---
name: ghl-describe-operation-under-reports-params
description: describe_operation can omit required parameters — the validator is the authority, not the catalogue.
metadata:
  type: reference
---

`describe_operation getPagesByFunnelId` lists `funnelId`, `limit`, `offset`. The
endpoint **also requires `locationId`**, and says so in a `422` if you omit it. Omit
`offset` and it 422s for that too. (Observed 2026-08-10.)

So treat the catalogue as a strong hint and not a contract. Send a deliberately minimal
request and read what the validator demands — that is current by construction in a way no
generated parameter list is guaranteed to be.

A related shape trap on the same endpoint: `GET /funnels/page` returns a **bare array**,
not `{"pages": [...]}`. A parser doing `data.get("pages", [])` reports zero pages on a
funnel that has six, and nothing errors. `GET /funnels/page/count` is a cheap way to check
whether your parser is lying to you.

The habit both of these teach: **before concluding the platform is wrong, check whether
your reader is.** It usually is.

See [[ghl-422-is-free-schema-documentation]], [[ghl-mcp-search-describe-execute]].
