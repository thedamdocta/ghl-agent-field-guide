# GHL agent tools

Standalone Python scripts for building on GoHighLevel programmatically.
Production-verified against a real account, then stripped of every client
identifier. Nothing here is hardcoded to any location, funnel, page, form, or
template — everything comes from arguments or environment variables.

Python 3.9+. Standard library only, except the four that drive an already-logged-in
Chrome and so need Playwright: `get_token.py`, `create_steps.py`,
`configure_trigger.py` and `publish_workflow.py` (plus `ghl_ui.py`, the library the
last two share). All of them import Playwright *lazily*, so `--help` works on a
machine that has never installed it.

---

## The one thing to understand first: GHL has two APIs and two credentials

Getting this wrong is the most common way to lose an afternoon.

| | Public API | Internal API |
|---|---|---|
| Host | `services.leadconnectorhq.com` | `backend.leadconnectorhq.com` |
| Credential | **PIT** (`Authorization: Bearer`) | **token-id** JWT (`token-id:` header) |
| Where it comes from | Settings → Private Integrations | a logged-in browser session |
| Lifetime | long-lived | ~1 hour |
| Covers | contacts, custom values, email templates, form *reads*, most CRUD | funnel page writes, form writes, workflow CRUD |
| Tool | `ghl_mcp.py`, `create_custom_values.py` | `inject_page.py`, `create_form.py`, `deploy_workflow.py` |

A third category needs **neither**: `capture_funnel.py` reads any *public* funnel
page with no credentials at all, and `create_steps.py`, `configure_trigger.py` and
`publish_workflow.py` drive the UI because creating a funnel step, attaching a
workflow trigger and publishing a workflow have **no API on either host**. Those
three borrow a live browser session instead of a token.

The PIT does **not** reach the internal API — it returns `Unauthorized`.
`Authorization: Bearer` does **not** work on the internal API either, for *any*
token; that host wants the `token-id` header.

Two more rules that hold everywhere:

- **curl, not urllib.** Cloudflare 403s the default Python user agent on GHL
  hosts. Every request in these tools goes through the system `curl` with a
  browser UA. This is not superstition — swapping it back reintroduces the 403.
- **A resolved request is not a permitted one.** `dryRun: true` returns
  `authorizationVerified: false`; it checks the *shape* of a call, not your
  token's scopes. The only proof is one real call.

---

## Setup

```bash
cp .env.example .env      # then fill in GHL_PIT and GHL_LOCATION_ID
pip install playwright    # only for the four UI-driving tools; no `playwright
                          # install` — they CONNECT to your Chrome
```

`GHL_LOCATION_ID` is the 20-character id in your GHL URL:
`app.gohighlevel.com/v2/location/<THIS>/dashboard`

Add `.env` and `.jwt` to `.gitignore` — both hold live credentials. Also ignore
`.workflows-deployed.json` (or whatever you pass to `deploy_workflow.py --state`)
and `.ghl-ids.json` (the id-lookup cache): neither is a credential, but both hold
real ids for a real account.

Every tool runs `--help`. Every tool that writes refuses to write without an
explicit flag.

### You do not have to go and find the ids

`--location-id`, `--funnel-id` and `--page-id` are **optional everywhere**. Give a
name instead — `--funnel "Launch"`, `--page "Opt-in"` — or give nothing at all when
there is only one candidate. `ghl_ids.py` resolves them and every tool prints what
it resolved:

```
  resolved funnel "Launch"       -> <funnelId>   (matched by name)
  resolved page   "Opt-in"       -> <pageId>     (matched by name)
```

The rule underneath, which is worth keeping if you extend these tools:

> **Refuse to invent. Never refuse to look up.**

An id is a fact about the account, so it gets looked up. A form name, a step name,
a spec — those are decisions, and a tool that invents one is worse than a tool that
stops. `create_form.py` still refuses without `--name`, and always should. And when
a lookup finds *several* real candidates, it lists them and stops: picking one for
you would be guessing between real options, which is how the wrong page gets
overwritten.

Explicit ids still work exactly as they always did, and skip the lookup entirely.

---

## The tools, in the order you use them

### 1. `ghl_mcp.py` — start here, always

A client for GHL's own MCP server, which fronts a generated catalogue of the
entire public API. **This is the highest-leverage tool in the directory**: it
replaces endpoint guessing entirely.

```bash
python3 ghl_mcp.py locations                       # proves the PIT works
python3 ghl_mcp.py search "email template"         # what operations exist?
python3 ghl_mcp.py describe create-email-template  # exact method/path/schema
python3 ghl_mcp.py execute create-email-template --yes --params-file body.json
```

The loop is always **search → describe → execute**. Never invent a REST path;
ask the catalogue. Operation ids do not follow the naming you would guess (a
listing operation can be `GET-all-or-<resource>` rather than `list-<resource>`),
which is precisely why guessing fails and searching works.

Also importable:

```python
from ghl_mcp import GHLMCP, load_env
pit, loc = load_env()
GHLMCP(pit, loc).describe_operation("create-custom-value")
```

Traps it handles for you, each one previously paid for in time:
responses are **SSE** (`data:` lines, not one JSON body) and **double-wrapped**
(JSON-RPC → `content[].text` → the real JSON); writes **require an
`idempotencyKey`**; `locationId` goes in the **path**, never the query (query
returns `422 "property locationId should not exist"`); the PIT can usually
create and update but **not delete** — archive instead.

Write operations refuse to run without `--yes`.

**What the MCP does not cover:** no `create-workflow`, and funnel pages are
read-only, and there is no create-funnel-step operation at all. Those need
`inject_page.py`, `deploy_workflow.py` and `create_steps.py` below. Re-check with
`search` before believing it — the catalogue grows.

### 1b. `ghl_ids.py` — resolve the ids so nothing else has to ask for them

```bash
python3 ghl_ids.py                          # every funnel in the location, with ids
python3 ghl_ids.py --funnel "Launch"        # that funnel's id, and all of its pages
python3 ghl_ids.py --funnel "Launch" --page "Opt-in" --json
python3 ghl_ids.py --refresh                # ignore the cache after creating something
python3 ghl_ids.py --self-test              # 15 offline fixture tests, no credentials
```

Read-only. Every other tool imports it, which is why `--funnel "<name>"` works
wherever `--funnel-id` does. Two routes do the whole job:

```
GET services.leadconnectorhq.com/funnels/funnel/list?locationId=<loc>&limit=20
    -> {"funnels": [{"_id", "name", "steps": [...]}]}

GET services.leadconnectorhq.com/funnels/page
        ?funnelId=<f>&locationId=<loc>&limit=20&offset=0
    -> a BARE ARRAY of {"_id", "name", "funnelId", "stepId"}
```

**Two traps, both live-confirmed, both worth the ink:**

1. `/funnels/page` returns a **bare array**, not `{"pages": [...]}` — it is the one
   collection route here that does not wrap. A parser reaching for a `"pages"` key
   gets `None`, reports "no pages", and makes a healthy endpoint look broken. That
   single wrong assumption is the whole reason this route had a bad reputation.
2. **All four query params are required.** Drop `locationId` or drop `offset` and it
   returns 422 rather than defaulting.

Results are cached in `.ghl-ids.json` for an hour so a multi-step build does not
re-query on every tool; `--refresh` bypasses it. Gitignore it — it holds your
account's funnel and page names.

### 2. `get_token.py` — capture the internal `token-id`

> Full cold-start runbook, including launching Chrome yourself and what to do when
> no authenticated profile exists yet:
> [`../knowledge/getting-the-token.md`](../knowledge/getting-the-token.md)

Needed by `inject_page.py`, `create_form.py` and `deploy_workflow.py`.
`create_steps.py` needs the same logged-in Chrome, but drives the UI rather than
the token.

**Prerequisite:** Chrome must already be running with a remote-debugging port
open, on a dedicated profile that you have already logged into GHL by hand:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.ghl-agent-profile"
```

Use a **dedicated** `--user-data-dir`. Chrome will not open a debugging port on a
profile another instance already owns, and the failure is quiet. Verify the port
is really listening with `curl -s http://127.0.0.1:9222/json/version` before
blaming the script.

```bash
python3 get_token.py                                    # writes ./.jwt
```

The location id comes from `--location-id`, then `$GHL_LOCATION_ID`, then `.env`.

**This is passive observation.** It attaches to your browser, subscribes to
network request events, navigates to a normal in-app URL, and reads the
`token-id` request header off calls the app makes on its own behalf. It does not
read storage, cookies, or the profile on disk, and it captures no credentials. If
the human logs out it stops working — there is no offline path, by design.

The token lives about an hour and GHL refreshes it while the session is alive, so
just re-run it. Do not cache it beyond one build.

### 3. `capture_funnel.py` — read a real page before you write one

No credentials. Works on **any public GHL funnel page**, including one you did not
build.

```bash
python3 capture_funnel.py https://funnel.example.com/optin --out optin.json
python3 capture_funnel.py <url> --exemplars exemplars.json   # clonable elements
python3 capture_funnel.py <url> --summary                    # analysis, no files
```

A public GHL funnel page is a server-rendered Nuxt 3 app, and the **complete page
definition ships inside the HTML** in `__NUXT_DATA__`. The payload is
`devalue`-serialized: a flat array where index 0 is the root and **every integer
inside an object or array is a pointer back into that same array**. Resolve those
pointers and you have the whole section→row→col→element tree — styles, responsive
flags, button wiring, merge tags.

Two things the resolver must do or it breaks: bound the depth *and* keep a visited
set (the graph self-references — one without the other still hangs), and fetch
with `curl` and a browser UA (Cloudflare 403s Python's default UA).

Desktop and mobile payloads are **byte-identical** — GHL serves one definition and
does responsive work with per-element flags. Do not fetch twice expecting two
layouts.

`--exemplars` is the important flag: it writes one clonable element per type, which
is what `ghl_generator.py` consumes. Mind the **role trap** — an exemplar carries
its original *role*, not just its schema. Cloning a page's first section when that
section was the sticky nav produced seven stacked sticky navs, schema-valid and
semantically wrong, with a zero-difference key diff. When a type occurs more than
once the tool says so; `--pick TYPE=N` chooses another.

Output holds the source account's real ids. Gitignore it.

### 4. `ghl_generator.py` — build the `pageData` tree

> **No `--templates` needed.** A corpus of 15 verified element types ships as
> `element-templates.json` and is the default. Pass `--templates` only to match an
> existing design. Likewise `create_form.py --seed` needs no donor form. See
> [`../knowledge/building-from-scratch.md`](../knowledge/building-from-scratch.md).

```bash
python3 ghl_generator.py --emit-example > page-spec.json
python3 ghl_generator.py --spec page-spec.json --funnel "Launch" --page "Opt-in" \
    --out page.json
python3 ghl_generator.py --spec page-spec.json --templates exemplars.json \
    --base captured-pagedata.json --out page.json    # explicit ids also still work
```

The ids here are only *stamped onto* the sections, so this tool stays usable
offline: if there is no PIT to look one up with, it prints a note and builds
anyway. A `--funnel`/`--page` NAME that does not resolve is fatal, though — you
asked for something specific, and a blank id would hide the mistake until the page
rendered wrong.

`css_emitter.py` *styles* a tree and `inject_page.py` *writes* one; this is what
**builds** one. It clones the exemplars from step 3 and overrides only text, colour
and layout — because a GHL element carries dozens of required keys and every value
is wrapped as `{"value": X}`, so hand-written elements fail in ways that never name
the missing key.

It mints authoring ids (no leading `c`) and sets `extra.nodeId` to the `c`-prefixed
rendered id, which is the relationship `css_emitter.py` depends on.

Three semantics it preserves, each one paid for:

- **Button actions are not interchangeable.** `go-to-next-funnel-step` needs no
  target; `scroll-to-element` writes `extra.scrollToElement`; `openPopup` needs a
  `popupId`; `go-to-funnel-step` needs a step id. Writing a scroll target into
  `visitWebsite` is schema-valid, returns 201, and produces a button that moves the
  page **0px** — that is how every CTA on a six-page funnel ended up inert. The
  tool refuses an action that requires a target when none was given.
- **Form submit behaviour lives on the PAGE element, not the form record.**
  Writing `formAction.actionType` / `redirectUrl` onto the form record returns 200
  and silently does not persist. Only `"ThankYouMessage"` is verified;
  `"Redirect"` is a candidate value, **unverified**.
- **The custom-code payload field is `extra.customCode`.** Guessing `code` / `html`
  / `text` renders an empty block and the script never runs.

Pass `--base` (a real page's `pageData`) so the seven top-level builder blocks are
cloned rather than defaulted — the empty defaults are unverified and the tool says
so loudly.

### 5. `css_emitter.py` — make styling actually apply

Run this **before** injecting any page.

```bash
python3 css_emitter.py page.json --root-vars '{"--ink":"#111","--bg":"#fff"}'
# -> page.styled.json
```

The core discovery: **GHL does not compile an element's `styles` dict into CSS at
render time.** The builder generates one CSS *string* per section and stores it at
`section.general.sectionStyles`, scoped to specific element ids. Set every style
property you like in `styles`, POST it successfully, and get back an unstyled
page. This module emits that string for your own ids.

It also handles the trap underneath the trap: **two id namespaces.** Every node
has an authoring id (`node.id`) and a rendered id (`node.extra.nodeId`).
Section-level layout keys off the first; element-level styling — button fills,
nav typography — keys off the second. Emit only one and half your CSS lands on a
selector that matches nothing, which reads as "my CSS is ignored". The two are
**independent ids**, not one id with a `c` in front — verified, they matched on 0
of 78 nodes of a real builder-authored page — so read the pair off `extra.nodeId`
and never reconstruct one from the other.

This tool is per-**element**. The design **system** is a different file.

### 5b. `page_shell.py` + `page-styles.starter.css` — the design system

```bash
python3 page_shell.py --emit                                 # print the block
python3 page_shell.py --attach page.json --out page.json     # BEFORE css_emitter.py
python3 page_shell.py --check page.json                      # prove it is wired
```

`sectionStyles` is the right home for "this heading is 76px" and the wrong home for
a type scale, a spacing scale, one button treatment and component classes. Those
belong in a page-level `<style>` riding in a `custom-code` element — and three
undocumented rules make that block ship inert: the payload field is
**`extra.customCode`**, the `<script>` must **not** be nested inside a `<div>`, and
it must wait for GHL's **`hydrationDone`** with page settings' "Optimise JavaScript"
turned **off**. `page_shell.py` emits a payload that satisfies all three and appends
it as a final section.

> **The stylesheet:** [`page-styles.starter.css`](page-styles.starter.css) ships
> paste-ready with tokens at the top and the full page selector map — the button
> wrapper is `div.c-button` and the button itself is `button[class*=cbutton]`, the
> inline form is `.ghl-form-wrap` (inline in the page document, *not* an iframe,
> unlike an external embed), and GHL's flex box inside every section and column is
> `> .inner`. Change the tokens; leave the selectors alone until something
> misbehaves.

Run `--attach` **before** `css_emitter.py`, or the shell section gets no
`sectionStyles` of its own and the page ends in roughly 130px of empty space beneath
the footer.

`--check` is a static check: exactly one shell, script wired, `<script>` not nested,
and every `gp-*` class the stylesheet targets is one the runtime script actually
assigns. A rule that styles a class nobody sets is invisible in review and does
nothing on the page — the same failure as a misspelled selector.

**Why there is a script at all:** a design system needs semantic section classes,
and GHL gives you no verified way to set one from the authoring tree
(`extra.customClass` exists but was empty on all 158 of its occurrences in the captured corpus —
**UNVERIFIED**). The script tags each section from its **content** — an `h1` makes a
hero, a form makes a form plate — never from its position, because a positional list
is wrong the moment a page has a different number of sections.

**Read [`../knowledge/page-css-and-classes.md`](../knowledge/page-css-and-classes.md)
before changing any selector.** It carries the verified specificity ladder, which is
what actually decides whether your CSS applies: `css_emitter.py` *forces*
`background-color`, `color`, `padding-top` and `padding-bottom` at `(0,2,0)` and is
injected **after** your stylesheet, so an equal-specificity rule of yours ties and
loses; and GHL itself emits **ID-selector** rules at `(1,1,0)` for element margins
and widths, which no class-based rule can outrank.

### 6. `create_steps.py` — create somewhere to inject into

```bash
python3 create_steps.py --funnel "Launch" \
    --step "Registration:registration" --step "Confirmation:confirmation" --apply
```

`--funnel-id <id>` still works. Drop the funnel entirely when the location has one.
The steps themselves are never invented: no `--step`/`--steps-file`, no run.

`inject_page.py` writes *into* an existing page; it cannot conjure one. **There is
no REST route for creating a funnel step** — `POST backend/funnels/page` 404s, and
`PUT services|backend /funnels/page` returns `403 "This route is not yet supported
by the IAM Service"` for both the PIT and the internal JWT. That is a platform
gate, not a scope problem. So this drives the real builder UI in the same
already-logged-in Chrome that `get_token.py` attaches to.

The non-obvious part: the dialog's inputs are **React-controlled**, so
`el.value = "x"` updates the DOM without telling React — the field looks filled,
the Create button stays disabled, and nothing explains why. The injected script
calls the native value setter and dispatches `input` + `change`. Selectors match on
visible button text, because GHL's generated class names churn between releases and
the labels do not.

It reads existing step names first and skips matches (GHL happily creates a second
step with the same name), derives a URL-safe path when you omit one, and **verifies
each step exists on the funnel afterwards** — a click that lands is not a step that
exists.

Nothing is created without `--apply`.

> **Styling it:** [`form-styles.starter.css`](form-styles.starter.css) ships
> paste-ready with the full selector map (the submit button is `.ghl-submit-btn`,
> dropdowns need eight rules, everything needs `!important`). Load it into
> `formData.form.fieldCSS`.

### 7. `create_form.py` — give the funnel its own form

```bash
python3 create_form.py --list                               # find a clone source
python3 create_form.py --dump <sourceFormId> --out src.json
python3 create_form.py --name "Webinar registration" --clone-from-file src.json \
    --fields first_name,email,phone --id-file .form-id --apply
```

Use a **native** form: a hand-rolled `<form>` in a custom-code block renders
perfectly and captures no leads. And give each funnel **its own** form — pointing a
page at a generically-named account form imports that form's fields, image, linked
header, branding and fixed width, and restyling it changes every other place it is
embedded.

Build it by **cloning a working form's `formData`** and deleting fields; hand-written
field dicts miss required keys.

Two warnings the tool encodes:

- **`POST /forms/{id}` 422s if the body contains `locationId`**, and the 422 names
  the field. Note the asymmetry: create (`POST /forms/`) *requires* `locationId` in
  the body, update (`POST /forms/{id}`) *rejects* it. `POST /forms/{id}` is the
  update route — `PUT` and `PATCH` both 404.
- **The forms list returns `name: null`** for forms created via the backend API, so
  any "does my form exist?" check that matches on name misses and creates a
  duplicate, every run, forever. Match on a stored id — that is what `--id-file` is
  for, and why re-runs update instead of duplicating.

The form renders **inline in the page document, not in an iframe**, so page CSS
reaches its submit button.

### 8. `create_custom_values.py` — create every slot before anything references it

```bash
python3 create_custom_values.py --surfaces --scan page.json --scan email.html
python3 create_custom_values.py --values values.json              # report only
python3 create_custom_values.py --scan page.json --scan email.html
python3 create_custom_values.py --values values.json --apply
python3 create_custom_values.py --values values.json --apply --overwrite
```

**Run `--surfaces` first, before you create anything.** A custom value earns its
place only when the same string appears on **more than one surface** (one page or one
email template = one surface); everything else should be literal text the client can
read and edit in the builder. `--surfaces` counts distinct surfaces per key and lists
the single-surface ones — the measurement that decision needs. Pure local analysis:
no credentials, no account access, writes nothing. On one real build it showed 59 of
75 slots on exactly one surface, each a silent-failure site that bought nothing. The
exception it flags but cannot judge: copy whose only surface is a raw-HTML email
template is usually better left as a slot.

**GHL resolves an unknown `{{custom_values.x}}` to the empty string. Silently.** A
live email once shipped reading "Grab the now" for exactly this reason and nothing
failed. `--scan` walks your generated pages and emails, extracts every referenced
slot, and reports the ones that do not exist — those are live silent failures, and
the tool exits non-zero on them.

Four API facts it is built around:

- **`PUT /customValues/bulk` is gone.** Not renamed — gone. It returns the
  *per-value* 422, and a per-value body to the same URL 404s with "The custom value
  id is invalid", i.e. `bulk` is being parsed as the `{id}` segment. Per-value
  writes only; twenty-odd calls is fine.
- **A per-value PUT needs `name` AND `value`.** Value alone fails. The `name` is
  sourced from the live record, never from a local constant, so an update can never
  silently rename a key.
- **A PUT needs an existing id**, so **creation is a separate call** (`POST`, no
  id). Resolve keys → ids first, then create the missing and update the rest.
- **`locationId` goes in the path**; in the query it 422s.

`fieldKey` is the wrapped form — `{{ custom_values.x }}` with braces *and* interior
spaces — so it is parsed with a regex, never string-matched.

Before you seed 70 slots, read `knowledge/custom-values.md` §3: a custom value earns
its place only when the same string appears on **more than one surface**. In one real
build 59 of 75 slots were single-surface — each a silent-failure risk that bought
nothing and made the client's own copy unreadable in the builder.

### 9. `inject_page.py` — write a page and prove it

```bash
python3 inject_page.py --funnel "Launch" --page "Opt-in" \
    --page-data page.styled.json --expect "a distinctive phrase"
python3 inject_page.py --page-id <id> --funnel-id <id> \
    --page-data page.styled.json --expect "a distinctive phrase"
```

This one WRITES, so read the `resolved page` line it prints before it sends
anything, or run it with `--dry-run` first. If you would rather supply the ids
yourself they are both in the builder URL:
`.../funnels/<funnelId>/pages/<pageId>/edit`

It reads the current `pageVersion`, POSTs `current + 1` to the builder's autosave
endpoint, then verifies on the **rendered preview URL** with retries.

Two reasons for that shape. `pageVersion` is optimistic concurrency — a wrong
version means your write is silently lost. And **read-after-write lag is real**: a
success response means "accepted", not "rendered". Checking once, immediately,
produces a false failure and sends you hunting a bug that does not exist.

Always pass `--expect`. Without it, verification only proves the page responds.
And make it a short distinctive phrase from your copy, not markup — GHL
*recompiles* page content, so what you POST is not byte-for-byte what is served.
(Email templates, by contrast, are stored verbatim.)

`--dry-run` validates and reports the version it would write.

### 10. `push_emails.py` — build email templates and prove they arrived

```bash
cp email-template.starter.html emails/01-welcome.html        # START HERE
python3 push_emails.py --emit-example > emails.manifest.json
python3 push_emails.py --manifest emails.manifest.json --check     # offline lint
python3 push_emails.py --manifest emails.manifest.json --dry-run   # payloads, no network
python3 push_emails.py --manifest emails.manifest.json --apply --verify
python3 push_emails.py --archive "SEQ 03" --apply
```

**Email is the easy surface in GHL.** `editorType:"html"` stores `editorContent`
**verbatim** — round-trip byte-identical, verified — unlike funnel pages, which GHL
recompiles at save time. Whatever you author is what sends. GHL adds exactly two
things: an outlook-fixes comment and MSO font-colour fallbacks.

**[`email-template.starter.html`](email-template.starter.html) is the artifact to
edit.** A complete paste-ready dark-ground document — table-based, inline-styled,
Outlook-safe — with masthead, stage label, headline, body, optional image, one
button, secondary link, signature and footer, and a six-token neutral palette
documented in a header block that also explains how it is applied and how it is
verified. Do not assemble one from fragments.

`--check`, `--dry-run` and `--emit-example` need neither credentials nor a network,
and **a lint failure refuses the write**. The lint is not style policing; every rule
is a client that renders your email wrong: a `<div>` background or a `float` Outlook
ignores outright, a missing `bgcolor` attribute beside an inline `background-color`,
an `<img>` with no `alt` when Outlook blocks images by default, a `.svg` Gmail will
not render, a text node with no explicit colour that a dark-mode client inverts to
invisible, body copy under the 16px floor that makes iOS Mail rescale the whole
message. It also prints every `{{custom_values.x}}` the templates reference, to feed
straight into `create_custom_values.py`.

Three API facts it is built around:

- **Writes require an `idempotencyKey`**, and this one is derived from a **hash of
  the content**, not the clock. A timestamped key is the obvious first
  implementation and it defeats the purpose: every retry becomes a new logical
  write. Content-addressed means a retry is the same write, while a genuine edit
  still gets a new key and is not swallowed as a duplicate.
- **The PIT cannot DELETE** — 401 "token is not authorized for this scope".
  `--archive` retires a template with `archived: true` instead.
- **Match by name.** There is no other natural key, so a re-run without matching
  creates a second `SEQ 01` every time, forever.

**`--verify` is the point.** The write response carries `data.previewUrl`, a
Firebase-hosted rendering of the *stored* template; `--verify` fetches it and
confirms a distinctive phrase from your copy is really in there. A `200` is not
proof. The results file also records every template **id** — a hard dependency of
the workflow build below.

### 11. `deploy_workflow.py` — create and update workflows

```bash
cp workflow-spec.starter.json workflows.json                 # START HERE
python3 deploy_workflow.py --emit-example > workflows.json   # or generate one
python3 deploy_workflow.py --spec workflows.json             # validate + lint
python3 deploy_workflow.py --spec workflows.json --deploy    # write
```

**`workflow-spec.starter.json` is the artifact to edit.** A complete four-workflow
lifecycle campaign — registered / did-not-attend / attended / closing — covering 16
action types, with two real branches, sibling exclusion, both wait shapes, and every
trap annotated inline via `_note` keys (keys starting with `_` are stripped before
deploy). Every value is a placeholder.

**Branching.** An `if_else` may carry `then` and `else`, each a nested list of steps.
That compiles to the three-node shape GHL actually stores — a condition node plus
`branch-yes` and `branch-no` nodes, with each path hanging off its branch node.
Listing steps *after* an `if_else` instead builds a straight line in which every
contact runs them whatever the condition said; the compiler refuses that rather than
deploying it.

**The linter runs on every spec** and blocks `--deploy` on an error. It catches the
failures that return 200 and then do nothing: empty `workflow_id` or `template_id`,
`branches: []`, `segments: []`, a blank event anchor, a `goto` to a nonexistent step,
a dangling `next`/`parentKey`, and tag conditions whose tag nothing in the spec
produces.

The public API has no `create-workflow`, which makes workflows look hand-built.
They are not — the internal API has full CRUD. POST mints an empty workflow and
returns an id; PUT installs the steps. Two calls, necessarily.

Naming trap: `workflowData.templates` is the list of **steps**, unrelated to email
templates. An email step *references* a template by id, which is why templates
must exist before you deploy a workflow that sends them.

The step factories are importable and each docstring records the failure its
schema prevents:

- `event_anchor()` / `wait_before()` — an **event-anchored** wait counts backward
  from an anchor date. Elapsed waits cannot express "3 hours before"; chaining
  them delivers the reminder *after* the event ends. `appointmentCondition:
  "skip"` makes a late registrant skip past reminders rather than receive them
  late.
- `branch_on_tag()` — an `if_else` with `segments: []` deploys happily and then
  never evaluates. Every contact falls through the none-branch and the branch is
  decorative.
- `leave_workflow()` — sibling exclusion needs a **real** workflow id. Empty, the
  step is inert and a contact can sit in two contradictory branches at once.
  Cold start: deploy once to mint ids, then run again to wire them. The `--state`
  file carries ids between runs and is what stops re-runs creating duplicates.

**Not done when this exits:** the workflow has a body and nothing else. Its trigger
is unset and it is still a Draft — which means it is inert. The next two tools are
what make it actually run, and they are the last two steps of the chain.

### 11b. `configure_trigger.py` — attach the trigger (there is no API)

```bash
python3 configure_trigger.py --workflow "WF 1" --trigger "Form Submitted"
python3 configure_trigger.py --workflow "WF 1" --trigger "Form Submitted" --apply
python3 configure_trigger.py --workflow "WF 2" --trigger "Contact Tag" \
    --filter "Tag is:did-not-attend" --apply
```

A workflow with no trigger has no way in. Every step is correct, every email exists,
and not one contact will ever enter it — and nothing in the UI says so. There is no
endpoint for this on either API; the `trigger` field in a build spec is a note to a
human, and nothing consumes it. So this drives the builder in the same
already-logged-in Chrome that `get_token.py` attaches to.

Three things it handles that are not guessable:

- **The picker renders below the fold.** A coordinate click at those coordinates
  lands on whatever is actually on screen there, which is usually nothing, silently.
  Every click in the picker is a *dispatched* MouseEvent instead, which fires on the
  element wherever it is.
- **The first-view modal blocks everything.** The AI-builder modal opens the first
  time any workflow is opened and eats every click underneath it. It is dismissed on
  the way in, before anything else is attempted.
- **Frame references die on Vue Router navigation.** The frame URL does not change,
  but the handle goes stale and every later call throws. The frame is re-acquired by
  polling for expected content after every navigating click.

**Filters are the brittle part** — they are framework-generated select widgets with
no stable ids, found by position in the config panel. When a filter step fails this
tool **saves nothing** and says so, leaving the panel open for you to finish by hand:
a half-configured trigger that got saved is worse than no trigger, because it looks
done. It also refuses to add a trigger whose label is already on the canvas unless
you pass `--force`, since two triggers means two ways in and every contact runs the
workflow twice.

It verifies by re-reading the canvas afterwards — a click that lands is not a trigger
that exists. Nothing is changed without `--apply`, and the workflow is still a Draft
when it exits.

### 11c. `publish_workflow.py` — Draft → Published (there is no API)

```bash
python3 publish_workflow.py --all
python3 publish_workflow.py --workflow "WF 1" --apply --verify
python3 publish_workflow.py --all --apply --verify
```

A workflow deploys in **Draft**, and a draft workflow is inert: the trigger never
fires, no contact ever enters it, and nothing anywhere tells you. Everything the
build did is real and does nothing. There is no endpoint for publishing either, so
this flips the toggle.

Two details, both of which cost hours if you improvise:

1. **Read the state from `aria-checked`, never from page text.**
   `body.innerText.includes('Draft')` returns **true on a workflow that is already
   published** — the word survives elsewhere in the builder chrome (save-state
   labels, version history). A tool that believes it reports "still draft" forever,
   or reports success at random. The toggle is `[role="switch"]`;
   `aria-checked="true"` means Published and nothing else does.
2. **The toggle alone persists nothing.** Flipping it sets local Vue state. Navigate
   away without clicking Save and the workflow is a draft again, with no error and no
   warning. This tool refuses to report success if it cannot find and click Save.

One **fresh page load per workflow**: walking the paginated list in place loses frame
references and starts throwing on the second row. `--all` opens every workflow on the
list and skips the ones already live, so it publishes exactly the drafts. `--verify`
re-opens each workflow from a fresh list load and re-reads `aria-checked`, which is
the only thing that proves Save actually persisted rather than the Vue state still
being warm. Names resolve the way `ghl_ids.py` resolves a funnel — exact, then a
unique prefix, then a unique substring, and several matches is an error that lists
them.

### `ghl_ui.py` — the shared iframe plumbing behind both

```bash
python3 ghl_ui.py --self-test
```

Not a step; a library. Both UI tools stand on it, so the cross-origin rules live in
one place and cannot drift apart: acquire the *frame* rather than the page, prefer
dispatched events over the mouse, translate any real mouse click through the iframe's
**queried** `bounding_box()` rather than a hardcoded offset (list view and full-page
builder view do not agree), re-acquire frames after navigation, and reach a builder
only by clicking a row in the list — a direct `/automation/builder/<id>` URL does not
create the iframe at all. Its module docstring is the reference for all of that.
`--self-test` runs offline fixture tests: no browser, no network, no account touched.

> **UNTESTED against a live account.** Both tools above were verified offline —
> argument parsing, every refusal path, and both state machines driven against a
> stubbed browser — but **no browser path in either has been run against a real
> GoHighLevel account.** Treat your first run as a test, not as a deploy: start with
> a `--dry-run` on one workflow and read the result before you reach for `--all`.

### 12. `scrub_secrets.py` — the gate before anything is published

```bash
python3 scrub_secrets.py . --env-file ../project/.env --secret "Client Name"
```

A knowledge repo like this one is written by copying lessons out of real client
work, which is exactly the process most likely to carry an account id, a CDN URL or
a client's name along with the lesson. Exits non-zero on any finding, so it can gate
a commit hook. Pass your real literals with `--secret` / `--env-file` — a generic
scanner cannot know them, and they are the ones that matter.

---

## Typical end-to-end order

```
 1. cp .env.example .env, fill in GHL_PIT + GHL_LOCATION_ID
 2. ghl_mcp.py locations                       # prove auth
 3. ghl_mcp.py search / describe               # find real operations, never guess
 4. capture_funnel.py <url> --exemplars ex.json  # READ a real page first
 4b. ghl_ids.py                                # see the account; ids resolved for you
 5. get_token.py                               # internal token, for 6-11
 6. ghl_generator.py --spec ... --out page.json  # BUILD the tree
 7. page_shell.py --attach page.json           # the design system, BEFORE the emitter
    css_emitter.py page.json                   # emit sectionStyles (or nothing styles)
    page_shell.py --check page.json            # one shell, wired, no orphan classes
 8. create_steps.py --funnel "..." --apply     # somewhere to inject into
    create_form.py --name ... --apply          # the funnel's own form
    create_custom_values.py --values ... --apply   # every slot, before it is referenced
 9. inject_page.py --expect "..."              # write the page
10. verify: sites.leadconnectorhq.com/preview/<pageId> — the ONLY proof
11. cp email-template.starter.html emails/01.html   # emails (before workflows)
    push_emails.py --manifest ... --check           # offline; refuses a bad write
    push_emails.py --manifest ... --apply --verify  # writes, then proves on previewUrl
12. deploy_workflow.py --spec ... --deploy     # workflows reference those template ids
13. configure_trigger.py --workflow ... --trigger ... --apply   # UI-driven; no API
14. publish_workflow.py --all --apply --verify # UI-driven; no API. Draft == inert
15. UI, by hand: publish the funnel (no tool for that one yet)
```

Steps 4→7 are the read/build/style loop; run them as many times as you like without
touching the account. Nothing before step 8 writes anything.

Two ordering rules that are not negotiable:

**Create custom values before anything references them.** GHL resolves an unknown
`{{custom_values.x}}` to an empty string, silently — a live email that reads
"Grab the now" is what that failure looks like in production. Run
`create_custom_values.py --scan` over your generated pages and emails as the check.

**Create email templates before deploying workflows.** `workflowData.templates` is
the list of *steps*, not email templates — but an email *step* references a template
by id, so the template must already exist. `push_emails.py` writes those ids to its
results file precisely so the workflow spec can consume them.

---

## Failure conventions

Every tool fails loudly with the fix in the message. No silent skips, no
defaulting past a missing value. If a tool exits non-zero, do not report the step
as done — particularly `inject_page.py`, which distinguishes "accepted" from
"verified on the rendered page" on purpose.
