# Producing the Work — From a Client Brief to a Page Worth Injecting

**For cold readers:** everything else in this repository tells you how to *put content
into* GoHighLevel — the schema, the auth, the injection path, the verification. This
file is about where the content comes from. It is the step that decides whether the
thing you inject is worth injecting.

You can run every script in `tools/` perfectly and still ship something generic. The
platform is indifferent to whether your page is any good. This is the part the platform
cannot help you with.

---

## The shape of the pipeline

```
capture a reference funnel   →  tools/capture_funnel.py
decode it into a structure map
derive a page spec, section by section, stating each section's JOB
collect the client's substance separately
decide the modularity boundary
build → inject → verify → review → measure → revise
```

The two halves that matter most are the third and fourth steps, and the failure mode is
always the same one: **treating the reference as a source of content rather than a
source of structure.**

---

## 1. Funnel-hacking, stated honestly

Funnel-hacking means finding a funnel that is demonstrably working in your client's
category, taking it apart, and rebuilding its machinery for a different offer. It is a
legitimate and extremely efficient method. It is also one edit away from plagiarism, so
the boundary needs to be explicit before you start rather than negotiated while you
build.

### What capture actually gives you

`tools/capture_funnel.py` reads any public GHL funnel page back into its full
definition. This is not screenshot-scraping. You get the real tree: every section, row,
column and element, every style value, every button action, every responsive flag. See
the tool's own header for the mechanism — the page ships its complete definition inside
the server-rendered payload, and resolving that payload is the whole trick.

This matters because eyeballing a screenshot gives you an *impression* of a layout.
Capture gives you the layout. Everything below depends on having the real thing.

### The line

> **Take structure. Never take substance.**

| Take | Never take |
|---|---|
| section sequence and count | verbatim copy, in whole or in part |
| what each section is *for* | headlines, subheads, bullet wording, button labels |
| layout: columns, rails, stacking order | images, illustrations, icons, video |
| element vocabulary (which widget kinds appear where) | logos, brand marks, fonts licensed to them |
| mechanics: where the form is, what the CTA does, popup vs inline | brand colours |
| the ORDER things appear in, and what is withheld until when | claims, statistics, proof, guarantees |
| email sequence shape and branch logic | any sentence of it |

The legal reason is obvious. The practical reason is stronger and more persuasive to a
client: **their copy is written for their offer.** It names their price, their promise,
their audience's objection, their credential. Ported to a different business it is at
best inert and at worst actively wrong — a sentence that made sense for a software
product does not make sense for a professional-services practice, and the mismatch is
visible to exactly the reader you most wanted to convince.

### The line gets crossed by accident, not by intent

On the build this file is drawn from, a competitor's **product name shipped hardcoded
into two rebuilt pages, including inside the `<title>` tag.** Nobody decided to do that.
It travelled through the capture, sat in an exemplar, survived a re-skin, and was found
in review. The page said the wrong company's product name in the browser tab.

Two defences, both cheap:

1. **Record reference copy as evidence, never as a draft.** In the spec, reference
   wording belongs in a quoted "what this section does, as they did it" note — not in
   the field where your copy goes. If it is sitting in the copy field, someone will ship
   it.
2. **Grep the finished build for the reference's proper nouns before injection.**
   Product names, company names, domain fragments. The same discipline
   `tools/scrub_secrets.py` applies to credentials, applied to somebody else's brand.

### What you may reproduce faithfully, and should

Structure copied *faithfully* is worth more than structure copied loosely, because the
sequencing is the part that was tested. In the sequence we captured, the single best
decision was structural restraint: **the offer link did not appear until the fifth
email. The first four sold attendance only.** That is a transferable decision. Nothing
in it is their words.

---

## 2. Decode the capture into a structure map

Before writing any spec, produce a plain inventory. Three findings from doing this once
saved days on the build:

**The vocabulary is small.** The schema is `section → row → column → element`, and the
entire six-page reference funnel used **fourteen element types.** Establishing that
bounded the whole rebuild — you are not implementing an open-ended design system, you
are arranging fourteen known things.

**Desktop and mobile are one definition.** The desktop and mobile payloads came back
byte-identical across six pages. Responsive behaviour lives in per-element flags
(force-column-on-mobile, hide-on-desktop, hide-on-mobile) and breakpoint style blocks.
So a four-page funnel is four page definitions, not eight. Fetching twice to compare is
worth doing once, to prove it to yourself.

**Some of the tree is not real, and some of what is real is not in the tree.**

- **Author-disabled sections** — hidden at both breakpoints — render nowhere. They are
  part of the source structure and must not appear in your output.
- **Responsive twins** — a desktop-only and a mobile-only variant of the same section —
  must collapse into *one* element controlled by a media query, not be emitted twice.
- **Whole features live outside the tree you are walking.** One rebuilt opt-in page
  shipped with **zero `<form>` elements, zero `<input>` elements, and two CTAs pointing
  at an anchor that did not exist.** The source's lead capture was a modal popup, and
  popups live in a separate list *outside* the main section tree. A main-tree-only walk
  cannot see it. Recovering it restored seven widgets. The defect was in the traversal,
  not in anyone's design judgement.

Together these mean the obvious fidelity metric is wrong:

> **Raw section-count parity does not measure fidelity.** Seventeen source sections
> becoming fifteen implemented sections was *correct*. A checker that does not encode
> the expected collapses will fail a perfect rebuild and pass a broken one.

See `methodology/verification.md` § "Verify your verifier."

### Verify the brief's assumptions against the artifact

The brief for this project asserted that the reference funnel was modular and
custom-value driven, and that the job was to reproduce that modularity.

Extraction found **zero custom values anywhere in it. Every string was hardcoded.**

One extraction pass converted the task from "copy their modularity" into "build
modularity they do not have" — a better product, but different work, a different
estimate, and a different build order. A second assumption fell the same way: the
reference palette was corporate neutral-and-blue, so **there was no accent colour to
inherit.** The brand colour had to be an input from the client, not something derived
from the reference.

> **Run the extraction before you plan around what the client believes is in the
> reference.** It costs one script run and it can change the shape of the whole job.

---

## 3. Deriving a page spec

A page spec is the artifact that converts a capture into something you can build
deliberately. Without one you will mimic — and mimicry is the failure that produces a
page which is structurally identical to the reference and communicates nothing.

**Write it section by section. For each section, state:**

| field | what goes in it |
|---|---|
| **Job** | one sentence: what this section is *for* in the sequence. "Establish the problem the reader already suspects." "Make the date and time impossible to miss." Not "hero" — that is a name, not a job. |
| **Content type** | what kind of material fills it: a claim, a list of three, a comparison, a logistics block, a proof block, a compliance block. |
| **Source of substance** | client, derived, or literal-and-ours. This column is the whole point of §4. |
| **Element vocabulary** | which GHL widget kinds, and how many. |
| **Responsive behaviour** | what collapses, what hides, what reorders. |
| **Modularity** | per-campaign slot or literal text. See §5. |
| **Fidelity risks** | anything you are unsure survives the rebuild. |

Two properties make a spec worth having:

**It is checkable.** "Three cards, each kicker + title + body, stacking on mobile" is
something a reviewer can hold a render against. "A features section" is not.

**It states jobs, so it survives a content change.** When the client's material turns
out not to fit — and it will — a section with a stated job can be re-filled. A section
defined only by its shape can only be mimicked harder.

### A spec that asserts a measurement must carry the measurement

The most expensive single line in this project was in a shared spec document. It
asserted that a particular colour pairing "passes" WCAG AA. Re-measured with the
relative-luminance formula, it was **3.67:1** — a clear fail for body text.

Six pages were built from that spec by six different agents. The result was roughly
**thirty-four inherited contrast failures**, all correct implementations of a false
premise.

The fix was not to patch the six pages. It was to replace the prose assertion with a
measured ratio table in the spec, *then* rebuild:

> **Anything that changes a shared rule must change the spec first, then the pages,
> then be re-verified.** Patching the artifacts without fixing the source of the rule
> re-introduces the bug on the next build.

This is the chain-check discipline from `methodology/verification.md` applied to
documents rather than to code. A spec is a producer; every page built from it is a
consumer.

### Spec hygiene that made the loop work

- **Open every spec with a "for cold readers" paragraph** — one sentence of current
  state, one sentence of staleness caveat. You will hand these to other agents, and to
  yourself after a context reset.
- **Name what the doc was written against** — which file version, which captures. An
  audit whose line references are stale can still have valid judgements; say which half
  is which.
- **Supersede explicitly.** "This replaces X for anything concerning line numbers; X's
  judgements still hold" is a sentence that saves an hour.
- **Include a "these parts are fine — do not touch" list.** Reviewers and repair agents
  will otherwise rewrite working craft. One entry on this project read, in effect,
  *this is the best single piece of work here and needs a sizing change, not a
  redesign* — and it survived three rounds because it was written down.

---

## 4. Where structure comes from vs where content comes from

> **The reference gives you the skeleton. The client gives you the substance. Mixing
> those up is how you end up with a beautiful funnel selling nothing.**

This is the single idea this file exists to install.

A captured funnel tells you that section four should be three short teaching promises.
It cannot tell you what your client teaches. If you let the reference fill that slot,
you will write three plausible-sounding promises that belong to nobody, and the page
will read exactly as what it is.

### What must come from the client, and what to do when it hasn't arrived

Make this an explicit list at the start of the build, not a discovery at the end:

- the offer, in the client's own framing, including what it is *not*
- the actual mechanics: is the session live or recorded? Is there a replay? What is
  genuinely limited, if anything?
- their credential and their bio — the trust block cannot be invented
- real, permissioned testimonials, with attribution the reader could check
- a real photograph of the person, if a person is on the page
- brand colour, brand marks, and anything licensed
- the destination URLs: offer, replay, booking, support, and the legal pages

**Blanks stay blank.** On this build, six content slots shipped empty pending client
information and were tracked as open items rather than filled with plausible placeholder
copy. That is the correct behaviour and it is uncomfortable, because a filled slot looks
finished and an empty one looks unfinished. The alternative is worse: invented substance
is very hard to find later, because it does not look like a bug.

**But do not let a placeholder reach a client's screen.** One page rendered a literal
bracketed placeholder string, in accent colour, into a screenshot the client saw. The
review note was blunt and correct: **a placeholder rendered to a client screenshot costs
more credibility than the missing widget does.** Blank is a state. A visible
`[ thing goes here ]` is a mistake.

The reconciliation between those two: an empty slot should be *invisible or framed as
deliberately pending*, never rendered as build debris.

### The client's material will not fit the reference's shape

Expect this and plan for it. A section whose job is "three teaching promises" and a
client who has two is a spec problem, not a client problem. Either the section's job
changes or the section goes. What must not happen is a third promise being invented to
fill a slot — which is how invented content enters a build that had rules against it.

---

## 5. Modularity as a first-class decision

Decide **before you build** which strings are per-campaign variables and which are
literal text. Retrofitting this is expensive, and we paid for it.

### What happened

The first rebuild marked **348 slots** as modular. That collapsed to 101 custom values
created in the account, then 142, then 160. Then a single question reframed it: the
client should be able to change a webinar *from a form*, not by hunting through 160
key/value pairs in a flat alphabetical list.

The measurement that settled it: of **75 modularised slots across six pages and nine
email templates, only 16 appeared on more than one surface.** Two — the business name
and the legal footer line — appeared on all fifteen. The event date appeared on five.
The remaining fifty-nine existed on exactly one page.

**Forty-eight were converted back to literal page text.** That conversion required a
full rebuild and re-injection of all six pages. The cost of over-modularising was paid
late, in full.

### The rule

> **A custom value earns its place only when the same string must appear on more than
> one surface. Everything else should be literal text the client can see and click.**

A custom value is a variable in your design system. A variable with one consumer is not
a variable, it is an indirection — and on this platform it is worse than that, because
**an unknown or emptied merge tag resolves to empty string silently.** Every variable
you introduce is a live silent-failure site. Fewer variables is a smaller attack
surface, not just a tidier one.

Applied to buttons, the rule has an especially blunt form:

> **A button whose text you cannot see in the builder is a button you cannot fix.**

Every button label on this build was converted from a slot to literal words.

### Apply it per editing surface, not globally

Page copy became literal because the page builder is WYSIWYG — the client clicks a
headline and types. **Email copy stayed a merge tag**, because email templates are
pushed as raw HTML. Making email copy literal would mean asking a non-technical owner to
edit markup to change a sentence, which is worse than a merge tag, not better.

Same rule, opposite answers, because the surfaces differ. Do not apply it mechanically.

### The four buckets that survive

| bucket | example contents | why it stays a variable |
|---|---|---|
| **Event mechanics** | date, time, timezone, join/replay/offer/booking URLs, offer name | changes every cycle, appears on several surfaces each |
| **Email copy** | teaching points, preview line, replay-window wording | the editing surface is raw HTML |
| **Derived** | weekday, ISO datetime, scheduling anchor | computed, never typed by a human |
| **Locked identity** | business name, sender name, legal footer | multi-surface, set once, and deliberately not exposed to the client's form |

Then build the operator's interface — the flat custom-values screen is not one. That is
`patterns/client-config-app.md`, which is the most transferable pattern in this
repository. The design-principle framing of the same rule is
`patterns/design-systems-in-ghl.md` §6.

---

## 6. Order of work

1. **Capture** the reference; resolve it; write the structure map. Prove the
   desktop/mobile identity for yourself.
2. **Reconcile the brief against the capture.** Report anything the brief assumed that
   the artifact contradicts, before planning.
3. **Collect the client's substance.** Name what is missing and keep the list visible.
4. **Write the design direction** — before any code. See `methodology/design-quality.md`.
5. **Write the page specs**, section by section, jobs first.
6. **Fix the modularity boundary** and write the slot list, with canonical names shared
   across pages so the same concept never has two names.
7. **Build**, inject, and verify at the rendered surface — `methodology/verification.md`.
8. **Review adversarially, measure, revise.** Not once.

Steps 4 and 6 are the two that get skipped under time pressure, and they are the two
whose absence is unrecoverable without a rebuild.

---

## 7. What is unresolved

- **How much structural fidelity is actually worth it.** We reproduced structure 1:1 as
  a discipline, and it was the right call for a first build against an unfamiliar
  platform. Whether a looser reading of the reference — take the sequence, redesign the
  sections — produces a better page faster is genuinely untested. My instinct is that
  1:1 is training wheels you should take off once you can read a capture fluently.
- **Capturing one reference is a sample of one.** Everything above assumes the reference
  is working. We inferred that from it being actively advertised, which is weak
  evidence. Capturing three funnels in a category and diffing their structures would be
  a much better method, and we did not do it.
- **The reference we studied contained real defects** — six of them in its email
  sequence alone, catalogued in `writing-copy.md` §3. A funnel being live is not
  evidence that all of it works. Copying it uncritically inherits its bugs along with
  its structure.

---

## Related

- `tools/capture_funnel.py` — the read side, and the exemplar-role trap
- `methodology/design-quality.md` — the design gate that belongs between the spec and
  the code
- `methodology/writing-copy.md` — filling the slots the spec creates
- `methodology/verification.md` — why "it exists" is the cheap half of correctness
- `patterns/webinar-funnel.md` — what each page in this particular chain must do
- `patterns/client-config-app.md` — the operator interface the modularity decision feeds
- `patterns/design-systems-in-ghl.md` — imposing a design on the platform once you have
  one
