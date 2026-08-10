---
name: ghl-nuxt-data-devalue-decoding
description: "A public GHL funnel page ships its complete definition in a __NUXT_DATA__ script tag, devalue-serialized: integers inside it are pointers into the same flat array."
metadata:
  type: reference
---

A published page is a server-rendered Nuxt 3 app, and the whole page definition — every
element, style, layout value and setting — rides inside one script tag with
`id="__NUXT_DATA__"`.

The payload is a **flat JSON array**. Index `0` is the root, and **any integer appearing
inside an object or array is an index back into that same array**, not a literal number.
Resolving it means walking and substituting recursively — with a depth bound, because the
graph self-references and an unbounded resolver will not terminate.

Consequences:

- **Any publicly reachable GHL page leaks its full definition to a plain HTTP GET**, with
  no credential. Section, row, column and element tree, responsive rules, button wiring.
  This is the read side of funnel hacking.
- **Desktop and mobile payloads are byte-identical** (verified across six pages). GHL
  serves one definition and does responsiveness with per-element flags and breakpoint
  style blocks. Capture N pages, not 2N — and do not let a fidelity checker count
  desktop/mobile twin sections as two.

Fetch with a real browser user agent; Cloudflare 403s default UAs on GHL hosts.

See [[ghl-node-id-is-not-c-plus-id]], [[ghl-exemplar-carries-its-role]],
[[ghl-popups-list-sits-outside-sections]].
