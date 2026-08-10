---
name: ghl-builder-iframes-ignore-mouse-coordinates
description: "GoHighLevel builder UIs are cross-origin iframes on their own subdomains, so mouse coordinates issued to the page go to the parent document and clicks appear to do nothing — and a direct builder URL never mounts the iframe at all; you must open the list view and click the row. — SYMPTOM: clicks do nothing, selectors all fail, or the builder loads an empty page with no iframe in it"
metadata:
  type: reference
---

The workflow and page builders are Vue single-page applications embedded as cross-origin
iframes. Working patterns, learned across roughly seven script iterations:

- **Dispatch events inside the frame** — `element.dispatchEvent(new MouseEvent('click',
  {bubbles: true}))` — rather than driving the mouse. The exception is a full-page iframe
  with its origin at 0,0, where iframe coordinates equal page coordinates and mouse clicks
  do work.
- **Frame references die on navigation**, and the iframe URL stays static because SPA
  routing changes content rather than URL — so you cannot detect navigation by URL.
  Re-acquire the frame by polling for content after any navigating click.
- **Match the builder iframe by HOST, not by substring.** A substring match on the
  builder's name also matches the *parent* URL, and you end up probing the empty parent
  document.
- **All frame work must happen inside ONE connection.** Frame handles do not survive across
  separate script invocations: mount, inspect, act and verify in a single run. This is also
  why browser agents are effectively one-at-a-time.
- **A direct URL to the builder often does not mount the iframe.** Navigate the SPA from
  its list view and click through so the app performs the transition itself.
- For bulk operations, reload the list page once per item rather than iterating in place.
- **Dismiss any modal first** — a promotional overlay intercepts every click and produces a
  perfect imitation of "the selector is wrong".

See [[ghl-read-aria-checked-not-innertext]], [[ghl-spa-fingerprints-automation-browsers]].
