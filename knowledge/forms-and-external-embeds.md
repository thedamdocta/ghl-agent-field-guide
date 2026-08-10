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

### The method, end to end

**1. Start from the shipped stylesheet.**
[`../tools/form-styles.starter.css`](../tools/form-styles.starter.css) is paste-ready
and carries the full selector map. Change the tokens at the top; leave the selectors
alone until something misbehaves.

**2. Know that every rule needs `!important`.** GHL ships its own stylesheet inside
the form document and it loads *after* yours, so an equal-specificity rule loses on
source order. Without `!important`, roughly half of your rules silently do nothing.

**3. The class names are not guessable.** This map cost real time to assemble:

| what you want to style | selector |
|---|---|
| text / email / phone / textarea | `#_builder-form .form-builder--item .form-control` |
| focus state | `… .form-control:focus` |
| placeholder | `… input::placeholder` (set `opacity:1` — Firefox dims it) |
| **submit button** | `#_builder-form .ghl-submit-btn` — **not** `button[type=submit]` |
| field labels | `#_builder-form label` |
| validation text | `#_builder-form .error-message` |
| consent + terms | `.checkbox-container`, `.terms-and-conditions`, and `.terms-text-container *` |
| phone country prefix | `.form-builder--item span[class*="prefix"]` |
| dropdowns | the `.multiselect` family — **eight** separate selectors |

Two that catch people. A dropdown is a vue-multiselect widget: style the container,
the tag wrapper, the inner input **and** `.multiselect__content-wrapper`, or the open
menu renders white-on-white. And the terms block arrives as author-controlled HTML
with its own inline colours, so it needs the `*` descendant rule to be reached at all.

**4. Match the submit button to your page by hand.** It renders inside the form's
document where your page CSS cannot reach it. If the page has its own CTA, replicate
those values here — otherwise the funnel ships with two different button styles and
only one is the one you designed.

**5. Write it, then VERIFY IT APPLIED.** A 200 on the write is not evidence:

```bash
# load the form's own widget document and read a computed style
open "https://api.leadconnectorhq.com/widget/form/{formId}"
```

Read the stored value back too (`GET backend…/forms/{formId}` →
`formData.form.fieldCSS`) and compare its length to what you sent. **Silent
truncation is the failure mode here**, so a length mismatch is the signal.

> **The trap that cost the most.** A rule like
> `#_builder-form .form-builder--item:last-child { display: flex }` reads as "the
> submit row". Every field is an only child of its own `.form-builder--item`, so
> `:last-child` matches **all of them** — in production it threw validation messages
> sideways and squeezed every input from 338px to 138px. Target `.ghl-submit-btn`.

## 6. Seeding the first form on an empty account

The gap: everything says *clone a working form's schema*, and a fresh sub-account has
none. A form created through the UI's **Create form** button exists with a real name
but carries essentially empty `formData` — it cannot seed a clone.

**You do not need a donor form.** Create the record, then write the schema. Two calls:

```bash
# BOTH calls are on the INTERNAL host with the token-id JWT. The public
# POST /forms/ is IAM-walled: 401 "not yet supported by the IAM Service".
POST backend.leadconnectorhq.com/forms/       {"locationId": "<loc>", "name": "<name>"}
     # → the id is at response["form"]["_id"]   (response["id"] is None)

GET  backend.leadconnectorhq.com/forms/{id}   # poll until readable — see below

POST backend.leadconnectorhq.com/forms/{id}   {"name": "<name>", "formData": {...}}
     # locationId must NOT be in this body
```

> **`400 "form does not exist or is deleted"` right after creating one?** Two causes,
> both common: you read `["id"]` instead of `["form"]["_id"]`, or you populated before
> the id propagated. Poll the GET until it resolves. See
> [`building-from-scratch.md`](building-from-scratch.md).

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

---

## Where CSS goes — and the mistake that keeps happening

**Never try to apply CSS at the preview URL.** An inheriting agent lost time to this
and it was entirely avoidable.

```
https://sites.leadconnectorhq.com/preview/{pageId}
```

That is a **rendered output**. It is read-only. It is the surface you *check* your work
on, never a surface you write to — there is nothing there to modify, and anything you
appear to change in a browser session is gone on reload. It is documented all over this
repo as "the verification surface", which is true and evidently easy to misread as "the
place the page lives". The page lives in `pageData`. The preview is a photograph of it.

**CSS has exactly two destinations, and which one depends on what you are styling:**

| styling… | goes into | how |
|---|---|---|
| the **page** — sections, headings, buttons, layout | a `custom-code` element in `pageData` (`extra.customCode`, wrapped in `<style>`) | `page_shell.py --attach`, then `inject_page.py` |
| the **form** — inputs, placeholders, the submit button, dropdowns | the **form record**, at `formData.form.fieldCSS` | `POST backend…/forms/{formId}` |

**They are different documents and neither reaches the other.** A GHL form renders in
its own document — an iframe when embedded on a third-party site — so page CSS cannot
cross into it and form CSS cannot escape it. Put form rules on the page and precisely
nothing happens; the page still returns 201 and the preview still renders, which is why
this failure is quiet.

The practical consequence people miss: **a submit button has to be styled twice.** Once
on the page for the page's own call-to-action, once in `fieldCSS` for the one inside the
form. Style it in one place only and the funnel ships with two different buttons, one of
which you did not design.

### The check

After writing either one, reload the preview URL and confirm the change is *there*.
That is what the preview is for. If you find yourself editing anything at that URL, you
are working on the photograph.
