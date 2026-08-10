---
name: ghl-custom-value-needs-two-surfaces
description: A custom value earns its place only when the same string must appear on more than one surface; everything else should be literal text the client can see and edit.
metadata:
  type: feedback
---

Counterintuitive, because the instinct when building modularly is to make everything a
slot. The measurement that settled it: across **6 pages and 9 email templates, 75
modularised slots, only 16 appeared on more than one surface.** Two — business name and
legal footer — appeared on all fifteen; the event date on five. **59 existed on exactly one
page**, and 48 were converted back to literal text at the cost of a full rebuild and
re-injection.

Why single-surface slots are actively harmful:

- **Every slot is a silent-failure site**, because an unknown tag resolves to empty string.
  More slots, more chances.
- **The client cannot see or fix their own copy.** The page builder is WYSIWYG; a headline
  that renders as a merge tag in the builder is one they cannot proofread. *A button whose
  text you cannot see in the builder is a button you cannot fix.*
- **It buries the values that matter.** One account held 142 custom values, most belonging
  to an unrelated line of business.

**The one exception is the editing surface.** Email copy stays a custom value even on one
surface, because templates are raw HTML and making the copy literal means editing markup
to change a sentence. The real rule: *put the string where the person who will change it
can safely change it.*

Method: count distinct surfaces per key. Count == 1, inline it.

See [[ghl-unknown-merge-tag-renders-empty]], [[ghl-customvalue-put-needs-name]].
