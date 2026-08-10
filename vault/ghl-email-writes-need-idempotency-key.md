---
name: ghl-email-writes-need-idempotency-key
description: MCP writes require an idempotencyKey passed as a sibling of params inside arguments — omit it and the write returns 400 naming the field.
metadata:
  type: reference
---

It goes **next to** `params`, not inside it:

    "arguments": {
      "operationId": "create-email-template",
      "idempotencyKey": "<unique-per-logical-write>",
      "params": { "path": {...}, "body": {...} }
    }

**Derive the key from a hash of the content, not from the clock.** A timestamped key — the
obvious first implementation — makes every retry a *new* logical write, which is exactly
what the key exists to prevent. Content-addressed means a retry after a network blip is
the same write, while a genuine edit gets a new key and is not swallowed as a duplicate.

Whether the server actually dedupes on it or merely requires it is **UNVERIFIED**, so
treat it as a real idempotency token rather than a formality.

The same requirement applies to custom-value writes through the MCP server.

While you are here: `locationId` belongs in `params.path`, never `params.query` — the
latter returns `422 "property locationId should not exist"`, the same rule that governs
the raw REST API surviving the MCP wrapper intact.

See [[ghl-mcp-search-describe-execute]], [[ghl-email-html-stored-verbatim]].
