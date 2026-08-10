---
name: ghl-test-the-empty-account-case
description: Test your tooling against an empty account first — the zero state is where an inheriting agent actually starts, and it is where tools that assume a donor object break.
metadata:
  type: feedback
---

The single worst way one GoHighLevel knowledge repo failed someone: its page generator
refused to run without exemplars captured from an existing public funnel page, and its form
tool refused without a form to clone. **On a fresh sub-account there is neither**, and on an
account using GHL as a back end there may never be a funnel page at all. The golden path was
untraversable from the state a new inheritor is actually in.

The same shape appeared twice more. A form created through the UI's Create button exists
with a real name and **essentially empty `formData`**, so it cannot seed a clone either. And
a workflow's `remove_from_workflow` needs sibling ids that do not exist until the workflows
do — a cold start that has to be handled explicitly rather than papered over with an empty
string.

The fixes are all the same: ship a seed corpus, and make cold-start paths first-class rather
than an afterthought. Overriding with a captured exemplar should be a *choice*; needing to
override should never be a prerequisite.

Generalised: **run your tool from the state your reader starts in, not from the state your
machine happens to be in.** A default that resolves to something plausible is worse than no
default.

See [[ghl-ship-the-artifact-not-its-description]], [[ghl-funnel-gets-its-own-form]],
[[ghl-empty-references-deploy-and-do-nothing]].
