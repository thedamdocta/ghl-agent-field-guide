# GoHighLevel Custom Values — CRUD, and When NOT to Use One

**Audience:** an agent that has never touched GoHighLevel (GHL). Everything marked
"verified" was observed in production against a live sub-account. Anything not
verified is labelled **UNVERIFIED** inline.

A **custom value** is a location-scoped key/value pair. You reference it anywhere GHL
renders content — funnel pages, email templates, workflow action attributes — as
`{{custom_values.some_key}}`, and GHL substitutes it server-side.

They are the mechanism that makes a funnel *modular*: build once, redeploy to a new
client or a new campaign by editing values instead of pages. **Used badly, they are
also the mechanism that makes a funnel unmaintainable and silently broken.** Section 3
is the important one.

---

## 1. CRUD

All custom-value operations work with a **Private Integration Token (PIT)** — no
short-lived browser JWT needed, unlike funnel pages and workflows.

```
Base: https://services.leadconnectorhq.com
Headers:
  Authorization: Bearer {PIT}
  Version:       2021-07-28
  Content-Type:  application/json
  User-Agent:    Mozilla/5.0 ...     <- Cloudflare 403s default UAs on GHL hosts
```

### List

```
GET /locations/{locationId}/customValues?limit=200
→ { "customValues": [ { "id", "name", "fieldKey", "value", ... }, ... ] }
```

### Create

```
POST /locations/{locationId}/customValues
Body: { "name": "event_date", "value": "<a date string>" }
→ response contains "id"
```

### Update — per value only

```
PUT /locations/{locationId}/customValues/{id}
Body: { "name": "event_date", "value": "<a new date string>" }
```

### Delete

`DELETE /locations/{locationId}/customValues/{id}` exists in the catalogue.
**UNVERIFIED** — never exercised. Note that the same PIT that could create and update
**email templates** returned `401 "token is not authorized for this scope"` on delete,
so do not assume delete scope here either. Test it before depending on it.

### Via GHL's MCP server

The same operations exist as `get-custom-values`, `create-custom-value`,
`update-custom-value` through `execute_operation` on
`https://services.leadconnectorhq.com/mcp/anthropic/v2`. Writes there require an
**`idempotencyKey`** argument. See `email-templates.md` §1 for the MCP transport
details (SSE responses, `locationId` in the path).

---

## 2. Five traps, all verified

### 1. `PUT /customValues/bulk` is GONE

```
PUT /locations/{loc}/customValues/bulk   body { customValues:[{id,value}] }
  → 422 "property customValues should not exist / name must be a string"
```

That 422 is the **per-value** schema talking. Confirmed by sending a per-value body to
the same URL:

```
  → 404 "The custom value id is invalid."
```

So `bulk` is being parsed as the `{id}` path segment. **There is no bulk route** — the
old one is gone, not renamed. Applications written against it (it worked as recently
as late 2025) will fail.

**Design consequence:** probe bulk once per process, memoise the failure, fall through
to per-value writes. Twenty-odd individual writes is a perfectly reasonable number, so
the fallback is not a compromise.

### 2. A per-value PUT requires `name` AND `value`

Sending only `value` fails. **Source `name` from the live record you just read, never
from your own constant** — that way a write can never accidentally rename a key.

### 3. `fieldKey` has braces AND spaces — parse it with a regex

- `name` is the literal snake_case key: `event_date`
- `fieldKey` is the wrapped form: `{{ custom_values.event_date }}` — **with braces AND
  interior spaces**

Parsing `fieldKey` by string-equality against a bare key returns "all missing". Use a
regex:

```python
KEY_RE = re.compile(r"\{\{\s*custom_values\.([A-Za-z0-9_]+)\s*\}\}")
key = KEY_RE.search(record["fieldKey"]).group(1)
```

Note the spacing is inconsistent in the wild: GHL's `fieldKey` carries spaces, while
working production page and email markup uses `{{custom_values.x}}` **without** them,
and a workflow `event_start_date` attribute was observed using `{{ custom_values.x }}`
**with** them. Both render. **Do not depend on the spacing anywhere — always regex.**

### 4. `locationId` belongs in the PATH

As a query param it returns `422 "property locationId should not exist"`. Same shape
as the forms and email-template 422s: **the response names the offending field**, so
post a minimal body first to learn the schema rather than guessing.

### 5. A PUT needs an EXISTING id

Writing to a key that does not exist yet has nothing to address. Creating is a
separate call. A launcher/config UI must resolve **keys → ids on load** and cache the
map.

**Bonus, verified:** read-after-write is consistent (0/10 stale across a test run), so
a form can safely re-hydrate immediately after saving.

---

## 3. THE DESIGN RULE

> **A custom value earns its place ONLY when the same string must appear on MORE THAN
> ONE surface. Everything else should be literal text the client can see and edit in
> the WYSIWYG builder.**

This is the rule that separates a maintainable GHL build from an unmaintainable one,
and it is counterintuitive — the instinct when building modularly is to make
*everything* a slot.

### How to measure it: count surfaces per key

A "surface" is one page or one email template. The method:

1. Enumerate every surface in the build (e.g. 6 pages + 9 emails = 15 surfaces).
2. For each `{{custom_values.x}}` reference, record which surface it appears on.
3. Count **distinct surfaces per key**.
4. **Count == 1 → it should not be a custom value.** Inline it as literal text.

**Do not do this by hand.** `create_custom_values.py --surfaces` performs exactly
these four steps. It is pure local analysis — no credentials, no account access,
writes nothing — so it is safe to run on a build before anything is deployed:

```bash
python3 create_custom_values.py --surfaces \
    --scan page1.json --scan page2.json --scan emails/*.html
```

```
  surfaces scanned:         15
  distinct keys referenced: 75
  on MORE THAN ONE surface: 16   <- these earn their place
  on exactly ONE surface:   59   <- inline these as literal text

  multi-surface (keep as custom values):
     15 surfaces  business_name
     15 surfaces  footer_disclaimer
      5 surfaces  event_date
  ...
  single-surface (candidates to inline):
      1 surface   hero_headline                      page1.json
```

`--json` gives the same data machine-readably. One caveat the count cannot see: a
single-surface key whose only surface is a **raw-HTML email template** should usually
stay a slot — see the exception below. The report flags those for you to judge, it
does not decide.

Real numbers from a production build, 6 pages + 9 emails:

| | count |
|---|---|
| total slots | **75** |
| appearing on **more than one** surface | **16** |
| appearing on exactly **one** surface | **59** |

`business_name` and `footer_disclaimer` appeared on all 15 surfaces. `event_date`
appeared on 5. The other 59 existed on exactly one page — **where the custom value
buys nothing and costs the client the ability to read their own copy in the builder.**

Fifty-nine of those were converted to literal text. The client's words were seeded
from the values already live in the account, so the pages kept their exact shipped
wording and **zero copy had to be invented.**

### Why single-surface slots are actively harmful

**1. Every unused or misspelled slot is a silent-failure surface.**

> **GHL resolves an unknown `{{custom_values.x}}` tag to the EMPTY STRING. Silently.
> No error, no warning, no log.**

A typo'd slot renders a sentence with a hole in it. A funnel-hacked reference sequence
shipped a live merge-tag failure — a call-to-action sentence rendered with its
noun missing, reading as a grammatical fragment — for
exactly this reason, and nobody caught it because nothing failed loudly. The same
behaviour applies identically on funnel pages and in email templates.

More slots = more places this can happen. Each single-surface slot adds risk and buys
nothing.

**2. The client cannot see or fix their own copy.**

The GHL page builder is WYSIWYG: the client clicks a headline and types. A headline
that renders as `{{custom_values.hero_headline}}` in the builder is a headline they
cannot read, cannot proofread, and cannot fix. Literal text is *more* editable, not
less. The same argument killed a `cta_label` slot — a button whose text you cannot see
in the builder is a button you cannot fix.

**3. It buries the values that matter.**

In one real account, changing the campaign meant finding a dozen entries among **142
custom values**, most belonging to an unrelated line of business. Signal-to-noise in
the custom-values list is itself a usability feature.

### The one important exception — the editing surface decides

**Email copy stays a custom value even when it appears on only one surface.**

Why: funnel pages are edited in a **WYSIWYG builder** (literal text wins), but email
templates built with `editorType: "html"` are **raw code**. Making email copy literal
would mean editing HTML to change a sentence — which is worse than a custom value, not
better.

**Different editing surface, different answer.** The rule is really: *put the string
wherever the person who will change it can safely change it.* Multi-surface strings go
in custom values because consistency matters more than convenience; single-surface
strings go wherever that surface's editor is friendliest.

### Four buckets — a working taxonomy

| bucket | example keys | who edits, how |
|---|---|---|
| **1 · Campaign mechanics** — changes every run | `event_date` `event_time` `event_timezone` `offer_name` `room_url` `replay_url` `offer_url` | a launcher form |
| **2 · Copy on a code-edited surface** — changes with the topic | `email_preview_line` `email_teach_1_title` `email_teach_1_body` | a launcher form |
| **3 · Derived, NEVER typed** | `event_day` (weekday, from the date) · `event_datetime_iso` (ISO-8601 with offset) · `event_anchor_naive` (`MM-DD-YYYY HH:MM`) | generated, never exposed |
| **4 · Locked business identity** — set once | `business_name` `sender_name` `support_email` `footer_links` `footer_disclaimer` | never in the form |
| **— · Everything else** | hero headlines, body copy, button labels, per-page subheads | **literal text in the builder** |

**Bucket 3 is the one people get wrong.** Nobody should hand-type an ISO timestamp,
and a hand-typed weekday can disagree with the date. Derive both. The ISO anchor is
what `event_start_date` reads in a workflow — **if it is malformed, the pre-event
reminder emails silently never send.** See `workflows.md` §4.

---

## 4. Verification

**A "no `custom_values.` appears in the rendered HTML" check proves NOTHING.** GHL
substitutes server-side, so a resolved page and a page whose tags all resolved to
empty string look identical in that test.

The real assertions:

1. **Against your generated source** (`pageData` JSON, email HTML) — confirm no key
   you intended to inline survives as a merge tag, and every key you intended to keep
   is still there.
2. **On the rendered surface** — spot-check that the expected literal strings actually
   appear. An empty-string resolution shows up as a missing word, not an error.
3. **Before the first send / launch**, list all custom values and diff against every
   key your templates reference. **Any referenced key with no record, or with a blank
   value, is a live silent failure.** Fail the build on it.

A seeding script should report blanks explicitly, e.g.:

```
OK  create   event_replay_hook   ← BLANK, client must supply
...
3 slot(s) created BLANK — they need real values before the first send,
or they render as nothing.
```

**One more, learned the expensive way:** if you keep a `VALUES = {...}` dict in a
seeding script, **re-snapshot it from the live API before editing.** An earlier
version of one such script covered only 37 of ~70 referenced slots; re-running it
would have left two keys undefined and silently killed a live countdown and a hero
treatment. Snapshot the account, then edit — never the reverse.
