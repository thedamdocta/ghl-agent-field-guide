---
name: ghl-never-probe-internal-host-with-empty-body
description: "POSTing an empty body to backend.leadconnectorhq.com is a write, not a question: it returns 200 and creates a nameless workflow."
metadata:
  type: reference
---

`POST backend.leadconnectorhq.com/workflow/{locationId}` with `{}` returns **200 and
creates a nameless workflow in the account.** Reported by a second account, 2026-08-09.

The internal host **does not validate request bodies at all**, so there is no 422 to read
and every probe leaves an artefact behind in a client's account. The
422-as-documentation technique is a *public host* technique and nothing else.

This is a good example of the wider rule that two GoHighLevel hosts are two different
services with different behaviour, not one API with quirks. A habit that is safe and
productive on `services.` litters the account on `backend.`.

Probe the public host freely. For the internal host, discover shapes by capturing what the
web app itself sends.

See [[ghl-422-is-free-schema-documentation]], [[ghl-two-hosts-two-schemes]],
[[ghl-endpoint-guessing-returns-200-for-nonsense]].
