---
name: ghl-exemplar-carries-its-role
description: Cloning an exemplar element inherits its ROLE as well as its schema, so a schema-valid clone of the wrong section produces a semantically wrong page.
metadata:
  type: feedback
---

Cloning is the right technique — a GHL element carries dozens of required keys, every
value wrapped as `{"value": X}`, and hand-written dictionaries always miss some. The trap
is which exemplar you clone.

The one chosen as "the section template" was **section 0 of the source page, which was the
sticky navigation bar**: `extra.sticky = stickyTop`, `title: main-navigation`, 12px
padding where content sections use 100-120px. The generated page rendered **seven
`stickyTop` sections stacked on one another**. The schema was valid. The CSS was valid.
The *semantics* were wrong.

**Why detection failed: a key-set diff between the generated tree and the source showed
ZERO differences.** Every key was present; the bug lived in a *value*. A diff of key sets
is structurally incapable of seeing a role.

The practice: before adopting any exemplar, inspect its **role-bearing fields** —
stickiness, positioning, semantic title, padding magnitude, width class — and keep
**separate exemplars per role** (nav / hero / content / footer). Diff values on
role-bearing fields, never key sets.

This generalises past GoHighLevel to every "copy a working example and edit it" workflow:
schema-valid is not semantically appropriate.

See [[ghl-nuxt-data-devalue-decoding]], [[ghl-existence-is-not-wiring]].
