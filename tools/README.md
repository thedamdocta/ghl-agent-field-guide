# GHL agent tools

Eleven standalone Python scripts for building on GoHighLevel programmatically.
Production-verified against a real account, then stripped of every client
identifier. Nothing here is hardcoded to any location, funnel, page, form, or
template — everything comes from arguments or environment variables.

Python 3.9+. Standard library only, except `get_token.py` and `create_steps.py`,
which need Playwright to drive an already-logged-in Chrome.

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
page with no credentials at all, and `create_steps.py` drives the UI because step
creation has no API on either host.

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
pip install playwright    # only needed for get_token.py
```

`GHL_LOCATION_ID` is the 20-character id in your GHL URL:
`app.gohighlevel.com/v2/location/<THIS>/dashboard`

Add `.env` and `.jwt` to `.gitignore` — both hold live credentials. Also ignore
`.workflows-deployed.json` (or whatever you pass to `deploy_workflow.py --state`):
it is not a credential, but it holds real workflow ids for a real account.

Every tool runs `--help`. Every tool that writes refuses to write without an
explicit flag.

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
python3 get_token.py --location-id "$GHL_LOCATION_ID"   # writes ./.jwt
```

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

```bash
python3 ghl_generator.py --emit-example > page-spec.json
python3 ghl_generator.py --spec page-spec.json --templates exemplars.json \
    --base captured-pagedata.json --out page.json
```

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
selector that matches nothing, which reads as "my CSS is ignored".

### 6. `create_steps.py` — create somewhere to inject into

```bash
python3 create_steps.py --funnel-id <id> \
    --step "Registration:registration" --step "Confirmation:confirmation" --apply
```

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
python3 create_custom_values.py --values values.json              # report only
python3 create_custom_values.py --scan page.json --scan email.html
python3 create_custom_values.py --values values.json --apply
python3 create_custom_values.py --values values.json --apply --overwrite
```

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
python3 inject_page.py --page-id <id> --funnel-id <id> \
    --page-data page.styled.json --expect "a distinctive phrase"
```

Both ids come from the builder URL:
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

### 10. `deploy_workflow.py` — create and update workflows

```bash
python3 deploy_workflow.py --emit-example > workflows.json   # see the schemas
python3 deploy_workflow.py --spec workflows.json             # validate only
python3 deploy_workflow.py --spec workflows.json --deploy    # write
```

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

**Not done when this exits:** triggers and publishing are still UI steps. A
deployed workflow with no trigger never runs.

### 11. `scrub_secrets.py` — the gate before anything is published

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
 5. get_token.py                               # internal token, for 6-11
 6. ghl_generator.py --spec ... --out page.json  # BUILD the tree
 7. css_emitter.py page.json                   # emit sectionStyles (or nothing styles)
 8. create_steps.py --funnel-id ... --apply    # somewhere to inject into
    create_form.py --name ... --apply          # the funnel's own form
    create_custom_values.py --values ... --apply   # every slot, before it is referenced
 9. inject_page.py --expect "..."              # write the page
10. verify: sites.leadconnectorhq.com/preview/<pageId> — the ONLY proof
11. ghl_mcp.py execute create-email-template   # emails (before workflows)
12. deploy_workflow.py --spec ... --deploy     # workflows reference those templates
13. UI: set workflow triggers, publish, publish the funnel
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
by id, so the template must already exist.

---

## Failure conventions

Every tool fails loudly with the fix in the message. No silent skips, no
defaulting past a missing value. If a tool exits non-zero, do not report the step
as done — particularly `inject_page.py`, which distinguishes "accepted" from
"verified on the rendered page" on purpose.
