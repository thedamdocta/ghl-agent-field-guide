# Writing Copy — The Words

**For cold readers:** this file is about the sentences that go into the slots the spec
creates. It assumes you have read `methodology/producing-the-work.md` for where the
slots come from and `methodology/design-quality.md` for the surface they sit on.

The reason it exists: **copy makes a page feel templated exactly as fast as the design
does.** A distinctive layout carrying generic copy reads generic. The reader does not
separate the two, and the sentence is the thing they actually consume.

There is also an asymmetry we committed and should not have, and it is worth naming at
the top because it is the failure this whole file guards against. In one editing pass we
correctly deleted fabricated testimonials — on the grounds that invented social proof on
a trust-dependent offer is worse than none — **and in the same pass left three invented
scarcity claims standing.**

> **The restraint was applied to the design and not to the copy.**

That is the default failure. Design discipline and copy discipline are separate habits,
and only one of them tends to be installed.

---

## 1. House rules

These are the ones that generalise past any single client. They are stated as
prohibitions because that is the form that survives a deadline.

### No invented statistics

Not softened, not hedged, not "industry average." If the client did not give you the
number and you cannot cite where it came from, the sentence does not get a number. This
includes the ones that feel harmless — percentages of people who do a thing, counts of
customers served, years of combined experience.

The reference sequence we captured built an entire banner around a revenue figure and
used a conversion-rate improvement as proof. Both were marked *unprovable* and *do not
transfer* — not because they were necessarily false, but because we had no way to know,
and neither did the reader.

### No invented testimonials or social proof

> **On a trust-dependent offer, invented proof is worse than none.**

The failure is not primarily ethical, though it is that. It is that fabricated proof is
*weak* proof, and the reader can tell. Two italic quotes side by side, attributed to a
first name only — no role, no place, nothing checkable — is the weakest available proof
shape. A reviewer's note: it reads as *"we had two."*

Ship the proof block absent. Then get real, permissioned testimonials and give each one
a **role and a location**, because that is what makes an attribution checkable. Absence
is a visible gap you can fill later. Fabrication is invisible and permanent.

The same applies to credentials. A page with no name, no credential and no firm mark on
any surface scored 2/10 and 3/10 for trust from two independent reviewers, and one
summarised the reader's position as: *I would give it an email address. A throwaway one.*
The fix for that is the client's real credential, not a better-designed trust badge.

### No income claims

No earnings, no revenue, no "students have made." In many jurisdictions this is
regulated; in all of them it is the fastest way to make a careful reader stop reading.
If the client insists, that is a conversation with them about their legal exposure, and
it is their decision to make in writing — not yours to make in a headline.

### No scarcity you cannot actually enforce

This is the one that shipped, twice, and it deserves the space.

If the session is an evergreen recording played on a schedule, then **a recording played
on a schedule has no seat limit. Nothing fills up. Nothing is at capacity.** Writing
"seats are limited" on it is simply a lie, and it was in the reference funnel we
captured — which is precisely why "it's in the reference" is not a justification.

The sharper analysis is about *which* false scarcity costs most:

> A line like *"limited so the session stays personal"* is worse than generic scarcity,
> because it makes a **specific operational promise** — a small room, a chance to be
> seen, the host's attention. A recording cannot keep that promise. The reader discovers
> this at the single worst moment available: sitting in the session, immediately before
> the offer. That does not cost you a registration. It costs the sale and the
> relationship.

Two corollaries:

**Do not lead with pressure.** One page opened with a scarcity line as its first
sentence, above everything. On a sensitive, high-consideration purchase, the first
sentence being a pressure line is a brand-safety problem, not a layout one. It was
replaced with a logistics line — channel, day, time — which is information the reader
actually wanted.

**Watch the vocabulary as well as the claim.** "Seats are limited," "spots are capped"
and their relatives are the vocabulary of a specific and low-trust category. Even where
the claim is true, the register may be wrong for the offer. See §6.

### Say the true reason to act instead

Every honest offer has one. Find it and use it:

- The session happens at a time; if you are not there you watch it later, which is worse
  than being there because you cannot ask anything.
- The replay window is real and closes, **if** it really closes.
- The thing being taught is seasonal, or the deadline is external and verifiable.
- The price changes on a date the client has actually committed to.
- Doing nothing has a specific cost that the client can name concretely.

True urgency is usually less loud and more specific than invented urgency. That is a
feature.

### Blanks stay blank

Six content slots on this build shipped empty, pending client information, tracked as
open items. That is correct. A filled slot looks finished; the whole risk of invented
content is that it does not look like a bug.

The one exception, from `producing-the-work.md` §4: **a visible placeholder string
rendered into a client screenshot costs more credibility than the missing widget.**
Empty is a state. `[ thing goes here ]` in accent colour is a mistake.

### Tell one story everywhere

A proposed hero line asserting that no replay would be sent **directly contradicted three
emails in the same funnel, all of which delivered a replay.** It also contradicted the
delivery model, and it would have suppressed registrations from the largest segment of
any webinar audience — people who want the content and know they cannot make the time.

> **Pick one story and tell it everywhere.**

The audit for this is mechanical and worth running once per build: list every claim about
*how the thing works* — live or recorded, replay or no replay, limited or not, price and
when it changes — and check each surface against the list. Contradictions between a page
and an email are invisible to whoever wrote either one.

### An expired state must exist

If a page carries a date or a countdown, decide what it says after that date. Ours
clamped at zero, so from one minute past the start time the page read the date, then
`00 DAYS 00 HOURS 00 MINUTES`, then a button inviting the reader to reserve a seat —
indefinitely. **A dead page converting at zero, forever.** This was measured live on an
iteration whose target date had already passed.

Copy has states. Write the expired one before you ship the live one.

---

## 2. Match the message to the state its position asserts

This is the copy half of the verification rule in `methodology/verification.md`:
**does each item's content match the state its position asserts?**

It is not automatable. It requires reading each message against the branch it sits in,
and it catches an entire class of failure that every structural check passes.

### What it catches

**An email in the wrong branch.** One of ours opened by referring to the reader having
watched the replay — and was deployed in the branch for people who attended the live
session and never watched a replay. The verification pass had counted the emails. All
nine were used. Each one existed. One of them was addressed to somebody who does not
exist.

**Branches that are not exclusive.** In the reference sequence we captured, **three
emails landed within a six-minute window with premises that cannot both be true** — one
addressed to someone who had not watched, another to someone who had watched but not
clicked. One recipient received both. The root cause was not copy at all: the branch
conditions were not mutually exclusive, so a single registrant satisfied more than one.

The copy consequence is what makes it a copy problem too. Each of those emails was
individually well written. The defect only exists in the relationship between them, so
no per-email review can find it.

**A message anchored to the wrong moment.** The reference's no-show email fired
**twenty minutes before the session began**, apologising for having missed the reader.
The wait step was anchored to session *start* instead of session *end*, with no
attendance gate. Again: perfect copy, wrong moment, and the sentence is what makes the
error visible to the reader.

### The practice

Write out the sequence as a table before writing a word of copy:

| # | branch / state | what is TRUE of this reader at this moment | what the message may therefore assert |
|---|---|---|---|

Then write copy against the third column only. If you cannot fill the third column for a
message, the message does not have a place in the sequence yet.

Two rules that fell out of this:

- **The CTA verb should track the state.** Save → Join → Watch, across a registration,
  reminder and replay sequence. The verb is a state indicator, and a stale verb is a
  contradiction the reader notices before they notice anything else.
- **Add a suppression condition, not just exclusive branches.** "Has already received a
  post-session message today" is cheap insurance against the six-minute pile-up, and it
  protects you when a branch condition is subtly wrong rather than obviously wrong.

### And check that the variables resolve

Unknown merge tags on this platform resolve to **empty string, silently**. A production
email in the reference sequence shipped with a hole in the middle of a sentence where a
product name should have been — no error, no visible token, no bounce. It is documented
in the repository README and in `methodology/verification.md`, and it is a copy problem
as much as a plumbing one, because the sentence that ships is the artifact.

Practical rules: **create every slot before the first send**, and **proof-render each
message with values populated.** Grepping the render for leftover tag syntax proves
nothing — a resolved tag and a tag that silently vanished look identical.

---

## 3. Constructions that transfer

Take the **shape**, never the words. The reference's sentences are evidence of a pattern,
not a draft. Every example below is invented for this document and belongs to no client.

### The negation triad

Three short negations in a row, pre-empting the three objections the reader is already
holding. It works because it is faster than an argument: instead of persuading, it
removes.

> *No portfolio review. No pitch at the end. No software you have to buy.*

The mechanics that matter: exactly three, all the same grammatical shape, all short, and
each one must be **true**. Its whole power is that it sounds like someone with nothing to
hide, so one false entry poisons the other two. Pick the three objections you actually
hear — not the three that are easiest to deny.

### The three-fold repetition that isolates one variable

Repeat what stays the same three times, then name the single thing that changes. It makes
a causal claim legible in one line, and it is one of the very few constructions that
survives being read fast.

> *Same bike. Same route. Same legs. The only thing that changes is the gearing.*

The discipline is in the three constants. They must be the things a sceptical reader
would otherwise blame, or the isolation is fake and the sentence is doing rhetoric
instead of argument. If your reader's real objection is not on the "same" list, they will
supply it themselves and the construction works against you.

### Naming plausible objections so replying costs one word

In a message asking for a reply, "any questions?" is an open-ended request that costs the
reader a paragraph to answer, so nobody answers it. Naming the likely objections lowers
the cost of a reply to a single word.

> *Too expensive? Wrong month? Not sure it works for a two-person shop? Reply with
> whichever one it is.*

Two reasons it outperforms the open question: replying is now a one-word act, and the
named objections tell the reader you have heard them before, which is itself reassuring.
Name three at most, and make one of them the objection you least want to hear — that is
the one that earns the trust.

### Naming one concrete thing inside the content to earn a click

Do not promise value. Name an object.

> *Bad: everything you need to get this sorted before the deadline.*
> *Better: slide 11 is the cut-off table, which nobody publishes anywhere.*

A named, specific, checkable object inside the content converts curiosity into a click,
and it costs nothing to give away because the specific thing is not the whole thing. The
generalisation: **specificity is cheaper than superlatives and works better.** One
concrete noun beats three adjectives, every time.

### Withholding, as a construction

Not a sentence but a structure, and the best decision in the sequence we captured: **the
offer link did not appear until the fifth email.** The first four sold attendance only.

Sequence-level restraint is a copy decision, and it is the one most likely to be
discarded under pressure from a client who wants the link everywhere. The argument for
keeping it: an offer link in email one converts nobody and teaches the reader that this
sequence is a pitch, which costs you the open on email two.

---

## 4. Voice

These are small and they compound. Most of them are about making the page describe the
reader's world rather than the builder's.

**Name things by what the reader controls.** A control is named for the outcome the
reader wants, not for the mechanism behind it or the internal name of the object. If a
reader cannot predict what a control does from its label, the label is wrong regardless
of how accurate it is.

**Active voice, and a real subject.** "You'll get the recording within an hour" rather
than "the recording will be made available." Passive voice hides who is responsible,
which is exactly the information a cautious reader is looking for.

**A control says exactly what happens when it is used.** If the button opens a form,
it does not say "learn more." If it starts a download, it says so. This is not pedantry;
a control that under-describes its action is the cheapest possible way to lose the trust
you spent the whole page building.

**The same action keeps the same name through the whole flow.** If the registration
button says one thing on the landing page, the confirmation heading, the reminder email
and the calendar entry should use that same word for that same act. Synonym drift across
surfaces makes a five-surface funnel feel like five vendors. Note this is the *action*
name — the CTA *verb* still tracks the state (§2), because that is a different thing
happening.

**Typeset, do not type.** Straight apostrophes and straight quotes at display size were
on this project's cliché watchlist and survived two critiques as a five-character fix.
The note was: *nothing says "typed, not typeset" faster.* Curly quotes, proper dashes,
non-breaking spaces where a number meets its unit.

**Typography can dictate copy, and it is allowed to.** At the display size the direction
called for, the face averaged roughly **74px per character**. A 71-character headline is
therefore about 5,250px of line — four lines at full width, against reference sites
running seven-to-nine-character display lines. The headline did not get smaller. **The
headline got shorter**, and a new italic deck tier was introduced beneath it to carry
what was cut.

That is the right order of operations. If a headline cannot be set at the size the design
requires, the headline is too long — treat it as a copy brief, not a CSS problem. And
when the design and the copy genuinely cannot both win, that is a contradiction to name
rather than to code around (`design-quality.md` §1).

---

## 5. The register belongs to the client, not to you

A quiet, credible offer and a loud, high-energy offer need different copy. Both can be
excellent. The mistake is having one default and applying it.

**The hype default is a tell.** Trained on the internet's marketing corpus, the default
register is loud: capitalised urgency, stacked superlatives, exclamation, pressure. On a
considered, high-trust purchase that register does not merely underperform — it
*disqualifies*. One reviewer's summary of the problem on our build was that the
vocabulary belonged to a speculative-opportunity category and the subject matter did not.
The words were competent. They were wearing the wrong clothes.

**How to find the right register.** In order of reliability:

1. **The client's own existing writing** — their site, their emails to clients, how they
   answer a question in a call. This is the highest-fidelity signal available and it is
   usually sitting there unread.
2. **How their audience talks about the problem**, including which words they avoid.
   Sensitive categories have euphemisms for a reason, and using the blunt word to sound
   direct can read as callous.
3. **The competitor funnel, last and least.** It tells you what worked for somebody
   else's audience. It is evidence about structure, not about voice.

**State the register in the spec, as a constraint you can be held to.** One or two
sentences, with an explicit *not*: "measured, plain, unhurried; the register of a
professional explaining something they have explained many times — **not** the register
of an announcement." Then any reviewer can check a draft against it, and so can you.

**And check it against the design.** A restrained visual direction carrying loud copy is
incoherent, and the incoherence reads as inauthenticity rather than as a design flaw. If
you have decided that restraint is the credibility (`design-quality.md` §2), the copy has
to be in on it.

---

## 6. What is unresolved

- **None of this was A/B tested.** Every rule here is a craft judgement, a client
  instruction, or a defence against a specific incident. Whether an honest urgency line
  converts as well as a false one on any given audience is unmeasured — and the argument
  for honesty here does not rest on conversion anyway.
- **Where the line sits on "structure, not words" for very short strings** is genuinely
  fuzzy. A four-word button label that is the obvious way to say a thing is not
  plagiarism. A headline is. There is a middle we never had to adjudicate, and you may.
- **We deleted the fabricated testimonials before writing any of this down**, which means
  the rationale survived and the examples did not. That is the right outcome for the
  client and a small loss for the teaching.
- **The register rule assumes the client has a voice to inherit.** For a brand-new
  business with nothing written, you are inventing one, and it should be flagged to them
  as an invention rather than presented as a finding.

---

## Related

- `methodology/producing-the-work.md` — where the slots come from, and structure vs
  substance
- `methodology/design-quality.md` — the surface the copy sits on
- `methodology/verification.md` — "does the content match the state its position
  asserts," and the merge-tag corollary
- `patterns/email-sequences.md` — branch exclusivity, wait kinds, and every tag needing a
  producer
- `patterns/webinar-funnel.md` §6 — the two things not to reproduce
