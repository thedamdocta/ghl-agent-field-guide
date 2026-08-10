---
name: ghl-mcp-search-describe-execute
description: GoHighLevel's own MCP server replaces endpoint guessing with a search_operations to describe_operation to execute_operation loop over the public API.
metadata:
  type: reference
---

The server sits at `/mcp/anthropic/v2` on the public host and takes the PIT as
`Authorization: Bearer`, with **`locationId` as its own header** and `Accept:
application/json, text/event-stream`. It works over plain `curl` — no MCP client library
— which makes it cheap to *probe* before committing to a dependency or an architecture.

It exposes **six meta-tools**, not one per endpoint: `search`, `fetch`,
`search_operations`, `describe_operation`, `execute_operation`, `list_locations`. The real
surface is a generated catalogue behind them, produced from the same source as the API,
so `describe_operation` is schema documentation you can trust more than prose.

Two parsing gotchas. Responses arrive as **SSE** — strip the `event:` / `data: ` prefixes
and concatenate before parsing. Then unwrap twice: the JSON-RPC result carries a `content`
array of text parts and the actual API payload is JSON encoded *inside* those strings.

Operation ids are inconsistently named — some lowercase-hyphenated, some `GET-`/`DELETE-`
prefixed. **Take them verbatim from `search_operations`; never construct one by pattern.**

`execute_operation` takes `params` partitioned into `path`, `query`, `body`. `dryRun:
true` returns `authorizationVerified: false` — it proves shape, never permission.

See [[ghl-describe-operation-under-reports-params]],
[[ghl-catalogue-gap-is-not-a-platform-limit]], [[ghl-200-is-not-proof]].
