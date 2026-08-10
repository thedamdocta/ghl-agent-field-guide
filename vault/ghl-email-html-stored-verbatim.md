---
name: ghl-email-html-stored-verbatim
description: An email template created with editorType html stores your editorContent verbatim — round-trip byte-identical, unlike funnel pages which GHL recompiles.
metadata:
  type: reference
---

This makes email the *easy* surface in GoHighLevel: you generate markup, you push it,
and that exact markup is what sends. Round-trip comparison showed the stored content
byte-identical to what was posted, with only two **additions** — an
`outlook-fixes-applied` comment and MSO font-colour fallbacks. No MJML recompilation, no
re-nesting, no attribute stripping.

The endpoint is `POST /emails/locations/{locationId}/templates` on the public host with a
PIT — no browser JWT, no OAuth. Body: `name`, `editorType: "html"`, `editorContent`,
`subjectLine`, `previewText`, `fromName`.

A practical consequence: **hand-authored email HTML is generally better than builder
output**, because builder paste artifacts — overridden font stacks, triplicated inline
colours, arbitrary type scales — are a common source of ugly email. Generating the markup
yourself removes that whole class of defect.

A successful create/update returns `data.id` and **`data.previewUrl`**, a hosted rendering
of the stored template. That is your verification surface: fetch it and confirm a
distinctive phrase from your copy is present.

Templates carry real names, so listing and matching by name before create-vs-update keeps
re-runs idempotent. That is safe here and **not** safe for forms.

See [[ghl-email-writes-need-idempotency-key]], [[ghl-email-svg-does-not-render]],
[[ghl-forms-list-returns-name-null]].
