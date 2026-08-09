# Failure Modes — The Catalogue of Silent Failures

> **Status:** every entry below was paid for once, on real client work. Each is written
> as **symptom / cause / detection**, because the symptom is usually the only thing you
> will be handed and the cause is never guessable from it.

---

## Why this file exists

GoHighLevel's dangerous failures are not the ones that throw. They are the ones where
the platform accepts your input, returns success, stores something, and then produces
output that is quietly wrong.

A loud failure costs you a debugging session. A silent failure costs you a client email
that ships with a broken sentence, a workflow that fires reminders at the wrong time for
a month, or a page that has been serving stale content since the day you "deployed" it.

The entries below are grouped by where the silence comes from: content substitution,
write paths, cloning, styling, automation logic, UI-automation misreads, and compliance.

---

## 1. Content-level silent failures

### 1.1 An unknown merge tag resolves to the EMPTY STRING

**Symptom.** A sentence in a live page or email is missing a word, and reads as
nonsense. A real production marketing email shipped with a call to action reading
**"Grab the now"** — a merge tag mid-sentence pointed at a key that did not exist, and
the noun simply vanished.

**Cause.** GoHighLevel substitutes `{{custom_values.<key>}}` server-side. If the key
does not exist in the account, the substitution succeeds and produces an empty string.
There is no error, no warning, no placeholder left behind, and nothing in any API
response indicates it happened.

**Why it is worse than it looks.** It fails *identically to success by absence*. You
cannot detect it by checking that no tags remain in the output, because both a correctly
resolved tag and a nonexistent one leave nothing behind. See the merge-tag corollary in
`verification.md`.

**Detection.**

- Maintain the set of tag names you emit as data, and diff it against the set of keys
  that actually exist in the account **before** you ship. This is the only check that
  catches the failure at zero cost.
- Then verify by **presence**: fetch the rendered surface and assert that specific
  literal strings appear where the tags were.
- Create every key the build references as part of the build, not as a manual step.
- Treat a mid-sentence tag as higher risk than a whole-line tag. A blanked line looks
  like a design choice; a blanked noun looks like the client's agency is incompetent.

**Design consequence.** A custom value earns its place only when the same string appears
on **more than one surface**. In one audit of 75 slots, only 16 appeared on multiple
surfaces. Everything else was better as literal text the client can see and edit
directly — fewer tags means fewer chances for this failure, and a client editing visible
copy in a WYSIWYG builder cannot produce "Grab the now."

---

### 1.2 A resolved tag and a converted tag are indistinguishable in output

Covered above and in `verification.md`, but restated here because it is the reason
several other checks in this file must assert presence rather than absence:

**"No `{{...}}` in the rendered HTML" proves nothing.** Assert against the generated
source, then spot-check for expected strings in the render.

---

## 2. Write paths that return success and do nothing

### 2.1 Form submit behaviour written on the form record does not persist

**Symptom.** You set the form's post-submit action — redirect to a URL versus show a
message — via the form record. The call returns `200`. Reading the form back may even
look plausible. The live form still does the old thing.

**Cause.** **Form submit behaviour is a property of the page ELEMENT that hosts the
form, not of the form record.** It lives on the page element's `extra` fields
(a submit-type field and a redirect-url field). Writing an action-type field onto the
form record returns `200` and silently does not persist.

**Detection.** Submit the form on the public preview URL and observe where you land.
There is no API-layer check that will catch this — the record write "succeeds."

**Generalisation.** On this platform, ask *which object owns this behaviour* before
writing. A form embedded in a page has properties split across two records, and the
split is not documented anywhere.

---

### 2.2 Direct storage writes return 200, persist, echo — and never render

**Symptom.** Upload a new page-data object to the platform's Firebase Storage bucket and
`PATCH` the Firestore pointer. Both return `200`. Firestore shows the new pointer. The
GoHighLevel REST API echoes the new values. The live page is unchanged, permanently.

**Cause.** Pages are **compiled at save time**. The renderer reads from a
`versionHistory[]` entry — each carrying its own download path and element census — not
from the top-level pointer you edited. The builder additionally holds its own draft and
will overwrite raw storage edits on its next save.

**Detection.** Fetch `https://sites.leadconnectorhq.com/preview/{pageId}` and grep for
your changed text. Nothing at the API layer distinguishes this from success — this is
false victory 2 in `verification.md`, and it survived four independent confirmations.

**The correct path.** The endpoint the builder's own Save button calls
(`POST backend.leadconnectorhq.com/funnels/builder/autosave/{pageId}` with the funnel
id, the page data tree, and the page version). It returns `201` and triggers a
recompile.

---

### 2.3 Large CSS pastes truncate silently in the form builder

**Symptom.** You paste a stylesheet into the form builder's Custom CSS field. The editor
shows hundreds of lines. Save reports no error. On reload, only part of the CSS is
present — and different forms in the same batch keep **different random chunks**.
Multi-line gradient declarations and `@import` rules are stripped first.

**Cause.** A practical size limit well below what the editor will visually accept.
Measured failure at around 14KB of CSS; the safe working ceiling is roughly 8KB.

**Detection.** After every paste-and-save, fetch the form's **public widget URL** and
assert that specific rules actually landed — measure a computed value you can see, such
as a field height. Do not trust what the editor displays in the browser. In one batch of
six identical pastes, a gradient rule was stripped from all six and one form's field
height came back at a different value from the other five.

**Practical rules.**

- Keep the stylesheet under ~8KB. Strip comments, consolidate duplicate selectors, drop
  nice-to-haves.
- Split critical rules (sizing, padding, placeholder, consent-checkbox layout) from
  cosmetic ones (shadows, scrollbars, gradients). Ship critical first.
- Prefer solid colours to gradients inside GoHighLevel forms; put gradients on the
  wrapper you control.
- **Automated paste failing is a symptom, not the bug.** Manual human paste has partial
  failures too. The fix is a smaller stylesheet, not a better click.

---

### 2.4 Scope asymmetry: create and update succeed, DELETE 401s

**Symptom.** A batch job creates and updates a resource family happily, then fails at
cleanup with `401 "token is not authorized for this scope"` — leaving the account
littered with test objects.

**Cause.** Read and write scopes on GoHighLevel are not a single axis. A token can be
authorised to create and mutate a resource and still be refused permission to destroy
it. Verified on email templates.

**Detection.** **Probe destructive verbs before you build a cleanup routine on top of
them.** Create one throwaway object and try to delete it, at the start of the job, not
the end.

**Workaround.** Where a delete is refused, `PATCH archived: true` instead. It is
generally accepted where deletion is not.

---

## 3. Cloning and structure

### 3.1 THE EXEMPLAR TRAP — cloning inherits ROLE, not just schema

This is the most expensive bug in this guide and the most transferable beyond
GoHighLevel.

**Symptom.** Generated page sections render **overlapping, out of order, with dead
vertical space**. The CSS is valid. The schema is correct. Nothing errors.

**Cause.** Generating a valid page tree by **cloning exemplar elements captured from a
real page** is a sound technique — GoHighLevel elements have dozens of required keys,
every value wrapped in a `{"value": ...}` envelope, and hand-written dictionaries always
miss something. But the exemplar chosen as "the section template" was **section 0 of the
source page, which was the sticky navigation bar**:

```
extra.sticky   = {"value": "stickyTop"}     <- inherited by every generated section
title          = "main-navigation"
paddingTop     = 12px                        <- content sections use 100px / 120px
backdropFilter = blur(90px)
```

Seven `stickyTop` sections stacked on one another. The schema was right; the
**semantics** were wrong.

**Why detection failed.** **A key-set diff between the generated tree and the source
tree showed ZERO differences.** Every key was present. The bug lived in a *value*. A
diff of key sets is structurally incapable of seeing a role.

**Detection.** Before cloning any exemplar, inspect its **role-bearing fields** —
stickiness, positioning, z-index, visibility flags, semantic titles, padding magnitude,
width class — and pick one whose role matches what you are generating. Keep **separate
exemplars per role** (nav / hero / content / footer), not one universal "section"
template. Diff values on role-bearing fields, never key sets.

**The generalisation.** Cloning a sample to satisfy a schema also inherits that sample's
*configuration*. Schema-valid is not semantically appropriate. This applies to every
"copy a working example and edit it" workflow you will ever run.

---

### 3.2 The lead-capture popup is a SIBLING of `sections`, not inside it

**Symptom.** A faithfully rebuilt opt-in page ships with **no lead capture at all**. It
looks complete.

**Cause.** In the page definition, `popupsList` sits beside `sections`, not within it. A
walk that recurses `sections` will silently omit the entire popup — which on an opt-in
page is where the form lives.

**Detection.** Enumerate top-level keys of the page definition before you write a
traversal. On the rebuild where this happened, every one of five independent review
lenses caught the missing form and the automated structural check did not.

---

### 3.3 Section counts are the wrong fidelity metric

**Symptom.** A pixel-faithful rebuild "fails" a structural parity check.

**Cause.** Source trees contain **desktop/mobile twin sections** that collapse into a
single responsive element at render time, and **author-disabled sections** (hidden on
both breakpoints) that render nowhere. Desktop and mobile payloads are byte-identical —
the platform serves one definition and switches per-element flags.

**Detection.** Encode the expected collapses in the checker. And see "verify your
verifier" in `verification.md`: this checker was independently wrong three times.

---

### 3.4 Reusing a pre-existing account form imports everything about it

**Symptom.** The client says: *"the form is too big, it has fields that don't belong, it
stretches the page and isn't centred."*

**Cause.** The page was pointed at a generically named form that already existed in the
account for an unrelated intake flow. Reading it back showed six fields where three were
expected — plus its own image, its own linked header, its own submit-button markup, a
fixed pixel width, and several thousand characters of its own field CSS. All of it
rendered inside the new funnel.

**Detection and rules.**

- **A funnel gets its OWN form.** Never point a page at a generically named account form
  ("Registration", "Contact Us"). Restyling it changes it everywhere else it is
  embedded, and reusing it imports fields you did not choose.
- Build the new form by **cloning a working form's schema** and deleting fields — see
  3.1 for the trap attached to that, and inspect the clone's role-bearing fields.
- **`GET /forms/?locationId=...` returns `name: null`** for forms created via the API.
  Any "does my form already exist?" check that matches on name will always miss and
  create a duplicate, forever. Persist the created id and match on that.
- `POST /forms/{id}` is the update route — `PUT` and `PATCH` return `404`. It `422`s if
  the body contains `locationId`, and the `422` names the offending property.
- The rendered form is **inline in the page document, not in an iframe**. Page CSS
  reaches it. Do not assume iframe isolation — that assumption costs you a working
  styling path.

---

## 4. Styling

### 4.1 Equal-specificity CSS ties lose on injection order — and yours is always first

**Symptom.** A form stays at its old width against your explicit `max-width`, and
`!important` does not help.

**Cause.** GoHighLevel writes each section's per-element CSS to the section's own styles
field and **injects it AFTER your page-level stylesheet**. Source order decides every
specificity **tie**, and the platform's rule is always later:

```css
.page-content [class*=cform-]      { max-width: 440px !important; }  /* yours,  (0,2,0), first */
.page-content .cform-<elementId>   { width: 333px; }                 /* theirs, (0,2,0), later */
```

`!important` does not save you here — it ranks you against *non-important* rules, not
against a later same-specificity rule in the same important tier.

**Detection and fix.** Read the **computed style** of the element and walk the ancestor
chain to find which rule actually carries the constraint; the winning rule is rarely on
the element you suspect. Fix by **raising specificity**, typically with a tag qualifier:

```css
.page-content div[class*=cform-] { ... }   /* (0,2,1) beats (0,2,0) */
```

**The rule:** assume anything keyed to a platform element id will be re-declared after
your stylesheet. Never rely on `!important` alone to beat it.

**Related structural fact.** There are **two id namespaces** — authoring ids and rendered
ids differ by a prefix, and the rendered id is stored on the element under an `extra`
field. Emit CSS for **both** or your selectors will match in the builder and not on the
live page, or vice versa.

---

### 4.2 Your own blanket rules are the most likely cause of an invisible element

**Symptom.** An element is present in the DOM with correct content and correct URLs, and
is simply not visible.

**Cause.** In one session three separate broad rules each silently destroyed something
specific and load-bearing: an odd/even background rule flattened a deliberate
per-section palette; a redefined `::before` reverted an earlier established treatment
because the later duplicate silently wins; and a `::after { display: none }` "restraint"
rule hid a portrait image that had been implemented as a section's `::after`.

Broad selectors are written to solve a global problem, and then something specific gets
built on the same hook later. The rule is invisible at the point of the new work.

**Detection.** When an element renders correctly and is invisible, **suspect your own
broad rule before you debug the element's own styling.** Read the computed style of the
element *and its pseudo-elements* — that reports `display: none` versus `opacity: 0`
versus masked instantly and ends the guessing. In the portrait case, the mask gradient
was blamed first and "fixed" while not being broken.

**Prevention.** Scope blanket rules by exclusion at the moment you write them. Grep the
stylesheet for the selector family before adding to it. Search for duplicate selectors —
a later duplicate silently wins.

**And the companion rule:** fix the one broken case; do not generalise the shared
default. Applying a shared-handler change to fix one navigation target silently shifted
four others that were working. Specific problems get specific fixes.

---

## 5. Automation and workflow logic

### 5.1 Elapsed waits versus event-anchored waits

**Symptom.** Reminder messages fire at nonsense times. In one reference sequence audited
during this work, a "sorry we missed you" no-show email fired **twenty minutes before
the event started**.

**Cause.** GoHighLevel has (at least) two kinds of wait step: an **elapsed** wait
(`type: "time"`) and an **event-anchored** wait (anchored to an appointment, with a
before/after selector). They are both called "wait" in the UI and both look correct in a
deployed definition.

An elapsed wait cannot express "three hours before the session" when every contact
enters the workflow at a different offset. And an anchored wait pointed at the *start*
of a session rather than its *end* produces the twenty-minutes-early no-show email.

**Detection.** Check the discriminating `type` field, not the step name. Then ask, for
each wait: *anchored to what, and does that anchor move per contact?* This is check 6 in
the `verification.md` checklist — right *kind* of primitive, not just right *name*.

---

### 5.2 Non-exclusive branches and empty branch conditions

**Symptom.** A contact receives two contradictory messages from the same sequence — in
one audited reference funnel, "you haven't watched" arrived alongside "you watched but
didn't click."

**Cause, part one.** Branch conditions were not mutually exclusive. Nothing in the
platform enforces exclusivity; overlapping conditions simply both match.

**Cause, part two, and worse.** In our own deployment, both branch steps shipped with
`segments: []` and every remove-from-workflow action shipped with `workflow_id: ""`.
**Empty stubs deploy successfully** — `201`, stored, and completely inert. The written
spec asserted "every branch is mutually exclusive" while the field that would have
enforced it was an empty array.

**Detection.** Grep the generated payload for `""`, `[]`, and `null` in every field that
references another object or carries a condition. Then, for any design that claims
exclusivity, **name the field that enforces it** and confirm it is populated.

**Prevention.** Make the code that builds these payloads **raise** rather than emit an
empty reference. That change was more valuable than any checklist item.

---

### 5.3 Do not add "create contact" actions

**Symptom.** Duplicate or redundant workflow steps; occasionally duplicated records.

**Cause.** GoHighLevel **auto-creates a contact on any inbound channel interaction** —
form submission, inbound SMS, inbound email, phone call, chat widget message. This is
not in the public documentation. By the time a workflow trigger fires, the contact
exists and `{{contact.*}}` fields are already populated.

**Detection and rule.** Workflow design starts at step two: create opportunity, add
tags, route to pipeline, notify, confirm. Never step one.

---

### 5.4 A derived value that is malformed fails silently downstream

**Symptom.** Two emails in a sequence never send. No error anywhere.

**Cause.** One derived datetime field, computed from day/date/time/timezone inputs,
anchors the first workflow. If it is malformed, the steps hanging off that anchor simply
never fire.

**Detection.** Identify the single derived values that anchor timing, and validate them
at generation time with real assertions — including daylight-saving behaviour, which
should come from the platform's timezone database rather than a hardcoded offset table.
Treat "one input that many things depend on" as requiring its own test suite.

---

## 6. UI automation that reads the wrong thing

### 6.1 `body.innerText` contains "Draft" even when published

**Symptom.** A bulk publish script reports that nothing was published. Manual inspection
shows several items *were* published.

**Cause.** The word "Draft" appears in multiple places in the builder chrome — save-state
labels, history, menus. A text-contains check on the page body is therefore always true.

**Detection.** Read the `aria-checked` attribute on the `[role="switch"]` publish toggle.
It is the only reliable signal.

**A second lesson from the same incident.** The first version of that script **actually
worked** — items it reported as failures were genuinely published. Its *detection* logic
was wrong while its *interaction* logic was fine. Before you rewrite a script that
reports failure, verify the failure independently; you may be about to fix the working
half.

---

### 6.2 A wrong selector fails identically to a page that never loaded

**Symptom.** An extraction loop writes zero bytes, nine times in a row. It looks exactly
like an auth failure, a load failure, or a blocked request.

**Cause.** The selector was for a different view of the same application. The class used
belonged to the standard reading pane; the print view being fetched uses a different
container class entirely.

**Detection.** When output is empty, **dump the container you did get** before
concluding the page failed to load. Zero bytes is ambiguous between "no page" and "no
match"; a byte count of the whole document disambiguates instantly.

---

### 6.3 The cross-origin builder iframe does not take mouse coordinates

**Symptom.** Clicks appear to do nothing inside the automation or page builder.

**Cause.** These builders are Vue single-page applications embedded as **cross-origin
iframes** on their own subdomains. Mouse coordinates issued to the page go to the parent
document, not to the iframe.

**Detection and working patterns**, learned across roughly seven script iterations:

- Dispatch events **inside the frame** (`element.dispatchEvent(new MouseEvent('click',
  {bubbles: true}))`) rather than driving the mouse — **except** when the iframe is
  full-page (origin at 0,0), where iframe coordinates equal page coordinates and mouse
  clicks do work.
- **Frame references die on navigation.** The iframe URL stays static because SPA routing
  changes content, not URL — so you cannot detect navigation by URL. Re-acquire the frame
  by polling for content after any navigating click.
- **Match the builder iframe by HOST, not by substring.** A substring match on the
  builder's name also matches the *parent* URL, and you end up probing the empty parent
  document.
- **All frame work must happen inside ONE connection.** Frame references do not survive
  across separate script invocations. Mount, inspect, act, and verify in a single run.
- **A direct URL to the builder often does not mount the iframe.** Navigate the SPA from
  its list view and click through, so the app performs the transition itself.
- For bulk operations, **reload the list page once per item** rather than iterating in
  place. Pagination plus dying frame references produces bugs that look random.
- Dismiss any modal before interacting — a promotional overlay intercepts every click and
  produces a perfect imitation of "the selector is wrong."

---

### 6.4 The SPA fingerprints automation-launched browsers

**Symptom.** A blank white page on every route, including the login route. Zero inputs,
zero content. Console shows a Firebase auth check failing.

**Cause.** The application checks Firebase auth before mounting, and in an
automation-launched browser that check fails, so the app never mounts. Stealth flags
alone did not fix it. Launching a persistent context against a real Chrome profile also
failed, because the automation framework adds a flag that breaks Chrome's own token
decryption for signed-in profiles.

**Working paths.** Attach over CDP to a **manually launched** real Chrome that is already
signed in, using a **cloned** profile directory so you never disturb the human's session.
Alternatively, persist a saved storage state (localStorage plus Firebase IndexedDB) from
one human login and reuse it.

**Environment caveat.** On recent Chrome versions, `--remote-debugging-port` alone on a
default profile no longer binds a TCP socket — the port file exists and nothing is
listening. Confirm with a listening-socket check before you debug anything else. A
dedicated user-data-dir works where the default profile does not.

---

## 7. Compliance scanning (A2P / 10DLC)

These are silent in a different way: the failure is a rejection with an opaque code, and
the actual cause is a structural property of your site that no error message names.

### 7.1 One opt-in source per URL

**Symptom.** Compliance review fails with "multiple opt-ins detected," repeatedly, after
each cleanup attempt.

**Cause.** The scanner rejects any single page that hosts **both** a chat widget and a
form collecting phone/SMS contact information. The rule is binary and applies **per
URL**, not per site.

**Detection and fix.** Isolate opt-in mechanisms across URLs — widget on a dedicated
page with no forms, forms on pages with no widget. Linking between them is fine.

### 7.2 Automated review cannot crawl JS-rendered sites

**Symptom.** Rejection with an opt-in error code on a site that is demonstrably,
completely compliant.

**Cause.** The scanner sees the raw HTML response. A client-rendered site (any modern JS
framework, or even vanilla HTML assembled by script) serves an effectively empty document
to it. Platform-hosted funnel pages are genuinely server-rendered, which is why they pass
— the same server-rendering fact that makes public page definitions readable in
`discovery.md`.

**Fix.** For automated review, host the compliance-bearing pages on the platform's own
funnel builder, with the chat widget present, and all required disclosures in the HTML.
Externally hosted sites must go through manual review.

### 7.3 The frequency phrase is required on BOTH consent checkboxes

**Symptom.** Rejection despite consent copy that matches the approved template.

**Cause.** The message-frequency disclosure is required on the **non-marketing** consent
checkbox as well as the marketing one. Guidance that says otherwise is wrong; omitting it
from the non-marketing checkbox is a rejection point.

### 7.4 A freemium email address on the brand profile weakens the identity signal

Carriers and the registry treat public-domain email addresses as a weaker identity
signal, and the platform's own form warns about it. Provision a branded address on the
business's own domain before submitting. **Check existing MX records first** — adding a
forwarding service blindly can replace working MX records and break the client's inbound
mail.

### 7.5 Manual review is the escape hatch

After repeated automated rejections on a rule that a compliant architecture keeps
tripping, **request manual review**. A human reviewer evaluates intent and opt-in
architecture holistically rather than pattern-matching the DOM. This is what finally
cleared an account that the scanner would never have passed.

Reach for it when: two or more scanner rejections on the same rule after genuine cleanup;
the architecture is actually compliant and the heuristic is over-broad; or the deadline
cost of iterating exceeds the cost of waiting for a human.

---

## 8. Your own tooling

The platform is not the only thing that fails silently. The tools you build to work on
it do too, and those failures are harder to see because you trust them.

### A default that resolves to something plausible

**Symptom.** A search tool returns results. They look reasonable. They are from the
wrong corpus entirely, and nothing says so.

**Cause.** A helper resolved its scope as
`os.environ.get('SOME_PROJECT_DIR', '<a hardcoded path>')`. The environment variable
was unset in the context the tool actually ran in, so every invocation — from anywhere
on the machine — silently answered from one hardcoded project. Other projects, with
hundreds of indexed notes, were simply unreachable. Nobody noticed for months, because
the tool never returned an *error*; it returned an *answer*.

**Detection.** Ask any tool that chooses something on your behalf to tell you what it
chose. If it cannot, that is the bug. Run it from a directory it has no business
defaulting into and see whether the output changes.

**The rule.** *A default that silently produces plausible results is worse than no
default.* An empty result set makes you look harder. A confident wrong one ends the
investigation. If a tool picks for you, it must say what it picked — and if nothing
resolves, it should fail with instructions rather than guess.

This generalises well past search tools: fallback config values, default branches,
implicit accounts, "current" workspaces. Anywhere a program quietly picks one of
several valid-looking options, you have this.

## The shape of all of these

Every entry in this file is one of three things:

1. **The platform accepted your write and the change is not where you looked.** (2.1,
   2.2, 2.3)
2. **The thing you cloned or referenced carried properties you did not inspect.** (3.1,
   3.4, 4.1)
3. **Your check measured something correlated with correctness rather than correctness.**
   (1.1, 5.2, 6.1, 6.2)

When you hit something new on this platform, sort it into one of those three before you
start debugging. It will usually tell you where to look.

---

## Related

- `verification.md` — the checklist designed to catch these before they ship
- `discovery.md` — how these were found, and how to find the next one
- `../knowledge/auth.md` — the credential and header map underlying most write paths here
