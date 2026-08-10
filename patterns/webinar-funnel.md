# Pattern — The Webinar Funnel

A webinar funnel is five pages and one clock. The pages are easy. Almost everything
that goes wrong is a mismatch between where a visitor is and what the surface in front
of them asserts.

This documents the page chain, what each page is actually responsible for, and the
handful of places where GHL puts behaviour somewhere other than where you would look
for it.

---

## 1. The chain

```
  Registration ──submit──▶ Confirmation ──▶ Webinar Room ──▶ Replay ──▶ Booking
       │                        │                 │             │          │
   the only            the only page that     the session    the second   the ask
   conversion          proves the machine       itself         chance
   on the site         worked
```

Five pages, five states, and **each page exists because a visitor can be in exactly
one of those states.** If two pages could serve the same state, one of them is copy,
not architecture.

The build gave each page a small typographic stage marker — *Reservation, Confirmed,
In Session, Replay, Consultation* — for a non-decorative reason: it is genuinely an
ordered sequence, and naming the position tells the visitor where they are without a
sentence. The same five words are reused as the stage labels in the email sequence,
which is most of what makes the inbox and the site read as one object. See
`email-sequences.md`.

---

## 2. What each page must do

### Registration

The only page with a conversion on it, so it is the only page allowed to be long.

- The date, time and timezone, together, above the fold. It costs one line and it is
  the single most common omission — the confirmation email in the funnel we analysed
  told the reader to add the session to their calendar **without naming a date, time
  or timezone anywhere in the message.**
- One form. One submit. No secondary CTA competing with it.
- Whatever proof you actually have. Not invented proof — see §6.

### Confirmation

Its job is to prove the machine worked. A visitor who submits a form and lands on a
page that does not obviously acknowledge the submission will re-submit.

- Restate the **when**, in full, with the timezone. This is the state the page is
  asserting; make the assertion.
- An add-to-calendar action. This is the highest-value control on the page and it is
  what actually moves show rate.
- Set expectations for what arrives by email next.
- Optionally a bonus or pre-work block. This is the natural place for it and the only
  page where it does not compete with something more important.

### Webinar Room

- The player mounts here. Whether that is a third-party evergreen platform embed or
  something self-built is a separate decision; architecturally this page is a frame
  around a slot.
- A single CTA. Before and during the session that CTA is *attend*, not *buy*.
- Nothing else. This page is competing with the session itself.

### Replay

- The replay embed.
- The offer, and **this is the first surface in the entire funnel where the offer link
  appears.** Everything before it sells attendance. That restraint is the strongest
  structural decision in the sequence we studied and it transfers directly.
- Any expiry framing here must be **true**. A "this comes down soon" headline on a
  replay that never comes down is a lie the client will be living with on an evergreen
  funnel, and it will be the only false sentence in an otherwise honest build.

### Booking

- The calendar widget and nothing that could distract from choosing a time.
- Native platform calendar widgets are added in the builder UI, not through the page
  injection API. Plan for one manual step here.

---

## 3. Where the behaviour actually lives

Three placements that are not where you would guess. Each of these returns `200` when
you write it to the wrong place.

### Form submit behaviour is on the PAGE element, not the form record

```json
{
  "extra": {
    "formId": {"value": "<formId>", "text": "<display name>"},
    "form_submit_type": "ThankYouMessage",
    "form_submit_redirect_url": ""
  }
}
```

**Writing `formAction.actionType` or `redirectUrl` onto the form record returns 200
and does not persist** — verified by round-trip. The page element is where GHL reads
submit behaviour from. The form record holds the *fields*; the page element holds the
*consequence of submitting them*.

Honest limit: only `"ThankYouMessage"` has been observed in captured production pages.
The redirect enum is inferred and **UNVERIFIED**. Confirm it by setting the option
once in the builder UI and re-capturing the page, or by one real submission. Do not
describe redirect-on-submit as working until you have.

### Every funnel gets its OWN form

Pointing a page at a pre-existing, generically-named account form ("Registration",
"Contact Us") imports that form's fields, its image, its header, its branding and its
fixed width. In production this rendered an unrelated intake form's image, linked
header and submit button in the middle of a webinar registration page — and restyling
it would have changed every other page that form is embedded on.

Build a new form per funnel by **cloning a working form's schema and deleting
fields**. Hand-written field dicts miss required keys.

### Button actions are per-action fields, not one generic target

The action type determines which `extra.*` field carries the destination — scroll
targets, popup ids, external URLs and funnel steps each live in a different key.
`go-to-next-funnel-step` is the correct default for a funnel CTA: it is what a funnel
CTA almost always means and it requires no id to be correct, so it cannot rot when a
page is rebuilt. Details in `knowledge/funnel-pages.md` §6.

---

## 4. Page vs funnel step

A funnel is an ordered list of **steps**; each step owns a **page**. The injection API
addresses pages by page id, but `go-to-next-funnel-step` resolves through the step
order. Two consequences:

- Reordering steps silently changes where every next-step CTA goes. That is usually
  what you want and occasionally catastrophic. Re-verify CTA destinations after any
  reorder.
- Creating a page is not the same act as creating a step. If a page is unreachable,
  check the step list before you debug the page.

---

## 5. Links: one slot, referenced everywhere

The join URL, the replay URL and the offer URL each appear on multiple pages and in
multiple emails. Each one gets **exactly one custom value**, referenced from every
surface.

This is not tidiness. The sequence we analysed shipped **two different offer URLs
across its own emails** — the same path with and without hyphens — which means one of
them was almost certainly a 404 sitting on the only link in the funnel that takes
money. One slot makes that class of bug structurally impossible.

Apply the rule from `client-config-app.md` §2 to decide what else becomes a custom
value: multi-surface strings only. Page headlines and button labels should be literal
text the client can read and edit in the builder.

---

## 6. Two things not to reproduce

**False scarcity on an evergreen funnel.** A capped-seats claim is false when the
session runs on a loop, and every visitor who registers twice can see that it is
false. If the funnel is evergreen, the honest urgency is the replay window — and only
if the replay window is real.

**Invented proof.** Revenue screenshots, conversion metrics and testimonials you did
not receive are not a design problem, they are the client's legal exposure. In
regulated or sensitive verticals this is not a close call. Ship the page with the
proof block absent rather than filled.

---

## 7. Build and verification order

1. Create the funnel and its five steps; record the page ids.
2. Create the form by cloning; wire it into the registration page **element**.
3. Create every custom value **before** any surface references it — unresolved merge
   tags render as empty string with no error.
4. Build each page tree, emit `sectionStyles` for both id namespaces
   (`design-systems-in-ghl.md`), inject, expect `201`.
5. **Verify on the rendered preview URL, not the API response.** Grep the served page
   for your literal strings.
6. Be careful with the obvious assertion here: the rendered preview shows **resolved**
   values, so "no `custom_values.` appears in the HTML" proves nothing on its own —
   the platform substitutes them server-side, including substituting unknown ones with
   nothing. Assert against the generated page document for the tags, and against the
   rendered page for the expected strings. Both, or you have checked neither.
7. One real form submission, end to end, before handover.

Step 7 is the one that gets skipped. The whole chain can be structurally perfect and
functionally inert; see `email-sequences.md` for what that looks like.
