---
name: ghl-read-aria-checked-not-innertext
description: Read aria-checked on the [role=switch] publish toggle — body.innerText contains the word Draft even when a workflow is published.
metadata:
  type: reference
---

A bulk publish script reported that nothing had been published. Manual inspection showed
several items *were* published. The word "Draft" appears in multiple places in the builder
chrome — save-state labels, history, menus — so a text-contains check on the page body is
always true.

`aria-checked` on the `[role="switch"]` element is the only reliable signal.

**A second lesson from the same incident, and it is the more valuable one.** The first
version of that script *actually worked*: the items it reported as failures were genuinely
published. Its **detection** logic was wrong while its **interaction** logic was fine.
Before you rewrite a script that reports failure, verify the failure independently — you
may be about to fix the working half.

This generalises to every UI-automation check you write on this platform: prefer a state
attribute the application sets deliberately over text a human happens to read. And prefer
scripted DOM inspection returning structured JSON over screenshots for functional
questions — reserve pixels for questions that are genuinely visual.

See [[ghl-triggers-and-publishing-have-no-api]], [[ghl-builder-iframes-ignore-mouse-coordinates]].
