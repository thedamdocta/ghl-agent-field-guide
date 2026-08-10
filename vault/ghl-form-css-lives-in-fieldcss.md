---
name: ghl-form-css-lives-in-fieldcss
description: "Form CSS goes in the form record at formData.form.fieldCSS, written through the internal host — page CSS cannot reach into a form and form CSS cannot escape it. — SYMPTOM: CSS not applying to the form; form looks unstyled"
metadata:
  type: reference
---

They are **different documents**. Put form rules on the page and precisely nothing
happens; the page still returns 201 and the preview still renders, which is why the
failure is quiet.

The write is `POST backend.../forms/{formId}` with the `token-id` header set — scripted,
diffable, verifiable, and strictly better than pasting into the builder textarea. The
public API has no form-write operation at all.

**Every rule needs `!important`.** GHL ships its own stylesheet inside the form document
and it loads *after* yours, so an equal-specificity rule loses on source order. Without
`!important` roughly half your rules silently do nothing.

**The practical consequence people miss: a submit button has to be styled twice.** Once on
the page for the page's own CTA, once in `fieldCSS` for the one inside the form. Style it
in one place only and the funnel ships two different buttons, one of which you did not
design.

On size: the ~8KB ceiling was measured against the **builder's textarea**, where a 14KB
paste appeared to save and persisted random partial chunks, differently on different
forms. An API write bypasses that textarea and ~2KB persisted cleanly. **UNVERIFIED
whether 8KB+ survives the API path** — read the stored value back and compare its length,
because silent truncation is the failure mode.

See [[ghl-submit-button-selector]], [[ghl-preview-url-is-read-only]].
