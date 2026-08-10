---
name: ghl-form-inline-on-page-iframe-elsewhere
description: A GHL form renders inline in the page document on a GHL funnel page, but arrives as an iframe on any third-party site.
metadata:
  type: reference
---

Verified by finding `.ghl-form-wrap` in the main frame of a funnel page. **Page CSS
reaches it there**, so the submit button can be unified with page buttons from your own
stylesheet — do not assume iframe isolation and lose a working styling path.

Off-platform it is `api.leadconnectorhq.com/widget/form/{formId}` in an iframe, and your
stylesheet cannot cross that boundary. `fieldCSS` is the only lever.

Three facts about the external embed:

- **Inline embed, popup mode and the direct widget URL are the same iframe** with the same
  constraints and identical submission attribution. The only real difference is stacking
  context: a popup is `position: fixed` and escapes an ancestor transform, an inline embed
  inherits it. A `zoom: 0.5` page shell once rendered a 560px form at 280px while the
  popup was fine.
- **There is no auto-resize.** The widget does not postMessage its height, so the
  embedding page must pin one. 780px fit a real deployment including consent checkbox and
  footer links; the widget caps content at roughly 500px wide internally, so wider than
  ~560px gives dead background.
- **Skip `form_embed.js` if you write the iframe yourself.** It rescans ~500ms after load,
  removes your element and rebuilds a fresh iframe — a second load and a visible flash.

See [[ghl-form-css-lives-in-fieldcss]], [[ghl-submit-button-selector]].
