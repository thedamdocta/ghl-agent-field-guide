# GHL agent tools

Five standalone Python scripts for building on GoHighLevel programmatically.
Production-verified against a real account, then stripped of every client
identifier. Nothing here is hardcoded to any location, funnel, page, form, or
template — everything comes from arguments or environment variables.

Python 3.9+. Standard library only, except `get_token.py`, which needs Playwright.

---

## The one thing to understand first: GHL has two APIs and two credentials

Getting this wrong is the most common way to lose an afternoon.

| | Public API | Internal API |
|---|---|---|
| Host | `services.leadconnectorhq.com` | `backend.leadconnectorhq.com` |
| Credential | **PIT** (`Authorization: Bearer`) | **token-id** JWT (`token-id:` header) |
| Where it comes from | Settings → Private Integrations | a logged-in browser session |
| Lifetime | long-lived | ~1 hour |
| Covers | contacts, custom values, email templates, most CRUD | funnel page writes, workflow CRUD |
| Tool | `ghl_mcp.py` | `inject_page.py`, `deploy_workflow.py` |

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
read-only. Those need tools 3 and 5 below. Re-check with `search` before
believing it — the catalogue grows.

### 2. `get_token.py` — capture the internal `token-id`

Needed only for tools 3 and 5.

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

### 3. `css_emitter.py` — make styling actually apply

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

### 4. `inject_page.py` — write a page and prove it

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

### 5. `deploy_workflow.py` — create and update workflows

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

---

## Typical end-to-end order

```
1. cp .env.example .env, fill in GHL_PIT + GHL_LOCATION_ID
2. ghl_mcp.py locations                     # prove auth
3. ghl_mcp.py search / describe             # find real operations, never guess
4. ghl_mcp.py execute ...                   # custom values, then email templates
5. get_token.py                             # internal token, for steps 6-8
6. css_emitter.py page.json                 # emit sectionStyles
7. inject_page.py --expect "..."            # write the page, verify rendered
8. deploy_workflow.py --spec ... --deploy   # workflows (templates must exist)
9. UI: set workflow triggers, publish, publish the funnel
```

Create **custom values before anything references them.** GHL resolves an unknown
`{{custom_values.x}}` to an empty string, silently — a live email that reads
"Grab the now" is what that failure looks like in production.

---

## Failure conventions

Every tool fails loudly with the fix in the message. No silent skips, no
defaulting past a missing value. If a tool exits non-zero, do not report the step
as done — particularly `inject_page.py`, which distinguishes "accepted" from
"verified on the rendered page" on purpose.
