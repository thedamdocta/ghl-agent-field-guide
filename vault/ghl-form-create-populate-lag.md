---
name: ghl-form-create-populate-lag
description: "A newly created form is not immediately readable — populating right away returns 400 form does not exist against an id you received seconds earlier. — SYMPTOM: HTTP 400 form does not exist or is deleted right after creating it"
metadata:
  type: reference
---

There is **read-after-write lag** between the create call and the populate call. Even
with the right id key, the identical call that fails immediately succeeds a minute later.
In live testing the form became readable on the second check.

**Poll `GET /forms/{id}` until it resolves before populating. Do not `sleep`.** A fixed
sleep is the wrong shape: too short still fails, and too long makes every subsequent run
pay the worst case.

The same patience applies to your verification. The update response **does not echo the
stored `formData`**, and reading back immediately returns an empty `formData` — so a
single check reports "no fields stored" while the fields are stored. That false negative
sends you debugging a write that worked. Retry the read-back too.

Timing is a variable on this platform generally: poll for the condition, and treat an
immediate empty read as unproven rather than as evidence of failure.

See [[ghl-form-create-is-internal-host-only]], [[ghl-200-is-not-proof]].
