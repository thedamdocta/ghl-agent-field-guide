---
name: ghl-catalogue-gap-is-not-a-platform-limit
description: Workflows are creatable through the internal API even though the MCP catalogue has no create-workflow — absent from the catalogue never means impossible.
metadata:
  type: reference
---

The catalogue exposes only `get-workflow`, `add-contact-to-workflow`,
`delete-contact-from-workflow` and `list-workflow-campaigns`. A client was once told that
workflow automation had to be hand-built in the UI on the strength of that gap. It was
wrong.

The internal host creates and updates them, with the `token-id` header set:

    POST   /workflow/{locationId}                body {"name": "..."}   -> id
    GET    /workflow/{locationId}/{workflowId}   -> read current `version`
    PUT    /workflow/{locationId}/{workflowId}   body {name, workflowData, version}
    DELETE /workflow/{locationId}/{workflowId}   -> {"success": true}

Verified: four workflows created and updated this way and read back with all steps and
template references intact.

Two operational notes. The internal API does **no name-deduplication and happily creates
duplicates**, so persist created ids and `PUT` over them rather than `POST`ing again. And
**read the current `version` before a `PUT`** — the update body carries it.

The generalisable point: the MCP server fronts the *public* API, and GoHighLevel's own web
app uses a different, larger internal one. Check the catalogue, then check the internal
API, *then* conclude a capability is missing.

See [[ghl-mcp-search-describe-execute]], [[ghl-triggers-and-publishing-have-no-api]].
