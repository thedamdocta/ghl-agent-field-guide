---
name: ghl-empty-references-deploy-and-do-nothing
description: Workflow steps with workflow_id empty and conditions with segments empty deploy successfully, appear in the builder, and are completely inert.
metadata:
  type: reference
---

The internal API validates *shape*, not *meaning*. Both of these return success, are
stored, and do nothing:

- `{"type": "remove_from_workflow", "attributes": {"workflow_id": ""}}` — sibling exclusion
  silently never happens, so a contact can sit in the "attended" **and** the "did not
  attend" branch at once, which is precisely the defect the multi-workflow architecture
  exists to prevent.
- An `if_else` with `segments: []` compiles, deploys, and **never evaluates** — every
  contact falls through the none-branch forever.

In one deployment the written spec asserted "every branch is mutually exclusive" while the
field that would have enforced it was an empty array.

**Cold-start problem:** `remove_from_workflow` needs real sibling ids, which do not exist
until the workflows do. Deploy once to mint ids, then run again to wire them — and **make
your builder raise rather than emit an empty id.** That change was more durable than any
checklist item.

**The general rule:** anything that references another object by id — `workflow_id`,
`template_id`, `targetNodeId`, `pipeline_id`, a tag name — can be structurally valid and
semantically empty. Grep the generated payload for `""`, `[]`, `null` in every reference
field, and add a post-deploy read-back that asserts each one resolves.

See [[ghl-existence-is-not-wiring]], [[ghl-if-else-is-three-nodes]].
