---
name: ghl-if-else-is-three-nodes
description: "An if_else in a GoHighLevel workflow is THREE nodes — condition-node plus branch-yes plus branch-no — and emitting only the first produces a straight line every contact runs. — SYMPTOM: both branches ran for everyone; the condition did not gate anything"
metadata:
  type: reference
---

This is the single easiest way to ship a branch that does not branch, and the step that
looks like the whole condition is only the first third of it. Verified across a captured
corpus: 10 `condition-node`, 14 `branch-yes`, 10 `branch-no`.

    condition-node   type: if_else, nodeType: "condition-node"
                     attributes.branches[] holds the REAL conditions
                     next: [ yes_id, no_id ]        <- a LIST, not a string
      branch-yes     nodeType: "branch-yes"; its id MUST EQUAL branches[0].id (14/14)
      branch-no      nodeType: "branch-no"; attributes {"else": true}, name "None"

Both branch nodes carry `parentKey` **and** `parent` set to the condition node's id, plus
`sibling` naming the other one. The first step of each path hangs off its branch node.

**The trap:** emit only the condition node and list your yes/no steps after it, and you get
a straight line — `next` is a single string, no branch nodes exist, and **every contact
runs every one of those steps regardless of the condition.** It deploys with a 200 and
looks plausible in a JSON dump.

Author it as nested `then` / `else` paths and let a compiler build the three nodes.
**Branches do not rejoin** — the only way back to a shared path is a `goto` pointing at a
step id in the same workflow.

See [[ghl-empty-references-deploy-and-do-nothing]], [[ghl-tag-conditions-need-a-producer]].
