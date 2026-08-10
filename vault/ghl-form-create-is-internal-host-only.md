---
name: ghl-form-create-is-internal-host-only
description: Form create is POST backend.../forms/ with the internal JWT, and the new id is at response[form][_id], not response[id].
metadata:
  type: reference
---

`POST services.leadconnectorhq.com/forms/` returns
`401 "This route is not yet supported by the IAM Service."` The public host cannot create
a form. **Both calls are on the internal host with the `token-id` JWT.**

    1. CREATE    POST backend.../forms/         {"locationId": "...", "name": "..."}
                 -> the id is at  response["form"]["_id"]   (response["id"] is None)
    2. VERIFY    GET  backend.../forms/{id}     poll until readable
    3. POPULATE  POST backend.../forms/{id}     {"name": "...", "formData": {...}}
                 -> locationId must NOT be in this body

Reading the wrong id key means you POST to `/forms/None` and get
`400 "form does not exist or is deleted"` — an error that sounds like the form was never
created when in fact you are asking about the wrong id.

Note the asymmetry: **CREATE requires `locationId` and UPDATE rejects it**, same verb,
same route family. Including it in the update body returns
`422 "property locationId should not exist"`; omitting `name` returns
`422 "name must be a string"`.

And `POST /forms/{id}` **is** the update route — `PUT` and `PATCH` both return `404`.

See [[ghl-form-create-populate-lag]], [[ghl-token-id-not-bearer]],
[[ghl-422-is-free-schema-documentation]].
