---
name: ghl-funnel-gets-its-own-form
description: Pointing a funnel page at a pre-existing generically-named account form imports that form's fields, image, header, branding and fixed width into your funnel.
metadata:
  type: feedback
---

The client's report was: *"the form is too big, it has fields that don't belong, it
stretches the page and isn't centred."*

The page had been pointed at a generically named form ("Registration", "Contact Us") that
already existed in the account for an unrelated intake flow. Reading it back showed **six
fields where three were expected**, plus its own image, its own linked header, its own
submit-button markup, a fixed pixel width, and several thousand characters of its own
`fieldCSS`. All of it rendered inside the new funnel.

And restyling it would have changed the form **everywhere else it is embedded**.

**A funnel gets its own form.** Build the new one by cloning a working form's `formData`
schema and deleting the fields you do not want — hand-written field dictionaries miss
required keys — and inspect the clone's role-bearing fields before adopting it.

On a fresh sub-account there is no donor form, and a form created through the UI's Create
button carries essentially empty `formData` so it cannot seed a clone. You do not need
one: create the record, then write a known-good seed schema.

See [[ghl-exemplar-carries-its-role]], [[ghl-form-create-is-internal-host-only]],
[[ghl-form-submit-behaviour-on-page-element]], [[ghl-test-the-empty-account-case]].
