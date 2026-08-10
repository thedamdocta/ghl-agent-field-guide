# Building from scratch on an empty account

> **Don't have `GHL_PIT` / `GHL_LOCATION_ID` / a funnel id yet?**
> Start at [`step-zero-credentials-and-ids.md`](step-zero-credentials-and-ids.md).
> It covers where each one comes from and which of them need a human (two of four).

**Nothing here requires a donor form, a reference funnel, or a page to clone.**
Everything you need ships in this repo.

That was not true of an earlier version, and it is the single worst way this guide has
failed someone. `ghl_generator.py` refused to run without exemplars captured from
somebody else's public funnel page. `create_form.py` refused without a form to clone.
On a fresh sub-account there is neither, and on an account using GHL as a back end
there may never be a funnel page at all. Both now work from a standing start.

---

## What ships, so you never rediscover it

| you need | it's already here |
|---|---|
| the shape of a GHL element | `tools/element-templates.json` — **15 verified types** |
| a working form field schema | `SEED_FIELDS` in `tools/create_form.py` |
| a page spec to start from | `ghl_generator.py --emit-example` |
| a workflow spec to start from | `deploy_workflow.py --emit-example` |

The element corpus covers: `section`, `row`, `col`, `headline`, `sub-headline`,
`paragraph`, `button`, `image`, `divider`, `form`, `custom-code`, `faq`, `svg`,
`social-icons`, `navigation-menu`. Every account id and hosted asset in it is a
placeholder.

**Why cloning was ever the advice.** A GHL element carries dozens of required keys,
most of them wrapped as `{"value": X}`, and a hand-written dict silently misses some.
So the original method was: read a real element, copy its shape. That was correct —
but the *output* of doing that work is a corpus, and the corpus is what should have
shipped. Telling the next agent to redo the reading is not passing on the knowledge.

---

## The whole chain, empty account to live page

```bash
export GHL_PIT=...  GHL_LOCATION_ID=...       # or put them in tools/.env

# 0. prove the token works, and see what the API offers
python3 tools/ghl_mcp.py locations

# 0b. see the account: every funnel, and every page in it, with its id
#     You never have to copy an id out of this. Names work everywhere ids do.
python3 tools/ghl_ids.py

# 1. internal token — needed for pages, forms and workflows
#    (see knowledge/getting-the-token.md; you can do this without a human)
python3 tools/get_token.py

# 2. a form, from the built-in seed. NO donor form required.
#    --name is REQUIRED and always will be: a form name is a decision, not a fact
#    the account can be asked for.
python3 tools/create_form.py --name "Registration" --seed \
        --fields first_name,email,phone --id-file .form-id --apply

# 3. custom values BEFORE anything references them
#    (an unknown {{custom_values.x}} renders as EMPTY STRING, silently)
python3 tools/create_custom_values.py --set webinar_date="July 30, 2026" --apply

# 4. somewhere to put the page. --funnel takes the NAME; drop it entirely if the
#    location has exactly one funnel.
python3 tools/create_steps.py --funnel "Launch" --step "Opt-in:optin" --apply

# 5. build the page tree — built-in elements, no --templates needed
python3 tools/ghl_generator.py --emit-example > spec.json
#    edit spec.json: your sections, your copy, your form id from .form-id
python3 tools/ghl_generator.py --spec spec.json \
        --funnel "Launch" --page "Opt-in" --out page.json

# 6. styling — WITHOUT THIS NOTHING IS STYLED
python3 tools/css_emitter.py page.json --out page-styled.json

# 7. write it, then verify at the RENDERED surface
python3 tools/inject_page.py --funnel "Launch" --page "Opt-in" \
        --page-data page-styled.json --expect "a distinctive phrase from your copy"
```

Every `--funnel`/`--page` above is optional sugar over `--funnel-id`/`--page-id`,
which still work unchanged. Both forms print what they resolved:

```
  resolved funnel "Launch"       -> <funnelId>   (matched by name)
  resolved page   "Opt-in"       -> <pageId>     (matched by name)
```

Read that line. A resolution you did not intend is only catchable if you look at it.
When two funnels could match, the tool lists them and stops rather than picking —
guessing between real options is how the wrong page gets overwritten.

Verified end to end with no capture and no donor: 2 sections, 10 nodes, 7,622 bytes of
emitted CSS.

---

## Forms and fields, in detail

### Two calls, BOTH on the internal host

```
1. CREATE   POST backend.leadconnectorhq.com/forms/      {"locationId": "...", "name": "..."}
            token-id header (NOT Bearer)
            → the id is at  response["form"]["_id"]

2. VERIFY   GET  backend.leadconnectorhq.com/forms/{id}   ← poll until readable

3. POPULATE POST backend.leadconnectorhq.com/forms/{id}   {"name": "...", "formData": {...}}
            NO locationId in this body
```

**Three things an earlier version of this file got wrong, each of which produces a
confusing failure:**

1. **CREATE is NOT on the public host.** `POST services.leadconnectorhq.com/forms/`
   returns `401 "This route is not yet supported by the IAM Service."` It cannot work.
   Both calls are on `backend.`, with the internal `token-id` JWT.

2. **The id is at `["form"]["_id"]`, not `["id"]`.** `response["id"]` is `None`. Read
   the wrong key and you POST to `/forms/None`, which answers
   **`400 "form does not exist or is deleted"`** — an error that sounds like the form
   was never created when in fact you are asking about the wrong id.

3. **There is read-after-write lag between the two calls.** Even with the right id,
   populating immediately after creating returns that same
   `400 "form does not exist or is deleted"` against an id handed to you seconds
   earlier — and the identical call succeeds a minute later. **Poll `GET /forms/{id}`
   until it resolves before populating.** In live testing the form became readable on
   the second check. A fixed `sleep` is the wrong shape: too short still fails, too
   long makes every run pay the worst case.

**The update body:** `{"name", "formData"}`. Both required, and `locationId` must be
absent.

| body | result |
|---|---|
| includes `locationId` | `422 "property locationId should not exist"` |
| omits `name` | `422 "name must be a string"` |
| `{name, formData}` | works |

So CREATE **requires** `locationId` and UPDATE **rejects** it — same verb, same route
family, opposite requirement.

**Verify by reading back, and retry that too.** The update response does **not** echo
the stored `formData`. Reading immediately after the write returns an empty
`formData`, so a single check reports "no fields stored" while the fields are stored —
a false negative that sends you debugging a write that worked.

And `POST /forms/{id}` **is** the update route — `PUT` and `PATCH` both 404.

### The field schema

```json
{ "tag": "first_name", "label": "First name", "placeholder": "First name",
  "required": true, "standard": true, "hiddenFieldQueryKey": "first_name" }
```

- **`tag`** — the contact field this maps to. This is what makes the submission land
  on a contact rather than nowhere.
- **`standard: true`** — a built-in contact field. Custom fields differ; create the
  custom field first and reference its id.
- **`hiddenFieldQueryKey`** — enables URL prefill, which is how a later step carries
  values forward.
- **`required`**, **`label`**, **`placeholder`** — as they read.

Wrapping `form` keys that matter: `formAction` (`"message"` keeps the visitor on the
page), `formSubmissionEvent`, `inputStyleType`, `fieldCSS`, `formLabelVisible`.

### Putting the form ON a page

The page element references the form **by id** — it does not contain it:

```json
{ "type": "form", "extra": { "formId": "<the id from step 2>" } }
```

Two rules learned from client-visible bugs:

1. **Use a native GHL form.** A hand-rolled `<form>` in a custom-code block renders
   perfectly and captures nothing.
2. **Give every funnel its own form.** Pointing a page at a generically-named account
   form imports that form's fields, image, header, branding and fixed width. In
   production that rendered an unrelated intake form's image and header inside a
   webinar funnel — and restyling it would have changed every other place that form
   is embedded.

### Submit behaviour is NOT on the form record

Writing `formAction.actionType` on the form returns **200 and does not persist**.
Redirect-after-submit lives on the **page element**: `extra.form_submit_type` and
`extra.form_submit_redirect_url`.

### Styling a form

Page CSS cannot reach a form on a third-party site (it is an iframe) and reaches it
only partially on a GHL page. Use `formData.form.fieldCSS`, written through the
internal host, targeting `#_builder-form`. See
[`forms-and-external-embeds.md`](forms-and-external-embeds.md).

---

## When you SHOULD capture instead

The built-in corpus is a starting point, not a straitjacket. Capture with
`tools/capture_funnel.py --exemplars` and pass `--templates` when you want to match an
existing design exactly, or need an element type the corpus lacks. Overriding is a
choice; needing to override should never be a prerequisite.

Related: [`funnel-pages.md`](funnel-pages.md) ·
[`forms-and-external-embeds.md`](forms-and-external-embeds.md) ·
[`getting-the-token.md`](getting-the-token.md) · [`../tools/README.md`](../tools/README.md)
