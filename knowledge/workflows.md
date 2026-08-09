# GoHighLevel Workflows — The Internal API and the Real Action Schemas

**Audience:** an agent that has never touched GoHighLevel (GHL). Everything marked
"verified" was observed in production against a live sub-account. Anything not
verified is labelled **UNVERIFIED** inline.

**Scope warning up front.** There is no public API for creating workflows, and the
internal one only covers the *body* of a workflow. **Triggers and publishing have no
API at all** — they are browser-only. Plan for that before you promise automation.

---

## 1. What has an API and what does not

| Capability | Path |
|---|---|
| Create a workflow shell | `POST backend.leadconnectorhq.com/workflow/{locationId}` — **internal API, verified** |
| Write the workflow body (steps) | `PUT backend.leadconnectorhq.com/workflow/{locationId}/{workflowId}` — **internal API, verified** |
| Read a workflow back | `GET backend.leadconnectorhq.com/workflow/{locationId}/{workflowId}` — verified |
| **Configure the trigger** | **NO API.** Browser automation only. |
| **Publish (Draft → Published)** | **NO API.** Browser automation only. |
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

`templates` is an **ordered array that is also a linked list**. Each step carries:

- `order` — its integer index,
- `next` — the `id` of the following step, or `null` at the end,
- `parentKey` — the id of the branch or step it hangs off (branch children hang off
  the `if_else` step's branch ids).

Linking helper:

```python
def link(steps):
    for i, s in enumerate(steps):
        s["order"] = i
        s["next"] = steps[i + 1]["id"] if i + 1 < len(steps) else None
    return steps
```

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
the tag list as `conditionValue`. `noneBranchName` is the fall-through.

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

### Other types available

```
remove_from_all_workflows · add_to_workflow · goto · create_opportunity
transition · add_notes · internal_notification · update_contact_field
sms · dnd_contact · manual-call · task-notification · facebook_conversion_api
```

**UNVERIFIED:** these type names were enumerated from captured definitions; only
`email`, `wait`, `event_start_date`, `if_else`, `add_contact_tag`,
`remove_contact_tag` and `remove_from_workflow` were deployed and read back.

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

### The general rule

Anything that references another object by id (`workflow_id`, `template_id`,
`popupId`, a tag name) can be **structurally valid and semantically empty**. Add a
post-deploy read-back that asserts every referenced id is non-empty and resolves. In
production this read-back is what confirmed "7/6/6/3 steps stored, 9 email actions,
every `template_id` valid" — and it is the only reason those numbers were trustworthy.

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

Both of these have **no API** and require browser automation:

1. **Trigger configuration.** The `trigger` field in your local build spec is
   documentation for a human/browser step, not something the API consumes.
2. **Publish (Draft → Published).** Workflows deploy in **Draft** and do nothing until
   published.

**Detect publish state via `aria-checked` on the `[role="switch"]` element — never via
`body.innerText.includes('Draft')`.** The word "Draft" appears elsewhere in the
builder chrome and returns a false positive.

---

## 8. Deploy checklist

1. Push email templates first; record their ids (`email-templates.md`).
2. Create/verify every custom value the workflows reference — especially the event
   anchor (`custom-values.md`).
3. Write the tag producer/consumer table. Fix the gaps or accept them explicitly.
4. Capture a fresh `token-id` (~60 min life).
5. **Cold start:** deploy once to mint workflow ids, then re-run to wire
   `remove_from_workflow`.
6. `PUT` each workflow; success == response contains `_id`.
7. **Read every workflow back** and assert: step count, action types, every
   `template_id` non-empty and valid, every `workflow_id` non-empty, every `if_else`
   carries at least one condition, every anchored wait has a populated
   `appointmentStartAfter` (not just `startAfter`).
8. Configure triggers in the browser.
9. Publish in the browser. Verify via `aria-checked`.
10. Confirm the event anchor custom value holds a real, parseable datetime. It is the
    one value that silently disables half the sequence.
