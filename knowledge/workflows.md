# GoHighLevel Workflows — The Internal API and the Real Action Schemas

**Audience:** an agent that has never touched GoHighLevel (GHL). Everything marked
"verified" was observed in production against a live sub-account. Anything not
verified is labelled **UNVERIFIED** inline.

**Scope warning up front.** There is no public API for creating workflows, and the
internal one only covers the *body* of a workflow. **Triggers and publishing have no
API at all** — they are browser-only. That is not a handoff to a human: the body goes
in through `tools/deploy_workflow.py`, and the two browser-only steps have tools of
their own, `tools/configure_trigger.py` and `tools/publish_workflow.py`. Plan for the
split before you promise automation — and note that **neither browser tool has been
run against a live account yet**; see [`known-unknowns.md`](known-unknowns.md).

---

## 1. What has an API and what does not

| Capability | Path |
|---|---|
| Create a workflow shell | `POST backend.leadconnectorhq.com/workflow/{locationId}` — **internal API, verified** |
| Write the workflow body (steps) | `PUT backend.leadconnectorhq.com/workflow/{locationId}/{workflowId}` — **internal API, verified** |
| Read a workflow back | `GET backend.leadconnectorhq.com/workflow/{locationId}/{workflowId}` — verified |
| **Configure the trigger** | **NO API.** Browser automation only — `tools/configure_trigger.py`. |
| **Publish (Draft → Published)** | **NO API.** Browser automation only — `tools/publish_workflow.py`. |
| Create a workflow via GHL's MCP server | **Does not exist.** The catalogue offers only `get-workflow`, `add-contact-to-workflow`, `delete-contact-from-workflow`, `list-workflow-campaigns`. |

**Check the catalogue before believing a capability is missing, and before believing
one exists.** `search_operations` on the MCP server replaces guessing — ask the
catalogue what exists rather than probing paths.

---

## 2. Auth — the header, not the scheme

```
POST/PUT/GET  https://backend.leadconnectorhq.com/workflow/{locationId}[/{workflowId}]

Headers:
  token-id:      {the eyJ... JWT}        <-- THIS, not Authorization: Bearer
  channel:       APP
  source:        WEB_USER
  Version:       2021-07-28
  Content-Type:  application/json
  User-Agent:    Mozilla/5.0 ...         <-- Cloudflare 403s default UAs on GHL hosts
```

Verified by testing both forms back to back with the **same** JWT:

- `Authorization: Bearer <token>` → `"Unauthorized"`
- `token-id: <token>` → **200**

**A Private Integration Token (PIT) does NOT work here at all.** The PIT reaches
`services.leadconnectorhq.com` (emails, custom values, media) but not
`backend.leadconnectorhq.com`. Verified: `"Unauthorized"`.

Get the JWT the same way as for funnel pages — **passively observe** any request to
`backend.leadconnectorhq.com` (DevTools → Network → Request Headers, or a
CDP-attached browser reading its own traffic). Life is roughly **60 minutes**, so
capture at deploy time and never persist it.

Note this is the **same header and the same token** the funnel-page autosave endpoint
uses. One capture serves both surfaces.

---

## 3. Body shape

```json
{
  "name":    "WF1 · Registered",
  "version": 1,
  "workflowData": { "templates": [ /* ordered array of steps */ ] }
}
```

`templates` is a **flat array that encodes a tree**. Verified by reading 34 captured
production workflow definitions (393 steps):

- `next` — the id of the following step. A **string** normally, **a LIST** on a
  condition node (holding its branch-node ids), `null` at the end of a path.
  Measured: 329 string, 13 list, 51 null.
- `parentKey` — the id of the node this one hangs off: the **previous step in the
  chain**, or the **branch node** when this step is first inside a branch. Present on
  every step except the first (331/393).
- `order` — a sequence hint, **not an index into the array**. Sibling branch nodes
  share one value and branch children restart at 0. The pointers are what carry the
  structure. **UNVERIFIED:** whether the builder reads `order` at all.

Some steps also carry `parent` (usually equal to `parentKey`, but only 57/331 of the
time) and `sibling` (on branch nodes). Treat `next` + `parentKey` as load-bearing and
the rest as cosmetic.

> **Do not hand-roll the linker.** `tools/deploy_workflow.py` compiles an authored
> spec — including nested `then`/`else` branches — into this wire format, and lints it
> for the failure modes in §5. `tools/workflow-spec.starter.json` is a complete
> four-workflow campaign in that format, covering 16 action types, ready to edit.

Every step is:

```json
{
  "id":   "<uuid4>",
  "name": "human label shown in the builder",
  "type": "<action type>",
  "cat":  "actions" | "conditions",
  "attributes": { /* type-specific */ }
}
```

### Deploy loop (idempotent)

The internal API **happily creates duplicates**, so track ids yourself:

```
if you have a stored id for this name:
    GET  /workflow/{loc}/{id}  -> read current `version`
    verb = "updated"
else:
    POST /workflow/{loc}  body {"name": ...}  -> id from response `id` or `_id`
    version, verb = 1, "created"

PUT /workflow/{loc}/{id}  body {"name","workflowData","version"}
success == response contains `_id`
```

Persist `{name, id}` to a local file. You need those ids for sibling exclusion
(§5), and on a cold start they do not exist yet.

---

## 4. The real action schemas

These were **read off working production webinar automations**, not guessed.

### `email`

```json
{
  "id": "<uuid>", "order": 14, "cat": "actions", "type": "email",
  "name": "Email 1",
  "parentKey": "<id of the branch/step this hangs off>",
  "next": "<id of next step, or null>",
  "attributes": {
    "subject":        "{{contact.first_name}}, <subject line text>",
    "template_id":    "<the saved email template's id>",
    "templatesource": "email-builder",
    "from_email":     "{{custom_values.support_email}}",
    "from_name":      "{{custom_values.business_name}}",
    "attachments":    []
  }
}
```

**`template_id` + `templatesource: "email-builder"` is the join** between a workflow
step and a saved email template. `templatesource` is required. **This is why the
templates must be created first** — see `email-templates.md`.

`from_email` and `from_name` accept merge tags, so the sender stays swappable per
deployment.

### `wait` — TWO different shapes, and picking the wrong one breaks the sequence

This is the subtlest bug in the whole system. Read both.

**Elapsed wait** — counts forward from the moment the contact *reaches this step*:

```json
{ "type": "wait", "cat": "conditions", "name": "wait 24 hours",
  "attributes": {
    "type": "time",
    "startAfter": { "when": "after", "type": "hours", "value": 24 },
    "windowCondition": { "field": "", "operator": "", "value": "" }
  }}
```

**Event-anchored wait** — counts **BACKWARD** from an `event_start_date` anchor. Note
`type` is `"appointment"`, not `"time"`, and the value is **always in MINUTES**:

```json
{ "type": "wait", "cat": "conditions", "name": "3 hours before the event",
  "attributes": {
    "type": "appointment",
    "appointmentStartAfter": {
      "when": "before", "type": "minutes", "value": 180,
      "distributed": { "months": 0, "days": 0, "hours": 3, "minutes": 0 }
    },
    "appointmentCondition": "skip"
  }}
```

> ### Elapsed waits CANNOT express "3 hours before an event."
>
> Every registrant signs up at a different offset from the event, so counting forward
> from enrolment gives each of them a different — and usually wrong — send time.
>
> Worked example: someone registers **35 hours** before the session. Wait 24h and the
> "it's tomorrow" email lands at **T−11h**. Chain another 21h and the "we begin in
> three hours" email arrives **ten hours after the webinar ended.**
>
> This is not hypothetical. A live production funnel was observed apologising for a
> no-show **twenty minutes before its own webinar began**, for exactly this reason.

**`appointmentCondition: "skip"` is the other half.** Someone who registers ninety
minutes before the session **skips** the T−24h and T−3h emails rather than receiving
them late. Without it they get a burst of contradictory, expired messages.

> **The tell that makes this easy to miss:** in captured workflow definitions, an
> event-anchored wait shows an **EMPTY `startAfter`**. The real timing lives in
> `appointmentStartAfter`. If you inspect only `startAfter` — the obvious field —
> every anchored wait looks like an unconfigured no-op. Always check both keys.

### `event_start_date` — what makes anchored waits possible

```json
{ "type": "event_start_date", "cat": "actions", "name": "Event Start Date",
  "attributes": {
    "type": "event_start_date",
    "event_start_type": "custom_field",
    "value": "{{ custom_values.event_datetime_iso }}"
  }}
```

This sets the event anchor from a custom value; every subsequent anchored wait
resolves relative to it instead of relative to enrolment. **Without this step a
"T−3h" reminder cannot exist at all.**

**Two failure modes to guard:**

1. **A blank or malformed anchor value deploys fine and does nothing** — the anchor
   silently never resolves and both pre-event emails never send. Validate the value,
   not just the deploy.
2. **Timezone.** A *naive* datetime (no offset) is interpreted in the **account's**
   timezone. If the event is in a different zone, pages render correctly but scheduled
   emails fire at the wrong hour, **silently**. Mitigation used in production: write
   **both** an ISO-8601 value with offset (self-describing) and a naive
   `MM-DD-YYYY HH:MM` value, point `event_start_date` at the ISO one, and warn loudly
   when a non-account zone is selected. **UNVERIFIED:** which format GHL actually
   parses best was never settled by test — it needs one throwaway workflow run.

Also worth knowing: **there is no API to change a location's timezone**, and you would
not want one — the account timezone governs every calendar, appointment, workflow and
contact timestamp in the whole sub-account. The blast radius of repointing it from a
campaign form is far larger than the campaign.

### `if_else`

```json
{ "type": "if_else", "cat": "conditions", "nodeType": "condition-node",
  "name": "Watched the replay?", "comments": [],
  "attributes": {
    "branches": [{
      "id": "<uuid>", "name": "Watched", "operator": "and", "showErrors": false,
      "segments": [{
        "__segmentId": "<uuid>", "operator": "and",
        "conditions": [{
          "conditionType":     "contact_detail",
          "conditionSubType":  "tags",
          "conditionOperator": "index-of-true",
          "conditionValue":    ["watched-replay"],
          "__conditionId":     "<uuid>",
          "isWait": false
        }]
      }]
    }],
    "operator": "and", "if": true,
    "conditionName": "Watched the replay?",
    "version": 2,
    "noneBranchName": "Not watched"
  }}
```

That is the **tag-condition** shape: `contact_detail` / `tags` / `index-of-true` with
the tag list as `conditionValue` (a **list**, even for one tag). Real records also
carry `ifElseNodeId: ""` and `__customFieldType__: "standard"` inside the condition;
both appear to be optional. `noneBranchName` is a label, **not** the mechanism — see
below.

Condition shapes observed in the corpus, with their operand types:

| conditionType | conditionSubType | operator | conditionValue |
|---|---|---|---|
| `contact_detail` | `tags` | `index-of-true` | **list** of tag names |
| `contact_detail` | `<custom field id>` | `==` | string |
| `contact_detail` | `<custom field id>` | `has_no_value` | `null` |
| `workflow_contact` | `workflow_contact` | `index-of-true` | **string** — a workflow id |

### ⚠ An `if_else` is THREE nodes, not one

**This is the single easiest way to ship a branch that does not branch**, and the step
that looks like the whole condition is only the first third of it. Verified across the
corpus: 10 `condition-node`, 14 `branch-yes`, 10 `branch-no`.

```
condition-node          type: if_else, nodeType: "condition-node"
  │                     attributes.branches[] holds the REAL conditions
  │                     next: [ yes_node_id, no_node_id ]   ← a LIST
  ├── branch-yes        type: if_else, nodeType: "branch-yes"
  │     │               id MUST EQUAL attributes.branches[0].id   (14/14)
  │     │               attributes: {"if": false, "conditionName": "Condition",
  │     │                            "operator": "and", "branches": []}
  │     └── first step of the matched path   (parentKey = branch-yes id)
  │           └── next → second step → …
  └── branch-no         type: if_else, nodeType: "branch-no"
        │               attributes: {"else": true}   ·   name: "None"
        └── first step of the fall-through path  (parentKey = branch-no id)
```

Both branch nodes carry `parentKey` **and** `parent` set to the condition node's id,
plus `sibling: [<the other branch node id>]`.

**The trap:** emit only the condition node, then list your "yes" and "no" steps after
it, and you get a straight line — `next` is a single string, no branch nodes exist,
and **every contact runs every one of those steps regardless of the condition.** It
deploys with a 200 and looks plausible in a JSON dump. This is the shape a naive
linker produces, and it is why `deploy_workflow.py` refuses a spec with steps after a
branch instead of compiling it.

Author it as nested paths and let the tool build the three nodes:

```json
{"type": "if_else", "name": "Watched the replay?",
 "attributes": { /* branches[] with a real condition, as above */ },
 "then": [ /* steps for the matched path */ ],
 "else": [ /* steps for the fall-through */ ]}
```

**Branches do not rejoin.** The only way back to a shared path is a `goto` pointing at
a step id in the same workflow.

### `add_contact_tag` / `remove_contact_tag`

```json
{ "type": "add_contact_tag", "cat": "actions", "name": "Tag: registered",
  "attributes": { "tags": ["registered"] } }
```

### `remove_from_workflow`

```json
{ "type": "remove_from_workflow", "cat": "actions", "name": "Remove from WF1",
  "attributes": { "type": "remove_from_workflow", "workflow_id": "<real workflow id>" } }
```

### `add_to_workflow`

```json
{ "type": "add_to_workflow", "cat": "actions", "name": "Add to onboarding",
  "attributes": { "type": "add_to_workflow", "workflow_id": "<real workflow id>",
                  "input_trigger_params": false } }
```

Same empty-id trap as `remove_from_workflow`: blank id, 200 response, nobody enrolled.

### `remove_from_all_workflows`

```json
{ "type": "remove_from_all_workflows", "cat": "actions",
  "attributes": { "type": "remove_from_all_workflows", "includeCurrent": false } }
```

`includeCurrent: false` keeps the workflow running this step alive, so steps after it
still execute. The blunt instrument for purchase suppression.

### `goto`

```json
{ "type": "goto", "cat": "actions",
  "attributes": { "type": "goto", "targetNodeId": "<id of a step in THIS workflow>" } }
```

The only way two branches rejoin. Nothing server-side checks that the target exists.

### `create_opportunity`

```json
{ "type": "create_opportunity", "cat": "actions",
  "attributes": {
    "type": "create_opportunity",
    "opportunity_name": "{{contact.first_name}} — <label>",
    "pipeline_id":       "<pipeline id>",
    "pipeline_stage_id": "<stage id>",
    "opportunity_source": "Form Submission",
    "monetary_value": 0, "fields": [], "allow_backward": false } }
```

Both ids are required and neither is discoverable from the workflow API — read them
from the pipelines API or the builder URL.

### `sms`

```json
{ "type": "sms", "cat": "actions",
  "attributes": { "body": "<text, merge tags allowed>", "attachments": [] } }
```

Note the asymmetry with `email`: **there is no template pointer.** SMS copy lives in
the step itself, so it is not swappable without redeploying the workflow.

### `add_notes`

```json
{ "type": "add_notes", "cat": "actions",
  "attributes": { "type": "add_notes", "html": "<note text, merge tags allowed>" } }
```

### `internal_notification`

Notifies a **team member**, not the contact.

```json
{ "type": "internal_notification", "cat": "actions",
  "attributes": { "type": "email",
    "email": { "to": "<address>", "subject": "<subject>", "body": "<body>" } } }
```

The SMS form uses `"type": "sms"` with an `"sms": {"to", "body"}` object instead.

### `update_contact_field`

```json
{ "type": "update_contact_field", "cat": "actions",
  "attributes": { "type": "update_contact_field", "actionType": "update_field_data",
    "fields": [ { "field_id": "<custom field id>", "value": "<value>" } ] } }
```

A per-**contact** custom FIELD. Not the same thing as a per-account custom VALUE.

### `dnd_contact`

```json
{ "type": "dnd_contact", "cat": "actions",
  "attributes": { "type": "dnd_contact", "dnd_contact": "enable" } }
```

`"enable"` turns Do Not Disturb ON (suppressing outbound); `"disable"` turns it off.

### `facebook_conversion_api`

```json
{ "type": "facebook_conversion_api", "cat": "actions",
  "attributes": { "type": "facebook_conversion_api", "event_name": "Lead",
    "pixel_id": "{{custom_values.pixel_id}}",
    "access_token": "{{custom_values.access_token}}",
    "currency": "USD", "value": 0, "test_event_code": "" } }
```

### `task-notification`

```json
{ "type": "task-notification", "cat": "actions",
  "attributes": { "type": "task-notification", "title": "<title>", "body": "<body>",
    "dueDate": "<date>", "assignedTo": "<user id>", "__customInputs__": {} } }
```

### `transition` — wait-for-reply

```json
{ "type": "transition", "attributes": { "type": "wait_reply",
    "description": "What happens when a contact replies" } }
```

### Frequency, and what that implies

Counted across 41 workflows in one mature production account (359 action steps).
Useful as a prior for what a real automation is actually made of:

| count | type | | count | type |
|---:|---|---|---:|---|
| 106 | `wait` | | 10 | `internal_notification` |
| 76 | `sms` | | 7 | `goto` |
| 39 | `email` | | 6 | `transition` |
| 34 | `if_else` | | 6 | `add_to_workflow` |
| 17 | `add_contact_tag` | | 4 | `remove_contact_tag` |
| 16 | `create_opportunity` | | 4 | `remove_from_all_workflows` |
| 16 | `add_notes` | | 2 | `event_start_date` |
| 10 | `remove_from_workflow` | | 1 each | `dnd_contact`, `manual-call`, `facebook_conversion_api`, `update_contact_field`, `task-notification` |

Twenty types is the whole vocabulary. If your design needs something outside this
list, you are probably designing an action GHL does not have.

**Verification status.** The shapes above were read off captured production
definitions. `email`, `wait` (both forms), `event_start_date`, `if_else`,
`add_contact_tag`, `remove_contact_tag` and `remove_from_workflow` were additionally
**deployed and read back**. The rest are **UNVERIFIED by round-trip** — the schema is
observed, but this repo has not itself deployed one and read it back.

---

## 5. ⚠ Things that DEPLOY SUCCESSFULLY and silently do nothing

**This is the section that will save you.** The internal API validates *shape*, not
*meaning*. Both of these return success, appear in the builder, and are completely
inert:

### Empty `workflow_id: ""`

```json
{"type": "remove_from_workflow", "attributes": {"workflow_id": ""}}   // deploys. inert.
```

Sibling exclusion silently does not happen, and a contact can sit in the "attended"
AND the "did not attend" branch at once — which is precisely the defect the
multi-workflow architecture exists to prevent.

**Cold-start problem:** `remove_from_workflow` needs real sibling ids, which do not
exist until the workflows do. **Deploy once to mint the ids, then run again to wire
them.** Make your builder *raise* rather than emit an empty id:

```python
def leave(workflow_name, wid):
    if not wid:
        raise ValueError(
            f"remove_from_workflow needs a real id for {workflow_name!r}. "
            "On a cold start, deploy once to mint ids, then run again to wire them.")
    return step("remove_from_workflow", f"Remove from {workflow_name}",
                {"type": "remove_from_workflow", "workflow_id": wid})
```

### Empty `segments: []`

An `if_else` with no segments compiles, deploys happily, and **never evaluates** —
every contact falls through the none-branch forever. It has to carry a real condition
to be worth anything.

### A condition node with no branch nodes

Covered in §4: the "branch" becomes a straight line and every contact runs both paths.
Deploys with a 200.

### A tag condition whose tag has no PRODUCER

The condition is well-formed, the branch nodes exist, the deploy is clean — and the
branch is still dead, because nothing in the account ever applies the tag it reads. On
a real build **four of five load-bearing tags had no producer**, which made a
structurally perfect campaign functionally inert past its first stage. No structural
check can catch this: it is a fact about the *rest of the account*, not the workflow.
Write the producer/consumer table (§6) before you build.

### The internal host does not validate bodies at all

```
POST backend…/workflow/{locationId}   with body {}
  → 200, and it CREATES A NAMELESS WORKFLOW in the account.
```

Elsewhere in GHL, posting an empty body is a legitimate way to make the API tell you
its schema — the `422` names the offending field. **That technique is unsafe here.**
This host does not validate, so the probe is not a question, it is a write. Never
probe `backend.leadconnectorhq.com` with an empty body; you will litter the account
with untitled workflows. See `methodology/discovery.md`.

### The general rule

Anything that references another object by id (`workflow_id`, `template_id`,
`targetNodeId`, `pipeline_id`, a tag name) can be **structurally valid and
semantically empty**. Add a post-deploy read-back that asserts every referenced id is
non-empty and resolves. In production this read-back is what confirmed "7/6/6/3 steps
stored, 9 email actions, every `template_id` valid" — and it is the only reason those
numbers were trustworthy.

**All of the above are checked for you.** `deploy_workflow.py` lints every spec before
it writes and refuses to deploy on an error:

```
$ python3 deploy_workflow.py --spec my-workflows.json
  ERROR  WF2 / Remove from WF1: workflow_id is empty. THIS DEPLOYS FINE AND DOES
         NOTHING — sibling exclusion silently never happens.
  ERROR  WF2 / Watched?: branch has segments: [] — deploys, matches nothing,
         every contact falls through
  WARN   WF2 / Watched?: condition reads tag 'watched-replay' but nothing in this
         spec produces it.
  lint: 2 error(s), 1 warning(s)
```

---

## 6. Architecture: several workflows, not one branching tree

Split a multi-stage campaign into **separate workflows per lifecycle stage** rather
than one giant branching tree, and have each one remove the contact from its siblings
on entry.

```
WF1 · Registered        trigger: registration form submitted
     ├ add_contact_tag "registered"
     ├ event_start_date  ← {{custom_values.event_datetime_iso}}
     ├ E1  confirmation                       immediately
     ├ wait_before(1440)  →  E2               T−24h
     └ wait_before(180)   →  E3               T−3h

WF2 · Did not attend    trigger: tag "did-not-attend" added
     ├ remove_from_workflow WF1
     ├ E4  replay ready                       immediately
     ├ wait 24h → if_else: replay watched?
     │      ├ Yes → E7
     │      └ No  → E8
     └ wait 24h → E6

WF3 · Attended          trigger: tag "attended" added
     ├ remove_from_workflow WF1
     ├ remove_from_workflow WF2
     └ wait 2h → E5

WF4 · Closing           trigger: tag "registered" added
     └ wait 48h → if_else: purchased? → No → E9
```

**Why:** each workflow stays readable, a tag does the routing, and exclusivity is
explicit. The failure this prevents was observed live — a funnel that shipped **three
contradictory emails to one person inside six minutes** because its conditions
overlapped.

**Purchase suppresses everything** — either a `remove_from_all_workflows` on the
purchase trigger, or a purchased-tag check before each send.

### Match each email to the state its copy asserts

An email whose copy says "you watched the replay" belongs in the *did-not-attend →
watched* branch, not in the *attended* branch. Someone who sat through the live
session never watched a replay, and telling them they did is the same
contradictory-premise bug in a subtler costume. **Audit every step against the claim
its copy makes about the contact's state.**

### Tags are a dependency graph — inventory the producers

Every tag your workflows *consume* needs something that *produces* it. In production
this was the single biggest gap:

| tag | consumed by | producer |
|---|---|---|
| `registered` | WF1, WF4 trigger | WF1 itself ✅ |
| `did-not-attend` | WF2 trigger | external platform ❌ none |
| `attended` | WF3 trigger | external platform ❌ none |
| `watched-replay` | WF2 branch | ❌ none |
| `purchased` | WF4 branch | ❌ none |

Four load-bearing tags, one known producer. Until something applies them, every
`if_else` evaluates false and every contact takes the none-branch — a structurally
complete, functionally inert campaign.

**Do this inventory before you build, not after.** Write the table.

### GHL auto-creates contacts

Any channel interaction — form submit, SMS, email, call, chat — creates the contact
automatically. **Never add a "Create Contact" action to a workflow.** Workflows always
start from "contact exists".

---

## 7. What is still manual after deploy

Both of these have **no API** and require browser automation. "Manual" means
*browser*, not *human* — each has a tool:

1. **Trigger configuration** — `tools/configure_trigger.py`. The `trigger` field in
   your local build spec is documentation for the browser step; the API never
   consumes it. A workflow with no trigger has no way in, and nothing flags it.
2. **Publish (Draft → Published)** — `tools/publish_workflow.py`. Workflows deploy in
   **Draft** and do nothing until published. `--all` publishes exactly the drafts.

**Neither tool's browser path has been run against a live account yet.** Both were
built from the verified production pattern and checked offline only. Dry-run first
(that is the default in both), read the result, and do not report a build as finished
on the strength of an exit code you have not watched.

**Detect publish state via `aria-checked` on the `[role="switch"]` element — never via
`body.innerText.includes('Draft')`.** The word "Draft" appears elsewhere in the
builder chrome and returns a false positive. And **click Save after toggling**: the
toggle sets local Vue state only, so navigating away discards it without an error.

---

## 8. Deploy checklist

0. Start from `tools/workflow-spec.starter.json` rather than a blank file. It is a
   complete four-workflow lifecycle campaign covering 16 action types, with the
   traps annotated inline.
1. Push email templates first; record their ids (`email-templates.md`).
2. Create/verify every custom value the workflows reference — especially the event
   anchor (`custom-values.md`).
3. Write the tag producer/consumer table. Fix the gaps or accept them explicitly.
4. Capture a fresh `token-id` (~60 min life).
5. **Lint before you write:** `deploy_workflow.py --spec <file>` with no `--deploy`.
   Zero errors, and no placeholder left in any id.
6. **Cold start:** deploy once to mint workflow ids, then re-run to wire
   `remove_from_workflow` / `add_to_workflow`.
7. `PUT` each workflow; success == response contains `_id`.
8. **Read every workflow back** and assert: step count, action types, every
   `template_id` non-empty and valid, every `workflow_id` non-empty, every `if_else`
   carries at least one condition **and has its two branch nodes**, every anchored
   wait has a populated `appointmentStartAfter` (not just `startAfter`), and every
   `next`/`parentKey`/`targetNodeId` resolves to a step that exists.
8. Configure triggers: `configure_trigger.py --workflow "<name>" --trigger "<type>"`,
   then again with `--apply`. It verifies by re-reading the canvas.
9. Publish: `publish_workflow.py --all --apply --verify`. Verified via `aria-checked`
   on a fresh page load — never via page text.
10. Confirm the event anchor custom value holds a real, parseable datetime. It is the
    one value that silently disables half the sequence.
