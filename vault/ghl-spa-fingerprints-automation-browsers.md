---
name: ghl-spa-fingerprints-automation-browsers
description: The GoHighLevel SPA checks Firebase auth before mounting and fails in automation-launched browsers, producing a blank white page on every route including login.
metadata:
  type: reference
---

Zero inputs, zero content, and a console showing a Firebase auth check failing. Stealth
flags alone did not fix it. Launching a persistent context against a real Chrome profile
also failed, because the automation framework adds a flag that breaks Chrome's own token
decryption for signed-in profiles.

**Working paths:** attach over CDP to a **manually launched** real Chrome that is already
signed in, using a cloned or dedicated profile directory so you never disturb the human's
session. Alternatively, persist a saved storage state — localStorage plus Firebase
IndexedDB — from one human login and reuse it.

**Environment caveat worth checking first:** on recent Chrome versions
`--remote-debugging-port` alone on a default profile no longer binds a TCP socket. The port
file exists and nothing is listening. Confirm with a listening-socket check before you
debug anything else. A dedicated `--user-data-dir` works where the default profile does
not, and Chrome will not open a debugging port on a profile another instance already owns —
it fails *silently*, the window opens normally and the port never listens.

See [[ghl-capture-internal-token-yourself]], [[ghl-builder-iframes-ignore-mouse-coordinates]].
