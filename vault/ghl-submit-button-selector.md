---
name: ghl-submit-button-selector
description: "The GoHighLevel form submit button is #_builder-form .ghl-submit-btn, not button[type=submit], and :last-child matches every field rather than the submit row."
metadata:
  type: reference
---

The class names inside a GHL form document are not guessable. This map cost real time to
assemble:

| target | selector |
|---|---|
| text / email / phone / textarea | `#_builder-form .form-builder--item .form-control` |
| placeholder | `... input::placeholder` — set `opacity:1`, Firefox dims it |
| **submit button** | `#_builder-form .ghl-submit-btn` |
| labels | `#_builder-form label` |
| validation text | `#_builder-form .error-message` |
| consent / terms | `.checkbox-container`, `.terms-and-conditions`, `.terms-text-container *` |
| phone country prefix | `.form-builder--item span[class*="prefix"]` |
| dropdowns | the `.multiselect` family — **eight** separate selectors |

Two that catch people. A dropdown is a vue-multiselect widget: style the container, the
tag wrapper, the inner input **and** `.multiselect__content-wrapper`, or the open menu
renders white-on-white. The terms block arrives as author-controlled HTML with its own
inline colours, so it needs the `*` descendant rule to be reached at all.

**The trap that cost the most:** `.form-builder--item:last-child` reads as "the submit
row". Every field is an only child of its own `.form-builder--item`, so it matches **all
of them** — in production it threw validation messages sideways and squeezed every input
from 338px to 138px.

See [[ghl-form-css-lives-in-fieldcss]].
