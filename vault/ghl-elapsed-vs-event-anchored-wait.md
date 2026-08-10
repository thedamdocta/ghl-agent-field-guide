---
name: ghl-elapsed-vs-event-anchored-wait
description: "GoHighLevel has two wait steps: an elapsed wait (type time) and an event-anchored wait (type appointment), and an elapsed wait cannot express three hours before an event. — SYMPTOM: scheduled emails never sent, or fired at the wrong time"
metadata:
  type: reference
---

Both are called "wait" in the UI and both look correct in a deployed definition. The
discriminating field is `attributes.type`.

**Elapsed** counts forward from the moment the contact reaches the step:
`{"type": "time", "startAfter": {"when": "after", "type": "hours", "value": 24}}`.

**Event-anchored** counts backward from an anchor: `{"type": "appointment",
"appointmentStartAfter": {"when": "before", "type": "minutes", "value": 180, ...},
"appointmentCondition": "skip"}` — note the value is **always in minutes**.

Why it matters: every registrant enters at a different offset. Someone who signs up 35
hours before the session, waited 24h, gets the "it's tomorrow" email at T-11h; chain
another 21h and "we begin in three hours" arrives **ten hours after the webinar ended**.
A live production funnel was observed apologising for a no-show **twenty minutes before its
own webinar began**.

**`appointmentCondition: "skip"`** is the other half — a late registrant skips the expired
reminders instead of receiving a burst of contradictory ones.

**The tell that makes this easy to miss:** an anchored wait shows an **empty `startAfter`**
in captured definitions. The real timing lives in `appointmentStartAfter`. Inspect only the
obvious field and every anchored wait looks like an unconfigured no-op. Check both keys.

See [[ghl-empty-references-deploy-and-do-nothing]], [[ghl-existence-is-not-wiring]].
