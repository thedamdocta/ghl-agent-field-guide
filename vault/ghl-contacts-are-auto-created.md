---
name: ghl-contacts-are-auto-created
description: GoHighLevel auto-creates a contact on any inbound channel interaction, so a workflow must never include a create-contact step.
metadata:
  type: reference
---

Form submission, inbound SMS, inbound email, phone call, chat widget message — all of
them create the contact automatically. This is not in the public documentation.

By the time a workflow trigger fires, **the contact exists and its `{{contact.*}}` fields
are already populated.** Workflow design therefore starts at step two: create opportunity,
add tags, route to pipeline, notify, confirm. Never step one.

Adding an explicit create-contact action produces duplicate or redundant steps and
occasionally duplicated records.

Related distinction that is easy to blur: a per-**contact** custom FIELD (written by
`update_contact_field` with a `field_id`) is not the same thing as a per-**account** custom
VALUE (`{{custom_values.x}}`). They look similar in prose and live in different systems.

See [[ghl-custom-value-needs-two-surfaces]], [[ghl-tag-conditions-need-a-producer]].
