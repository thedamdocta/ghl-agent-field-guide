# Roadmap — what to read for what you are doing

The README lists what exists. This tells you **which files to open, in what order, for the
task in front of you** — and where the floor drops out.

Read this once before starting. It is short, and it will save you from the two ways
agents get stuck here: not knowing a doc exists, and not knowing that a thing you
assumed was one problem is actually four.

---

## First, the shape of the platform

**GoHighLevel is separate services wearing one interface.** Pages, forms, emails,
workflows and memberships are different applications, on different hosts, with
different auth, different validation and different failure modes. There is no single
mental model that covers all of them, and an approach that worked in one place will
mislead you in the next.

That is why this repo is split the way it is, and why **the answer to "how do I do X"
is usually "which X"**. Expect to go deeper than feels reasonable — GHL rewards it and
punishes assuming.

**Inheriting this properly?** [`vault/`](vault/README.md) is this repository distilled
into 51 atomic memory notes — one file per fact, indexed by
[`vault/_GHL_INDEX.md`](vault/_GHL_INDEX.md) — so the knowledge surfaces from your own
memory search instead of needing a re-read.

Two files pay for themselves before you touch anything:

1. [`methodology/how-to-learn-ghl.md`](methodology/how-to-learn-ghl.md) — how to find
   out anything not written down here. The most portable file in the repo.
2. [`knowledge/known-unknowns.md`](knowledge/known-unknowns.md) — what is BLOCKED,
   UNTESTED, and UNEXPLORED. Check it before spending an afternoon on a wall someone
   already hit.

---

## Always, before anything

| | |
|---|---|
| 1 | [`knowledge/step-zero-credentials-and-ids.md`](knowledge/step-zero-credentials-and-ids.md) — a PIT, a location id, and what to ask a human for (only four things ever need one) |
| 2 | `python3 tools/ghl_mcp.py locations` — proves the token before you build on it |
| 3 | [`knowledge/api-map.md`](knowledge/api-map.md) — which host, which auth, what is walled off |

**Writing pages, forms, funnel steps or workflows?** You also need the internal token:
[`knowledge/getting-the-token.md`](knowledge/getting-the-token.md). You capture it
yourself; a human is needed once, for the first login on a fresh browser profile.

---

## By task

### Build a funnel page
```
knowledge/building-from-scratch.md      the whole chain, empty account to live page
knowledge/funnel-pages.md               the pageData model, autosave, sectionStyles
knowledge/page-css-and-classes.md       the rendered class map + specificity ladder
tools/page-styles.starter.css           a working stylesheet — do not write one blind
patterns/design-systems-in-ghl.md       how to make it not look templated
```
**Rabbit hole:** CSS. GHL injects per-element rules AFTER your stylesheet, so equal
specificity loses on source order, and it emits `#id` rules no class can beat. Read
`page-css-and-classes.md` fully before writing a single selector.

### Build a form
```
knowledge/building-from-scratch.md §Forms and fields    the two-call create/populate
knowledge/forms-and-external-embeds.md                  iframes, CSS, embedding it
tools/create_form.py --seed                             no donor form needed
tools/form-styles.starter.css                           the full selector map
```
**Rabbit hole:** a form is a different DOCUMENT from the page. Page CSS cannot reach
it. Its class names are not guessable (the submit button is `.ghl-submit-btn`), and
the id you need is at `["form"]["_id"]`, not `["id"]`.

### Build an email sequence
```
knowledge/email-templates.md      editorType:"html" stores your markup VERBATIM
tools/email-template.starter.html a complete dark-ground document
patterns/email-sequences.md       separate workflows per stage, and why
methodology/writing-copy.md       the words, which make or break it
```
**Rabbit hole:** email is a different platform. Table layouts, inline styles, no
webfonts in Outlook, no SVG, and a 16px floor. Do not carry web instincts in.

### Build workflows / automation
```
knowledge/workflows.md               action schemas, the linked-list, both wait shapes
tools/workflow-spec.starter.json     4 workflows, 16 action types, 2 real branches
patterns/email-sequences.md          the architecture that keeps branches exclusive
knowledge/driving-the-ui.md          triggers and publishing have NO API
```
**Rabbit hole, and the worst one here:** an `if_else` is THREE nodes, not one. A flat
node is a straight line and both paths run for everyone. `wait` is two different
actions and using the wrong one silently destroys your schedule. Empty
`workflow_id:""` and `segments:[]` deploy successfully and do nothing.

### Make it operable by the client
```
patterns/client-config-app.md    a gated form that writes only an allowlist
knowledge/custom-values.md       the >1-surface rule for what should be a custom value
```

### Something has no API
```
knowledge/driving-the-ui.md      you CAN click. Setup, iframes, the quirks table.
knowledge/known-unknowns.md      or it may be genuinely blocked — check first
```

---

## By symptom

| what you are seeing | read |
|---|---|
| `"Unauthorized"` with a token you know is good | `knowledge/auth.md` — wrong HEADER, not wrong token |
| `400 "form does not exist or is deleted"` right after creating one | `building-from-scratch.md §Forms` — wrong id key, or propagation lag |
| a 200/201 and nothing changed on the live surface | `methodology/verification.md` |
| CSS applied and nothing happened | `page-css-and-classes.md` — specificity, or the wrong document entirely |
| a merge tag rendered as nothing | `custom-values.md` — unknown tags resolve to EMPTY STRING |
| scheduled emails never sent | `workflows.md` — elapsed vs event-anchored `wait` |
| both branches of a condition ran | `workflows.md` — `if_else` is three nodes |
| a list endpoint returns zero and you know it should not | `api-map.md` — bare array vs wrapped object |
| an operation is missing from the MCP catalogue | `mcp-server.md` — absent ≠ impossible |
| you are about to ask a human to do something | `step-zero-credentials-and-ids.md` — only four things need one |

---

## Before you commit anything

```bash
python3 tools/check_docs.py .          # every documented flag exists; no dead links
python3 tools/check_vault.py vault/    # notes parse, names match, links resolve
python3 tools/scrub_secrets.py . --env-file .env --secret "<client name>"
```

Then [`CONTRIBUTING.md`](CONTRIBUTING.md) — especially *ship the artifact, not its
description*, which is the failure this repo was rebuilt out of.

---

## How to go down the rabbit hole well

**Go one level deeper than feels necessary, once.** Nearly every defect recorded here
came from stopping at the first plausible explanation: the endpoint looked broken (the
parser was wrong), the token looked invalid (the header was wrong), the branch looked
deployed (it was one node instead of three).

**When something behaves inconsistently, suspect a second system before suspecting
chaos.** Different host, different document, different mode. Two things sharing a name
are often different things — `wait` and `wait`, a form on a GHL page and the same form
in an iframe.

**And when you surface, write it down.** Add the file, date it, say what it cost.
`known-unknowns.md` shrinking is the clearest sign this is working.
