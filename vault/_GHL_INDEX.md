---
name: ghl-index
description: Router for the GoHighLevel field-guide vault notes — 51 atomic facts about building on GHL, grouped by surface.
metadata:
  type: reference
---

# GoHighLevel — vault index

Add these lines to your own memory index. Each entry is one file in this folder; the
hook is what to search for when you are stuck. Everything here was observed against a
live GoHighLevel account — anything not verified says so inside the note.

**Start with [[ghl-two-hosts-two-schemes]].** Nothing else makes sense without it.

## Auth

- [[ghl-two-hosts-two-schemes]] — two hostnames, two auth schemes; a credential for one is rejected by the other
- [[ghl-token-id-not-bearer]] — the internal host wants a `token-id` header; Bearer returns "Unauthorized"
- [[ghl-pit-scopes-are-partial]] — create and update can succeed while DELETE 401s on the same token
- [[ghl-capture-internal-token-yourself]] — read the token off traffic a logged-in Chrome already sends; no human paste
- [[ghl-internal-token-60-minute-life]] — the JWT expires in ~60 min, so a long build 401s partway and looks like flakiness

## Discovery and the API map

- [[ghl-mcp-search-describe-execute]] — GHL's own MCP server: six meta-tools, SSE, and no endpoint guessing
- [[ghl-describe-operation-under-reports-params]] — the catalogue can omit required params; the validator is the authority
- [[ghl-422-is-free-schema-documentation]] — POST `{}` and the 422 names the fields; public host only
- [[ghl-never-probe-internal-host-with-empty-body]] — on `backend.`, an empty body is a write that creates a nameless workflow
- [[ghl-endpoint-guessing-returns-200-for-nonsense]] — unknown paths return 200 echoing your segment; control-test with a garbage id
- [[ghl-catalogue-gap-is-not-a-platform-limit]] — no `create-workflow` in the catalogue, yet workflows are creatable internally

## Pages

- [[ghl-funnel-page-autosave-write-path]] — the builder's autosave endpoint is the only page write; REST is IAM-walled
- [[ghl-firebase-direct-write-is-a-dead-end]] — the JWT reaches Firestore, but pages compile at save and the live page never moves
- [[ghl-nuxt-data-devalue-decoding]] — every public page leaks its full definition; integers are pointers
- [[ghl-section-styles-injected-after-your-stylesheet]] — page CSS lives in `sectionStyles` and is injected last
- [[ghl-important-does-not-settle-a-tie]] — `!important` loses to a later same-specificity rule; raise specificity
- [[ghl-node-id-is-not-c-plus-id]] — authoring and rendered ids are independent; emit CSS for both
- [[ghl-exemplar-carries-its-role]] — a clone inherits the exemplar's role, and a key-set diff cannot see it
- [[ghl-popups-list-sits-outside-sections]] — `popupsList` is a sibling of `sections`, so the opt-in modal is easy to lose
- [[ghl-custom-code-payload-is-extra-customcode]] — payload at `extra.customCode`, script not nested, wait for `hydrationDone`
- [[ghl-preview-url-is-read-only]] — the preview is a photograph of the page, never a surface you write to

## Forms

- [[ghl-form-create-is-internal-host-only]] — create on `backend.`, and the id is at `["form"]["_id"]`
- [[ghl-form-create-populate-lag]] — a form is not readable immediately; poll, do not sleep
- [[ghl-form-css-lives-in-fieldcss]] — form CSS goes in the form record; page CSS cannot reach it
- [[ghl-submit-button-selector]] — `.ghl-submit-btn`, not `button[type=submit]`, and `:last-child` hits every field
- [[ghl-forms-list-returns-name-null]] — API-created forms list with `name: null`, so name-matching duplicates forever
- [[ghl-funnel-gets-its-own-form]] — reusing an account form imports its fields, image, header and width
- [[ghl-form-submit-behaviour-on-page-element]] — redirect-after-submit lives on the page element, not the form record
- [[ghl-form-inline-on-page-iframe-elsewhere]] — inline in a GHL page, iframed everywhere else; no auto-resize

## Emails

- [[ghl-email-html-stored-verbatim]] — `editorType: "html"` round-trips byte-identical; email is the easy surface
- [[ghl-email-writes-need-idempotency-key]] — required on writes, and derive it from content rather than the clock
- [[ghl-email-svg-does-not-render]] — raster to PNG at 2x on an opaque ground, hosted in the client's own library

## Workflows

- [[ghl-if-else-is-three-nodes]] — a condition node without its two branch nodes is a straight line
- [[ghl-elapsed-vs-event-anchored-wait]] — two different `wait` steps; the wrong one destroys your schedule silently
- [[ghl-empty-references-deploy-and-do-nothing]] — `workflow_id: ""` and `segments: []` deploy cleanly and are inert
- [[ghl-triggers-and-publishing-have-no-api]] — both are browser-only, and workflows deploy in Draft
- [[ghl-tag-conditions-need-a-producer]] — a tag nothing applies makes a perfect campaign functionally dead
- [[ghl-contacts-are-auto-created]] — any inbound interaction creates the contact; never add a create-contact step

## Custom values

- [[ghl-unknown-merge-tag-renders-empty]] — an unknown tag resolves to empty string, silently, on pages and in email
- [[ghl-custom-value-needs-two-surfaces]] — a slot earns its place only on more than one surface
- [[ghl-customvalues-bulk-is-gone]] — the bulk route was removed; `bulk` is parsed as an id
- [[ghl-customvalue-put-needs-name]] — PUT needs `name` too, and `fieldKey` has braces *and* spaces

## UI automation

- [[ghl-builder-iframes-ignore-mouse-coordinates]] — cross-origin builder iframes; dispatch events inside the frame
- [[ghl-read-aria-checked-not-innertext]] — "Draft" appears in the chrome; read the switch's `aria-checked`
- [[ghl-spa-fingerprints-automation-browsers]] — blank page on every route in an automation-launched browser
- [[ghl-memberships-are-a-different-vendor]] — memberships run on another company's domain with a third auth scheme

## Practice

- [[ghl-200-is-not-proof]] — verify at the rendered surface; the API will echo a write that never landed
- [[ghl-existence-is-not-wiring]] — "does the step exist" is the half a 200 already told you
- [[ghl-ship-the-artifact-not-its-description]] — if the instruction needs an artifact you have, ship the artifact
- [[ghl-test-the-empty-account-case]] — run your tool from the state your reader starts in
- [[ghl-do-not-trust-a-recorded-fact]] — including these notes; send one request and confirm
