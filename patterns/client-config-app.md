# Pattern — The Client Config App

**The problem this solves:** custom values are an excellent modularity mechanism and a
terrible operations interface. The moment you hand a finished funnel to a
non-technical owner, the thing you built becomes unusable to them — not because it is
broken, but because there is no surface where "change the webinar" is a coherent act.

This is the most transferable pattern in this repository. Build it for any client
funnel you expect someone else to operate.

---

## 1. Why the platform UI is not the answer

The account this was built against held **160 custom values**. Roughly twenty of them
drove the funnel. The rest belonged to an entirely unrelated line of the same
business.

GHL's custom-values screen is a flat, alphabetical list of key/value pairs. It gives
the owner no signal about:

- which values belong to which system,
- which ones are safe to edit,
- what breaks if a value is cleared,
- whether a value appears on one page or on fifteen surfaces,
- which values are machine-format strings that must never be hand-typed.

So the realistic outcome of "just edit the custom values" is one of two failures:
the owner does not touch anything and the funnel ossifies, or the owner edits the
wrong twenty characters and the funnel breaks silently — remember that **an unknown
or emptied merge tag resolves to empty string with no error anywhere**.

The fix is a small, single-purpose web application that writes an **allowlisted
subset** of the account's custom values and nothing else.

---

## 2. Decide what is a custom value BEFORE you build the app

Do this first. It determines the size of the form, and it is the decision that
actually makes the funnel operable.

> **A custom value earns its place only when the same string must appear on more than
> one surface. Everything else should be literal text the client can see and edit.**

Measured on the real build: across 6 pages and 9 email templates there were **75
modularised slots**. Only **16 were multi-surface.** Two (the business name and the
legal footer line) appeared on all fifteen surfaces; the event date appeared on five.
The remaining 59 existed on exactly one page.

For those 59 the custom value bought nothing and cost something real: the owner opens
the page builder, sees `{{custom_values.hero_headline}}` where the headline should be,
and cannot edit the copy in the place it is being read.

**48 of them were converted back to literal text on the pages.** Including every
button label — a button whose text you cannot see in the builder is a button you
cannot fix.

### The four buckets that survive

| bucket | contents | why it stays a custom value |
|---|---|---|
| **Event mechanics** | date, time, timezone, join URL, replay URL, offer URL, calendar URL, offer name | changes every cycle; appears on 3–5 surfaces each |
| **Email copy** | teaching points, preview line, replay window wording | see below |
| **Derived** | weekday, ISO datetime, naive datetime anchor | computed, never typed |
| **Locked identity** | business name, sender name, support address, legal footer | multi-surface, set once, **kept out of the form entirely** |

**Why email copy stays a custom value when page copy does not.** The page builder is
WYSIWYG — the client clicks a headline and types. Email templates pushed as
`editorType: "html"` are raw code. Making email copy literal would mean asking a
non-technical owner to edit HTML to change a sentence, which is worse than a merge
tag, not better. *Different editing surface, different answer.* Do not apply the rule
mechanically; apply it per surface.

**Locked identity is deliberately not in the form.** Exposing the legal disclaimer as
an editable field creates the ability to break a compliance line on fifteen surfaces
in exchange for a capability nobody asked for. The allowlist is where you say no.

---

## 3. The allowlist is a security boundary, not a filter

The app holds a token that can write anything in the location. The allowlist is the
only thing standing between the config form and the rest of the business's data.

Two rules follow, and the second one is the one people get wrong:

**Rule 1 — the token never reaches the browser.** It lives in a server-side
environment variable and is used only inside route handlers. The client-side form
posts a plain `{key: value}` patch to your own API route. There is no configuration
in which the browser holds a platform credential.

**Rule 2 — reject the whole write, do not silently drop out-of-scope keys.**

```
PUT /api/custom-values   { "webinar_date": "...", "footer_disclaimer": "..." }
→ 403 { "error": "allowlist_violation", "rejected": ["footer_disclaimer"] }
   and NOTHING is written, including the legitimate key.
```

Silently filtering is the tempting implementation and it is wrong. A patch containing
an out-of-scope key means one of two things: your own form has drifted and is sending
a key the server does not expect, or someone is probing the endpoint. In the first
case a silent filter hides a real bug — the client presses Save, gets a success
toast, and a field does not persist, with no error anywhere to find later. In the
second case a silent filter is a partial-success oracle. Failing the whole request
distinguishes neither case but makes both loud.

Verify it deliberately: attempt a write against a locked identity key and against a
converted-to-literal key, and assert that nothing changed.

**The gate fails closed.** Both the passphrase and the cookie-signing secret must be
present at boot; if either is missing the app refuses entry rather than opening. A
gate that opens when misconfigured is not a gate.

**A note on duplicated allowlists.** This build ended up with two — a typed constant
tuple on the server, and a field manifest with UI labels on the client. That is a
defensible split, but they drifted within a day: the form began sending a key the
server did not know, and every save died with a 403 that blamed the caller. The fix
was to compare the two at module load and **throw on disagreement**. If you split a
list of truths across two files, make the process refuse to start when they disagree.

---

## 4. Derive machine values; never ask a human for them

The scheduled reminder emails anchor off a machine-format datetime. Nobody should
hand-type an ISO-8601 string with an offset, and nothing good happens when they try.

The form collects three human inputs — a date, a start time, a timezone — and derives
three machine values from them:

- **the weekday**, computed from the date, so the day and the date can never disagree
  (a hand-maintained pair drifts the first time someone moves the event),
- **an ISO datetime with offset** — self-describing, no ambient timezone needed,
- **a naive `MM-DD-YYYY HH:MM` anchor** — the shape the platform's own scheduling
  fields were observed to use.

DST is resolved from the runtime's ICU data, never hardcoded. Test it across a summer
date, a winter date, both DST transition boundaries, and a zone that does not observe
DST at all. The derivation was verified against all five.

**The pickers matter more than they look.** Three details, ported behaviour-for-
behaviour from a launcher a client found genuinely easy to use:

1. **Hour options are 12-hour labels over 24-hour values.** The operator picks `07 PM`, the
   system stores `19`. No AM/PM toggle to get backwards, no typing.
2. **The timezone list renders the current local time in each zone, refreshed every
   60 seconds.** The zone is confirmed by reading "it is 3:42 PM there right now"
   rather than by decoding `America/New_York`. This is the single feature that makes
   the control self-verifying, and it is cheap.
3. **Display ⇄ storage conversion happens at the form boundary.** The stored values
   stay human strings that the pages render verbatim; the form never shows a machine
   string and never asks for one.

The original implementation of those pickers was hard because it was DOM surgery over
a pre-existing component library. Built fresh they are three controlled components.
**Port the behaviour; do not port the technique.**

---

## 5. Show the blast radius

Each field in the form carries a **surfaces count** — "appears on 5 surfaces" — shown
next to the input.

This is the cheapest good idea in the whole app. It converts an invisible property of
the system into something the operator can see at the moment of editing. Changing the
event date touches five surfaces; changing a replay-window sentence touches two. The
operator does not need to know what the surfaces are to behave correctly once they
know there are five of them.

It also enforces the §2 rule on you as the builder. If you find yourself writing
`surfaces: 1` on a field, that field should not be in the form and should not be a
custom value.

---

## 6. Hydrate, then save

Never render an empty form for a live system.

```
GET  /api/custom-values   → read all values, filter to the allowlist,
                             return { key: {id, name, value} } for each
PUT  /api/custom-values   → validate against the allowlist, resolve key → id,
                             write, then read back and compare
```

Three properties fall out of this that are worth stating explicitly:

- **The form always shows what is actually live**, so the client is editing reality
  rather than a blank slate that would blank out anything not retyped.
- **Key → id resolution happens on the read**, which you need anyway because the write
  route addresses values by **id, not by key**.
- **A missing key on hydrate is a real signal** — it means the slot was deleted in the
  platform UI. Surface it rather than treating absence as an empty string, because
  writing to a nonexistent slot is exactly how you ship a `Grab the  now` sentence.

Round-trip verification — write, read back, compare — is the only acceptable
definition of a successful save here. See `methodology/verification.md`; a `200` from
this platform is not evidence.

Also note: the per-value update route requires the value's **`name` as well as its
`value`**, and you should source that name from the live record you just read. That
makes it structurally impossible for a save to rename a key into or out of the
allowlist.

---

## 7. What is untested or unresolved

Stated plainly, because an unqualified pattern document is a liability.

- **No live email has been sent through this.** The app writes correctly and the
  values read back correctly. Whether a workflow's event anchor consumes the ISO
  value or the naive value **has not been tested with a real send.** It needs one
  throwaway workflow run and no amount of reading will settle it.
- **Naive datetimes are interpreted in the ACCOUNT's timezone.** If the event runs in
  a different zone from the account, the pages render correctly and the scheduled
  reminders fire at the wrong hour, silently. The app writes both formats and raises
  a visible caution the moment a non-account zone is selected. That is a mitigation,
  not a fix.
- **Do not attempt to solve that by writing the account timezone from the form.** No
  such write was found in the API, and it would be wrong anyway — the account
  timezone governs every calendar, appointment, workflow and contact timestamp in the
  business, including systems that have nothing to do with your funnel. The blast
  radius is not yours to spend.
- **The bulk-write endpoint is gone.** `PUT /customValues/bulk` worked in a codebase
  from late 2025 and now returns a 422 with a per-value schema error, while a
  per-value body to the same URL 404s with "custom value id is invalid" — i.e. `bulk`
  is being parsed as an `{id}`. The app probes once per process, memoises the failure,
  and falls back to per-value writes. Twenty-odd individual writes is a fine number.
  **Re-probe rather than trusting either this document or the vendor's.**
- **Authorization is a shared passphrase.** It is adequate for one operator and does
  not model multiple users, roles, or an audit trail. If more than one person will
  ever edit, this needs replacing rather than extending.

---

## 8. Shape checklist

```
/api/custom-values     GET hydrate · PUT save        (server-only token)
/api/auth              sign in / out                  (fails closed)
proxy or middleware    the gate on every route
lib/<platform>.ts      client + allowlist (typed, server side)
lib/fields.ts          field manifest: label, kind, surfaces, help text
lib/datetime.ts        derivation, DST, zone mapping — with tests
components/pickers/    date · time · timezone
```

Keep it boring. This build used the framework's own routing, plain CSS, and no date
library, no UI library, and no new runtime dependencies — because the thing most
likely to break a client-facing admin tool eighteen months from now is a dependency,
not a design decision.
