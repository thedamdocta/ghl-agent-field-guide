# Verification — A 200 Is Not Proof

> **Status:** every failure described here actually shipped, or nearly shipped, on a
> live client account. The two "false victories" in the first section were both
> declared as successes in writing before being walked back in the same session.

---

## The problem, stated plainly

GoHighLevel will tell you that your write succeeded, store the thing you wrote, echo it
back when you read it, and render a page that does not contain your change.

That is not a bug you can route around with better error handling. It is a property of
the platform: pages are **compiled at save time**, so the served page is a build
artifact, not a live read of the record you just modified. Any verification method that
stops at the API layer is structurally incapable of catching it.

Hence the rule this whole document exists to install:

> **Verify at the rendered surface, not at the API response.**

And the harder rule that took another two months to learn:

> **Checking that a piece EXISTS is not checking that it is WIRED.**

---

## The two false victories

Both of these were called successes in writing. Both were wrong. They are worth reading
in full because the *feeling* of each one is identical to the feeling of a real success.

### False victory 1 — reading `401 -> 422` as "authorized"

The sequence: an unauthenticated probe of a write endpoint returned `401`. Adding a
credential and an empty body returned `422`. The status code moved, which reads
unmistakably as progress — the endpoint now knows who you are and is complaining about
your payload.

It was written down as "auth confirmed."

Then a **real** payload went to the same endpoint and returned
`403 "This route is not yet supported by the IAM Service."` The route was walled the
entire time.

**What actually happened:** the body validator runs *before* the authorization layer. A
`422` means the validator engaged with your request. It says nothing whatsoever about
whether you are permitted to make it.

**The generalisation:** *a 422 proves the shape of your request, never your permission
to make it.* The same shape appears in the platform's MCP server, where `dryRun: true`
returns `authorizationVerified: false` — it resolves and previews the call and
explicitly does not check scopes. A clean dry run is a shape check. Only a real write is
a permission check.

### False victory 2 — the write that returned 200, persisted, echoed, and did nothing

This one is worse, because every check that could be automated passed.

The attempted write path: upload a new page-data object to the platform's Firebase
Storage bucket, then `PATCH` the Firestore document's pointer field to reference it.

- The upload returned `200`.
- The `PATCH` returned `200`.
- Reading the Firestore document back showed the new pointer.
- Reading the GoHighLevel REST API back **echoed the new values**.

Four independent confirmations. The change was written up as working.

**The live page never changed.** Not once, on any of the attempts.

The root cause is that the renderer does not read the top-level pointer at all. It reads
from a `versionHistory[]` entry, each of which carries its own download path and element
census. The builder additionally holds its own draft and will overwrite raw storage
edits on its next save. The write path was real, the storage was real, and the renderer
was simply looking somewhere else.

**What caught it:** a human asked for a screenshot.

Not a better assertion, not a more careful re-read of the API — a request to *look at
the page*. Every machine-checkable signal available at the time said the write had
landed.

The correct write path turned out to be the endpoint the builder's own Save button
calls, found by traffic capture (see `discovery.md`). That path returns `201` and
triggers a recompile, and its result *is* visible at the rendered surface.

---

## Where the rendered surfaces are

"Verify at the rendered surface" is only actionable if you know where the surfaces are.
For GoHighLevel:

| Artifact | Rendered surface | Notes |
|---|---|---|
| Funnel / website page | `https://sites.leadconnectorhq.com/preview/{pageId}` | Public, server-rendered, needs no custom domain and no auth. Fetch it and grep for your changed text. This is the single most useful verification URL on the platform. |
| Form | The form's public widget URL | The builder's editor pane lies about what was saved (see the CSS truncation entry in `failure-modes.md`). The widget is the truth. |
| Email template | Send one, or fetch the stored template body | HTML email templates round-trip byte-identical, so a stored-body check is meaningful here — unlike pages, which are recompiled. |
| Workflow | The builder UI's own state attributes, plus the stored definition | Read `aria-checked` on the publish toggle. Do **not** read body text; see below. |
| Custom values | Re-read after write, then check a page that consumes them | Read-after-write was consistent across a 10-attempt test — no staleness observed. |

The page preview URL deserves emphasis. It is public, it needs no domain configuration,
it is server-rendered so a plain HTTP fetch sees the real content, and it reflects the
compiled artifact rather than the source record. It converts "verify at the rendered
surface" from a manual screenshot ritual into a one-line automated grep.

---

## Existence is the cheap half of correctness

The second, deeper lesson. In one session a human asked two entirely ordinary questions
and each one uncovered a real bug in work that had **already passed a verification
pass**.

**"Did you use all the reference emails I gave you?"** — All of them were used. But one
whose copy opened by referring to the reader having watched a replay was deployed in the
branch for people who attended the live session and never watched a replay. The content
contradicted the state its position asserted. The verification pass had counted emails.

**"You included the necessary wait steps, correct?"** — There were wait steps. They were
the wrong *kind*. The platform has elapsed waits and event-anchored waits, and only the
event-anchored kind can express "three hours before the session" when every registrant
signs up at a different offset. The reminders would have fired at nonsense times. The
verification pass had confirmed that wait steps existed.

**Then, while fixing those two, a third:** every "remove from workflow" action in the
deployment had `workflow_id: ""`, and both branch steps had `segments: []`. **Empty
stubs deploy successfully.** They return `201`, they are stored, and they are completely
inert. The written spec claimed "every branch is mutually exclusive" while the mechanism
that would have enforced exclusivity was an empty array.

The pattern across all three: **the verification asked "does the step exist?" It never
asked "does the step do anything?"** Existence is the half of correctness that a `200`
already tells you. It is therefore the half not worth checking.

---

## The merge-tag corollary

**A resolved merge tag looks identical to a converted one.**

GoHighLevel substitutes custom values server-side. So if you render a page or an email
and grep the output for `{{custom_values.` and find nothing, you have learned *nothing*.
Both of these produce zero matches:

- Every tag resolved correctly to real content.
- Every tag pointed at a key that does not exist and silently resolved to the empty
  string.

The second case is not hypothetical; a production marketing email shipped with a
sentence reading "Grab the now" because an unresolved tag vanished mid-sentence. (Full
entry in `failure-modes.md`.)

**How to verify merge tags properly, in order:**

1. Assert against the **generated source**, before the platform ever sees it — the tag
   names you emitted are a set you control and can diff against the set of keys that
   actually exist in the account.
2. Then fetch the **rendered** output and spot-check that the expected *literal strings*
   appear. Not "no tags remain" — "the words that should be there, are there."
3. For anything where a missing value would corrupt a sentence rather than merely blank
   a line, check that sentence specifically.

The general form: **when a failure mode is indistinguishable from success by absence,
you must verify by presence.**

---

## Verify your verifier

Three separate times in one project, the *verification tooling itself* was wrong:

- A structural fidelity check counted only `<section>` elements and silently missed
  `<footer>`, `<header>`, and a structural bar div — under-reporting the real structure.
- A byte-size check measured the wrong region of the document and therefore missed the
  second symptom of a bug it had already half-detected.
- A contrast-checking regex false-positived on a colour token that actually passes
  comfortably.

A review panel disagreed with that tooling four times and was right all four times.

Two rules fall out:

**Crude regex heuristics need their own verification.** Run your checker against a known-
good and a known-bad input before you trust its verdict on unknown input.

**Measure the defect, not a symptom of it.** Several of these failures were the checker
measuring something correlated with the bug rather than the bug. Related: one review
finding was wrongly *dismissed* because the wrong symptom was measured — the finding was
real and the measurement was aimed at the wrong quantity.

A third rule, specific to this platform: **choose the right fidelity metric.** Raw
section-count parity is wrong for GoHighLevel pages, because source trees contain
desktop/mobile twin sections that collapse into one responsive element on render, and
author-disabled sections that render nowhere at all. A checker that does not encode
those collapses will report a mismatch on a perfect rebuild.

---

## The verification checklist

Run this before any "done." It is ordered cheapest-first.

**Layer 1 — the write itself**

1. Did the call return the status the platform's *own UI* gets for this action? (Capture
   the traffic once and know what normal looks like. `201` from an autosave endpoint and
   `200` from a record update are different normals.)
2. Did you use the endpoint the UI uses, or one you inferred? If inferred, it needs a
   rendered-surface check before it is believed at all.

**Layer 2 — does it exist**

3. Re-read the record. Do your values come back?
4. Did anything you did *not* intend to change, change? (Version fields, pointers,
   names.)

**Layer 3 — is it wired** *(this is the layer that keeps getting skipped)*

5. **Does every reference resolve to a real id?** Grep the generated payload for `""`,
   `[]`, `null`, and `0` in any field that names another object — workflow ids, form
   ids, template ids, pipeline stage ids, segment lists. An empty reference deploys
   cleanly and does nothing.
6. **Is this the right *kind* of primitive, not just the right *name*?** Two things both
   called "wait" behaved completely differently. Check the discriminating field
   (`type`), not the label.
7. **Does each item's content match the state its position asserts?** An email that says
   "you watched the replay" cannot sit in the branch for people who did not. This is a
   semantic check and it cannot be automated away — read the content against its
   position.
8. **Are the branches actually exclusive?** If your design says "mutually exclusive,"
   name the field that enforces it and confirm it is populated.

**Layer 4 — the rendered surface**

9. Fetch the public rendered surface — not the builder, not the API — and grep for the
   literal strings you expect to be present.
10. Confirm the *absence* of things that should be gone, separately.
11. For anything visual, look at it. Screenshots are for "does this look right"; DOM and
    computed-style inspection via script is better and cheaper for "did the handler fire,
    did the state change, is this element actually visible."

**Layer 5 — the neighbours**

12. Check at least one adjacent case that was working before. Shared handlers, shared
    stylesheets, and shared defaults mean a scoped-looking fix can be a blanket change.
13. Trace the chain: what *produces* the thing you changed, and what *consumes* it?
    Verify every link, not the point of change. Chain breaks on this platform are
    typically silent — a consumer that destructures a field you removed simply renders
    nothing rather than throwing anything you will see.

---

## Build things that fail loudly

The most durable fix from the empty-stub incident was not a better checklist. It was
changing the code that generated the payload so that the function which had been
emitting `workflow_id: ""` now **raises** instead.

Prefer a factory that throws over one that emits an empty field. Every silent default
you allow into a builder is a future silent production failure, and the platform will
happily accept and store it.

The same principle applies to tooling you write for yourself: **if the tool cannot do
what was asked, it must say so on stderr and exit non-zero, not quietly degrade.** A
tool that silently returns a lesser result is worse than one that fails, because the
lesser result gets believed.

---

## The DONE receipt

A four-line artifact that makes verification auditable after the fact, and which is
noticeably annoying to write when the work is not actually done:

```
Changed:         <the artifact you modified>
Consumer:        <the thing that reads or renders it>
Verified by:     <observable evidence from the CONSUMER side>
Remaining risk:  <what you did not check>
```

The enforcement rules are simple enough to pattern-match:

- If `Consumer:` is blank, the task is not done.
- If `Verified by:` only describes the producer ("the API returned 201"), the task is
  not done.
- `Remaining risk:` is not a confession. It is a scoping artifact that lets whoever picks
  this up next know which edges are unexamined.

Why this shape rather than a longer writeup: reasoning disappears at the end of a
session. A structured receipt persists in a log, a commit message, or a handoff note.
Future agents can audit a receipt; they cannot audit your past thinking.

---

## Related

- `discovery.md` — the `401 -> 422` trap in its original context, and the control test
  for false-positive endpoints
- `failure-modes.md` — the catalogue of silent failures this checklist is designed to
  catch
- `working-with-agents.md` — why an agent's own report of success is a lead and not
  evidence
