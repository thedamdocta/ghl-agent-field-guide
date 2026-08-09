# GoHighLevel Funnel Pages — Read, Write, Verify

**Audience:** an agent that has never touched GoHighLevel (GHL). Everything marked
"verified" was observed in production against a live sub-account. Anything not
verified is labelled **UNVERIFIED** inline. Never upgrade an unverified claim without
observing it yourself.

**The one thing to internalise before anything else:** a `200` or `201` from GHL is
**not** proof your change took effect. GHL *compiles* funnel pages at save time, and
the served page is a build artifact, not a live read of the stored document. The only
proof is the rendered page. This mistake cost hours; see [Verification](#5-verification--the-only-thing-that-counts).

---

## 1. What a GHL funnel page actually is

A public GHL funnel page is a **server-rendered Nuxt 3 application**. The complete
page definition — every element, style, layout value and setting — ships inside the
HTML in a single script tag:

```html
<script type="application/json" data-nuxt-data="nuxt-app" data-ssr="true" id="__NUXT_DATA__">
```

The payload is **`devalue`-serialized**: a flat JSON array where index `0` is the
root, and **any integer appearing inside an object or array is a POINTER (an index)
into that same array**, not a literal number. Resolving it means walking the array and
substituting pointers recursively.

**Consequence — verified:** any publicly reachable GHL funnel page leaks its full
definition to anyone who fetches the HTML. This is the read side of "funnel hacking":
fetch the page, extract the payload, resolve it, and you have the complete
section→row→col→element tree, including responsive rules and button wiring.

Two practical notes from doing this:

- **Use `curl` with a real browser User-Agent.** Cloudflare returns 403 to Python's
  default UA on GHL hosts. This applies to every GHL host in this guide.
- **Desktop and mobile payloads are byte-identical** (verified across six pages). GHL
  serves ONE definition and does the responsive work with per-element flags and
  breakpoint style blocks. Do not fetch twice expecting two layouts.

Minimal extraction sketch:

```python
NUXT_RE = re.compile(
    r'<script type="application/json"[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)

def resolve(flat, i, depth=0, maxdepth=60):
    """flat[0] is the root; ints are indices back into flat."""
    if depth > maxdepth:
        return None                      # devalue graphs contain cycles — bound it
    node = flat[i]
    if isinstance(node, int):
        return resolve(flat, node, depth + 1)
    if isinstance(node, list):
        return [resolve(flat, x, depth + 1) for x in node]
    if isinstance(node, dict):
        return {k: resolve(flat, v, depth + 1) for k, v in node.items()}
    return node
```

The `maxdepth` bound is not optional — the graph self-references.

---

## 2. The write path

**REST page-write endpoints are IAM-walled. Do not retry them.** Verified: `PUT
services/funnels/page` and `PUT backend/funnels/page` return `403 "This route is not
yet supported by the IAM Service"` once a real `locationId` is supplied; `POST
backend/funnels/page` returns `404`. This holds for both a Private Integration Token
(PIT) and an account JWT.

**The path that works — verified on the rendered page:**

```
POST https://backend.leadconnectorhq.com/funnels/builder/autosave/{pageId}

Headers:
  token-id:      {the eyJ... token}        <- NOT `Authorization: Bearer`
  channel:       APP
  source:        WEB_USER
  Version:       2021-07-28
  Content-Type:  application/json
  User-Agent:    Mozilla/5.0 ...           <- required; Cloudflare blocks default UAs

Body:
  {
    "funnelId":    "<funnelId>",
    "pageData":    { ...the full authoring tree... },
    "pageVersion": <integer>
  }

→ 201 Created. The response carries the NEW pageDataUrl + pageDataDownloadUrl that
  GHL minted for you. GHL writes the object AND recompiles the page.
```

**Discover required fields by POSTing `{}`** — the `422` validator names them. This
is the general GHL technique: the validator tells you the shape, so you never have to
guess a body.

### The dead end that looks like success

There is a Firebase-direct path — the `token-id` header *is* a Firebase ID token
(`iss: securetoken.google.com/highlevel-backend`, `aud: highlevel-backend`), so it
authenticates directly to Firestore and Firebase Storage as
`Authorization: Bearer {token-id}`. You can genuinely upload a new page-data object
(200) and PATCH the page document's pointer (200), and the GHL REST API will happily
echo your new values back.

**The live page never changes.** GHL compiles at save time; editing the source while
the site serves a stale build looks exactly like success. The builder also holds its
own draft and will overwrite a raw storage edit on its next save.

The auth finding is true and useful (it is how the schema was discovered in the first
place). **The write must still go through the autosave endpoint above.**

### Auth token

`token-id` is a JWT (~1000 chars, starts `eyJ`) with roughly a **60-minute** life.
Capture it **passively** from any request to `backend.leadconnectorhq.com` — DevTools
→ Network → Request Headers, or a CDP-attached browser reading its own traffic.

Two notes:

- The same token value goes in **different header names** depending on host:
  `token-id:` for `backend.leadconnectorhq.com`, `Authorization: Bearer` for
  `*.googleapis.com`.
- Do not try to have an agent sweep `localStorage` pattern-matching for `eyJ`. Some
  agent harnesses block that command *shape* regardless of permissions. Passive
  network capture is the reliable route.

---

## 3. The authoring schema

The body of `pageData` is the **authoring tree**. Top level:

```json
{
  "sections": [...],  "settings": {...},  "general": {...},
  "pageStyles": {...}, "trackingCode": {...}, "fontsForPreview": {...},
  "popups": {...},     "popupsList": [...]
}
```

**`popupsList` is not inside `sections`.** Modals — including the opt-in capture
modal, usually the single most important element on the page — live there. A
`sections`-only walk silently misses them.

Hierarchy: **`section` → `row` → `col` → `element`**.

### Element shape

```json
{
  "extra":  { "nodeId", "visibility": {"value": {"hideDesktop","hideMobile"}},
              "text": {"value": "<h1>…</h1>"},
              "desktopFontSize": {"value": 62, "unit": "px"},
              "mobileFontSize":  {"value": 34, "unit": "px"},
              "typography": {"value": "var(--headlinefont)"},
              "customClass": {"value": []},
              "elementVersion": {"value": 2}, "name": "headline" },
  "class":  { "entranceAnimation", "animationScale|Duration|Delay|Easing", "colWidth" },
  "styles": { "backgroundColor", "color", "fontFamily", "fontWeight", "boxShadow",
              "paddingTop|Bottom|Left|Right": {"value":100,"unit":"px"}, ... },
  "mobileStyles": { ... },
  "wrapper": {...}, "mobileWrapper": {...}, "meta": {...},
  "id", "type", "child": [childIds], "tagName", "customClass",
  "visibility": {"hideDesktop","hideMobile"}
}
```

**Every value is wrapped.** `{"value": X}` or `{"value": X, "unit": "px"}` — never a
bare scalar. Rich text is **HTML inside `extra.text.value`**.

Element vocabulary observed in real GHL output: `heading`, `sub-heading`,
`paragraph`, `button`, `image`, `svg`, `divider`, `form`, `custom-code`,
`nav-menu-v2`, plus containers `section`, `row`, `column`.

**Mixing native elements with `custom-code` blocks is sanctioned** — GHL's own Funnel
AI emits both in one page. Native elements matter because the client can still edit
them visually in the builder.

### Generating valid elements: clone, don't hand-write

Elements carry dozens of required keys. The reliable technique is to **clone an
exemplar element captured from a real page** and mutate it, which guarantees no
required key is missing.

**The trap (verified, cost a full rebuild):** an exemplar carries its original
*role*, not just its schema. Cloning `sections[0]` from a page whose section 0 was
the sticky navigation bar produced seven `stickyTop` sections stacked on top of each
other. The schema was valid, the CSS was valid, the *semantics* were wrong — and a
key-set diff showed **zero** differences.

Inspect role-bearing fields before adopting an exemplar: `extra.sticky`, `title`,
`class.width`, padding magnitude. Keep **separate** exemplars for nav / hero /
content / footer.

### The `custom-code` payload field

The payload lives at **`extra.customCode`**. Guessing `code` / `html` / `text`
silently produces an empty block: the element renders, the script never runs.

---

## 4. Styling — `section.general.sectionStyles`

**This is the single highest-value fact in this document.**

> **GHL does NOT compile an element's `styles` dict into CSS at render time.**

The builder generates **one CSS string per section**, stored at
`section.general.sectionStyles`, with every rule scoped to a specific element ID:

```css
.hl_page-preview--content .section-g6H7i8{box-shadow:none;padding-top:12px}
@media screen and (min-width:0px) and (max-width:480px){
  .hl_page-preview--content .section-g6H7i8{padding-top:10px!important}
}
```

So a from-scratch page generator **must emit this string for its own ids, or nothing
is styled** — the `styles` dict alone renders as an unstyled page. This is the piece
that turns "modify an existing page" into "inject any design".

### Mapping rules (decoded from real GHL output)

| authoring | CSS |
|---|---|
| camelCase key | kebab-case property (`backgroundColor` → `background-color`) |
| `{"value": 12, "unit": "px"}` | `12px` |
| `{"value": "none"}` | `none` |
| `mobileStyles` | inside the `max-width:480px` media block, with `!important` |
| `extra.desktopFontSize` | `font-size` (type lives on `extra`, **not** `styles`) |
| `extra.mobileFontSize` | `font-size` inside the media block |
| `extra.typography` | `font-family` |
| `class.colWidth` | `width: N%` on columns |
| `extra.visibility.value.hideDesktop` | `@media (min-width:481px){…display:none!important}` |
| `extra.visibility.value.hideMobile` | `display:none!important` inside the mobile block |
| empty-string values | skip entirely |

Selector prefix: `.hl_page-preview--content .` + the id.
Mobile media query: `@media screen and (min-width:0px) and (max-width:480px)`.

**Never emit these keys as CSS** — they are GHL-internal layout hints, not
properties:

```
forceColumnLayoutForMobile · justifyContentColumnLayout · alignContentColumnLayout
colWidth · rowWidth · alignRow · nestedColumn · allowRowMaxWidth
hideElements · showElements · elementScreenshot · customClass
inlineColors · inlineTypographies · visibility · sticky · bgImage
entranceAnimation · animationScale · animationDuration · animationDelay · animationEasing
```

### The specificity rule — read this twice

**GHL injects `sectionStyles` AFTER your own stylesheet** (yours rides in a
`custom-code` element). Source order therefore decides every specificity **tie**, and
**GHL always wins the ties**.

Real failure: a form stayed 333px wide against a 440px rule. Both selectors were
specificity `(0,2,0)`:

```css
.hl_page-preview--content [class*=cform-]{max-width:440px!important}  /* ours, first */
.hl_page-preview--content .cform-j9K0l1{width:333px}                /* GHL's, later */
```

**`!important` did not save it.** `!important` ranks you against *non*-important
rules; it does nothing against a later same-specificity rule in the same important
tier.

**The fix is a tag qualifier, which raises specificity:**

```css
.hl_page-preview--content div[class*=cform-]{...}   /* (0,2,1) beats (0,2,0) */
```

**Rules:** assume anything keyed to a GHL element id will be re-declared later. Raise
SPECIFICITY, never rely on `!important` alone. Diagnose by reading *computed* style
and walking the ancestor chain — the winning rule is rarely on the element you
suspect.

The mirror image of the same problem: GHL's base stylesheet outranks a plain rule
you emit, so a small **forced set** is justified in the emitter —
`background-color`, `color`, `padding-top`, `padding-bottom` — or every section
renders transparent and the page flattens to a single colour.

### The two ID namespaces — emit CSS for BOTH

| Context | Prefix | Example |
|---|---|---|
| **Authoring** (`pageData` — what you WRITE) | **no** leading `c` | `heading-a1B2c3`, `button-d4E5f`, `section-g6H7i8` |
| **Rendered** (`__NUXT_DATA__` — what you READ off a live page) | **leading** `c` | `cheading-…`, `cbutton-…`, `cform-…` |

Inside an authoring element, **`extra.nodeId` carries the RENDERED id**. So:
authoring `id` ↔ rendered `extra.nodeId`.

- When minting new elements, use authoring ids **without** the `c`.
- When copying ids scraped from a live page, **strip the leading `c` first**.
- **Emit each CSS rule against BOTH selectors** — element-level styling (button
  fills, nav type) is keyed off the rendered id:

```python
sel = f".hl_page-preview--content .{node['id']}"
rendered = node.get("extra", {}).get("nodeId")
sels = sel if not rendered else f"{sel},.hl_page-preview--content .{rendered}"
```

---

## 5. Verification — the only thing that counts

```
https://sites.leadconnectorhq.com/preview/{pageId}
```

Public, server-rendered, **no custom domain needed**. Fetch it and grep for your
changed text. This is the only proof.

**Two false-victory patterns already burned in production:**

1. A `200` plus the API echoing your write is **not** evidence the rendered page
   changed (the Firebase-direct trap above).
2. A `401 → 422` shift is the **body validator** passing, not authorization. Do not
   read it as "authorized".

**One more subtlety:** the rendered preview shows **resolved** merge tags, because
GHL substitutes `{{custom_values.*}}` server-side. So "no `custom_values.` appears in
the HTML" proves nothing. Assert against your generated `pageData` JSON **and**
spot-check that the expected literal strings appear on the page.

### Endpoint discovery — never guess

`GET /funnels/funnel/{x}` and `/funnels/page/{x}` accept **any** string as an id and
fall through to a generic get-by-id route, returning 200 for `ai`, `clone`, `import`
and other non-routes. **Always control-test with a nonsense id
(`.../funnel/zzzznotreal`); if it behaves identically, your "discovery" is
meaningless.**

Endpoints are discovered by **capturing real UI traffic** — make the target system
perform the action while you observe passively, then read the artifacts it produced.
Watching beat guessing, decisively, every time it was tried.

---

## 6. Button actions

**The action fields are not interchangeable.** Writing a scroll target into
`visitWebsite` is schema-valid, returns 201, and produces a button that moves the
page **0px** — verified; every CTA on a six-page funnel was inert this way.

| `extra.action` value | where the target goes |
|---|---|
| `go-to-next-funnel-step` | nothing — `visitWebsite {url:"", newTab:false}`, no target needed |
| `go-to-funnel-step` | needs a funnel step id |
| `scroll-to-element` | **`extra.scrollToElement.value`** = the target nodeId |
| `openPopup` | **`extra.popupId.value`** = the popup id (from `popupsList`) |
| `open-website` / `visit-website` | `extra.visitWebsite.value = {url, newTab}` |

`go-to-next-funnel-step` is the sane default for a funnel CTA — it is what a funnel
CTA almost always wants, and it needs no id to be correct.

Also seen on the button element: `saleAction: {"value": "go-to-next-funnel-step"}`.

---

## 7. Forms

### Submit behaviour lives on the PAGE ELEMENT, not the form record

```json
{
  "extra": {
    "formId": {"value": "<formId>", "text": "<display name>"},
    "form_submit_type": "ThankYouMessage",
    "form_submit_redirect_url": ""
  }
}
```

**Writing `formAction.actionType` / `redirectUrl` onto the FORM record returns 200
and silently does not persist** (verified by round-trip). The page element is where
GHL reads it from.

**UNVERIFIED:** only `"ThankYouMessage"` has been observed in captured production
pages. The `"Redirect"` enum is a **candidate value**, inferred, not confirmed. Verify
it by setting the option once in the GHL builder UI and re-capturing the page, or by
one real test submission. Do not describe redirect-on-submit as working until then.

### Give every funnel its OWN form

Pointing a page at a pre-existing, generically-named account form ("Registration",
"Contact Us") **imports that form's fields, image, header, branding and fixed
width**. In production this rendered an unrelated intake form's image, linked header
and SUBMIT button inside a webinar funnel — and restyling it would have changed every
other place that form is embedded.

Form API notes (verified):

- **Build a new form by CLONING a working form's `formData` schema** and deleting
  unwanted fields. Hand-written field dicts miss required keys.
- **`GET /forms/?locationId=…` returns `name: null`** for forms created via the
  backend API. Any "does my form already exist?" check that matches on **name** will
  always miss and create a duplicate. **Match on a stored id.**
- **`POST /forms/{id}` is the update route** — PUT and PATCH both 404. It **422s if
  the body contains `locationId`**, and the 422 names the offending property, so post
  a minimal body first to learn the shape.
- **The form renders INLINE in the page document, not in an iframe** (verified by
  finding `.ghl-form-wrap` in the main frame). Page CSS reaches it, so the submit
  button can be unified with the page buttons from your stylesheet. Do not assume
  iframe isolation.

---

## 8. Media

Host assets in the client's own GHL media library rather than a third-party CDN — a
third-party generation URL can vanish when its owner deletes the generation.

```
POST {GHL_API}/medias/upload-file?locationId={locationId}
  -H "Authorization: Bearer {PIT}"
  -H "Version: 2021-07-28"
  -F "file=@local.png;type=image/png"
  -F "hosted=false"
  -F "name=asset-name.png"

→ {"fileId":"...","url":"https://assets.cdn.filesafe.space/{locationId}/media/{uuid}.png"}
```

Verified for PNG (alpha preserved) and MP4. The returned URL is the same form the
funnel builder itself uses, so it is safe to reference from page CSS.

---

## 9. Checklist for a from-scratch page injection

1. Capture a fresh `token-id` (passive network observation, ~60 min life).
2. Read an existing page's `__NUXT_DATA__` to harvest **role-matched** exemplars.
3. Build the authoring tree: `section → row → col → element`, every value wrapped,
   authoring ids **without** the `c` prefix, `extra.nodeId` set to the `c`-prefixed
   form.
4. **Emit `section.general.sectionStyles` for every section**, for BOTH id
   namespaces. Skip the internal-hint keys. Force the small background/colour/padding
   set.
5. Wire buttons using the correct per-action field.
6. Put form submit behaviour on the **page element**.
7. `POST /funnels/builder/autosave/{pageId}` → expect **201**.
8. **Verify at `sites.leadconnectorhq.com/preview/{pageId}`.** Grep for your literal
   strings. A 201 is not a result.
