# Pattern — Lifecycle Email Sequences

**The architectural claim:** split a multi-stage sequence into **separate workflows
per lifecycle stage**, routed by tags, rather than building one workflow with a
branching tree inside it.

The reason is not readability, though it is more readable. It is that separate
workflows are what make branch exclusivity **provable** instead of asserted.

---

## 1. The failure this prevents

We captured a complete nine-email webinar sequence from a competitor funnel we
analysed — pulled live out of a real inbox, one recipient, four days. It was built on
this same platform. Two of its defects are worth more than any amount of theory.

**Three emails in six minutes, with contradictory premises.** On the second evening,
messages 6, 7 and 8 all landed between 10:33 and 10:39 PM. One said *you haven't
opened the replay yet*. Another said *you watched the replay but didn't act*. Another
was addressed to no-shows. **The same person received all three.** The branch
conditions were not mutually exclusive, so a single contact satisfied several of them
and every matching branch fired. Nothing errored. Every individual email was well
written.

**An apology that arrived before the thing it apologised for.** The no-show email —
*"Sorry we missed you live today"* — was delivered **twenty minutes before the webinar
started**, then re-sent two and a half hours later. Its wait step was anchored to the
wrong moment: it counted forward from the moment the contact registered rather than
from the session, so a registrant who signed up thirty-five hours out received the
"you missed it" message on a schedule that had nothing to do with the session at all.

Both are configuration failures inside one branching tree. Both are structurally
prevented by the split.

A third, smaller, worth naming: that sequence also shipped a live sentence reading
*"Ready to fill your next webinar without the guesswork? Grab the  now"* — an
unresolved merge tag, rendered as empty string, no error, no bounce, sent to a real
list. Create every slot before first send and proof-render every template with values
populated.

---

## 2. The shape

One workflow per lifecycle stage. Entry is a tag. Every workflow removes the contact
from its siblings on entry.

```
WF1 · Registered          trigger: registration form submitted
    ├ tag "registered"
    ├ event_start_date  ←  {{custom_values.<event_datetime>}}
    ├ E1  seat confirmed                immediately
    ├ E2  the one teaching email        T−24h   (anchored)
    └ E3  we begin shortly              T−3h    (anchored)

WF2 · Did not attend      trigger: tag "did-not-attend"
    ├ remove from WF1
    ├ E4  replay is ready               immediately
    └ wait 24h → replay link clicked?
         ├ No  → E8  you haven't opened it yet
         └ Yes → E6  the replay is still up

WF3 · Attended            trigger: tag "attended"
    ├ remove from WF1, WF2
    ├ E5  was there something I didn't answer      +2h
    └ wait 24h → E7  can I ask what's holding you up?

WF4 · Closing             trigger: tag "registered", wait to T+48h
    └ purchased?  No → E9  closing this out
```

### Why this makes exclusivity provable

In a single branching tree, "these branches are mutually exclusive" is a property of
the *conditions you wrote*, and nothing checks it. Two conditions can both be true.
Verifying it means reasoning about every combination of contact state by hand, every
time you edit any condition.

In the split, exclusivity is a property of the *structure*:

- A contact enters WF2 or WF3 by tag, and those tags come from a single upstream
  decision — attended or not — that cannot be both.
- **Entering removes the contact from the siblings.** Even if a tag were somehow
  applied twice, the removal makes the overlap terminate rather than compound.
- Each workflow is small enough to read in full. WF3 is four steps. You can hold the
  whole thing in your head, which is the actual precondition for noticing a bug.

The cost is real and worth stating: four workflows is four things to deploy, four
things to publish, and four places to look when something does not fire. You are
trading a debugging cost you can pay for a correctness property you cannot otherwise
obtain.

**Purchase suppresses everything.** Either a `remove_from_all_workflows` on the
purchase trigger, or a purchased check before each send. Pick one and apply it
everywhere; a sequence that keeps selling to someone who already bought is worse than
a sequence that stops early.

---

## 3. The two wait shapes, and why using the wrong one destroys the schedule

This is the mechanism behind the apology-before-the-event defect, and it is easy to
get wrong because both shapes are the same action type.

**Elapsed wait** — counts forward from the moment the contact reaches the step:

```json
{ "type": "wait", "cat": "conditions",
  "attributes": { "type": "time",
    "startAfter": { "when": "after", "type": "minutes", "value": 150 } } }
```

**Event-anchored wait** — counts backward (or forward) from an event anchor. Note the
inner `type` is `"appointment"`, not `"time"`, and the value is **always in minutes**:

```json
{ "type": "wait", "cat": "conditions", "name": "1 day before",
  "attributes": { "type": "appointment",
    "appointmentStartAfter": { "when": "before", "type": "minutes", "value": 1440,
      "distributed": { "months": 0, "days": 1, "hours": 0, "minutes": 0 } },
    "appointmentCondition": "skip" } }
```

**Elapsed waits cannot express "3 hours before."** Every registrant enters at a
different offset from the session, so counting forward from enrolment gives each of
them a different — and usually wrong — send time. Register 35 hours out, wait 24, and
your "tomorrow" email lands at T−11h. Chain another 21 and "we begin in three hours"
arrives ten hours after the session ended.

**`appointmentCondition: "skip"` is the other half.** Someone who registers ninety
minutes before the session **skips** the T−24h and T−3h emails rather than receiving
them late in a burst. That one field is what would have stopped the analysed funnel
apologising for a no-show before its own event began.

**The tell when reading captured definitions:** an event-anchored wait shows an
**empty `startAfter`**. The real timing lives in `appointmentStartAfter`. If you
inspect only `startAfter` — which is the field you would naturally check — an anchored
wait looks unconfigured.

### The anchor itself

```json
{ "type": "event_start_date", "name": "Event Start Date",
  "attributes": { "type": "event_start_date",
    "event_start_type": "custom_field",
    "value": "{{ custom_values.<event_datetime> }}" } }
```

This step is what makes relative-to-event timing possible at all. Place it early in
the entry workflow, before any anchored wait. **If the custom value is blank or
malformed, the anchor resolves to nothing and every anchored wait silently never
fires** — no error, no failed send, just an email that never happens. This is the
single highest-consequence empty string in the whole build, and it is the reason the
config app in `client-config-app.md` derives that value rather than asking for it.

Which datetime format the anchor actually parses — a self-describing ISO string with
offset, or a naive `MM-DD-YYYY HH:MM` — **is untested.** Write both to separate slots,
point the anchor at one, and settle it with a throwaway run.

**Anchor no-show messaging to session END, not session start.** A gate on attendance
is necessary but not sufficient; if the wait resolves before the session finishes, the
attendance tag does not exist yet regardless of how correct your condition is.

---

## 4. Every tag needs a producer

The split routes on tags. A tag with no producer is a workflow that never runs.

On the real build, four tags were load-bearing:

| tag | consumed by | producer | state |
|---|---|---|---|
| `registered` | WF1, WF4 trigger | WF1 itself | works |
| `did-not-attend` | WF2 trigger | the webinar platform | not available |
| `attended` | WF3 trigger | the webinar platform | not available |
| `watched-replay` | WF2 branch | — | **none** |
| `purchased` | WF4 branch | — | **none** |

The four workflows deployed, wired and verified. They were **structurally complete and
functionally inert past the session**, because every post-session branch waits on a
tag nothing applied. Both `if_else` steps evaluated false for every contact and every
contact took the fall-through branch.

**This is the failure mode to internalise: existence is not wiring.** Every "is the
workflow there?" check passed. What was missing was a producer for a tag, which no
structural check of the workflow can detect.

Do this audit explicitly, as a table, before you call a sequence done: for every
condition and every trigger, name the thing that writes the value it reads. If you
cannot name it, the branch is decoration.

Native fallbacks when the platform will not report attendance:

- **Attendance:** invert the default. Presume no-show at session-end + ~2h, and clear
  it for anyone who loaded the room page or clicked the join link. Needs one anchored
  `when: "after"` wait and a small tagging workflow. *This was designed and not built —
  untested.*
- **Replay watched:** a link-click trigger on the replay button in the replay email.
- **Purchased:** the order-form or payment trigger.

---

## 5. Content architecture

The split is about timing and routing. These are about the messages themselves, and
they matter as much.

**Match each message to the state its copy asserts.** Every email in a lifecycle
sequence makes a factual claim about the recipient — *you registered*, *you didn't
show*, *you watched but didn't act*. That claim is either true when it arrives or the
message is worse than not sending it. Write the assertion down for each email
explicitly, then check that the branch and the wait together can only deliver it to
people for whom it is true. The three-emails-in-six-minutes defect is exactly this
check not being performed.

A cheap corollary: **the CTA verb should track the state.** Save → Join → Watch. If
the verb does not change when the state changes, one of the two is wrong.

**Withhold the offer link until after the event.** In the sequence we analysed, emails
1 through 4 sold only attendance; the offer link first appeared in email 5, after the
session. That was the single best structural decision in it. Selling the offer before
the event competes with the event, and the event is what sells the offer.

**Front-load one teaching email, not three.** The pre-event run is three messages:
confirm, teach, imminent. Exactly one of them teaches, and it is what earns the second
day's open. Naming failure modes as a short list is a construction that transfers well
— naming a problem makes it feel diagnosable, and it costs nothing to give away
because the fix is what the session is for.

**Weight the sequence after the event.** Three before, six after. Most of the work
happens once the recipient knows what you are talking about.

**Match the register to the offer.** In the sequence we analysed, the two softest
emails — a no-pressure "was there something I didn't answer" and a name-three-plausible-
objections ask, both with no button — were the exceptions. On anything sensitive,
personal or high-consideration, that posture should be the default rather than the
exception.

---

## 6. Deployment notes

- **Cold start.** A `remove_from_workflow` step needs its sibling's real workflow id,
  which does not exist until the sibling has been deployed. Deploy once to mint the
  ids, then run again to wire them.
- **Make empty ids fatal in your own code.** A step with `workflow_id: ""` deploys
  happily and does nothing — the worst failure mode available here, because it is
  invisible at every layer. Raise rather than emit an empty id.
- **Conditions with `segments: []` deploy successfully too**, and match nothing.
  Assert on the contents, not the presence, of every condition you generate.
- **Trigger configuration and publishing may have no API.** Both were done through the
  builder UI. When detecting published state from the DOM, key off the switch's
  `aria-checked` attribute — a text search for "Draft" returns a false positive,
  because the word appears elsewhere in the builder chrome.
- **A workflow write may need different auth from everything else.** On this platform
  the workflow write path lives on the internal host and rejects the Private
  Integration Token outright. See `knowledge/auth.md`.

---

## 7. Untested

- No live send has gone through the deployed sequence.
- The event-anchor datetime format question in §3.
- The inverted-attendance fallback in §4 is designed, not built.
- The unsubscribe / manage-preferences merge tags were never exercised on this
  account. Verify them before a real send, along with whether custom values resolve
  inside the email builder identically to how they resolve on funnel pages. They
  should. It was not round-tripped.
