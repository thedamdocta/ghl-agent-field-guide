---
name: ghl-forms-list-returns-name-null
description: "GET /forms/?locationId=... returns name: null for API-created forms, so any does-my-form-exist check that matches on name creates a duplicate every run."
metadata:
  type: reference
---

Forever. Every run. Nothing errors.

**Persist the created form id to disk and match on the id**, which is the only stable key
you have.

Reported by a second account (2026-08-09) and worth knowing: `name: null` appears
**specific to API-created forms**. UI-created forms carry a real name, which narrows the
trap usefully but does not remove it.

Note the contrast with email templates, which *do* carry real names — there, listing and
matching by name before deciding create-vs-update is exactly the right idempotency
strategy. The same technique applied to forms litters the account. **Two resource families
in one platform, opposite answers, because one of them has a natural key and the other
does not.**

The wider habit: before writing an idempotency check, confirm the field you are matching
on is actually populated for objects created the way *you* create them.

See [[ghl-funnel-gets-its-own-form]], [[ghl-email-html-stored-verbatim]].
