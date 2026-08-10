---
name: ghl-custom-code-payload-is-extra-customcode
description: A custom-code element's payload field is extra.customCode — guessing code, html or text yields an element that renders and a script that never runs.
metadata:
  type: reference
---

This is how a page-level stylesheet or script gets onto a GoHighLevel page, and three of
its rules are undocumented and all of them fail silently.

**The payload field is `extra.customCode`.** Guessing `code` / `html` / `text` produces an
element that renders as an empty block.

**`<script>` must not be nested inside a `<div>`.** The `<link>`, `<style>` and `<script>`
tags must be siblings at the top level of the payload.

**The script must wait for GHL's `hydrationDone` event, and the page's "Optimise
JavaScript" setting must be OFF** — otherwise hydration defers and your script runs
against a DOM that is not there yet.

Two more things learned from shipping it. Load fonts with `<link>` plus `preconnect`,
never `@import`; `@import` serialises the font fetch behind the stylesheet parse and
delays first paint. And **the section carrying the stylesheet has no visible content and
must be forced to occupy no space** — left alone it keeps whatever padding its exemplar
had, the emitter then forces that padding, and the page ends in a hundred-odd pixels of
nothing beneath the footer.

See [[ghl-section-styles-injected-after-your-stylesheet]], [[ghl-preview-url-is-read-only]].
