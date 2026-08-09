# GoHighLevel's Own MCP Server

`https://services.leadconnectorhq.com/mcp/anthropic/v2`

> **Status:** probed and used in production against a live account on 2026-08-04 and
> 2026-08-06 with a sub-account Private Integration Token. Every behaviour below was
> observed. Items we did not exercise are marked **UNVERIFIED**.

---

## Why this exists and why you should reach for it first

GoHighLevel publishes an MCP server that fronts its entire public API. For an agent,
this changes the shape of the work in one specific way:

> **The `search_operations` -> `describe_operation` -> `execute_operation` loop replaces
> endpoint guessing entirely.**

That matters more than it sounds. Guessing GoHighLevel endpoint names is actively
dangerous, not merely inefficient — unknown paths fall through to generic get-by-id
routes and return `200` with a plausible-looking body, so a guess can produce a
convincing false discovery (see `api-map.md` for the nonsense-id control that exposes
this). The MCP catalogue removes the guessing step from the process. **Ask the
catalogue what exists rather than probing paths.**

Practically: before you conclude a GoHighLevel capability is missing, search the
catalogue. We once told a client that workflow automation had to be hand-built in the
UI, on the strength of a catalogue gap — a claim that turned out to be wrong for a
different reason (see "What it does NOT cover" below). Check the catalogue, then check
the internal API, *then* conclude.

---

## Auth — just the PIT, no OAuth

```
POST https://services.leadconnectorhq.com/mcp/anthropic/v2
Authorization: Bearer <YOUR_PIT>
locationId:    {locationId}
Content-Type:  application/json
Accept:        application/json, text/event-stream
```

Note that `locationId` is its own **header** here. The PIT is the same Private
Integration Token used for the rest of the public API — see `auth.md` for how to obtain
one and what scopes gate.

**It works over plain `curl`.** No MCP client library is required. This matters because
it makes the server cheap to *probe* — you can find out what a capability does before
committing to a config change, a dependency, or an architecture.

Send a browser-like user agent (`-A "Mozilla/5.0"`). Cloudflare 403s the default Python
`urllib` UA on GoHighLevel hosts, and the HTML error body that comes back does not look
like an MCP error at all.

---

## Transport — SSE, so parse `data:` lines

Responses come back as **Server-Sent Events**, not as a single JSON body. Every line of
interest is prefixed `data: `. You must strip the `event:` / `data: ` prefixes and
concatenate before parsing, or `json.loads` will fail on the first character.

Then there is a second unwrapping: the JSON-RPC result contains a `content` array of
text parts, and the *actual* API payload is JSON encoded **inside** those text parts. So
a full round trip is: strip SSE -> parse JSON-RPC -> join `result.content[*].text` ->
parse that string as JSON.

```python
import json, subprocess

MCP = "https://services.leadconnectorhq.com/mcp/anthropic/v2"

def rpc(pit: str, location_id: str, payload: dict) -> dict:
    """curl, not urllib — Cloudflare 403s the default Python UA on GHL hosts."""
    p = subprocess.run(
        ["curl", "-s", "--max-time", "60", "-X", "POST", MCP,
         "-H", f"Authorization: Bearer {pit}",
         "-H", f"locationId: {location_id}",
         "-H", "Content-Type: application/json",
         "-H", "Accept: application/json, text/event-stream",
         "-A", "Mozilla/5.0",
         "-d", json.dumps(payload)],
        capture_output=True, text=True)

    # 1. strip SSE framing
    raw = "".join(l[6:] for l in p.stdout.splitlines() if l.startswith("data: "))
    if not raw:
        return {"_raw": p.stdout[:400]}

    # 2. JSON-RPC envelope
    outer = json.loads(raw)

    # 3. the real payload is JSON *inside* the text content parts
    txt = "".join(c.get("text", "") for c in outer.get("result", {}).get("content", []))
    try:
        return json.loads(txt)
    except Exception:
        return {"_text": txt[:400]}
```

---

## Six meta-tools, not hundreds

The server does **not** expose one MCP tool per API endpoint. It exposes six meta-tools,
and the real surface is a generated catalogue sitting behind them.

| Tool | What it does |
|---|---|
| `search` | General search across the catalogue |
| `fetch` | Retrieve a specific catalogue item |
| `search_operations` | **Find operations by keyword** — the entry point |
| `describe_operation` | **Get an operation's full parameter schema** |
| `execute_operation` | **Actually call it** |
| `list_locations` | Enumerate locations the token can reach |

This design is why the server is worth using even when you already know the REST route:
the catalogue is generated from the same source as the API, so `describe_operation` is
schema documentation you can trust more than any prose.

---

## The loop — search, describe, execute

### 1. Search for the capability

```bash
curl -s -X POST "https://services.leadconnectorhq.com/mcp/anthropic/v2" \
  -H "Authorization: Bearer <YOUR_PIT>" \
  -H "locationId: {locationId}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -A "Mozilla/5.0" \
  -d '{
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {
      "name": "search_operations",
      "arguments": { "query": "email template" }
    }
  }'
```

You get back operation ids — the names you use everywhere downstream. Real examples
returned by this catalogue:

```
create-email-template          POST   /emails/locations/{locationId}/templates
update-email-template          PATCH  /emails/locations/{locationId}/templates/{templateId}
GET-all-or-email-sms-templates GET    /locations/{locationId}/templates
DELETE-an-email-sms-template   DELETE …
create-template-folder         …
import-email-template          …
```

Note the inconsistent naming convention — some ids are lowercase-hyphenated, some are
`GET-`/`DELETE-` prefixed and verbose. **Do not construct operation ids by pattern.**
Take them verbatim from `search_operations`.

### 2. Describe it before you call it

```bash
  -d '{
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {
      "name": "describe_operation",
      "arguments": { "operationId": "create-email-template" }
    }
  }'
```

This returns the parameter schema — which fields live in `path`, which in `query`, which
in `body`. Read it. The `path` / `query` split is the thing people get wrong (see the
`locationId` trap below).

### 3. Execute

`execute_operation` takes an `operationId` plus a `params` object partitioned into
`path`, `query`, and `body`.

```bash
  -d '{
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {
      "name": "execute_operation",
      "arguments": {
        "operationId": "create-email-template",
        "idempotencyKey": "my-build-welcome-email-1754500000",
        "params": {
          "path": { "locationId": "{locationId}" },
          "body": {
            "name": "Welcome Email",
            "editorType": "html",
            "editorContent": "<html>…</html>",
            "subjectLine": "Your seat is confirmed",
            "previewText": "Details inside",
            "fromName": "<SENDER_NAME>"
          }
        }
      }
    }
  }'
```

Paginated reads follow the same shape with `query`:

```json
{
  "operationId": "GET-all-or-email-sms-templates",
  "params": { "query": { "limit": 100, "skip": 0 } }
}
```

Page by incrementing `skip` by the page size until a short page comes back.

---

## Three traps, all of which cost time

### 1. `idempotencyKey` is REQUIRED on writes

Omit it and the write returns a **400** — which, helpfully, names the missing field.
It is passed as a sibling of `params` inside `arguments`, **not** inside `params`:

```json
"arguments": {
  "operationId": "create-email-template",
  "idempotencyKey": "<unique-per-write>",
  "params": { … }
}
```

Use a key that is unique per logical write. Reusing a key across genuinely different
writes is untested by us (**UNVERIFIED** whether the server dedupes on it or ignores it),
so treat it as a real idempotency token and mint a fresh one — a stable prefix plus a
timestamp works.

### 2. `dryRun: true` checks the SHAPE, not your PERMISSION

This is the trap most likely to produce a confident, wrong report.

`dryRun` resolves and previews the request, and it returns:

```json
{ "authorizationVerified": false }
```

**It does not check scopes.** A successful dry run proves your parameters are
well-formed and the operation exists. It proves nothing about whether your token may
perform it.

We proved the gap empirically on email templates: a dry run reported success, a real
create then succeeded, and a real **delete returned 401** `"token is not authorized for
this scope"`. Same catalogue, same token, same dry-run verdict. Only the real write
distinguished them.

> **A resolved request is not a permitted one.** Always confirm a new capability with one
> real write before you build on it or report it as available.

### 3. `locationId` in `query` returns 422

```
422 "property locationId should not exist"
```

`locationId` belongs in `params.path` (or in the request header), never in
`params.query`. This is the same rule that governs the raw REST API, and it survives the
MCP wrapper intact.

The broader habit worth taking from this: **GoHighLevel 422s name the offending
property.** Treat them as free schema documentation rather than as errors to suppress.
Send a deliberately minimal or wrong body, read what it complains about, and you have
the contract. See `api-map.md` for the full pattern.

---

## What it unlocks — verified in production

**Email templates, end to end.** `create-email-template` with `editorType: "html"`
accepts a raw `editorContent` HTML string. That means email markup can be **generated
programmatically and pushed** — no drag-and-drop builder, no UI automation.

And critically: **`editorType: "html"` stores content VERBATIM.** Round-trip verified
byte-identical — what you POST is what is served back. The only modifications GHL made
were additive and benign (an `<!-- outlook-fixes-applied -->` comment and MSO
font-colour fallbacks). This is a meaningful contrast with funnel pages, which GHL
*recompiles* at save time and where an API echo is not proof of anything.

A practical consequence worth stating plainly: hand-authored email HTML is generally
*better* than builder output, because builder paste artifacts (overridden font stacks,
triplicated inline colours, arbitrary type scales) are a common source of ugly email.
Generating the markup yourself removes that whole class of defect.

**Full custom-value CRUD**, including `create-custom-value`, which is the prerequisite
for the per-value update path documented in `api-map.md`.

**Retirement pattern for templates.** Since delete 401s, `PATCH archived: true` instead.
Design your cleanup around archiving from the start.

**Idempotent re-runs.** List existing templates, match by name, and `update` where a name
already exists rather than `create`. Re-running a build script then does not litter the
account with duplicates. (Note this is safe for *templates*, which do carry names —
it is explicitly **not** safe for forms, whose list endpoint returns `name: null`. See
`api-map.md`.)

---

## What it does NOT cover — check before assuming a capability

### No `create-workflow`

The catalogue exposes only `get-workflow`, `add-contact-to-workflow`,
`delete-contact-from-workflow`, and `list-workflow-campaigns`. There is no operation to
author a workflow.

**Do not conclude from this that workflows must be built by hand.** They are creatable —
just not here. The internal API on `backend.leadconnectorhq.com` creates and updates
them with the `token-id` credential:

```
POST /workflow/{locationId}          body {"name": "..."}
PUT  /workflow/{locationId}/{workflowId}   body {name, workflowData, version}
```

Verified working. Full detail, including the duplicate-creation caveat and the two kinds
of wait step, is in `api-map.md`. **This is the clearest example in this corpus of why a
catalogue gap is not a platform limit:** the MCP server fronts the *public* API, and
GoHighLevel's own web app uses a different, larger internal one.

### Funnel pages are read-only

The catalogue offers `getPagesByFunnelId`, `getPagesCountByFunnelId`, and
`update-redirect-by-id`. There is no page-content write.

`POST /funnels/builder/autosave/{pageId}` on the internal host remains the only page
write path, and the REST alternatives are IAM-walled for every credential we tested. See
`api-map.md`.

### Agency-scoped operations

With a sub-account PIT, `/locations/search` returns 403 and `/oauth/installedLocations`
returns 401 on the raw API. Whether `list_locations` behaves differently through the MCP
layer, or whether an agency-scoped PIT clears these, is **UNVERIFIED**.

---

## Decision rule

Use the MCP server when the capability lives on the public API — contacts, custom values,
email templates, media, opportunities. It is faster than raw REST, it is
self-documenting, and it eliminates a genuinely hazardous failure mode (false-positive
endpoint discovery).

Drop to the internal API on `backend.leadconnectorhq.com` when the capability is
something the GoHighLevel *web app* does but the public API does not expose — funnel page
writes, workflow authoring, form writes.

And when neither has it, capture the UI performing the action and read the request. That
is how every hard-won route in this guide was found. Watching beat guessing every single
time we tried both.

---

## Related

- `auth.md` — obtaining a PIT, the scope asymmetries, and the entirely different
  credential the internal host requires
- `api-map.md` — the full capability table, the 422-as-documentation pattern, and the
  nonsense-id control that catches false endpoint discoveries
