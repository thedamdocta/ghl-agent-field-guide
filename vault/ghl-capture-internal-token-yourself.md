---
name: ghl-capture-internal-token-yourself
description: The internal token is captured by passively reading the token-id request header off traffic a logged-in Chrome already generates — no human paste required.
metadata:
  type: reference
---

It is **not** in a cookie and **not** reliably in localStorage. It is observed on the
wire.

The working, fully automated method: launch a *separate* Chrome instance with a dedicated
`--user-data-dir` and `--remote-debugging-port`, attach over CDP, register a request
listener, navigate to any ordinary in-app URL, and read `token-id` off the calls the app
makes on its own behalf. The value is ~1000-1100 characters and starts `eyJ`. Much
shorter means it is not the token.

A human is needed exactly **once**, for the first login on a fresh profile — and often
that has already happened, so check for an existing profile and an open debug port before
asking anyone for anything. Never ask for a password.

Three anti-patterns, each of which cost real time:

1. **Do not ask a human to paste it out of devtools.** The capture is automatable.
2. **Do not hunt for an `eyJ` cookie.** The old `m_a` cookie is gone and cookies are not
   the source.
3. **Do not sweep localStorage for JWT-shaped strings.** Fragile across builds, and some
   agent harnesses block that *command shape* regardless of permissions.

Before blaming the token, confirm the profile is logged in: a signed-out profile settles
on a redirect URL with an empty `<title>` and produces a convincing "bad token" symptom.
Use a dedicated `user-data-dir` or the debug port silently never listens.

See [[ghl-internal-token-60-minute-life]], [[ghl-token-id-not-bearer]].
