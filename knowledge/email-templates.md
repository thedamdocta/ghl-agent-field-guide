# GoHighLevel Email Templates — Raw HTML In, Raw HTML Out

**Audience:** an agent that has never touched GoHighLevel (GHL). Everything marked
"verified" was observed in production against a live sub-account. Anything not
verified is labelled **UNVERIFIED** inline.

**The headline fact:** unlike funnel pages — which GHL recompiles at save time, so
what you write is not what gets served — **email templates with
`editorType: "html"` store your `editorContent` VERBATIM.** Round-trip byte-identical,
verified. This makes email the *easy* surface in GHL: you generate markup, you push
it, and that exact markup is what sends.

---

## 1. The API

**Underlying endpoint:** `POST /emails/locations/{locationId}/templates`

Two transports reach it. Both were verified with a **Private Integration Token
(PIT)** — no short-lived browser JWT and no OAuth required, unlike funnel pages and
workflows.

### Direct REST

```
POST https://services.leadconnectorhq.com/emails/locations/{locationId}/templates
  Authorization: Bearer {PIT}
  Version: 2021-07-28
  Content-Type: application/json
```

### Via GHL's own MCP server (what was actually used)

```
POST https://services.leadconnectorhq.com/mcp/anthropic/v2
  Authorization: Bearer {PIT}
  locationId:    {locationId}
  Content-Type:  application/json
  Accept:        application/json, text/event-stream
  User-Agent:    Mozilla/5.0 ...          <- Cloudflare 403s default UAs on GHL hosts
```

The MCP server exposes six meta-tools (`search`, `fetch`, `search_operations`,
`describe_operation`, `execute_operation`, `list_locations`). Email work uses
`execute_operation` with these operation ids:

```
create-email-template · update-email-template · import-email-template
create-template-folder · GET-all-or-email-sms-templates
```

**Responses arrive as SSE `data:` lines.** Strip the `event:` / `data: ` prefixes and
concatenate before parsing. It works over plain `curl`, so it is cheap to probe.

### Request body

```json
{
  "name":          "SEQ 01 - Step one",
  "editorType":    "html",
  "editorContent": "<!doctype html><html>…</html>",
  "subjectLine":   "<the subject line>",
  "previewText":   "<the inbox preview line>",
  "fromName":      "Sender Name"
}
```

MCP call shape:

```json
{ "jsonrpc": "2.0", "id": 1, "method": "tools/call",
  "params": { "name": "execute_operation", "arguments": {
      "operationId": "create-email-template",
      "params": { "path": {"locationId": "<locationId>"}, "body": { ... } },
      "idempotencyKey": "seq-01-<timestamp>"
  }}}
```

### Hard-won rules (all verified)

| Rule | Detail |
|---|---|
| **`idempotencyKey` is REQUIRED on writes** | Omit it and you get a `400` that names the field. |
| **`locationId` goes in the PATH, never the query** | Query returns `422 "property locationId should not exist"`. Same shape as the forms 422 — the response names the offending field, so post a minimal body first to learn the schema. |
| **Create and update work; DELETE may 401** | The PIT returned `401 "token is not authorized for this scope"` on delete. **To retire a template, update it with `archived: true` instead.** |
| **`dryRun: true` proves shape, not permission** | It returns `authorizationVerified: false` — it resolves and previews the request without checking scopes. A successful dry run is not a successful write. Always confirm with one real write. |
| **Match existing templates by NAME to stay idempotent** | List via `GET-all-or-email-sms-templates` with `{"query": {"limit": 100, "skip": N}}`, paginate, filter by your name prefix, then `update-email-template` instead of creating a duplicate. |

### The response — and your verification surface

A successful create/update returns `data.id` and **`data.previewUrl`** — a
Firebase-hosted rendering of the stored template.

**`previewUrl` is your verification surface.** Fetch it and confirm your markup
survived. Same discipline as funnel pages: a `200` is not proof, the rendered surface
is.

### What GHL adds

Round-trip comparison showed the stored content byte-identical to what was posted,
with only two **additions**:

- an `<!-- outlook-fixes-applied -->` comment, and
- MSO font-colour fallbacks.

**No MJML recompilation, no re-nesting, no attribute stripping.** Whatever you author
is what sends.

---

## 2. Building email HTML that actually survives

`editorType: "html"` means you own the whole document, which means you own every
rendering bug too. What follows is the construction that shipped a dark-ground,
brand-consistent nine-email sequence.

### Why table-based and inline-styled

Outlook on Windows renders through the **Word engine**. It ignores CSS backgrounds on
`div`s, ignores `float`, and ignores most positioning. So everything load-bearing
uses `<table>` and carries the background **twice** — as the `bgcolor` *attribute*
**and** as an inline `style`.

Every text node carries an **explicit colour**. On a dark ground, a text node that
inherits its colour is one client-side inversion away from black-on-black. This is
not theoretical; it shipped once.

### The document shell

```html
<!doctype html>
<html lang="en" style="background-color:#0B0B0D;">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<style>
  :root { color-scheme: dark; supported-color-schemes: dark; }
  body,table,td,p,h1,a { -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }
  img { -ms-interpolation-mode:bicubic; border:0; outline:none; text-decoration:none; }
  a { text-decoration:none; }
  @media only screen and (max-width:620px) {
    .sheet { width:100% !important; }
    .sheet td { padding-left:24px !important; padding-right:24px !important; }
    .sheet h1 { font-size:27px !important; line-height:1.24 !important; }
  }
</style>
</head>
<body style="margin:0;padding:0;background-color:#0B0B0D;">

  <!-- preheader: the inbox preview line, hidden in the body -->
  <div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;
              opacity:0;overflow:hidden;color:#0B0B0D;">PREHEADER TEXT</div>

  <!-- full-bleed ground -->
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
         bgcolor="#0B0B0D" style="background-color:#0B0B0D;margin:0;padding:0;">
    <tr><td align="center" style="padding:0;">

      <!-- the 600px sheet -->
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600"
             class="sheet" bgcolor="#0B0B0D"
             style="width:600px;max-width:600px;background-color:#0B0B0D;">
        <!-- content rows -->
      </table>

    </td></tr>
  </table>
</body></html>
```

Points that matter:

- **`role="presentation"` on every layout table** — otherwise screen readers announce
  them as data tables.
- **`x-apple-disable-message-reformatting`** stops Apple Mail resizing your type.
- **`color-scheme` / `supported-color-schemes`** declare intent to dark-mode-aware
  clients. They reduce, but do not eliminate, forced inversion.
- **600px** is the durable content width. The media query is the only responsive
  mechanism you can rely on, and Gmail respects it in `<style>` in the head.
- **`cellpadding="0" cellspacing="0" border="0"`** on every table, every time.

### Buttons

The one construction that works everywhere is a padded `<a>` inside a `bgcolor`'d
`<td>`:

```html
<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"><tr>
  <td align="center" bgcolor="#DBA49E" style="background-color:#DBA49E;border-radius:2px;">
    <a href="{{custom_values.offer_url}}"
       style="display:inline-block;padding:16px 38px;font-family:Georgia,serif;
              font-size:12px;font-weight:700;letter-spacing:.2em;
              text-transform:uppercase;color:#17131A;text-decoration:none;">
      CALL TO ACTION
    </a>
  </td>
</tr></table>
```

No VML needed for a small radius. **VML is only worth adding for a pill-shaped
button** where Outlook's square corners would be conspicuous. **UNVERIFIED:** the VML
rounded-button fallback was not built or tested here.

### Rules, dividers and spacers

Use a `<td>` with a height and a `bgcolor`, plus `font-size:0;line-height:0` and a
`&nbsp;` so Outlook does not collapse it:

```html
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="54"><tr>
  <td height="1" bgcolor="#B08A5E"
      style="background-color:#B08A5E;font-size:0;line-height:0;">&nbsp;</td>
</tr></table>
```

### Images

```html
<img src="{{custom_values.banner_url}}" width="300" height="34" alt="Descriptive text"
     border="0" style="display:block;width:300px;height:34px;border:0;outline:none;
                       text-decoration:none;-ms-interpolation-mode:bicubic;">
```

- **`display:block`** kills the baseline gap under images.
- **Width and height as attributes AND inline styles** — Outlook reads the attributes.
- **`alt` text is load-bearing.** Outlook blocks images by default, so anything only
  present as a raster is invisible to a real share of your audience.
- **SVG does not render in Gmail.** Ship vector marks as rasters.
- On a dark ground, render the raster **on the ground colour rather than
  transparent** — a transparent PNG in a client that force-inverts lands as the wrong
  colour on the wrong field and falls apart.
- **Host images in the client's own GHL media library** (`POST
  /medias/upload-file?locationId={locationId}` with the PIT), not a third-party CDN
  that can disappear. See `funnel-pages.md` §8.

### Type

Webfonts do not load in Outlook and are unreliable elsewhere, **so the fallback is
doing real work.** Pick a fallback that is genuinely close in colour and width to your
display face rather than a token `sans-serif`. Declare the family **once** per text
node and do not fight yourself with overrides.

A real observation from a funnel-hacked competitor sequence: they declared a webfont
family at the top and then overrode every single span to Arial — the declared font
never applied anywhere. Set it where it renders.

**Give email a real type scale.** The same reference ran 13/14/16px and nothing else,
so every message read as one undifferentiated block. Two or three genuinely distinct
tiers is the cheapest quality win available in the inbox.

### Merge tags

- `{{custom_values.slot_name}}` — per-deployment strings. See `custom-values.md`.
- `{{contact.first_name}}` — verified working in templates.
- `{{right_now.year}}` — verified working (already shipping in production footers).

**GHL resolves unknown `{{custom_values.x}}` tags to EMPTY STRING, silently.** A
typo'd slot produces a sentence with a hole in it and no error anywhere. The
funnel-hacked reference shipped a live merge-tag failure — a sentence reading
a call-to-action sentence rendered with its noun missing. **Create the slot before
you reference it,
and proof-render before the first send.**

**UNVERIFIED in the account this guide came from — test before relying on them:**

- the unsubscribe / manage-preferences merge tags (`{{unsubscribe_link}}` was used in
  production markup but never confirmed to resolve),
- whether custom values resolve inside the **email** builder identically to funnel
  pages (they should; not round-tripped).

Both deserve one real test send.

---

## 3. Structure of a good sequence email

Captured from teardown of a working nine-email webinar sequence. A given email uses a
subset of these beats, in this order:

| # | beat | job |
|---|---|---|
| 1 | **BANNER / MASTHEAD** | restate the promise that earned the opt-in |
| 2 | **SALUTATION** | one line, `{{contact.first_name}}`, blank line after |
| 3 | **STATUS** | tell them where they stand — one sentence, no hedging |
| 4 | **PREVIEW** | what they're about to get |
| 5 | **ACTION** | the one button — centred, brand fill, **ONE per email** |
| 6 | **UTILITY** | the small practical instruction |
| 7 | **CLOSE** | two short sentences |
| 8 | **SIGNATURE** | em-dash, bold |
| 9 | **FOOTER** | legal band, disclaimer, unsubscribe |

**The structural insight worth keeping:** the masthead carries the *entire* promise
and the body **never repeats the headline**. The body only does status → preview →
action. That is why good sequence emails read short. Do not re-state the offer in body
copy.

Two corollaries observed:

- **One filled button per email.** A repeat CTA is demoted to a ruled text link. Two
  filled buttons compete; four are noise.
- **Spacing does the work of dividers.** The strongest reference sequence used *no*
  horizontal rules at all and exactly **one** accent colour, used twice.

Two design decisions with real trade-offs, stated so you can choose deliberately:

- **A raster masthead with type baked in** gives total art-direction control and costs
  three things: it is invisible when images are blocked (Outlook default), the type
  does not reflow on a phone, and every new campaign needs a new file.
- **Live text over a coloured band** survives image-blocking, reflows, and swaps by
  editing a custom value. It costs the baked-in art direction. This is the modular
  choice, and modularity is usually the point of building this way.

---

## 4. Push script shape

```
1. Read local generated HTML + a manifest (name, subject, preview text).
2. List existing templates, paginated, filtered by your name prefix → {name: id}.
3. For each: if name exists → update-email-template with {path:{locationId,templateId}, body}
             else          → create-email-template with {path:{locationId}, body}
   ALWAYS pass idempotencyKey.
4. Record {key, name, id, previewUrl, ok} to a JSON file.
5. Fetch each previewUrl and confirm the markup.
```

**Step 4 is not bookkeeping.** Workflow email actions join to templates by
`template_id`, so the ids you record here are a hard dependency of the workflow
build — the templates must exist first. See `workflows.md`.
