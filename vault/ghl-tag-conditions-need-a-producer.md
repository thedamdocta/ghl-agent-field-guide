---
name: ghl-tag-conditions-need-a-producer
description: A tag condition whose tag has no producer is well-formed, deploys cleanly, and is still dead — no structural check can catch it, because it is a fact about the rest of the account.
metadata:
  type: feedback
---

On a real build, **four of five load-bearing tags had no producer**. The condition was
well-formed, the branch nodes existed, the deploy was clean — and every `if_else`
evaluated false, so every contact took the none-branch. A structurally perfect campaign,
functionally inert past its first stage.

Write the producer/consumer table **before** you build:

| tag | consumed by | producer |
|---|---|---|
| `registered` | WF1, WF4 trigger | WF1 itself |
| `did-not-attend` | WF2 trigger | external platform — none |
| `attended` | WF3 trigger | external platform — none |
| `watched-replay` | WF2 branch | none |

Tags are a dependency graph. Every tag your workflows *consume* needs something in the
account that *produces* it, and "something" often means a third-party integration nobody
has configured yet. Fix the gaps or accept them explicitly, in writing.

This is why the architecture that works is **separate workflows per lifecycle stage**, each
removing the contact from its siblings on entry, rather than one giant branching tree. The
failure it prevents was observed live: a funnel that shipped **three contradictory emails
to one person inside six minutes** because its conditions overlapped.

See [[ghl-empty-references-deploy-and-do-nothing]], [[ghl-if-else-is-three-nodes]],
[[ghl-contacts-are-auto-created]].
