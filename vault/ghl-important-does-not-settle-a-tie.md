---
name: ghl-important-does-not-settle-a-tie
description: !important ranks you against non-important rules only; it cannot beat a later same-specificity important rule, so raise specificity instead.
metadata:
  type: reference
---

A form stayed **333px** wide against a **440px `!important`** rule. Both selectors were
specificity `(0,2,0)` and GoHighLevel's came second in source order. `!important` did not
save it, because it ranks you against *non*-important rules and does nothing against a
later same-specificity rule in the same important tier.

The fix is a **tag qualifier**, which raises specificity:
`.hl_page-preview--content div[class*=cform-]` at `(0,2,1)` beats `(0,2,0)`.

Two more rungs worth knowing. A page-level `.hl_page-preview--content h1` is `(0,1,1)` and
loses to an element rule at `(0,2,0)` — which is how a source file that plainly says one
colour ships text in another. Add one descendant step, `[class*=section-] h1` at
`(0,2,1)`, or set the colour per element and mean it. And GHL emits **`#id` rules** (77 on
one page, carrying `margin`, `width`, `height`) that no class can beat: match with an id
of your own, or change the element's `styles` so the emitter writes the value.

A media query adds **no** specificity.

Diagnose by reading **computed** style and walking the ancestor chain. A rule that is
present and losing looks exactly like a rule that is absent.

See [[ghl-section-styles-injected-after-your-stylesheet]], [[ghl-200-is-not-proof]].
