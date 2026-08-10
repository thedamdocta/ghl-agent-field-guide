# Forms, and embedding them outside GoHighLevel

For the case where GHL is a **back end only**: your own site, your own domain, your own
markup, with a GHL form embedded in it. Different constraints from a form on a GHL
funnel page, and the differences decide your design ceiling.

Everything here was verified in production on a live bespoke site, except where marked
UNVERIFIED.

---

## 1. An external embed is an IFRAME. Always.

This is the answer that determines everything else.

A form on a **GHL funnel page** is server-rendered into the page document, so the
page's own stylesheet reaches it. **That is a GHL-page-only behaviour.** On a
third-party site the form arrives as an iframe:

```
https://api.leadconnectorhq.com/widget/form/{formId}
```

Your stylesheet cannot cross that boundary. **The form's own Custom CSS is your only
styling lever** — see §5, because it is writable by API and that changes the picture.

## 2. Load the iframe directly; skip the embed script

```html
<iframe src="https://api.leadconnectorhq.com/widget/form/{formId}"
        title="Sign up" loading="lazy" style="width:100%;height:780px;border:0"></iframe>
```

**Do not include `form_embed.js` if you are writing the iframe yourself.** That script
scans the DOM on load *and again ~500 ms later* for `[data-form-id]`, then **removes
the element it finds and rebuilds a fresh iframe inside new wrapper divs** — a second
load and a visible flash. Measured with a MutationObserver:

```
t =   0ms  iframe added
t = 568ms  iframe removed, wrappers added, second load begins
```

Avoid it by doing any one of: omit the script; omit every `data-*` attribute; never
call `window.FormEmbed.init()`. The script exists for people who drop a bare
`<div data-form-id="…">` in their HTML and want it mounted for them. If you control
the markup, you do not want it.

**Driving your own modal:** use this plain iframe and open/close it yourself. Do not
nest GHL's popup mode inside your own modal — you would be running two mount paths
over the same widget for no gain.

## 3. Embed modes render identically — because they are the same iframe

Inline embed, popup mode and the direct widget URL all load **the same
`/widget/form/{formId}` iframe** and inherit the same internal constraints. There is
no CSS-reach advantage to any of them, and submission attribution is identical
because the submitting document is identical.

The one real difference is **stacking context**, not styling: a popup is
`position: fixed` and therefore escapes any transform/zoom on an ancestor, while an
inline embed sits inside your layout and inherits it. That bit us once — a `zoom: 0.5`
on a page shell rendered a 560px form at 280px, unreadably small, while the popup
version was fine. If an ancestor is scaled, cancel it on the embed container with
`zoom: calc(1 / var(--scale))`. Use `zoom`, not `transform: scale` — scale rasterises
and the iframe text goes visibly fuzzy.

## 4. Height: there is no auto-resize. Pin it.

**The GHL form does not postMessage its height.** The embedding page must set one.
Your instinct about a modal clipping its own submit button is exactly the failure.

On a real deployment, **780px** was the number that fit every field plus the consent
checkbox, the submit button, and the Privacy/Terms footer links without triggering the
iframe's internal scrollbar. Treat that as a starting point and verify against your own
field count.

Also: **the widget caps its content at roughly 500px wide internally.** Making the
iframe wider than ~560px produces dead background, not a wider form. 560×780 is a
sane default.

## 5. Custom CSS IS writable by API — via the internal host

The public API has no form-write operation (`search_operations` returns only
`get-forms` and `get-forms-submissions`). But the **internal** host accepts it:

```
POST backend.leadconnectorhq.com/forms/{formId}
  token-id: <jwt>   channel: APP   source: WEB_USER   Version: 2021-07-28
```

CSS lives at `formData.form.fieldCSS`. Scripted, diffable, verifiable styling —
strictly better than pasting into the builder textarea.

**On the ~8KB truncation ceiling:** that was measured against the **builder's Custom
CSS textarea**, where a 14KB paste appeared to save and then persisted only random
partial chunks, differently on different forms. An API write bypasses that textarea
entirely. A ~2KB `fieldCSS` written this way persisted cleanly and completely.
**UNVERIFIED: whether a large (8KB+) payload survives the API path.** Test before
relying on it, and read the value back rather than trusting the response.

Target the builder's own ids — the form document uses `#_builder-form`:

```css
#_builder-form .form-builder--item input { … }
#_builder-form button[type=submit] { … }
```

> Watch for a trap here: a rule like `.form-builder--item:last-child { display:flex }`
> looks like it targets the submit row. Every field is an only child of its own
> wrapper, so `:last-child` matches **all of them**.

## 6. Seeding the first form on an empty account

The gap: everything says *clone a working form's schema*, and a fresh sub-account has
none. A form created through the UI's **Create form** button exists with a real name
but carries essentially empty `formData` — it cannot seed a clone.

**You do not need a donor form.** Create the record, then write the schema. Two calls:

```bash
# 1. create the record — PUBLIC host, PIT.  Do NOT send locationId in the body:
#    it 422s, and the error names the offending field.
POST services.leadconnectorhq.com/forms/     {"locationId": "<loc>", "name": "<name>"}   # → { id }

# 2. populate it — INTERNAL host, token-id
POST backend.leadconnectorhq.com/forms/{id}  { "formData": <below> }
```

A minimal known-good `formData`, verified in production:

```json
{
  "form": {
    "fields": [
      { "tag": "first_name", "label": "First name", "placeholder": "First name",
        "required": true, "standard": true, "hiddenFieldQueryKey": "first_name" },
      { "tag": "email", "label": "Email", "placeholder": "Email address",
        "required": true, "standard": true, "hiddenFieldQueryKey": "email" },
      { "tag": "phone", "label": "Phone", "placeholder": "Phone number",
        "required": true, "standard": true, "hiddenFieldQueryKey": "phone",
        "enableCountryPicker": false }
    ],
    "formAction": "message",
    "formSubmissionEvent": "Save my seat",
    "formLabelVisible": false,
    "fullScreenMode": false,
    "inputStyleType": "line",
    "fieldCSS": "",
    "customStyle": ""
  }
}
```

Per-field keys that matter: `tag` (the contact field it maps to), `label`,
`placeholder`, `required`, `standard` (true for built-in contact fields), and
`hiddenFieldQueryKey` (which enables URL prefill — useful for a confirmation step that
carries values forward).

`tools/create_form.py` does both calls.

## 7. Submit behaviour does NOT live on the form record

Writing `formAction.actionType` on the form returns **200 and silently does not
persist**. Round-trip it and you will see the old value.

- **On a GHL funnel page**, redirect-after-submit lives on the **page element**:
  `extra.form_submit_type` / `extra.form_submit_redirect_url`.
- **On your own site**, you own the post-submit experience anyway — listen for the
  submission or use `formAction: "message"` and handle the rest yourself.

## 8. Why a GHL form rather than your own React form

Worth stating because it is the reason to accept the iframe at all: **form submissions
are append-only records, while contact fields are overwritten.** A custom form posting
to the contacts API gives you the latest state and destroys the history. If you need to
know what somebody said *this time*, the submission record is the only thing that keeps
it, and `get-forms-submissions` reads it back.

---

## Corrections contributed by a second account (2026-08-09)

Verified independently on a different sub-account. Two of these correct claims
elsewhere in this guide:

- **`DELETE backend.leadconnectorhq.com/workflow/{locationId}/{id}` exists** and
  returns `{"success": true}`. It was missing from `api-map.md`.
- **`POST backend…/workflow/{loc}` with `{}` returns 200 and CREATES a nameless
  workflow.** The internal host does not validate bodies, so the
  "POST an empty body and read the 422" probe in `methodology/discovery.md` is
  **destructive there**. That technique is for the *public* host only. See the warning
  now carried in that file.
- **`name: null` on a form appears specific to API-created forms.** UI-created forms
  carry a real name, which narrows the duplicate-creation trap usefully.

Related: [`funnel-pages.md`](funnel-pages.md) · [`auth.md`](auth.md) ·
[`getting-the-token.md`](getting-the-token.md) ·
[`../tools/create_form.py`](../tools/create_form.py)
