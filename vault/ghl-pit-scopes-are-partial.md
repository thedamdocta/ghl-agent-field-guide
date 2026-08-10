---
name: ghl-pit-scopes-are-partial
description: A Private Integration Token can create and update a resource and still be refused permission to delete it — read and write scopes are not one axis.
metadata:
  type: reference
---

Verified on email templates with a token that had template scopes: **create succeeded,
update succeeded, delete returned `401 "token is not authorized for this scope"`.** Same
token, same resource family.

Two consequences.

**Retire, do not delete.** Where a delete is refused, `PATCH archived: true` is generally
accepted. Design cleanup around archiving from the start.

**Probe destructive verbs at the START of a job, not the end.** Create one throwaway
object and try to delete it before you build a cleanup routine on top of the assumption.
A delete that 401s after a batch job leaves the client's account littered.

A PIT created inside a sub-account is also sub-account scoped. `GET /locations/search`
returns **403** and `GET /oauth/installedLocations` returns **401**, so always pass
`locationId` explicitly and never write code that expects to discover the location from
the token. Whether an agency-scoped PIT clears those is **UNVERIFIED**.

Read a `401` from a PIT as "missing scope" at least as readily as "closed route" —
re-test with the internal JWT before concluding a route is walled. Scopes are chosen once
at creation in the UI and the token is displayed once, so grant everything you plausibly
need up front.

See [[ghl-two-hosts-two-schemes]], [[ghl-endpoint-guessing-returns-200-for-nonsense]].
