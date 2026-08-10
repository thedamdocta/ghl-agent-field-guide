---
name: ghl-form-submit-behaviour-on-page-element
description: Redirect-after-submit lives on the page element that hosts the form, not on the form record — writing it to the form returns 200 and does not persist.
metadata:
  type: reference
---

On a funnel page the behaviour sits in the form element's `extra`:

    "extra": {
      "formId": {"value": "<formId>", "text": "<display name>"},
      "form_submit_type": "ThankYouMessage",
      "form_submit_redirect_url": ""
    }

Writing `formAction.actionType` / `redirectUrl` onto the **form record** returns `200` and
**silently does not persist** — verified by round-trip. There is no API-layer check that
catches this; the record write "succeeds". Detection is to submit the form on the public
preview and observe where you land.

**UNVERIFIED:** only `"ThankYouMessage"` has been observed in captured production pages.
`"Redirect"` is a candidate value, inferred rather than confirmed. Settle it by setting the
option once in the builder and re-capturing, or with one real test submission — and do not
describe redirect-on-submit as working until then.

The generalisation, which is the transferable half: **ask which object owns this behaviour
before you write it.** A form embedded in a page has its properties split across two
records, and the split is not documented anywhere.

See [[ghl-form-inline-on-page-iframe-elsewhere]], [[ghl-existence-is-not-wiring]].
