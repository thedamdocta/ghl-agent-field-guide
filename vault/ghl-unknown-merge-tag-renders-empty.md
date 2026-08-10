---
name: ghl-unknown-merge-tag-renders-empty
description: "GoHighLevel resolves an unknown custom_values merge tag to the empty string, silently — no error, no warning, no placeholder left behind. — SYMPTOM: a merge tag rendered as nothing; a sentence shipped with a word missing"
metadata:
  type: reference
---

A production marketing email shipped with a call to action reading **"Grab the now"** —
a merge tag mid-sentence pointed at a key that did not exist and the noun simply vanished.
Nobody caught it, because nothing failed.

**Why it is worse than it looks: it fails identically to success by absence.** You cannot
detect it by checking that no `{{custom_values.` remains in the rendered output, because a
correctly resolved tag and a nonexistent one both leave nothing behind. The same behaviour
holds on funnel pages and in email templates.

How to verify properly, in order:

1. **Assert against the generated source**, before the platform ever sees it — the tag
   names you emit are a set you control, and you can diff it against the set of keys that
   actually exist in the account.
2. **Then verify by presence** on the rendered surface: the words that should be there,
   are there. Not "no tags remain".
3. Treat a **mid-sentence** tag as higher risk than a whole-line one. A blanked line reads
   as a design choice; a blanked noun reads as incompetence.

Create every key the build references as part of the build, and fail the build on any
referenced key with no record or a blank value.

See [[ghl-custom-value-needs-two-surfaces]], [[ghl-existence-is-not-wiring]].
