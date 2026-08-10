---
name: ghl-popups-list-sits-outside-sections
description: popupsList is a sibling of sections in pageData, so a sections-only walk silently ships an opt-in page with no lead capture.
metadata:
  type: reference
---

The top level of `pageData` is `sections`, `settings`, `general`, `pageStyles`,
`trackingCode`, `fontsForPreview`, `popups`, `popupsList`. **Modals — including the opt-in
capture modal, usually the single most important element on the page — live in
`popupsList`, not inside `sections`.**

The failure in production: a faithfully rebuilt opt-in page shipped with **zero `<form>`
elements, zero `<input>` elements, and two CTAs pointing at an anchor that did not
exist.** The source's lead capture was a modal popup. A main-tree-only traversal cannot
see it. Recovering it restored seven widgets, and the defect was in the traversal, not in
anyone's design judgement.

Worth noting how it was caught: every one of five independent review lenses spotted the
missing form and the automated structural check did not.

**Enumerate the top-level keys of a document before you write a traversal over it.** That
single habit is what this entry is really for.

A button that opens one references it by `extra.popupId.value`, taken from `popupsList`.

See [[ghl-nuxt-data-devalue-decoding]], [[ghl-existence-is-not-wiring]].
