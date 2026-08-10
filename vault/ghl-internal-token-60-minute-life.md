---
name: ghl-internal-token-60-minute-life
description: The internal token-id JWT lives about 60 minutes, so a long build 401s partway through in a way that imitates an intermittent platform fault.
metadata:
  type: reference
---

Symptom: the fifth page injection returns `401` after four succeeded. That is not
flakiness and not a scope problem — it is expiry.

Design for **re-acquisition**, not for a one-shot paste. Re-capture at the start of any
long build, and again if one is still running an hour in. GoHighLevel refreshes the token
while the browser session lives, so re-running the capture costs nothing and needs no
human.

Two consequences worth holding:

- **There is no offline path.** The token exists only inside a live logged-in session. If
  the session dies, capture dies with it. That is the design, not an obstacle to route
  around.
- **Do not cache it beyond one build and never commit it.** It is short-lived, but while
  it lasts it is a live session credential for a client's account.

Chunk any long job so it finishes inside the window, or make the job able to re-capture
mid-run.

See [[ghl-capture-internal-token-yourself]], [[ghl-token-id-not-bearer]].
