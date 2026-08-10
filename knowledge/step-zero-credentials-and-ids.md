# Step zero — credentials and ids

**Read this before `building-from-scratch.md`.** Every runbook here opens with

```bash
export GHL_PIT=...  GHL_LOCATION_ID=...
```

and nothing used to say where those come from. An agent that cannot obtain the first
credential cannot take step one, and the honest outcome is that it stops and asks a
human to do the job — which is the failure this whole repository exists to prevent.

Four things are needed. Two require a person once. Two you can discover yourself.

| | what | who gets it |
|---|---|---|
| `GHL_PIT` | Private Integration Token | **human, once** — it is shown once and never again |
| `GHL_LOCATION_ID` | the sub-account | you, from the URL or the API |
| `FUNNEL_ID` | a funnel | you, from the API |
| `PAGE_ID` | a page inside it | you, from the API or the builder URL |

---

## 1. The Private Integration Token — the one thing to ask for

There is no API that mints a PIT; you need someone with sub-account access. Ask
precisely, because a token with the wrong scopes fails later in ways that look like
bugs rather than permissions.

> I need a Private Integration Token for the GoHighLevel sub-account.
>
> **Settings → Private Integrations → Create new integration.** Name it anything.
> Select these scopes, then copy the token — GHL shows it **once**:
>
> `contacts.readonly` `contacts.write` · `locations.readonly`
> `locations/customValues.readonly` `locations/customValues.write`
> `locations/customFields.readonly` `locations/customFields.write`
> `forms.readonly` · `funnels/page.readonly` `funnels/funnel.readonly`
> `workflows.readonly` · `emails/builder.readonly` `emails/builder.write`
> `medias.readonly` `medias.write`
>
> Paste it into `.env` as `GHL_PIT=` — don't paste it into chat.

It starts `pit-`. Store it in `.env` (gitignored), never in a commit, never inline in
a script.

**Scopes are not all-or-nothing, and the gaps are invisible until you hit them.** On
one account, email templates could be *created and updated* but `DELETE` returned
`401 "The token is not authorized for this scope."` If a single operation 401s while
others succeed, suspect the scope before the token.

## 2. Verify the token before building anything on it

```bash
python3 tools/ghl_mcp.py locations
```

That both proves the PIT works and lists the sub-accounts it can reach. **Do this
first, every time.** Debugging a build on a bad credential is the most expensive way
to discover a bad credential.

## 3. `GHL_LOCATION_ID`

Two ways, no human needed:

- **From `ghl_mcp.py locations`** above.
- **From any GHL URL** while in the sub-account:
  `app.gohighlevel.com/v2/location/`**`<THIS IS IT>`**`/dashboard`

20 characters, mixed case and digits.

## 4. `FUNNEL_ID`

```bash
curl -s -H "Authorization: Bearer $GHL_PIT" -H "Version: 2021-07-28" \
  -A "Mozilla/5.0" \
  "https://services.leadconnectorhq.com/funnels/funnel/list?locationId=$GHL_LOCATION_ID&limit=20"
```

Returns each funnel's `_id`, `name`, and a **`steps` array of step ids**. Verified.

No funnel yet? Create one in the UI — there is no public create-funnel endpoint. It is
a two-minute manual step, once per project.

## 5. `PAGE_ID`

Least tidy of the four. In order of reliability:

1. **The builder URL.** Open the page in the funnel builder; the id is in the address.
   Always works.
2. **`GET /funnels/page?funnelId=<id>&limit=20&offset=0`** — `funnelId`, `limit` and
   `offset` are all **required**, and `locationId` must NOT be passed.
   ⚠️ **In testing this returned `pages: 0` on a funnel that demonstrably had six.**
   Treat it as unreliable and fall back to the builder URL. If you find the condition
   under which it works, correct this file.
3. `tools/create_steps.py` prints the ids of steps it creates — capture them then
   rather than re-discovering them later.

**Keep an id map.** Write `page-ids.json` mapping human names to ids the moment you
have them. Every later step needs them and re-deriving them is pure waste.

```json
{ "Optin": "…", "Registration": "…", "Confirmation": "…" }
```

## 6. The internal token — separate, and you get it yourself

The PIT does **not** work on `backend.leadconnectorhq.com`, which is where pages,
forms and workflows are written. That needs a short-lived browser JWT, and **you can
capture it without a human** once a logged-in Chrome profile exists.

Full runbook: [`getting-the-token.md`](getting-the-token.md).

---

## What actually requires a human, in total

Everything else is yours.

1. **Creating the PIT** — once per sub-account.
2. **The first browser login** on a fresh Chrome profile — once, ever; the profile
   stays authenticated afterwards.
3. **Creating a funnel** — no public endpoint.
4. **Workflow triggers and publishing** — no API; drive the UI or ask.

If you find yourself about to ask for anything else, check this file first. The
answer is probably that you can do it.

---

## `.env`

```bash
GHL_PIT=pit-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
GHL_LOCATION_ID=xxxxxxxxxxxxxxxxxxxx
# optional, per project
FUNNEL_ID=xxxxxxxxxxxxxxxxxxxx
```

`chmod 600 .env` and confirm it is gitignored. Run
`python3 tools/scrub_secrets.py . --env-file .env` before any commit.

Next: [`building-from-scratch.md`](building-from-scratch.md).
