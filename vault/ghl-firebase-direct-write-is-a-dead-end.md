---
name: ghl-firebase-direct-write-is-a-dead-end
description: The token-id JWT is a Firebase ID token that authenticates Firestore and Firebase Storage directly — but writes there return 200 and the live page never changes.
metadata:
  type: reference
---

The JWT decodes with `iss: securetoken.google.com/highlevel-backend`,
`aud: highlevel-backend`. Presented the conventional way as `Authorization: Bearer` it is
accepted by `firestore.googleapis.com` and `firebasestorage.googleapis.com` directly.
There is **no `signInWithCustomToken` exchange to replay** — the token the app already
carries is the end of that chain. Same string, two header names by host.

That is genuinely useful for **reading** the native page authoring tree, and it is how the
page schema was discovered.

**It is not a write path, and this is the most expensive false victory in the corpus.**
Uploading a new page-data object (200), PATCHing the Firestore pointer (200), reading the
document back with the new pointer, and watching the GHL REST API echo your values — four
independent confirmations — and the live page never changed, on any attempt.

GoHighLevel **compiles pages at save time**. The renderer reads a `versionHistory[]`
entry, not the top-level pointer you edited, and the builder holds its own draft that
overwrites raw storage edits on its next save.

What caught it was a human asking for a screenshot.

See [[ghl-funnel-page-autosave-write-path]], [[ghl-200-is-not-proof]].
