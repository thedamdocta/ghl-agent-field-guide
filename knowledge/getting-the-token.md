# Getting the internal token — do this yourself

**Read this before anything that writes a page, a form, a funnel step or a workflow.**
Those live on `backend.leadconnectorhq.com`, where your Private Integration Token does
**not** work. You need a short-lived Firebase JWT that only exists inside a logged-in
browser session.

**You can get it on your own.** You launch the browser, you capture the token, you
refresh it when it expires. A human is needed exactly once — for the first login on a
brand-new profile — and often that has already happened, so check before you ask.

---

## 0. Do you even need it?

| you want to… | what you need |
|---|---|
| contacts, custom values, email templates, most REST | **PIT only** — skip this page |
| write a funnel page (`autosave`) | internal token |
| create or update a workflow | internal token |
| create a form / funnel step | internal token *and* a live browser session |

Only in the first row? Stop here and use `tools/ghl_mcp.py`.

---

## 1. Look for an authenticated profile before doing anything else

A Chrome profile stays logged in indefinitely. If one exists from any previous
session, you need no human at all.

```bash
# Chrome profiles created for this purpose usually live in a project or under $HOME
ls -d ~/.ghl-agent-profile ./build/*profile* ./*profile* 2>/dev/null

# Is something already listening on a debug port?
lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | grep -iE "chrome|9222|9444"
```

Found a profile → go to step 2, on your own.
Found nothing → step 5, ask for a one-time login.

---

## 2. Launch Chrome yourself

You run this. Not a human.

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.ghl-agent-profile" \
  --no-first-run --no-default-browser-check \
  "https://app.gohighlevel.com/v2/location/$GHL_LOCATION_ID/funnels-websites/funnels" \
  >/dev/null 2>&1 &
```

Linux: `google-chrome`. Windows: `chrome.exe`, `--user-data-dir="%USERPROFILE%\.ghl-agent-profile"`.

Three things that will cost you time if you skip them:

- **Use a dedicated `--user-data-dir`.** Chrome will not open a debugging port on a
  profile another instance already owns, and it fails *silently* — the window opens
  normally and the port simply never listens.
- **This is a separate instance.** It does not disturb the human's everyday Chrome,
  their tabs, or another agent's browser session. Launch your own; don't hijack theirs.
- **Pick a port nobody else is using.** 9222 is the common default, so if something
  already holds it, use 9444 or anything free.

Give it ~10 seconds to settle before the next step.

---

## 3. Verify — port, then login. In that order.

```bash
curl -s http://127.0.0.1:9222/json/version          # port open?
```

Nothing back → Chrome was already running and swallowed the flag, or a different
`--user-data-dir` was used. Quit Chrome fully and relaunch.

```bash
curl -s http://127.0.0.1:9222/json/list \
  | python3 -c "import sys,json; [print(t.get('url','')[:90]) for t in json.load(sys.stdin) if t.get('type')=='page']"
```

- **Logged in** → a real path: `app.gohighlevel.com/v2/location/<id>/...`
- **Logged out** → `app.gohighlevel.com/?url=...`, and an **empty `<title>`**

This check has its own step because a logged-out profile produces a *"bad token"*
symptom, which sends you off re-capturing a token that was never the problem.

---

## 4. Capture

```bash
pip install playwright     # just this. NOT `playwright install` — you connect to an
                           # existing Chrome, you do not ship a browser.

python3 tools/get_token.py --location-id "$GHL_LOCATION_ID" --port 9222
```

Success looks like:

```
  captured token-id (1064 chars) -> .jwt
  valid for 59 more minutes
```

~1,000+ characters, starts `eyJ`. Much shorter means it is not the token.

**What it does, because this shapes the failure modes.** It attaches to the running
browser, subscribes to network request events, navigates to an ordinary in-app URL,
and reads the `token-id` **request header** off calls the app makes on its own behalf.
Passive observation of traffic that was happening anyway. It does not read cookies,
storage, or the profile on disk, and it never handles a credential.

Consequence: there is **no offline path**. If the session dies, capture dies with it.
That is the design, not an obstacle to route around.

---

## 5. Only if no authenticated profile exists

You cannot log in yourself — it needs credentials you do not have and usually a 2FA
code. Don't try, and never ask for a password. Ask for a one-time login instead:

> I need a one-time browser login to reach GoHighLevel's internal API. Please run
> this and log in in the window that opens, then tell me when you see the dashboard.
> Leave it open.
>
> ```bash
> "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
>   --remote-debugging-port=9222 \
>   --user-data-dir="$HOME/.ghl-agent-profile" \
>   --no-first-run "https://app.gohighlevel.com/"
> ```
>
> I never see the password. After this the profile stays authenticated and I can
> refresh tokens myself indefinitely.

**Once. Ever.** From then on you are back at step 2, autonomous.

---

## 6. Use it correctly — this is where a day disappears

```
token-id: <the jwt>          ← NOT Authorization: Bearer
channel: APP
source: WEB_USER
Version: 2021-07-28
```

**`Authorization: Bearer <the same token>` returns `"Unauthorized"` on this host.**
The token is fine; the header name is wrong. Because the error says "Unauthorized" it
reads as a credentials problem, and you will burn an hour re-capturing a token that
was never broken. **Check the header before you re-capture.**

| host | header | token |
|---|---|---|
| `services.leadconnectorhq.com` | `Authorization: Bearer` | your PIT |
| `backend.leadconnectorhq.com` | **`token-id`** | this JWT |

---

## 7. Lifetime — re-capture, don't nurse it

About **60 minutes**, and GHL refreshes it while the browser session lives, so just
re-run `get_token.py`. No human, no ceremony.

Re-capture at the **start of any long build**, and again if one is still running an
hour in. An expired token produces a `401` on the fifth page injection after four
succeeded — which looks exactly like an intermittent platform fault and is not.

Don't cache it beyond one build. Don't commit it. `.jwt` is gitignored.

When you are finished with a build, close the Chrome instance you launched and free
the port.

---

## Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `/json/version` returns nothing | port not open; Chrome already running | quit Chrome fully, relaunch with the flags |
| capture finds no token | profile logged out | step 3 — check the settled URL |
| token captured, every call `401` | using `Authorization: Bearer` | use the `token-id` header |
| worked, then `401` mid-run | expired (~60 min) | re-run `get_token.py` |
| `ModuleNotFoundError: playwright` | missing dep | `pip install playwright` |
| pages fine, custom values `401` | wrong token for that host | custom values are PIT + Bearer |
| Chrome opens but port never listens | shared `--user-data-dir` | use a dedicated one |

---

## What this does NOT get you

- **Triggers and publishing workflows.** No API at all — drive the UI with Playwright.
- **Anything the logged-in user cannot do.** The token carries their permissions.
- **A path that survives logout.** See step 4.

Related: [`auth.md`](auth.md) · [`api-map.md`](api-map.md) ·
[`../tools/get_token.py`](../tools/get_token.py)
