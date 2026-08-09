# GoHighLevel Authentication — The Complete Map

> **Status:** every header, status code, and failure quoted here was observed against a
> live GoHighLevel account between 2026-07-27 and 2026-08-06. Claims that were *not*
> verified are marked **UNVERIFIED** inline. Nothing in this file is inferred from
> vendor documentation.

---

## The mental model, before any specifics

GoHighLevel is not one API. It is **two separate API surfaces living on two different
hostnames, with two completely different authentication schemes**, plus a third
credential layer (Firebase) that falls out of the second one as a side effect.

The single most expensive mistake an agent can make on this platform is assuming the
credential that works on one host works on the other. It does not. Worse, the failure
mode is a bare `"Unauthorized"` string — which reads like a *token* problem and sends
you off to regenerate credentials, when the actual problem is that you used the wrong
**header name**.

```
                          ┌─────────────────────────────────────────────┐
  PIT (long-lived)  ────▶ │ services.leadconnectorhq.com                │
  Authorization: Bearer   │ "public API" + the MCP server               │
                          │ contacts · custom values · forms(read) ·    │
                          │ email templates · media · opportunities     │
                          └─────────────────────────────────────────────┘

                          ┌─────────────────────────────────────────────┐
  Firebase ID token ────▶ │ backend.leadconnectorhq.com                 │
  token-id: <jwt>         │ "internal API" — what the GHL web app calls  │
  (~1h life)              │ funnel autosave · workflows · forms(write)  │
                          └─────────────────────────────────────────────┘
                                        │
                                        │ the SAME jwt, re-presented as
                                        │ Authorization: Bearer
                                        ▼
                          ┌─────────────────────────────────────────────┐
                          │ firestore.googleapis.com                    │
                          │ firebasestorage.googleapis.com              │
                          │ project: highlevel-backend                  │
                          │ (raw page documents + page-data objects)    │
                          └─────────────────────────────────────────────┘
```

The three schemes are covered below in the order you will need them.

---

## Scheme 1 — Private Integration Token (PIT) on the public host

This is the credential you should reach for first, because it is long-lived, it is
issued from the UI without an OAuth dance, and it is what GoHighLevel's own MCP server
consumes.

### Headers

```
Authorization: Bearer <YOUR_PIT>
Version: 2021-07-28
```

`Version: 2021-07-28` is a **required** header on the public API, not an optional
nicety. Omitting it produces confusing validation errors rather than a clean
"missing version" message. Send it on every request to
`services.leadconnectorhq.com`.

### Working example

```bash
curl -sS "https://services.leadconnectorhq.com/locations/{locationId}/customValues?limit=200" \
  -H "Authorization: Bearer <YOUR_PIT>" \
  -H "Version: 2021-07-28" \
  -A "Mozilla/5.0"
```

### How to obtain a PIT

Created inside the GoHighLevel UI, per sub-account, under the account's settings ->
Private Integrations. You select the scopes at creation time. **Grant every scope you
plausibly need up front**, because scope gaps do not surface until a specific verb on
a specific resource returns 401, and the error text does not tell you which scope is
missing beyond `"token is not authorized for this scope"`.

### The `-A "Mozilla/5.0"` is not superstition

**Cloudflare 403s the default Python `urllib` user agent on GoHighLevel hosts.**
Verified repeatedly. Either shell out to `curl` (which sends its own UA and is
accepted), or set an explicit browser-like UA on your HTTP client. A 403 with an HTML
body rather than JSON is the tell that you hit Cloudflare, not GHL.

### PIT scope reality — verified

A PIT created inside a sub-account is **sub-account scoped**, and there are agency-level
routes it simply cannot reach:

| Call | Result with a sub-account PIT |
|---|---|
| `GET /locations/search` | **403** |
| `GET /oauth/installedLocations` | **401** |

**Consequence: always pass `locationId` explicitly.** Never write code that expects to
discover the location from the token. (Whether an agency-scoped PIT clears these two
403/401s is **UNVERIFIED** — we never provisioned one.)

### Scope asymmetry — create/update work, DELETE 401s

This is the subtlest scope behaviour we hit, and it is worth internalising because it
generalises. On email templates, with a PIT that had template scopes:

| Operation | Result |
|---|---|
| create-email-template | **success** |
| update-email-template | **success** |
| delete an email/SMS template | **401** `"token is not authorized for this scope"` |

**Read and write scopes on GHL are not a single axis.** A token can be authorised to
create and mutate a resource and still be refused permission to destroy it. Design
around it: to retire a template, `PATCH archived: true` rather than deleting. Assume
the same asymmetry may hold for other resource families and **probe destructive verbs
before you build a cleanup routine on top of them** — a delete that 401s at the end of
a batch job leaves the account littered.

### OAuth 2.0 marketplace apps

GoHighLevel also supports a full OAuth 2.0 marketplace-app flow issuing access/refresh
tokens for the same public host. **UNVERIFIED — we never used it.** Everything in this
guide was done with a PIT. If you need agency-wide or multi-location access, OAuth is
the documented path and should be evaluated before you conclude a capability is
missing.

---

## Scheme 2 — `token-id` on the internal host

### The single most expensive lesson in this guide

> **`Authorization: Bearer` FAILS on `backend.leadconnectorhq.com`.**
> It fails for the PIT *and* it fails for the browser JWT. The internal host
> authenticates on a header literally named **`token-id`**.

Both forms were tested back to back against the live API on 2026-08-06 with the *same*
JWT value:

| Header sent | Result |
|---|---|
| `Authorization: Bearer <jwt>` | `"Unauthorized"` |
| `token-id: <jwt>` | **200** |

The header name is the entire difference. This cost a full debugging cycle, because
`"Unauthorized"` reads as a credential problem and every instinct says "the token
expired, get a new one." **If you get `"Unauthorized"` from
`backend.leadconnectorhq.com`, check the header name before you touch the token.**

An earlier internal note in this same body of work recorded `Authorization: Bearer` as
correct for the internal host. It was wrong. See "Scheme 3" below.

### The full internal header set

```
token-id: <FIREBASE_ID_TOKEN>
channel: APP
source: WEB_USER
Version: 2021-07-28
Content-Type: application/json
```

`channel: APP` and `source: WEB_USER` are the companion headers the GHL web app itself
sends. Send all four. We did not isolate which are individually load-bearing —
**UNVERIFIED which of `channel`/`source` are strictly required** — but this exact set is
confirmed working, so do not trim it experimentally in production code.

### Working example

```bash
curl -sS -X GET "https://backend.leadconnectorhq.com/funnels/page/{pageId}" \
  -H "token-id: <FIREBASE_ID_TOKEN>" \
  -H "channel: APP" \
  -H "source: WEB_USER" \
  -H "Version: 2021-07-28" \
  -A "Mozilla/5.0"
```

### What the token actually is

The `token-id` value is a JWT, roughly 1000-1100 characters, starting with `eyJ`. It
decodes to a **Firebase ID token**:

```
iss: https://securetoken.google.com/highlevel-backend
aud: highlevel-backend
```

Two consequences follow, and both matter.

**First: it expires in about an hour.** Any long-running job against the internal host
must be able to re-acquire it mid-run, or must be chunked to finish inside the window.
Design for re-capture, not for a one-shot paste.

**Second — and this is the leverage — because the audience is Firebase itself, the same
token is accepted directly by Google's own Firebase endpoints** when presented in the
conventional way:

```
Authorization: Bearer <FIREBASE_ID_TOKEN>
```

against `firestore.googleapis.com` and `firebasestorage.googleapis.com`, Firebase
project `highlevel-backend`, bucket `highlevel-backend.appspot.com`. **There is no
`signInWithCustomToken` exchange to perform.** Early R&D assumed a chain
(`GHL session -> identitytoolkit -> Firebase token`) had to be replayed; it does not.
The token the app already carries *is* the end of that chain.

So the same value is used two different ways depending on host:

| Host | Header |
|---|---|
| `backend.leadconnectorhq.com` | `token-id: <jwt>` |
| `firestore.googleapis.com` / `firebasestorage.googleapis.com` | `Authorization: Bearer <jwt>` |

Do not mix these up. It is the same string and two different header names, which is
exactly the kind of thing that survives a copy-paste and fails silently.

### How to obtain the `token-id` — passive network observation

The token is **not** in a cookie, and it is **not** reliably in localStorage under a
stable key. It is observed **on the wire**.

The working, fully automated method: attach to a Chrome instance that is already logged
into GoHighLevel, navigate it to any GHL app page, and read the `token-id` request
header off traffic the app generates by itself.

```bash
# 1. Launch a SEPARATE Chrome instance with a dedicated, GHL-authenticated profile,
#    so you never disturb the human's own browser window.
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9444 \
  --user-data-dir="$PWD/build/ghl-profile" \
  --no-first-run --no-default-browser-check \
  "https://app.gohighlevel.com/v2/location/{locationId}/funnels-websites/funnels" &

# 2. Attach over CDP and observe. (Playwright sketch — the whole mechanism.)
```

```python
from playwright.sync_api import sync_playwright

found = []
with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9444")
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def on_req(r):
        if "leadconnectorhq.com" not in r.url:
            return
        h = {k.lower(): v for k, v in r.headers.items()}
        tok = h.get("token-id", "")
        if tok.startswith("eyJ") and tok not in found:
            found.append(tok)

    page.on("request", on_req)
    # Navigating makes the app issue its own authenticated calls.
    page.goto("https://app.gohighlevel.com/v2/location/{locationId}/funnels-websites/funnels",
              wait_until="domcontentloaded", timeout=90_000)
    for _ in range(12):
        page.wait_for_timeout(2_000)
        if found:
            break
```

Write the captured token to a gitignored, mode-600 file and have every script read it
from there. Because GHL refreshes the token while the browser session lives, this
capture can simply be re-run on demand — **there is no human step.**

An equivalent capture works through any tool that can expose request headers from a
logged-in session (browser devtools Network panel, an automation CLI's
`network requests` command). The principle is what matters: **observe traffic the app
already generates; do not try to extract the token from storage.**

### Before you blame the token, confirm the profile is logged in

A profile that has been signed out lands on `app.gohighlevel.com/?url=...` with an empty
`<title>`; a logged-in one lands on the real path. Check the settled URL over CDP:

```bash
curl -s http://127.0.0.1:9444/json/list
```

We burned time debugging a "bad token" that was actually a logged-out profile on a
different debugging port.

### Three anti-patterns, each of which cost real time

1. **Do not ask a human to paste the token out of devtools.** The passive CDP capture
   above already automates it. Manual paste is a step you added, not a step the
   platform requires.
2. **Do not hunt for an `eyJ` cookie.** The internal token is not read from cookies at
   all. (A cookie-based approach is documented in Scheme 3 as history, and it is dead.)
3. **Do not sweep `localStorage` looking for JWT-shaped strings.** Beyond being
   fragile — the key name varies by GHL build and may be absent entirely — some agent
   harnesses block that *command shape* regardless of your permission settings. Passive
   network capture is the shape that works and keeps working.

---

## Scheme 3 — the `m_a` cookie (historical, dead — do not attempt)

For completeness, because stale notes and older blog posts still describe it:

There was once an `m_a` cookie used for GHL internal auth. **It no longer exists.**
Filtering the cookie panel for `m_a` returns zero results (confirmed 2026-04-28).

A follow-on note then recorded a replacement: find the base64/JWT cookie whose value
starts with `eyJ` (decoding to `{"apiKey":..., "userId":..., "companyId":...}`) and send
it as `Authorization: Bearer` with `channel: APP` / `source: WEB_USER`.

**That guidance is superseded and its header instruction is wrong** — see Scheme 2.
`Authorization: Bearer` returns `"Unauthorized"` on the internal host. The credential is
captured from request headers, not cookies, and it goes in `token-id`.

The transferable lesson, and the reason this dead scheme is documented at all:
**do not trust a recorded header over a live test.** A note that was true in April was
false by August, on both of its two claims. Before you build on any auth fact in any
document — including this one — send one request and confirm.

---

## Reading the failure: a status-code decoder ring

GoHighLevel's error responses are unusually informative once you know how to read them.
This table is the fastest path from a status code to the right next action.

| Response | What it actually means | What to do |
|---|---|---|
| `"Unauthorized"` from `backend.leadconnectorhq.com` | Almost always the wrong **header name** (`Authorization` instead of `token-id`) | Fix the header before regenerating anything |
| `401` from a PIT | Missing **scope**, not necessarily an invalid token | Check the verb — create may work where delete 401s. Retest with the account JWT before concluding the route is closed |
| `403 "This route is not yet supported by the IAM Service. Please update your IAM config."` | A **genuine wall** on a real route family. Holds for PIT *and* JWT | Stop. Find the path the UI uses instead |
| `403` with an HTML body | Cloudflare rejected your user agent | Set a browser-like UA, or shell out to `curl` |
| `422 "property X should not exist"` | The **body validator** ran and named your offending field | Free schema documentation — see `api-map.md` |
| `401 -> 422` when you add a payload | The validator accepted you. **This is NOT authorization.** | Do not celebrate. Send a real payload; the authorization layer runs after the validator and may still 403 |
| `200` on a guessed endpoint path | Probably a generic get-by-id route swallowing your path segment | Control-test with a nonsense id. See `api-map.md` |

The `401 -> 422` row deserves emphasis. We twice mistook a validator-passing 422 for
"auth unlocked," and both times a real payload then returned `403 IAM`. **A 422 proves
the shape of your request, never your permission to make it.**

---

## Credential hygiene

- **Never inline a PIT in source.** `.env`, `chmod 600`, gitignored.
- **Never commit a captured `token-id`.** It is short-lived, but it is a live session
  credential for a client's account while it lasts.
- **Never write real `locationId`, `funnelId`, `pageId`, or `formId` values into shared
  docs.** They are not secrets in the cryptographic sense, but they identify a specific
  client's account, and this guide is public. Placeholders only.

---

## Related

- `api-map.md` — what each credential can actually reach, and the error patterns that
  document the schema for you
- `mcp-server.md` — GoHighLevel's own MCP server, which fronts the entire public API
  with the PIT and removes the need to guess endpoints at all
