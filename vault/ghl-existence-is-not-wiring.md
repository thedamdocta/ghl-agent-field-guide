---
name: ghl-existence-is-not-wiring
description: Checking that a piece EXISTS is not checking that it is WIRED — empty stubs deploy cleanly and every is-it-there check passes.
metadata:
  type: feedback
---

Three defects found in one session, in work that had **already passed a verification
pass**, all of the same shape.

*"Did you use all the reference emails?"* — all of them were used. But one whose copy opened
by referring to the reader having watched a replay was deployed in the branch for people who
attended live and never watched a replay. **The content contradicted the state its position
asserted.** The verification pass had counted emails.

*"You included the necessary wait steps, correct?"* — there were wait steps. They were the
wrong *kind*. The reminders would have fired at nonsense times. The pass had confirmed that
wait steps existed.

*And while fixing those:* every remove-from-workflow action carried `workflow_id: ""` and
both branch steps carried `segments: []`. Deployed, stored, inert.

**The pattern: the verification asked "does the step exist?" It never asked "does the step
do anything?"** Existence is the half of correctness a 200 already tells you, and therefore
the half not worth checking.

The wiring layer, concretely: does every reference resolve to a real id; is this the right
*kind* of primitive and not just the right *name*; does each item's content match the state
its position asserts; if the design claims exclusivity, which field enforces it and is it
populated.

See [[ghl-200-is-not-proof]], [[ghl-empty-references-deploy-and-do-nothing]],
[[ghl-elapsed-vs-event-anchored-wait]].
