# GoHighLevel API Map — What Is Reachable, What Is Walled, What Is Gone

> **Status:** every status code in this file was observed against a live GoHighLevel
> account between 2026-07-27 and 2026-08-06. Anything not actually exercised is marked
> **UNVERIFIED**. Read `auth.md` first — none of this makes sense without the
> two-hosts/two-schemes model.

---

## The mental model

Every capability on GoHighLevel falls into one of four tiers. Before you write a line
of code against a feature, decide which tier it is in — that decision determines your
credential, your host, and whether the work is even possible.

**Tier 1 — Public API, reachable with the PIT.** `services.leadconnectorhq.com`.
Contacts, custom values, email templates, media, opportunities, form *reads*. This is
also the tier GoHighLevel's own MCP server fronts, which means you should discover
these endpoints by asking the MCP catalogue rather than by guessing paths.

**Tier 2 — Internal API, reachable only with the browser `token-id` JWT.**
`backend.leadconnectorhq.com`. This is the API the GoHighLevel web app itself calls.
Funnel page autosave, workflow create/update, form writes. The PIT does not reach this
host at all.

**Tier 3 — IAM-walled.** A real route family that returns
`403 "This route is not yet supported by the IAM Service. Please update your IAM
config."` for **both** the PIT and the JWT. This is a platform-side gate, not a scope
problem. There is no credential that opens it. When you hit this, stop probing and go
find the route the UI actually uses.

**Tier 4 — Gone or nonexistent.** Routes that were removed (`customValues/bulk`) or
that never existed and only *appear* to work because of a path-matching quirk. Tier 4
is dangerous precisely because it can return `200`.

The governing rule across all four tiers:

> **Discover endpoints by capturing what the GoHighLevel UI does, or by querying the
> MCP catalogue. Never by guessing path names.** Guessing produced false positives
> twice in a single session, and each one looked like a discovery.

---

## Capability table

Verbs listed are the ones we actually exercised. Blank cells mean untested, not
unavailable.

| Capability | Host / credential | Route | Status |
|---|---|---|---|
| List custom values | public / PIT | `GET /locations/{locationId}/customValues?limit=200` | Works |
| Create custom value | public / PIT | `POST /locations/{locationId}/customValues` | Works |
| Update custom value | public / PIT | `PUT /locations/{locationId}/customValues/{id}` | Works — **`name` required, see below** |
| Bulk update custom values | public / PIT | `PUT /locations/{locationId}/customValues/bulk` | **GONE** — no such route |
| Create email template | public / PIT (via MCP) | `POST /emails/locations/{locationId}/templates` | Works — `editorType:"html"` |
| Update email template | public / PIT (via MCP) | `PATCH /emails/locations/{locationId}/templates/{templateId}` | Works |
| List email/SMS templates | public / PIT (via MCP) | `GET /locations/{locationId}/templates` | Works (paginate on `skip`) |
| Delete email/SMS template | public / PIT (via MCP) | delete op | **401** scope-denied — archive instead |
| Create template folder | public / PIT (via MCP) | catalogue op `create-template-folder` | **UNVERIFIED** — present in catalogue, never exercised |
| Import email template | public / PIT (via MCP) | catalogue op `import-email-template` | **UNVERIFIED** — present in catalogue, never exercised |
| Upload media | public / PIT | `POST /medias/upload-file?locationId={locationId}` | Works — multipart; see below |
| List forms | public / PIT | `GET /forms/?locationId={locationId}&limit=50` | Works — **returns `name: null`, see trap** |
| Create form | internal / JWT | `POST /forms/` body `{locationId, name}` | Works — id at `.form._id` |
| Update form | internal / JWT | `POST /forms/{formId}` | Works — **PUT and PATCH both 404** |
| Delete form | internal / JWT | `DELETE /forms/{formId}` | Works |
| Read funnel page | internal / JWT | `GET /funnels/page/{pageId}` | Works |
| Write funnel page | internal / JWT | `POST /funnels/builder/autosave/{pageId}` | **201** — the only page write path |
| Write funnel page (REST) | either | `PUT /funnels/page` | **403 IAM** on both hosts, both credentials |
| Write funnel page (REST) | internal | `POST /funnels/page` | **404** — no such route |
| Create workflow | internal / JWT | `POST /workflow/{locationId}` body `{name}` | Works — returns id |
| Update workflow | internal / JWT | `PUT /workflow/{locationId}/{workflowId}` | Works — body `{name, workflowData, version}` |
| Read workflow | internal / JWT | `GET /workflow/{locationId}/{workflowId}` | Works — read `version` before writing |
| Create workflow | public / PIT (via MCP) | — | **Not in the catalogue** |
| Add/remove contact in workflow | public / PIT (via MCP) | `add-contact-to-workflow` etc. | Available |
| List funnel pages | public / PIT (via MCP) | `getPagesByFunnelId` | Read-only |
| Agency-scope location search | public / PIT | `GET /locations/search` | **403** with a sub-account PIT |
| Installed locations | public / PIT | `GET /oauth/installedLocations` | **401** with a sub-account PIT |
| Create pipeline | either | — | **Failed** on both hosts in a 2026-04-28 test. UI only. Worth re-testing |
| Read page document | Firebase / same JWT | `GET firestore…/funnel_pages/{pageId}` | **200** |
| Read page-data object | Firebase / same JWT | `GET firebasestorage…/o/{path}?alt=media` | **200** — `alt=media` mandatory |
| Write page-data object | Firebase / same JWT | `POST firebasestorage…/o?name=…&uploadType=media` | **200** — but see the compile trap |
| Repoint page document | Firebase / same JWT | `PATCH firestore…?updateMask.fieldPaths=…` | **200** — but see the compile trap |

---

## The 422 pattern: treat validation errors as free schema documentation

This is the single most useful habit on this platform.

GoHighLevel's body validator runs before authorization, and **it names the offending
property in the error message**. That means you can extract the required shape of any
endpoint without documentation, without guessing, and without a single successful
request — by deliberately sending a wrong body and reading what it complains about.

**The technique: POST an empty object first.**

```bash
curl -sS -X POST "https://backend.leadconnectorhq.com/funnels/builder/autosave/{pageId}" \
  -H "token-id: <FIREBASE_ID_TOKEN>" \
  -H "channel: APP" -H "source: WEB_USER" -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  -A "Mozilla/5.0" \
  -d '{}'
```

The 422 that comes back names the required fields — in this case `funnelId`, `pageData`,
`pageVersion`. That is the whole request contract, obtained in one call.

The same mechanism works in the negative direction, telling you about fields that must
**not** be present:

```
PUT /locations/{locationId}/customValues/bulk   body {customValues:[{id,value}]}
  -> 422 "property customValues should not exist / name must be a string"
```

Read that carefully. It is not saying "bulk is broken." It is saying **"I am the
per-value schema, and you sent me a bulk body"** — which is how we learned that `bulk`
was being parsed as an `{id}` path segment and that the bulk route no longer exists at
all. The error told us the truth about the routing table.

Three more real examples of the same pattern:

| What was sent | 422 says | What it teaches |
|---|---|---|
| `locationId` as a **query** param | `"property locationId should not exist"` | `locationId` belongs in path or header |
| `locationId` inside a form-update **body** | `"property locationId should not exist"` | Post a minimal body first to learn the shape |
| MCP `execute_operation` with `locationId` in `params.query` | `"property locationId should not exist"` | Same rule holds through the MCP layer |

**Habit to adopt:** when an endpoint is unfamiliar, send `{}` before you send anything
real. One throwaway request buys the entire contract, and it costs nothing because a
422 changes no state.

**The corresponding discipline:** a 422 means the *validator* accepted your identity
enough to inspect your body. It does **not** mean you are authorized. We twice read a
`401 -> 422` transition as "auth unlocked," and both times the real payload then
returned `403 IAM`. A 422 proves shape. Only a successful write proves permission.

---

## `locationId` goes in the path, not the query

Across the public API, `locationId` is a **path segment**:

```
GET  /locations/{locationId}/customValues
PUT  /locations/{locationId}/customValues/{id}
POST /emails/locations/{locationId}/templates
```

Passing it as a query parameter returns `422 "property locationId should not exist"`.
The same rule survives the MCP wrapper: put it in `params.path`, never `params.query`.

**Two verified exceptions, so you do not over-generalise:**

```
POST /medias/upload-file?locationId={locationId}     <- query, and it works
GET  /forms/?locationId={locationId}&limit=50        <- query, and it works
```

Media upload and the forms list genuinely take it in the query. The rule is a strong
default, not a law. When in doubt, send it in the path, and let the 422 correct you.

---

## `customValues/bulk` is gone — the per-value path is the only path

Tested live 2026-08-06 while porting code that had used the bulk route successfully in
November 2025. It worked for that author then. It does not work now.

```
PUT /locations/{locationId}/customValues/bulk
    body {customValues:[{id, value}]}
  -> 422 "property customValues should not exist / name must be a string"
```

Confirmed by sending a *per-value* body to the same URL:

```
  -> 404 "The custom value id is invalid."
```

So `bulk` is being parsed as the `{id}` path segment. **The route was removed, not
renamed.**

### The working path

```bash
# read
curl -sS "https://services.leadconnectorhq.com/locations/{locationId}/customValues?limit=200" \
  -H "Authorization: Bearer <YOUR_PIT>" -H "Version: 2021-07-28" -A "Mozilla/5.0"

# write — one call per value
curl -sS -X PUT "https://services.leadconnectorhq.com/locations/{locationId}/customValues/{customValueId}" \
  -H "Authorization: Bearer <YOUR_PIT>" -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" -A "Mozilla/5.0" \
  -d '{"name":"webinar_date","value":"2026-09-01T18:00:00-04:00"}'
```

Four things about this endpoint that are easy to get wrong:

**`name` is REQUIRED, not just `value`.** And you should source `name` from the live
record you just read, never from a constant in your own code — otherwise a value update
can silently rename the key and break every `{{custom_values.*}}` reference on every
page and email that used it.

**`name` and `fieldKey` are different strings.** `name` is the bare snake_case key
(`webinar_date`). `fieldKey` is the wrapped form — `{{ custom_values.webinar_date }}`,
**with braces AND spaces**. Matching `fieldKey` by string equality against a bare key
returns "all missing" for every value. Use a regex.

**A per-value PUT needs an id that already exists.** Creating the value is a separate
`POST` to `/locations/{locationId}/customValues`. Writing to a key that does not exist
yet has nothing to address.

**Read-after-write is consistent.** Zero stale reads across a ten-iteration test — a
form or script can re-hydrate immediately after saving.

**Design consequence:** probe `bulk` once per process, memoise the failure, fall through
to per-value writes. Twenty-odd individual calls is a perfectly reasonable number; the
fallback is not a compromise.

---

## The endpoint-guessing trap — why a 200 can be meaningless

Learned 2026-07-27 after twice believing a nonexistent endpoint was real.

`backend.leadconnectorhq.com/funnels/funnel/{x}` accepts **any** string as an id and
falls through to a generic get-by-id route. So all of these return `200`:

```
GET /funnels/funnel/ai                    -> 200  {"_id":"ai", "_ref":{_firestore:…}}
GET /funnels/funnel/clone                 -> 200  {"_id":"clone", …}
GET /funnels/funnel/import-clickfunnels   -> 200  {"_id":"import-clickfunnels", …}
```

None of these are AI, clone, or import routes. They are one route, echoing your path
segment back at you.

### The control that proves it

```
GET /funnels/funnel/zzzznotreal   -> 200, IDENTICAL shape {"_id":"zzzznotreal", …}
GET /funnels/page/zzzznotreal     -> 400, IDENTICAL to /funnels/page/ai
```

**Always probe a deliberately nonsense id first and compare.** If the nonsense id
behaves the same as your "discovery," you have discovered nothing. This one-line control
would have saved hours.

### The two responses that *are* real signals

- **`403 "This route is not yet supported by the IAM Service"`** — you found a genuine
  route family, and it is walled. Real information.
- **`401` from a PIT** — may be nothing more than a missing scope on a sub-account
  token. Re-test with the account JWT before concluding the route is closed.

### What actually discovers an endpoint

**Capture real traffic while the GoHighLevel UI performs the action.** Devtools Network
panel, or an automation tool's request log. That is how the `token-id` header itself was
found, and how the funnel autosave route was found. Both were invisible to guessing.

Generalised: **when a system resists probing, make it perform the action while you
observe passively, then read the artifacts it produces.** Watching beat guessing,
decisively, every time we tried both.

---

## The IAM wall — funnel page writes via REST do not exist

Do not re-attempt these. Confirmed for **both** the PIT and the account JWT:

| Endpoint | Empty body | With a real `locationId` |
|---|---|---|
| `PUT services…/funnels/page` | 422 (validator) | **403 IAM** |
| `PUT backend…/funnels/page` | 422 (validator) | **403 IAM** |
| `POST backend…/funnels/page` | — | **404** (no such route) |

The REST write path for funnel pages is not a scope problem you can solve with a better
token. It is a platform gate.

### The write path that does work

```bash
curl -sS -X POST "https://backend.leadconnectorhq.com/funnels/builder/autosave/{pageId}" \
  -H "token-id: <FIREBASE_ID_TOKEN>" \
  -H "channel: APP" -H "source: WEB_USER" -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" -A "Mozilla/5.0" \
  -d '{"funnelId":"{funnelId}","pageData":{ /* full authoring tree */ },"pageVersion":3}'
# -> 201 Created. Response carries the NEW pageDataUrl + pageDataDownloadUrl.
```

`201`, and GoHighLevel writes the page-data object **and recompiles the page**. That
recompilation is the whole point, and it is what the next section is about.

Sibling endpoints observed in the same builder Save action, **UNVERIFIED** — seen in
captured traffic, never exercised by us:

```
POST /funnels/builder/prebuilt-section/sync/changes
POST /funnels/builder/element-template/sync/changes
POST /funnels/builder/global-sections/{funnelId}
```

---

## The compile trap — the most expensive false victory in this corpus

The `token-id` JWT is a Firebase ID token, so it authenticates directly to Firestore and
Firebase Storage (see `auth.md`). That is real, and it is genuinely useful for
**reading** the native page authoring tree. Every step below was confirmed `200`:

```
GET   firestore…/funnel_pages/{pageId}                        -> 200  (page_data_url, page_version)
GET   firebasestorage…/o/{urlencoded-path}?alt=media          -> 200  (the authoring tree)
POST  firebasestorage…/o?name={new-path}&uploadType=media     -> 200  (uploads a new object)
PATCH firestore…/funnel_pages/{pageId}?updateMask.fieldPaths=…-> 200  (repoints + bumps version)
DELETE firebasestorage…/o/{urlencoded-path}                   -> 204
```

**And the live page never changes.**

GoHighLevel **compiles** pages at save time. The served page is a build artifact, not a
live read of `page_data_url`. You can rewrite the source object, repoint the document,
watch the GHL REST API cheerfully echo your new values back — and the rendered site
still serves the old build. The builder also holds its own draft and will overwrite a
raw storage edit on its next save.

**The general lesson, which cost two false victories in one session:**

> A `200`, plus an API echoing your own write back at you, is **not** proof that a change
> took effect. Verify at the surface the user actually experiences.

### How to verify a page write — the only proof

```
https://sites.leadconnectorhq.com/preview/{pageId}
```

Public, server-rendered, no connected domain required. `curl` it and grep for your
changed text. If your string is not in that HTML, your write did not land, whatever the
status code said.

Two useful properties of GHL pages worth knowing while you are here: they are genuinely
server-rendered (`data-ssr="true"`), which is why external crawlers and compliance
scanners can read them where a client-rendered SPA would fail. And a GHL form embedded
in a page renders **inline in the page document, not in an iframe** — page CSS reaches
it, so form controls can be styled from the page stylesheet. Do not assume iframe
isolation.

---

## Traps in specific resource families

### Forms — the list endpoint returns `name: null`

`GET /forms/?locationId={locationId}` returns `name: null` for forms created through the
backend API. **Any "does my form already exist?" check that matches on name will always
miss and create a duplicate**, every run, forever. Persist the returned form id to disk
and match on the id.

Two more form facts, both verified:

- `POST /forms/{formId}` is the **update** route. `PUT` and `PATCH` both 404.
- The update body **422s if it contains `locationId`**. The error names the property —
  post a minimal body first to learn the shape.

And one design rule, learned from a client-visible bug: **a funnel gets its own form.**
Pointing a funnel page at a pre-existing, generically-named account form ("Registration",
"Contact Us") imports that form's fields, image, linked header, fixed width, and
thousands of characters of its own `fieldCSS` into your page. Restyling it would also
change it everywhere else it is embedded. Build the new form by **cloning a working
form's `formData` schema** and deleting the fields you do not want — hand-written field
dictionaries miss required keys.

### Media — upload to the client's own library, always

```bash
curl -sS -X POST "https://services.leadconnectorhq.com/medias/upload-file?locationId={locationId}" \
  -H "Authorization: Bearer <YOUR_PIT>" \
  -H "Version: 2021-07-28" \
  -A "Mozilla/5.0" \
  -F "file=@./local-asset.mp4;type=video/mp4" \
  -F "hosted=false" \
  -F "name=asset.mp4"
# -> {"fileId":"…","url":"https://assets.cdn.filesafe.space/{locationId}/media/{uuid}.mp4"}
```

Verified for mp4 video and for PNG with alpha preserved. The returned URL is the same
form the funnel builder itself uses, so it is safe to reference directly from page CSS.

**Why it matters:** anything a live page depends on belongs in the client's own media
library. Third-party generation-service CDN links are outside the client's control and
vanish when someone deletes a generation upstream.

### Workflows — creatable via the internal API, contrary to the MCP catalogue

The MCP catalogue offers no `create-workflow` operation, which makes it easy to conclude
that workflows must be hand-built in the UI. **That conclusion is wrong.** The internal
API creates and updates them:

```
POST /workflow/{locationId}          body {"name": "..."}            -> {id}
GET  /workflow/{locationId}/{id}                                     -> read current `version`
PUT  /workflow/{locationId}/{id}     body {name, workflowData, version}
```

All with the Scheme-2 header set. Verified: four workflows created and updated this way,
read back with all steps and template references intact.

Two operational notes. **The internal API happily creates duplicates** — it does no
name-deduplication, so persist created ids and `PUT` over them rather than `POST`ing
again. And **read the current `version` before a `PUT`**; the update body carries it.

Workflow step schemas are dense and should be **read off real, working workflows in the
account rather than guessed** — the same capture-don't-guess principle as everywhere
else. One concrete example of why: there are two distinct kinds of wait step, an elapsed
wait (`type: "time"`) and an event-anchored wait (`type: "appointment"` with
`appointmentStartAfter`), and an elapsed wait fundamentally **cannot** express "three
hours before the event" when every contact enters at a different offset. Anchored waits
show an empty `startAfter` — the timing lives in the other field. Getting this wrong
produces automations that fire at absurd times.

### Contacts are auto-created — never add a "create contact" step

Any inbound channel interaction — form submission, SMS, email reply, call, chat — creates
the contact automatically. Workflows should therefore always be authored starting from
"the contact exists." Adding an explicit create-contact action produces duplicates.

### Custom values in generated content

`{{custom_values.some_key}}` placeholders resolve **server-side** in funnel pages and
email templates. This is the mechanism that makes a build re-deployable across accounts:
ship the pages and workflows once, then re-brand by editing custom values rather than
editing pages. Note the earlier `fieldKey` trap — the API's wrapped form has braces *and*
spaces, which does not match the compact form you write into content.

---

## Working checklist for approaching any new GHL capability

1. **Ask the MCP catalogue first.** `search_operations` for the resource name. If a
   real operation exists, you are done — see `mcp-server.md`.
2. **If the catalogue has nothing, capture the UI doing it.** Open devtools, perform the
   action by hand, read the request. This is the only reliable discovery method.
3. **Send `{}` to the discovered route.** The 422 hands you the contract.
4. **Control-test with a nonsense id** before believing any `200` from a path you
   guessed.
5. **Do one real write, not a dry run.** Only a real write proves scope.
6. **Verify at the rendered surface**, not at the API echo.
7. **Write down what you learned, including the status codes.** The authority of a note
   like this one comes entirely from every code in it having been observed rather than
   assumed. Keep it that way.

---

## Related

- `auth.md` — the credential for each tier, and the status-code decoder ring
- `mcp-server.md` — the catalogue that replaces steps 1–3 above for anything on the
  public API
