# Design Quality — How to Make It Not Look Templated

**For cold readers:** this file is about the gap between a page that is structurally
correct and a page somebody would believe was commissioned. Everything here was learned
by scoring one funnel repeatedly, badly at first, and finding out why.

The verdict that produced this document, from a reviewer scoring a page 27 out of 60:

> *A good template in careful hands. Competent enough that nobody calls it ugly, and
> nowhere near the register where a visitor thinks "someone was commissioned to make
> this."*

That is the failure this file is about. It is not a failure of effort. Every individual
choice on that page was defensible. The reviewer's diagnosis was that **no single moment
on it was brave.**

---

## 1. Gate every UI build through a design phase, before any code

Do not open a file until a direction document exists. Not a mood board — a set of
constraints you can be held to.

### What the document must name

**A palette: four to six values, each named, each with a stated job.** Not "warm
neutrals." A list, in which every entry says what it is *for* — the field, the accent,
the dark ground, the rules and ornament, the body text. Six is a ceiling, not a target;
one reviewer counted **seven-plus colour registers in play against a prescribed three.**

**Two typefaces, chosen deliberately, and a stated reason.** A display face and a body
face. The reason matters more than the faces: it is what stops the next decision from
drifting. A good reason sounds like *this face was cut in the same century and country
as the subject matter*. A bad reason sounds like *it looks premium*.

Faces must share DNA. Pairing a high-contrast classical serif with a geometric sans is
the most common way to get a page that looks like two pages. Same family across
optical sizes — a display cut and a text cut of one family — cannot clash by
construction.

**A layout concept, stated as a rule you can check a render against.** "Asymmetric
editorial: content sits left on a wide margin, display type runs eight of twelve
columns, body sits narrow at five." Or: "perfect axial symmetry, extreme scale contrast
on the axis, exactly one ornament on the axis, asymmetric weight resolved by balancing
masses at the *edges*." Either is checkable. "Clean and modern" is not.

**One signature element.** The single thing the work is remembered by. A rule that
carries a mark and repeats at every section transition. A single seal that appears once,
at the close. A specific way images meet type. One. If you name three, you have named
none, and the reader will remember nothing.

**Then derive every later decision from that document.** When a question comes up mid-
build — should this divider be a hairline or the drawn ornament? should this button be
filled or ruled? — the answer is in the direction, or the direction is incomplete.

### The failure this gate is designed to prevent, which we committed anyway

We had the direction document. It was written early, it was specific, and it named a
signature element as *the mark of the whole direction*.

**That element was never built.** A fully-specified ornament was referenced **zero
times** in the page builder — the review note called it "the single most beautiful asset
in the project is dead CSS" — while **seventeen pieces of undesigned default ornament
shipped in its place**: seven automatic inter-section hairlines, four bordered timer
plates, two quote rules at unrelated positions, four unstyled default dividers, and one
decorative band rendering as a smear.

> **A direction document that is not a build-time constraint is decoration.**

Two mechanisms fixed it, and both are cheap:

1. **Re-enter design mode at the start of every refinement round**, not once at the
   beginning. Corrective rounds drift toward defaults by gravity; re-reading the
   direction is the counterweight.
2. **Encode the layout rule into the code and name it.** On this project the sentence
   "the ornament is the left-hand mass, the figure is the right-hand mass, the type is
   centred between them" became named classes. Every subsequent layout question was
   checked against that sentence rather than re-litigated.

### Name the contradiction instead of coding around it

The most valuable thing the design gate did was surface a conflict the project had been
avoiding for weeks. The client had asked for centred information. The chosen visual
reference — a straddle-and-overlap editorial collage — **structurally requires long
asymmetric display lines crossing an image.** You cannot have both. Every incremental
fix had been a half-implementation of one while pretending to honour the other.

The resolution is what a gate is for: **do not code around a contradiction, change the
reference target.** The direction moved to a different reference world entirely — one
that was equally expensive-looking, equally suited to the subject, and *compatible with
centred type* — and its five rules were then written down as constraints.

If two requirements are structurally incompatible, no amount of CSS resolves it. Say so,
in one paragraph, and offer the two coherent alternatives.

---

## 2. The calibration problem

AI-generated design does not fail by being ugly. It fails by clustering. Ask any model
for "premium, editorial, not generic" and the output lands in one of a very small number
of places:

- **warm cream ground, high-contrast serif display, a terracotta or rust accent**
- **near-black ground, one acid or neon accent, tight tracked caps**
- **broadsheet layout, hairline rules everywhere, small-caps labels**

These are not bad looks. They are *defaults*, and a client who has seen three agency
decks has seen all three.

> **If your design plan reads like something you would produce for any brief, it is a
> default, not a choice. Revise it, and state what you changed and why.**

The stating is the load-bearing part. Our direction document survived review because it
contained lines like *deliberately not the common display-serif-plus-geometric-sans
pairing, and not the face that was my own first instinct, which was modern-warm rather
than period-correct*. Anyone reading that can check whether the escape was real. A
document that names no rejected alternative has not demonstrated that it considered any.

Note also that we picked the dark-hero default and rejected it *for a reason about the
audience*, not for a reason about taste: a near-black hero with a loud CTA reads as
speculative-opportunity to a risk-averse buyer, which was the exact wrong signal.
**Restraint was the credibility.** That is what a justified choice looks like — it cites
the reader, not the trend.

### Keep a cliché watchlist, and rank it by how loudly each item says "machine-made"

This artifact was more useful than any amount of general advice. Ours, abridged and
generalised:

| tell | why it reads templated | what replaced it |
|---|---|---|
| a permanent coloured glow around a filled CTA | measured **+16 luminance over ~100px, at rest, on every page** — the loudest object on the site after the headline | no glow; hover changes fill and rule only |
| the generated "antique books in raking light" plate | the most-generated image concept in its whole category — the visual equivalent of a gavel | abstract texture, no objects |
| a rounded filled slab as the button | "the engraved plate hiding inside it is good; the container is the tell" | square corners, ruled edge |
| straight apostrophes at display size | *"nothing says 'typed, not typeset' faster"* — and it survived two critiques as a five-character fix | proper punctuation |
| Unicode dingbats as ornament (✕ ✓ ▪ •) | font-dependent; they render as UI symbols | an en-dash and a small solid square: same information, none of the signature |
| three identical one-third-width cards | the bento cliché | widths broken to 38/32/30 with vertical offsets of 0/28/14px and a hairline instead of borders — breaks the pattern **without changing the content** |
| a four-box DAYS/HOURS/MINUTES/SECONDS timer | four equal boxes in a row is the shape of every funnel timer ever shipped | one engraved line; seconds deleted |
| the same background image on every page | arrived *with* the theme rollout, which makes it the newest cliché in the set | vary per page, or remove from most |

And the sharpest item on the list, which is about repetition rather than any single
element:

> **The universal opening move.** Small tracked uppercase label → very large serif →
> short paragraph → one filled pill. *"All six pages open this way. On one page it is a
> masthead; on six it is a template."*

A device is a signature the first time and a template the sixth time. Vary the opening.

### Also keep a "not present — keep it that way" list

Cheap, and it stops regression: gradient text, glassmorphism, aurora/mesh blobs,
tilt-on-hover cards, AI-generated people, generic shield-and-lock trust icons, stock
smiling families, and whatever the visual clichés of your client's specific category
are. Write the category-specific ones down; they are the ones you will otherwise
generate by accident.

### Rules for generated assets

If you are generating supporting imagery, three rules kept ours from reading as
generated:

**One prompt shape for the whole set.** A fixed lighting, film and palette spec reused
across every asset — single warm key from one named angle, no rim light, deep shadow, a
stated grain, a stated depth of field. Twelve images generated from twelve prompts
produce twelve looks, which is itself the tell.

**A disqualification list.** Anything with **hands, a face, or legible lettering is
disqualified from generation.** Invented lettering on a document is the fastest tell
there is, and on a trust-dependent page it is an active credibility hazard. Real people
are photographed, never generated, never AI-retouched, never AI-upscaled.

**Match the asset's medium to the design's medium.** One generated ornament failed
diagnosably: it was a photoreal 3D render, so at magnification it carried cast shadows,
modelled relief and specular highlights. A desaturating filter chain *desaturates it but
cannot un-model it*, and the design wanted flat line-work.

> **No filter turns a render into an engraving.**

It was redrawn as vector line-work and relocated to where a divider had been asked for
in the first place.

One more, on treating a real photograph: there is a ceiling. Pushed past roughly 0.7 on
a grayscale filter, a real person **stops reading as a real person and starts reading as
a treated asset** — which reintroduces exactly the suspicion the real-photo rule exists
to prevent. A separate reviewer attacked the same value from the other side, arguing
that even 0.42 turned the page's one trust asset into a stock silhouette. That range is
genuinely contested; the point is that it is a decision with a behavioural cost, not a
taste knob.

---

## 3. Measure, don't eyeball

This is the section with the highest return in the file.

Almost every design fix that actually moved the score on this project came from
**measuring the render**, not from looking at it. Looking at it told us something felt
flat. Measuring told us why, in a form specific enough to fix.

### The loop

```
render at a known viewport
 → read COMPUTED styles and geometry out of the live page via script,
   returning JSON
 → compare against the direction document's stated values
 → fix the measured defect
 → re-render and re-measure the same quantity
```

**Screenshots are for judging taste. Script evaluation is for finding bugs.** A
screenshot can tell you a page feels undesigned. It cannot tell you that your second
type tier does not exist. Use both, for different questions.

### Four defects that were invisible and obvious once measured

**(a) A type scale with a hole and a duplicate.** Measured tiers on one page:

| tier | rendered | ratio to the next |
|---|---:|---:|
| h1 | 74px | 1.76 |
| h2 | 42px | 1.83 |
| h3 | 23px | **1.10** |
| deck | 21px | 1.27 |
| body | 16.5px | — |

Three names — h3, deck, body — are **one tier to the eye**. The card titles and card
bodies in a three-card section were effectively the same size, so that section had no
internal hierarchy at all. Meanwhile the top of the scale ran 74:16.5 = **4.5:1**
display-to-body, against reference sites measured at 10:1 and 17:1. Later, a reviewer
counted **fifteen sizes and twelve tracking values on one page.**

**(b) A 100px headline on a short page.** Five secondary pages carried an h1 of **100px
— identical to the flagship page**, on sheets as short as 1367px, and the scale then
fell **100px → 16.5px with nothing in between.** The design answer was semantic, not
cosmetic: those pages are stations in a sequence, not landing pages. *The flagship
shouts; the stations speak.* They got their own tier — 62 / 30 / 21 / 16.5 / 10 — with
section padding cut from 159px to 98px on a sheet that short.

**(c) A CSS specificity tie that deleted an entire type tier.** The deck/standfirst was
written as a bare class selector, `(0,1,0)`. The blanket body rule was a *descendant*
selector, `(0,1,1)`. Descendant wins. The deck lost every contested property and
rendered **at body size in body colour — pixel-identical to the paragraph beneath it.**
The fold had no second type tier at all, and the page looked *fine*, because nothing was
broken, something was simply absent.

Two neighbours of the same bug, both found the same way:

- **Injected CSS loses ties by source order.** The platform injects per-section styles
  *after* your stylesheet, so an equal-specificity rule of yours loses. A form stayed
  333px wide against an authored 440px max-width. Adding a tag qualifier — `div[class*=…]`
  rather than `[class*=…]` — broke the tie.
- **A blanket `!important` set eats element-level intent.** Three colour arguments were
  silently discarded, with the measurable result that **two comparison columns rendered
  identical in colour**, so the entire before/after distinction survived on a single
  leading glyph. Relatedly: eight element-level declared font sizes were overridden by
  clamps, meaning **eight declared sizes in the source were lies.** Pick the clamps or
  pick the element sizes. Never both.

**(d) An ornament at 30% of its own width.** A decorative plate with a true aspect of
**1600:495 (3.23:1)** was placed in a container that crushed it to roughly **30% of its
width**. It rendered as a grey smudge, and read as noise rather than architecture. The
corrected placement measured 190 × 59px — verified arithmetically against the source
asset: 190 × 495/1600 = 58.8. ✓

The same family of bug bit a cut-out portrait: `background-size: contain` fits the
**image canvas** inside the box, and a background-removed cut-out carries a large
transparent margin, so the visible figure rendered far smaller than the box implied —
measured at about **6% of the fold** against a reference subject at ~50%. The fix needed
two parts, and one alone did nothing: switch to `auto 100%` so *height* drives the
scale, **and trim the source file to the figure's bounding box first.** Verification is
literal: open the file; the visible ink should touch all four canvas edges.

> **An ornament box must carry its source plate's aspect ratio.** If it does not, the
> art is not "a bit small" — it is a different piece of art.

### Other things worth measuring, all of which were wrong at least once

- **Spacing keyed to viewport *height*.** Every section carried `clamp(72px, 9vh, 132px)`.
  The `9vh` term means vertical rhythm changes with the visitor's window: **85px on a
  laptop, 129px on a tall monitor.** That is not a system, it is a function of somebody's
  screen. Key spacing to width.
- **Whether a spacing scale exists at all.** The margin values found in one stylesheet:
  22, 18, 10, 24, 26, 7, 8, 12, 22, 40. Ten numbers with no relationship. Prescription:
  a six-step scale and nothing else. Individually invisible; in aggregate it is most of
  what separates "designed" from "assembled."
- **Whether your grid is one grid.** Three different systems coexisted in one stylesheet
   — a content rail at 130px, a decorative spine at 65px, a container cap at 1180px, each
  answering to a different number.
- **Unaccounted geometry.** A button's predicted width from its label was ~191px;
  measured **238px.** The 47px difference was the platform's own inner `<span>` padding,
  which no rule neutralised. A descendant reset made the width deterministic.
- **Whether your animation actually runs.** Stagger delays were staged with
  `:nth-child(2|3|4|5)` — but the platform wraps every element in its own container, so
  each animated element is `:first-child` of its own wrapper and **every delay resolved
  to 0ms.** Everything faded in simultaneously; the entire "arrives in reading order"
  thesis was unimplemented. In the same block, `button` was missing from the element
  collector, so the CTA never animated while everything around it did.
- **Whether your selectors work for the reason you think.** Four rules hooked the hero
  off `:nth-of-type(2)`, which matches on element *type*, not on the attribute selector
  next to it. It was working **by coincidence** and would move to the wrong element on
  any injected wrapper. Replaced by a JS pass tagging sections with stable semantic
  class names — which alone unblocked half the remaining fixes.
- **Whether your rule *won*, not merely whether it exists.** On a platform that injects
  a generated stylesheet after yours, a rule that is present and outranked looks exactly
  like a rule that was never written — and the instinct is to rewrite a correct rule
  instead of raising its specificity by one class. So when a measured value is wrong,
  measure the winning rule too, not just the value:

  ```js
  // for one element, list every rule that mentions the property, in cascade order
  const el = document.querySelector('h1');
  [...document.styleSheets].flatMap(s => { try { return [...s.cssRules] } catch { return [] } })
    .filter(r => r.style && r.style.getPropertyValue('color'))
    .filter(r => el.matches(r.selectorText))
    .map(r => ({ sel: r.selectorText,
                 val: r.style.getPropertyValue('color'),
                 imp: r.style.getPropertyPriority('color') }));
  ```

  Compare the last entry with `getComputedStyle(el).color`. If your rule is in the list
  and not the winner, the fix is arithmetic, not authorship. For GHL specifically the
  ladder is in `knowledge/page-css-and-classes.md`; the generalisable habit is that
  **"the rule is in the file" is not a measurement.**
- **Dead code that promises an interaction.** One script removed and re-added a class
  four times per second to trigger an animation. **There was no rule for that class
  anywhere in the stylesheet.** The promised micro-interaction did not exist; the page
  forced a reflow 4×/s for no visual result.
- **A latent bug one render away.** Four selector lists were written `A, B:hover { … }`,
  where `:hover` binds to `B` only — so every anchor-rendered button would be
  permanently in its hover state, glow and all. Dormant purely because those buttons
  happened to render as `<button>`. It survived three critiques.
- **Contrast, always, and at the source.** Six live black-on-black elements measured
  between **1.02:1 and 1.06:1**. Root cause: semantic colour aliases kept their old
  meanings after the ground flipped from light to dark. They rendered at all only
  because a blanket `!important` elsewhere happened to catch them — *the page was one
  selector edit from a blank footer.* Fixed at the source by deleting the aliasing, not
  in CSS.
- **Sub-perceptual feedback.** `translateY(-1px)` on hover: **below the perceptual
  threshold — it reads as a rendering wobble, not as feedback.** Either 0 or 2px. Same
  family: `border-radius: 1px` — **zero is a decision, 1px is a hedge.**
- **Clipping traps.** `min-height:88vh` + centred flex + `overflow:hidden` silently cuts
  the top off on a short viewport, unrecoverably, with no scroll into it.

### Verify your verifier

Three separate times on this project the *measuring tool itself* was wrong: a structural
checker that counted only `<section>` and missed `<footer>`, `<header>` and a bar div; a
byte-offset check that measured a symptom rather than the defect and therefore caught
one of a bug's two forms; and a contrast regex that false-positived on a token measuring
a comfortable 7.02:1.

An adversarial review panel disagreed with that tooling **four times and was right every
time.**

> **Crude heuristics need their own verification. Run your checker against a known-good
> and a known-bad input before you believe its verdict on unknown input. And measure the
> defect, not a symptom of it.**

More on this in `methodology/verification.md`.

---

## 4. Iterate to a standard, not to a count

"Do three rounds of polish" produces three rounds of polish. It does not produce a
standard. Define the standard, then iterate until you hit it.

### The rubric

Six dimensions, ten points each, sixty total: **typographic craft · colour and light ·
composition and rhythm · ornament and detail · restraint · trust signal.**

Every score cell carries a *why* split in two: what earned the points, then a bolded
**"but"** clause naming what capped them — and nearly every clause is a measured number
rather than an impression. That structure is what makes a score actionable. "Typography:
5/10" is useless. "5/10 — the display cut is right and the tracking is per-tier; **but**
h3, deck and body are within 1.4× of each other, so three named tiers render as one" is
a work item.

### The score trajectory, and the most important thing we learned from it

**22 → 31 → 31 → 40 out of 60.**

The zero-delta pass is the one worth studying. Between those two 31s sat a complete,
genuinely better-engineered rewrite. Per-dimension: typographic 5→5, colour 5→6,
composition 4→5, ornament **5→4**, restraint 5→5, trust **7→6**. Two dimensions went
*backwards* while the total held.

The audit's own diagnosis:

> **"The rewrite was lateral. It closed every defect the client could point at and
> opened or retained every defect the client could not name."**
>
> **"Every gain was corrective and every corrective act cost something directive"** — the
> headline shrank below the reference register, the atmosphere was deleted, the ornament
> budget went to default hairlines.

That is the mechanism behind the complaint *"you're only doing incremental changes,"* and
the number proved the client right. Corrective work does not accumulate into a
direction. It is running to stand still.

The structural consequence for the fix list is the transferable part:

> **Items 1–12 close what the client can point at. Items 13–30 close what they cannot
> name but are reacting to. Ship them together, or the next screenshot produces the same
> conversation.**

### Adversarial review: several critics, different lenses

Five independent reviewers, each with a distinct brief, each reviewing the whole set and
each writing its own verdict file:

| lens | brief |
|---|---|
| **contrarian** | Distrust the fidelity claim. Assume it is *not* faithful and prove where. |
| **executioner** | Ship-readiness. Will it actually render and function? What breaks in production? |
| **expansionist** | Completeness. What is *missing* that should be there? |
| **first-principles** | Strip to essentials. Structural diff against the source. Does it reproduce the source's intent, or just something that looks similar? |
| **outsider** | Fresh eyes, as end-user *and* as the client. Would the client accept this as theirs? |

Two things made this work rather than generate noise:

- **A shared pass contract defined up front** — the seven properties every page had to
  satisfy — so the lenses argued against a fixed bar rather than against each other's
  taste.
- **Judgment questions only.** Facts get measured. Panels are for "is this good," never
  for "is this 46 pixels."

### Agreement between reviewers means very little

The empirical case is unambiguous. Round-one pass/revise/fail tallies on the same six
pages: one lens **0/2/4**, three lenses around **0/5/1**, and one lens **5/1/0**. One
reviewer passed five of six pages that another failed four of six.

Round two, scoring the same single page: **27, 27, 29, 33, 41 out of 60.** A fourteen-
point spread on identical evidence.

They agreed where the question was easy — restraint scored 7–8 across the board, trust
scored 2–5 across the board — and diverged hardest exactly where craft judgement lives:
ornament **3 vs 8**, typography **4 vs 8**, colour **4 vs 8**. The same ornament was
"genuinely well cut, real craft" to one reviewer and "fails at all four appearances" to
another — because **one was judging the drawing and the other was judging whether it
rendered.**

> **A chair decides.** Consensus is not a decision procedure; it is a tie-breaker you
> have not earned.

### How the chair decides

> **Reviewer output is a lead, not evidence.** Every claim is re-measured mechanically
> before it enters the fix queue.

Sort every claim into five buckets:

1. **Confirmed — must fix**, with the measurement attached and a severity.
2. **Overstated — do not act on as stated.**
3. **Resolved — my own verifier was wrong.**
4. **Accepted as judgement** — not mechanically checkable; weigh against the other
   lenses.
5. **Verified clean — no action.**

Agreement then becomes a *priority escalator* rather than a proof: "confirmed by two
independent lenses" is a reason to do it first, not a reason to skip the measurement.

Two self-corrections from running this, both kept in the record because they are the
argument for the procedure. One panel claim was dismissed as overstated because the
wrong quantity had been measured — **the reviewer was right.** One claim was accepted
that should not have been, and would have cost two wasted edits.

### Operational rules that make the loop cheaper

- **Capture screenshots after the last edit and before launching reviewers.** One round's
  reviewers scored a button defect that had already been fixed, because the captures
  were taken mid-edit.
- **Do not edit files while reviewers are reading them.** Wait for all verdicts, then one
  coordinated pass.
- **Give reviewers matched evidence.** One reviewer caught that a mobile capture set was
  stale relative to the desktop set — an element visible in one and absent from the
  other, and absent from source. Re-shoot before anyone signs off.
- **Turn the standard into numeric gates.** Ours were ten lines of the form
  *metric | now | target*: h1 rendered size, h1 line count, display:body ratio, distinct
  images across the set, subject's visible ink as a percentage of the fold, left ink edge
  across all pages, label contrast. Eight of ten were automatable off the captures.
- **Verify the next round explicitly.** Take the promised fixes and mark each **LANDED /
  PARTIAL / NOT LANDED** with measured evidence — measuring the *render*, not the source.
  Ours came out 11 landed, 3 partial, 1 not landed. Flag anything you could not verify
  rather than passing it: *"no capture of this exists — it is unverified and should not
  be called closed."*
- **Keep a one-glance gate.** Open every page's capture side by side. If the left ink
  edge, the first baseline and the footer mark do not agree within a few pixels across
  all of them, **the system is not installed, and no amount of per-page polish will
  substitute.**

Delegation mechanics for all of this — file ownership, budgets, and why a subagent's
self-report is a lead — are in `methodology/working-with-agents.md`.

---

## 5. Restraint

> **Spend boldness in one place. Keep everything around it disciplined.**

The measured version of this is the most useful sentence in the whole review corpus:

> **Prominence is a function of concentration, not frequency.**

The accent colour appeared in about **twelve places, most of them at 10px or smaller**.
The client's brief was that the accent stay prominent. Twelve small marks produce a
diffuse haze; the way to *honour* a brief for prominence is to **cut the appearances and
enlarge the survivors.** Budget: four appearances at full strength, and everything at or
below 12px moves to a quieter colour.

The same arithmetic applies to darkness. Three near-black grounds were being used to
signal section changes, with a **maximum perceptual difference under one lightness
step**. So the "spend the darkness here" moment at the final CTA was a two-value shift
nobody could see: **darkness cannot be the device on a dark page.** Collapse to one
ground and get variation from imagery and ornament instead.

**Cut one thing before shipping.** Not as a ritual — because there is always one element
that is present out of momentum. Ours, in order across the rounds: filled buttons cut
from four to two (the repeat CTA demoted to a ruled link); seconds deleted from the
countdown; the four timer plates collapsed to one engraved line; an empty tail section —
a decorative rule floating over 132px of nothing — reduced to zero height; testimonials
removed outright rather than restyled.

Note the pattern in the fixes. When a reviewer said "the before/after doesn't read as
more than a list," the diagnosis was that **it *was* a list** — the fix was a ruled
schedule with a heavy column head and hairline row separators, not a nicer list. When a
client said "the accent isn't bold enough, it's very thin," the stroke was **uniform** —
the fix was weight contrast, not thicker lines. When a hover colour swap read muddy at
full width, the fix was **no colour swap at all**: the fill warms and the rule closes in.

### The opposite failure, which is also real

Restraint is not subtraction. Two reviewers scored the same page from opposite
directions, and both were right:

> **"Restraint has been spent on subtraction until there is nothing left to be
> restrained about."**

> **"Axial symmetry is achieved and then not exploited. Symmetry needs something to be
> symmetrical *about*, and after the hero there is nothing on the axis but more centred
> text."**

A page with everything removed is not restrained, it is empty. Restraint means one
element is allowed to be loud. If you cannot point at that element, you have not been
restrained; you have been timid.

---

## 6. What is subjective, and what is unresolved

Stated plainly, because a design document that pretends to objectivity is useless:

- **Scores are not measurements.** Six dimensions × ten points is a forcing device that
  makes reviewers commit and makes movement visible. A 14-point spread on identical
  evidence is the honest error bar. Do not report a score to a client as a fact.
- **The target we set — 60/60 — was never reached.** The project ended at 40. Whether
  the last twenty points were achievable at all, or whether the rubric's ceiling is
  aspirational by construction, is genuinely unknown.
- **The photograph-treatment range is contested** and we never resolved it. One reviewer
  argued any desaturation costs trust; another argued the untreated image broke the
  palette. We picked a number in the middle and it satisfied nobody entirely.
- **We never A/B tested any of this.** Every claim here is a craft judgement or a
  measurement, not a conversion result. A page that scores 40 and a page that scores 22
  have not been compared on a metric that pays anyone.
- **Whether 1:1 structural fidelity constrains design quality** is open. Several of the
  review's harshest findings — the metronome section rhythm, the identical opening move
  on every page — are properties inherited from the reference. We did not test whether
  breaking fidelity deliberately would have scored better.

---

## Related

- `methodology/producing-the-work.md` — the spec this design phase sits between
- `methodology/writing-copy.md` — copy makes a page feel templated as fast as layout does
- `methodology/verification.md` — measuring the render, and verifying your verifier
- `methodology/working-with-agents.md` — running a review panel without generating noise
- `patterns/design-systems-in-ghl.md` — the four points where the platform fights a
  design system, and how to emit CSS it will respect
- `knowledge/page-css-and-classes.md` — the rendered class map, the specificity ladder,
  and a worked page spec → tree → CSS → injected with real values
- `tools/page-styles.starter.css` — a working, brand-neutral page stylesheet to start
  from instead of a blank file
