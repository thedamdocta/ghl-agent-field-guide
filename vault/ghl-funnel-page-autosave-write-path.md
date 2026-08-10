---
name: ghl-funnel-page-autosave-write-path
description: The only funnel page write path is POST backend.../funnels/builder/autosave/{pageId}; every REST page-write route is IAM-walled.
metadata:
  type: reference
---

Do not re-attempt the REST routes. Confirmed for **both** the PIT and the account JWT:
`PUT services.../funnels/page` and `PUT backend.../funnels/page` return
`403 "This route is not yet supported by the IAM Service"` once a real `locationId` is
supplied, and `POST backend.../funnels/page` returns `404`. That is a platform gate, not a
scope problem a better token solves.

The path that works is the one the builder's own Save button calls:

    POST https://backend.leadconnectorhq.com/funnels/builder/autosave/{pageId}
    headers: token-id, channel: APP, source: WEB_USER, Version: 2021-07-28
    body:    {"funnelId": "...", "pageData": { ...full authoring tree... },
              "pageVersion": <int>}
    -> 201 Created

The response carries the **new** `pageDataUrl` / `pageDataDownloadUrl` GoHighLevel minted
for you. GHL writes the object *and recompiles the page* — that recompile is the entire
point, and it is why direct storage writes do not work.

It was found by capturing traffic while the builder saved. Guessing had produced only
false positives and a wall of `403 IAM`.

A `201` is not a result. Verify on the rendered preview.

See [[ghl-firebase-direct-write-is-a-dead-end]], [[ghl-200-is-not-proof]],
[[ghl-preview-url-is-read-only]].
