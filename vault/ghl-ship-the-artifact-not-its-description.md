---
name: ghl-ship-the-artifact-not-its-description
description: When a note says do X and X requires an artifact you already produced, ship the artifact — telling the next agent to repeat your discovery is not passing on knowledge.
metadata:
  type: feedback
---

Four times in one session a knowledge repo shipped a *description* of an artifact instead
of the artifact:

| documented | missing |
|---|---|
| how to decode the page payload | the decoder |
| "clone an element's shape" | any element corpus |
| "clone a form's field schema" | any seed schema |
| "style via fieldCSS, target `#_builder-form`" | a working stylesheet |

Each reads as complete. Each leaves the reader to redo work that was already done — and on
a fresh account, three of the four are **impossible** to redo at all, because there is
nothing to clone from.

The related failure, from the same root: a note described some work as *"cloned the field
schema"* when the code **hand-wrote** it. Months later that description — not the code — was
used to build a tool, which then refused to run without a donor form. **Descriptions drift
from implementations, and the description is what propagates.**

Two habits fall out. When you write "do X", ask whether X requires an artifact you have; if
so, commit the artifact. And when you read your own notes, check them against the code
before acting on them.

A prose rule does not survive a tired session. A check that fails does.

See [[ghl-test-the-empty-account-case]], [[ghl-do-not-trust-a-recorded-fact]].
