---
name: ghl-section-styles-injected-after-your-stylesheet
description: "Page CSS lives in section.general.sectionStyles, which GoHighLevel injects AFTER your own stylesheet, so every equal-specificity tie loses. — SYMPTOM: CSS applied but nothing changed on the page"
metadata:
  type: reference
---

**GHL does not compile an element's `styles` dict into CSS at render time.** The builder
generates one CSS string per section, stored at `section.general.sectionStyles`, with
every rule scoped to a specific element id under the prefix
`.hl_page-preview--content .`. A from-scratch page generator **must emit that string for
its own ids or nothing is styled** — the `styles` dict alone renders an unstyled page.

Three stylesheets reach a page, in load order: GHL's platform sheet; your page-level
`<style>` (which rides in a `custom-code` element); and `sectionStyles`, in section order.
Yours is number two. GHL's is number three and wins every tie.

Match the builder's mobile query verbatim —
`@media screen and (min-width:0px) and (max-width:480px)` — rather than improving it to a
plain `max-width`; identical query text is what keeps the two sheets from interleaving
surprisingly.

**Replace `sectionStyles` wholesale; never merge into it.** Appending lets a stale
builder hand-edit survive and silently fight your generated rules, and which one wins
depends on emission order.

Never emit GHL's internal layout hints as CSS properties — `colWidth`, `rowWidth`,
`forceColumnLayoutForMobile`, `visibility`, `sticky`, `entranceAnimation` and friends are
not declarations.

See [[ghl-important-does-not-settle-a-tie]], [[ghl-node-id-is-not-c-plus-id]].
