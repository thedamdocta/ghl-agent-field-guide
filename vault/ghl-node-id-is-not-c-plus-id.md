---
name: ghl-node-id-is-not-c-plus-id
description: "extra.nodeId is NOT c + id: the authoring and rendered ids share a type prefix and carry different random suffixes."
metadata:
  type: reference
---

Verified on a real builder-authored page: `extra.nodeId` equalled `"c" + id` for
**0 of 78 nodes**. They share the type prefix (`button-` / `cbutton-`) and nothing else.

Consequences that bite:

- **Stripping the leading `c` off a scraped rendered id matches nothing.** The only link
  between the two is `extra.nodeId` on the authoring node — read the pair off the tree,
  never reconstruct it.
- **Emit each CSS rule against BOTH ids.** The division of labour is systematic:
  sections/rows/columns carry padding, background and borders on the *authoring* id, while
  element **appearance** — font, colour, fill, padding — keys off the *rendered* id.
- The cost of doing that correctly: a button's background paints the wrapper as well as
  the `<button>`. Invisible while the wrapper hugs the button, a full-width slab of accent
  colour the moment it does not. Force the wrapper transparent.
- **Never target an exact id in a hand-written stylesheet.** Match the type prefix:
  `[class*=section-]`, `[class*=cbutton-]` — which catches both namespaces at once.

Minting `nodeId = "c" + id` for elements you *create* is a fine convention (it only has to
be unique and `c`-prefixed), but it is a convention, not a fact about GoHighLevel. Code
that assumes it works on pages you generated and breaks on pages you captured.

See [[ghl-section-styles-injected-after-your-stylesheet]], [[ghl-nuxt-data-devalue-decoding]].
