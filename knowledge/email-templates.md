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
rendering bug too.

**Do not assemble a document from the fragments below. A complete, working one is
shipped:**

```
tools/email-template.starter.html     paste-ready dark-ground document
tools/push_emails.py --check          lints it, offline, no credentials
```

The starter is a full valid document — masthead, stage label, headline, body,
optional image, one button, secondary link, signature, footer — with a six-token
neutral palette documented in its header block and every construction below
already applied. Copy it, swap the tokens and the copy, run `--check`, push it.

The rest of this section is *why* it is built the way it is, so you can change it
without breaking it. `--check` enforces every rule marked **(checked)** and fails
the build rather than letting it reach an inbox.

### Why table-based and inline-styled

Outlook on Windows renders through the **Word engine**. It ignores CSS backgrounds on
`div`s, ignores `float`, and ignores most positioning. So everything load-bearing
uses `<table>` and carries the background **twice** — as the `bgcolor` *attribute*
**and** as an inline `style`. **(checked)**

Every text node carries an **explicit colour**. On a dark ground, a text node that
inherits its colour is one client-side inversion away from black-on-black. This is
not theoretical; it shipped once. **(checked)**

### There is no token mechanism — the palette is find-and-replace

CSS custom properties (`var(--x)`) **do not resolve in Outlook**, and inline styles
cannot reference them reliably in any client. Email has no variables. So a palette
is a literal-hex find-and-replace, which is why the starter declares its six tokens
in a table at the top of the file and uses nothing else. `--check` inventories every
distinct hex and warns when the palette grows past a handful: one ground and one
accent used twice beats four accents.

### The 16px floor

**Body copy is 16px and does not go below it.** Below 16px, iOS Mail zooms the
message to fit and your 600px sheet stops being 600px — the layout you tested is not
the layout that arrives. Small type also fails contrast for a real share of any list.
Labels, legal and footers legitimately go smaller; the floor is for copy people
*read*. `--check` lists every declared size under 16px so each exception stays
deliberate.

Related, and the cheapest quality win in the inbox: **give the document a real type
scale.** One captured reference sequence ran 13/14/16px and nothing else, so every
message read as one undifferentiated grey block. Two or three genuinely distinct
tiers is most of the difference between amateur and not.

### The document shell

A full-bleed ground table wrapping a 600px sheet table, with a hidden preheader div
before both. It is the top of `tools/email-template.starter.html`; the points that
matter about it are:

- **`role="presentation"` on every layout table** — otherwise screen readers announce
  them as data tables. **(checked)**
- **`cellpadding="0" cellspacing="0" border="0"`** on every table, every time.
  **(checked)**
- **`x-apple-disable-message-reformatting`** stops Apple Mail resizing your type.
  **(checked)**
- **`color-scheme` / `supported-color-schemes`** declare intent to dark-mode-aware
  clients. They reduce, but do not eliminate, forced inversion.
- **600px** is the durable content width. The media query is the only responsive
  mechanism you can rely on, and Gmail respects it in `<style>` in the head.
- **A hidden preheader div** sets the inbox preview line. Omit it and the client
  scrapes your first visible sentence instead.
- **Scope the mobile padding override to a class on content cells**, not a blanket
  `.sheet td`. A blanket rule also hits the button cell and the hairline cells and
  pulls them apart. The starter uses `.pad` for this.
- **Never write a literal comment-close sequence inside an HTML comment.** It ends
  the comment early and everything after it becomes live markup. This was a real
  defect in the first draft of the starter; `--check` caught it and reading it did
  not.

### Buttons

The one construction that works everywhere is a padded `<a>` inside a `bgcolor`'d
`<td>`:

```html
<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"><tr>
  <td align="center" bgcolor="#7d8fb3" style="background-color:#7d8fb3;border-radius:2px;">
    <a href="{{custom_values.offer_url}}"
       style="display:inline-block;padding:16px 38px;font-family:Georgia,serif;
              font-size:12px;font-weight:700;letter-spacing:.2em;
              text-transform:uppercase;color:#12141a;text-decoration:none;">
      {{custom_values.cta_label}}
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
  <td height="1" bgcolor="#7d8fb3"
      style="background-color:#7d8fb3;font-size:0;line-height:0;">&nbsp;</td>
</tr></table>
```

### Images

```html
<img src="{{custom_values.banner_url}}" width="300" height="34" alt="Descriptive text"
     border="0" style="display:block;width:300px;height:34px;border:0;outline:none;
                       text-decoration:none;-ms-interpolation-mode:bicubic;">
```

- **`display:block`** kills the baseline gap under images. **(checked)**
- **Width and height as attributes AND inline styles** — Outlook reads the
  attributes, not the style. **(checked)**
- **`alt` text is load-bearing.** Outlook blocks images by default, so anything only
  present as a raster is invisible to a real share of your audience. **(checked)**

### SVG cannot travel into email

**SVG does not render in Gmail.** Any vector mark — a logo, a rule, an ornament, a
signature device — has to be **rastered to PNG** before it can be used, which means
the thing you designed as vector on the site becomes a fixed-size bitmap in the
inbox. Three consequences, all of which bite:

- **Render it at 2× the display size** and set the display size in the width/height
  attributes, or it is soft on every modern screen.
- **Render it ON the ground colour, not transparent.** A transparent PNG in a client
  that force-inverts lands as the wrong colour on the wrong field and falls apart.
  Baking in an opaque ground is what makes it survive inversion.
- **Host it where it will still be there.** Use the client's own GHL media library
  (`POST /medias/upload-file?locationId={locationId}` with the PIT), not a
  third-party CDN that can disappear or a build-server URL that is not public. See
  `funnel-pages.md` §8.

`--check` fails on any `.svg` in a `src`. **(checked)**

Because a raster masthead is invisible when images are blocked, the starter sets its
masthead in **live type** instead. See §3 for the trade-off.

### Type

Webfonts **do not load in Outlook — ever** — and are unreliable in several other
clients, **so the fallback is doing the real work for a large share of your
audience.** Pick a fallback genuinely close in colour, width and x-height to your
display face rather than a token `sans-serif`, and check the mail with the webfont
disabled, because that is what many recipients get:

```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=...">
style="font-family:'Your Display Face',Georgia,'Times New Roman',serif;"
```

Declare the family **once** per text node and do not fight yourself with overrides.
A real observation from a funnel-hacked competitor sequence: they declared a webfont
family at the top and then overrode every single span to Arial — the declared font
never applied anywhere, in any client. Set it where it renders.

The starter ships with a system-safe stack only, so it renders identically everywhere
out of the box. Add a webfont deliberately, and keep the fallback honest.

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

## 4. Pushing them — `tools/push_emails.py`

The push is a shipped tool, not a shape to reimplement:

```bash
python3 push_emails.py --emit-example > emails.manifest.json
python3 push_emails.py --manifest emails.manifest.json --check     # offline lint
python3 push_emails.py --manifest emails.manifest.json --dry-run   # payloads, no network
python3 push_emails.py --manifest emails.manifest.json --apply
python3 push_emails.py --manifest emails.manifest.json --verify    # fetch previewUrl
python3 push_emails.py --archive "SEQ 03" --apply                  # retire; DELETE 401s
```

`--check`, `--dry-run` and `--emit-example` need neither credentials nor a network.
Nothing reaches the account without `--apply`, and **a lint failure refuses the
write** rather than shipping a template that renders wrong in a client you are not
looking at.

Four things it does that a hand-rolled call does not:

- **Matches existing templates by name and updates them.** There is no other natural
  key, so a re-run without matching creates a second `SEQ 01` every time, forever.
- **Derives the `idempotencyKey` from a hash of the content**, not from the clock. A
  timestamped key — the obvious first implementation — makes every retry a *new*
  logical write, which is exactly what the key exists to prevent. Content-addressed
  means a retry after a network blip is the same write, while a genuine edit gets a
  new key and is not swallowed as a duplicate.
- **Records `{key, name, id, previewUrl, ok}` to a JSON file.** This is not
  bookkeeping. Workflow email actions join to templates by `template_id`, so those
  ids are a hard dependency of the workflow build and the templates must exist first.
  See `workflows.md`.
- **Verifies on `previewUrl`**, checking that a distinctive phrase from your copy is
  present in what GHL actually serves. A `200` on the write is not proof.

It imports `ghl_mcp.py` as a library, so the SSE parsing, the double-unwrapping and
the `locationId`-in-the-path rule are handled in one place.
