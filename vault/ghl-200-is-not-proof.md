---
name: ghl-200-is-not-proof
description: A 200 from GoHighLevel, plus the API echoing your write back, is not evidence the change took effect — verify at the rendered surface.
metadata:
  type: feedback
---

Pages are **compiled at save time**, so the served page is a build artifact rather than a
live read of the record you modified. Any verification that stops at the API layer is
structurally incapable of catching a failed write.

The canonical incident: an upload returned 200, a pointer PATCH returned 200, reading the
document back showed the new pointer, and the GHL REST API echoed the new values. **Four
independent confirmations, and the live page never changed.** What caught it was a human
asking for a screenshot.

Where the rendered surfaces are:

| artifact | surface |
|---|---|
| funnel page | the public preview URL — server-rendered, no auth, no custom domain; `curl` it and grep for your literal string |
| form | the form's public widget document; the builder's editor pane lies about what was saved |
| email template | the returned `previewUrl`, or a real send |
| workflow | the stored definition read back, plus `aria-checked` for publish state |

Two corollaries. A `401 -> 422` shift is the body validator passing, not authorization. And
the rendered page shows **resolved** merge tags, so "no `custom_values.` appears in the
HTML" proves nothing — assert against your generated source **and** spot-check for expected
literal strings.

See [[ghl-existence-is-not-wiring]], [[ghl-preview-url-is-read-only]],
[[ghl-firebase-direct-write-is-a-dead-end]].
