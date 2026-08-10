#!/usr/bin/env python3
"""
deploy_workflow.py — create and update GHL workflows through the internal API.

WHY THIS EXISTS
---------------
GHL's public API has no `create-workflow`. Search the MCP catalogue and you will
find read operations and contact-membership operations only (`get-workflow`,
`add-contact-to-workflow`, `delete-contact-from-workflow`, ...). That absence
makes it look like workflows must be hand-built in the UI.

They do not. The builder's own internal API has full CRUD:

    POST https://backend.leadconnectorhq.com/workflow/<locationId>
         {"name": "..."}                       -> mints an empty workflow, returns id
    GET  https://backend.leadconnectorhq.com/workflow/<locationId>/<workflowId>
         -> current record, including `version`
    PUT  https://backend.leadconnectorhq.com/workflow/<locationId>/<workflowId>
         {"name":..., "workflowData": {"templates": [...steps...]}, "version": n}

Two-step by necessity: POST mints the id, PUT installs the steps. There is no
single call that does both.

AUTH — SETTLED BY TESTING BOTH FORMS AGAINST THE LIVE API
-----------------------------------------------------------
`Authorization: Bearer <token>` returns "Unauthorized" here, for the PIT AND for
the browser JWT. The internal API wants the **`token-id` header** — the same
header funnel autosave uses. Run `get_token.py` first.

NAMING TRAP: `workflowData.templates` is the list of STEPS. It has nothing to do
with email templates. An email step REFERENCES an email template by id, which is
a different thing entirely, and is why templates must exist before you deploy a
workflow that sends them (see `ghl_mcp.py` for creating them).

WHAT THIS TOOL DOES NOT DO
--------------------------
It installs steps. It does NOT configure triggers or publish. Those remain UI
steps at time of writing. A deployed workflow with no trigger is inert and will
not run — do not report a deploy as finished until the trigger is set and the
workflow is published.

STEP SCHEMAS — READ THESE BEFORE AUTHORING A SPEC
--------------------------------------------------
The factory functions below carry schemas read off real, working automations
rather than guessed. Each docstring records a failure that the schema prevents.
`--emit-example` prints a runnable skeleton using them.

USAGE
-----
    python3 deploy_workflow.py --emit-example > workflows.json
    python3 deploy_workflow.py --spec workflows.json               # validate only
    python3 deploy_workflow.py --spec workflows.json --deploy      # write

    # ids of previously deployed workflows are remembered here:
    python3 deploy_workflow.py --spec workflows.json --deploy \
        --state .workflows-deployed.json

Default is validate-and-print. Nothing is written without `--deploy`.

SPEC FORMAT
-----------
A JSON list. Each entry:

    {
      "name": "Whatever you want to call it",
      "trigger": "free-text note to yourself; NOT deployed, triggers are UI-only",
      "steps": [ <step objects>, ... ]
    }

`{"workflowData": {"templates": [...]}}` is accepted in place of `steps` so a
record pulled straight from GHL can be round-tripped. Step `id`, `order`,
`next` and `parentKey` are filled in automatically.

BRANCHING — the part that is easy to get silently wrong
--------------------------------------------------------
An `if_else` step may carry `then` and `else` (aliases: `yes` / `no`), each a
nested list of steps:

    {"type": "if_else", "name": "Watched?", "attributes": {...},
     "then": [ ...steps run when the condition matches... ],
     "else": [ ...steps run when it does not... ]}

This compiles to the THREE-node shape real GHL workflows use — a condition node
plus a `branch-yes` and a `branch-no` node, with each path's steps hanging off
its branch node. Listing steps AFTER an if_else instead of inside `then`/`else`
produces a straight line in which every contact runs them regardless of the
condition; the compiler refuses that rather than deploying it.

`tools/workflow-spec.starter.json` is a complete four-workflow lifecycle spec in
this format, ready to edit.

LINTING
-------
Every spec is linted before deploy for the failures that RETURN 200 AND DO
NOTHING: empty `workflow_id`, empty `template_id`, `branches: []`,
`segments: []`, a blank event anchor, a `goto` to a nonexistent step, a dangling
`next`/`parentKey`, and tag conditions whose tag has no producer anywhere in the
spec. Errors block `--deploy`.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import uuid

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import ghl_ids  # noqa: E402  (sibling module; the path fix above must run first)

INTERNAL_API = "https://backend.leadconnectorhq.com/workflow"

# Values that are obviously stand-ins. They are warnings during validation and
# hard blockers at --deploy time: deploying one produces a step that points at
# nothing, which the API accepts and which then silently does nothing.
PLACEHOLDER_RE = re.compile(r"REPLACE_ME|REPLACE_WITH|^<.+>$|PUT_.*_HERE", re.I)

# Cloudflare 403s the default Python UA on GHL hosts. curl, browser UA.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


# ── step factories ───────────────────────────────────────────────────────────
# Importable: `from deploy_workflow import email_step, wait_before, ...`

def step(type_: str, name: str, attributes: dict, cat: str = "actions",
         **extra) -> dict:
    """Base shape every step shares: id, name, type, cat, attributes."""
    return {"id": str(uuid.uuid4()), "name": name, "type": type_, "cat": cat,
            "attributes": attributes, **extra}


def email_step(template_id: str, name: str, subject: str,
               from_email: str, from_name: str) -> dict:
    """Send a saved email template.

    `template_id` + `templatesource: "email-builder"` is the join between a
    workflow step and a saved template. This is why templates must be created
    FIRST — the step is a pointer, and a pointer to nothing sends nothing.

    from_email / from_name are good candidates for custom values
    (e.g. "{{custom_values.support_email}}") so one edit changes every workflow.
    """
    if not template_id:
        raise ValueError(
            f"email step {name!r} has no template_id. Create the template first "
            f"(ghl_mcp.py execute create-email-template) and pass its id.")
    return step("email", name, {
        "subject": subject,
        "template_id": template_id,
        "templatesource": "email-builder",
        "from_email": from_email,
        "from_name": from_name,
        "attachments": [],
    })


def wait(value: int, unit: str = "hours", when: str = "after",
         label=None) -> dict:
    """An ELAPSED wait — counts forward from the moment the contact arrives here.

    Correct whenever "now" and "the event" are the same instant: e.g. a branch
    entered by a tag applied right after something happened.
    """
    return step("wait", label or f"wait {value} {unit}", {
        "type": "time",
        "startAfter": {"when": when, "type": unit, "value": value},
        "windowCondition": {"field": "", "operator": "", "value": ""},
    }, cat="conditions")


def wait_before(minutes: int, label: str, days: int = 0, hours: int = 0) -> dict:
    """An EVENT-ANCHORED wait — counts BACKWARD from the event_start_date anchor.

    A completely different shape from an elapsed wait: `type: "appointment"` with
    `appointmentStartAfter.when: "before"`, value in MINUTES.

    WHY IT MATTERS. Elapsed waits cannot express "3 hours before the event".
    Someone who signs up at T-35h and then waits 24h lands at T-11h; chain another
    21h and the "we begin in three hours" message arrives ten hours AFTER the
    event ended. Every registrant enters at a different offset, so only a
    backward-counted anchor is correct.

    `appointmentCondition: "skip"` is the other half. If someone registers ninety
    minutes before the event, the T-24h and T-3h messages are SKIPPED rather than
    fired late. That one field is the difference between a sequence that adapts to
    late signups and one that apologises for a no-show before the event has
    started. (Yes, that is a real defect observed in a live funnel.)
    """
    return step("wait", label, {
        "type": "appointment",
        "appointmentStartAfter": {
            "when": "before", "type": "minutes", "value": minutes,
            "distributed": {"months": 0, "days": days, "hours": hours,
                            "minutes": 0},
        },
        "appointmentCondition": "skip",
    }, cat="conditions")


def event_anchor(custom_value: str, name: str = "Event Start Date") -> dict:
    """Set the clock for the whole sequence from a custom value holding an ISO date.

    Without this step a backward-counted wait cannot exist — you can only count
    forward from enrolment. Place it near the top, before any wait_before().

    `custom_value` is something like "{{ custom_values.your_event_datetime_iso }}".
    Create that custom value first, and give it a real value: GHL resolves an
    unknown {{custom_values.x}} to an EMPTY STRING, silently.
    """
    if not custom_value:
        raise ValueError("event_anchor needs a custom value reference, e.g. "
                         "'{{ custom_values.event_datetime_iso }}'")
    return step("event_start_date", name, {
        "type": "event_start_date",
        "event_start_type": "custom_field",
        "value": custom_value,
    })


def tag_step(tags: list, add: bool = True) -> dict:
    """Add or remove contact tags."""
    return step("add_contact_tag" if add else "remove_contact_tag",
                ("Tag: " if add else "Untag: ") + ", ".join(tags),
                {"tags": tags})


def leave_workflow(workflow_name: str, workflow_id) -> dict:
    """Sibling exclusion — what makes parallel branches mutually exclusive.

    `workflow_id` MUST be a real id. Left empty, the step deploys happily, is
    inert, the exclusion silently does not happen, and one contact can sit in two
    contradictory branches at once — which is usually the exact defect this
    architecture exists to prevent.

    Cold-start ordering: deploy once to mint ids, then run again so the ids can be
    wired in. That is what --state exists for.
    """
    if not workflow_id:
        raise ValueError(
            f"remove_from_workflow needs a real id for {workflow_name!r}. "
            f"On a cold start, deploy once to mint ids, then run again to wire "
            f"them (the --state file carries them between runs).")
    return step("remove_from_workflow", f"Remove from {workflow_name}",
                {"type": "remove_from_workflow", "workflow_id": workflow_id})


def join_workflow(workflow_name: str, workflow_id, input_trigger_params: bool = False
                  ) -> dict:
    """Enrol the contact into another workflow. Same empty-id trap as leave_workflow."""
    if not workflow_id:
        raise ValueError(
            f"add_to_workflow needs a real id for {workflow_name!r}. An empty "
            f"workflow_id deploys successfully and enrols nobody.")
    return step("add_to_workflow", f"Add to {workflow_name}",
                {"type": "add_to_workflow", "workflow_id": workflow_id,
                 "input_trigger_params": input_trigger_params})


def leave_all_workflows(include_current: bool = False,
                        name: str = "Remove from all workflows") -> dict:
    """The blunt suppression instrument — e.g. on a purchase trigger.

    `includeCurrent: False` keeps the workflow that is running this step alive, so
    the steps after it still execute. Set True to stop everything including self.
    """
    return step("remove_from_all_workflows", name,
                {"type": "remove_from_all_workflows",
                 "includeCurrent": include_current})


def sms_step(body: str, name: str = "SMS") -> dict:
    """Send an SMS. Note the schema is just body + attachments — there is no
    template pointer, unlike `email`. The copy lives in the step itself."""
    if not body:
        raise ValueError("sms step needs a body; an empty body sends an empty text.")
    return step("sms", name, {"body": body, "attachments": []})


def add_note(html: str, name: str = "Add note") -> dict:
    """Append a note to the contact record. `html` accepts merge tags."""
    return step("add_notes", name, {"type": "add_notes", "html": html})


def notify_internal(to: str, subject: str, body: str,
                    name: str = "Notify the team") -> dict:
    """Email a team member (NOT the contact). Use `channel="sms"` shape for SMS."""
    return step("internal_notification", name,
                {"type": "email",
                 "email": {"to": to, "subject": subject, "body": body}})


def create_opportunity(opportunity_name: str, pipeline_id: str,
                       pipeline_stage_id: str, source: str = "Workflow",
                       monetary_value: int = 0,
                       name: str = "Create opportunity") -> dict:
    """Create a pipeline opportunity.

    Both ids are REQUIRED and are not discoverable from this tool — read them from
    the pipelines API or the builder URL. An empty pipeline id is another
    deploys-fine-does-nothing step.
    """
    for label, value in (("pipeline_id", pipeline_id),
                         ("pipeline_stage_id", pipeline_stage_id)):
        if not value:
            raise ValueError(
                f"create_opportunity needs a real {label}. Look it up first — an "
                f"empty one deploys successfully and creates no opportunity.")
    return step("create_opportunity", name, {
        "type": "create_opportunity",
        "opportunity_name": opportunity_name,
        "pipeline_id": pipeline_id,
        "pipeline_stage_id": pipeline_stage_id,
        "opportunity_source": source,
        "monetary_value": monetary_value,
        "fields": [],
        "allow_backward": False,
    })


def update_field(field_id: str, value: str, name: str = "Update field") -> dict:
    """Write a contact custom FIELD (per-contact) — not a custom VALUE (per-account)."""
    return step("update_contact_field", name, {
        "type": "update_contact_field",
        "actionType": "update_field_data",
        "fields": [{"field_id": field_id, "value": value}],
    })


def set_dnd(enable: bool = True, name: str = "Do not disturb") -> dict:
    return step("dnd_contact", name,
                {"type": "dnd_contact",
                 "dnd_contact": "enable" if enable else "disable"})


def goto(target_step_id: str, name: str = "Go to") -> dict:
    """Jump to another step by id — the only way two branches rejoin.

    `targetNodeId` must be the id of a step that exists in THIS workflow. The
    linter checks that; the API does not.
    """
    if not target_step_id:
        raise ValueError("goto needs a targetNodeId — the id of a step in this "
                         "same workflow.")
    return step("goto", name, {"type": "goto", "targetNodeId": target_step_id})


def branch_on_tag(name: str, tag_name: str, yes_name: str,
                  no_name: str) -> dict:
    """An if/else on a contact tag.

    An if_else with `segments: []` compiles, deploys, and then NEVER EVALUATES —
    every contact falls through the none-branch and the branch is decorative. It
    has to carry a real condition.

    Schema: `contact_detail` / `tags` / `index-of-true`, with the tag list as the
    condition value.
    """
    return step("if_else", name, {
        "branches": [{
            "id": str(uuid.uuid4()), "name": yes_name, "operator": "and",
            "showErrors": False,
            "segments": [{
                "__segmentId": str(uuid.uuid4()), "operator": "and",
                "conditions": [{
                    "conditionType": "contact_detail",
                    "conditionSubType": "tags",
                    "conditionOperator": "index-of-true",
                    "conditionValue": [tag_name],
                    "__conditionId": str(uuid.uuid4()),
                    "isWait": False,
                }],
            }],
        }],
        "operator": "and", "if": True, "conditionName": name,
        "version": 2, "noneBranchName": no_name,
    }, cat="conditions", nodeType="condition-node", comments=[])


def branch(name: str, tag_name: str, yes_name: str, no_name: str,
           then: list, otherwise: list) -> dict:
    """A COMPLETE tag branch: the condition plus both paths.

    Prefer this over calling branch_on_tag() and then listing steps after it. A
    condition node followed by ordinary steps is a straight line, not a branch —
    every contact runs those steps whatever the condition said. See compile_steps().
    """
    node = branch_on_tag(name, tag_name, yes_name, no_name)
    node["then"] = then
    node["else"] = otherwise
    return node


# ── the linked list, and the three-node shape of a branch ────────────────────
#
# `workflowData.templates` is a FLAT array that encodes a TREE. Read off 34
# captured production workflow definitions (393 steps):
#
#   * `next`      — id of the following step. A STRING normally; a LIST on a
#                   condition node, holding its branch-node ids. (329 string,
#                   13 list, 51 null.)
#   * `parentKey` — id of the node this one hangs off: the PREVIOUS step in the
#                   chain, or the branch node when this is first inside a branch.
#                   Present on every step except the first (331/393).
#   * `order`     — a sequence hint, NOT an index into the array. Sibling branch
#                   nodes share one value and branch children restart. The
#                   `next`/`parentKey` pointers are what actually carry structure;
#                   **UNVERIFIED** whether the builder reads `order` at all.
#
# An `if_else` is THREE nodes, not one:
#
#   1. condition-node  carries attributes.branches[] (the real conditions);
#                      `next` is [yes_node_id, no_node_id]
#   2. branch-yes      its `id` MUST EQUAL attributes.branches[0].id  (14/14 in
#                      the corpus); attributes {"if": false, "branches": []}
#   3. branch-no       the fall-through; attributes {"else": true}
#
# The steps of each path hang off the BRANCH node (parentKey = branch node id),
# never off the condition node. Emitting only the condition node — which is what
# a naive flat linker does — produces a workflow whose "branch" is a straight
# line: both paths run for everybody.

def _compile(steps: list, parent_key, out: list) -> str | None:
    """Flatten one chain into `out`. Returns the id of its first step."""
    head = None
    prev = None            # the previous step object in this chain
    hang_from = parent_key  # what the NEXT step should record as its parentKey
    order = 0

    for raw in steps:
        if not isinstance(raw, dict) or "type" not in raw:
            raise SystemExit(f"FATAL: malformed step {json.dumps(raw)[:120]} — "
                             f"every step needs at least 'type' and 'attributes'.")
        if prev is None and hang_from is None and out and parent_key is None:
            pass  # first step of the workflow: no parentKey, by design

        # Keys starting with "_" are spec annotations (JSON has no comments) and
        # are stripped before the body is sent.
        node = {k: v for k, v in raw.items() if not k.startswith("_")}
        # `then`/`else` (aliases `yes`/`no`) are OUR spec sugar, never wire fields.
        yes_path = node.pop("then", None)
        if yes_path is None:
            yes_path = node.pop("yes", None)
        no_path = node.pop("else", None)
        if no_path is None:
            no_path = node.pop("no", None)

        node.setdefault("id", str(uuid.uuid4()))
        node.setdefault("attributes", {})
        node["order"] = order
        order += 1
        if hang_from is not None:
            node["parentKey"] = hang_from
        node.setdefault("next", None)

        if prev is not None:
            prev["next"] = node["id"]
        if head is None:
            head = node["id"]
        out.append(node)

        if node["type"] == "if_else" and (yes_path is not None or no_path is not None):
            attrs = node["attributes"]
            branches = attrs.get("branches") or []
            if not branches:
                raise SystemExit(
                    f"FATAL: if_else {node.get('name')!r} declares then/else but "
                    f"carries no conditions. An if_else with branches: [] deploys "
                    f"successfully and NEVER evaluates — every contact takes the "
                    f"fall-through. Give it a real condition.")

            node["nodeType"] = "condition-node"
            node["cat"] = node.get("cat", "conditions")
            node.setdefault("comments", [])

            # The branch-yes NODE id and attributes.branches[0].id are the same id.
            yes_id = branches[0].get("id") or str(uuid.uuid4())
            branches[0]["id"] = yes_id
            no_id = str(uuid.uuid4())

            yes_node = {
                "id": yes_id, "parent": node["id"], "parentKey": node["id"],
                "order": order, "name": branches[0].get("name") or "If Yes",
                "type": "if_else", "cat": "conditions",
                "attributes": {"if": False, "conditionName": "Condition",
                               "operator": "and", "branches": []},
                "sibling": [no_id], "comments": [], "nodeType": "branch-yes",
                "next": None,
            }
            no_node = {
                "id": no_id, "parent": node["id"], "parentKey": node["id"],
                "order": order, "name": attrs.get("noneBranchName") or "None",
                "type": "if_else", "cat": "conditions",
                "attributes": {"else": True},
                "sibling": [yes_id], "comments": [], "nodeType": "branch-no",
                "next": None,
            }
            order += 1
            node["next"] = [yes_id, no_id]
            out.append(yes_node)
            out.append(no_node)

            yes_node["next"] = _compile(yes_path or [], yes_id, out)
            no_node["next"] = _compile(no_path or [], no_id, out)

            # Paths do not rejoin. Anything listed after a branch at this level is
            # unreachable, so say so rather than silently dropping it.
            prev = None
            hang_from = None
            continue

        prev = node
        hang_from = node["id"]

    return head


def compile_steps(steps: list) -> list:
    """Compile an authored step list (which may nest via then/else) to wire format.

    Returns the flat `templates` array GHL stores.
    """
    out: list = []
    _compile(steps, None, out)
    # Guard the unreachable-tail mistake described in _compile().
    for i, s in enumerate(steps):
        is_branch = isinstance(s, dict) and (s.get("then") is not None
                                             or s.get("yes") is not None
                                             or s.get("else") is not None
                                             or s.get("no") is not None)
        if is_branch and i != len(steps) - 1:
            raise SystemExit(
                f"FATAL: step {i} ({s.get('name') or s.get('type')!r}) branches, but "
                f"{len(steps) - i - 1} more step(s) follow it at the same level. "
                f"Branch paths do not rejoin in GHL — move those steps inside "
                f"'then' and/or 'else', or rejoin them explicitly with a goto.")
    return out


def link(steps: list) -> list:
    """Flat linked list: `order` plus a `next` pointer. No branching.

    Kept for straight-line sequences and for specs written against the older
    shape. Use compile_steps() for anything containing an if_else with paths.
    """
    for s in steps:
        s.setdefault("id", str(uuid.uuid4()))
    for i, s in enumerate(steps):
        s["order"] = i
        s["next"] = steps[i + 1]["id"] if i + 1 < len(steps) else None
    return steps


# ── spec loading ─────────────────────────────────────────────────────────────

def load_spec(path: str) -> list:
    src = pathlib.Path(path).expanduser()
    if not src.is_file():
        raise SystemExit(f"FATAL: no such spec file: {src}")
    try:
        doc = json.loads(src.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FATAL: {src} is not valid JSON: {exc}")
    if isinstance(doc, dict):
        doc = [doc]
    if not isinstance(doc, list):
        raise SystemExit("FATAL: spec must be a JSON list of workflow objects "
                         "(or a single object).")

    out = []
    for i, wf in enumerate(doc):
        if not isinstance(wf, dict):
            raise SystemExit(f"FATAL: spec entry {i} is not an object.")
        name = wf.get("name")
        if not name:
            raise SystemExit(f"FATAL: spec entry {i} has no 'name'.")
        steps = wf.get("steps")
        if steps is None:
            steps = (wf.get("workflowData") or {}).get("templates")
        if not isinstance(steps, list) or not steps:
            raise SystemExit(
                f"FATAL: workflow {name!r} has no steps. Provide 'steps': [...] "
                f"or 'workflowData': {{'templates': [...]}}.")
        for j, s in enumerate(steps):
            if not isinstance(s, dict) or "type" not in s:
                raise SystemExit(
                    f"FATAL: workflow {name!r} step {j} is malformed — every step "
                    f"needs at least a 'type' and 'attributes'.")
        out.append({"name": name,
                    "trigger": wf.get("trigger", ""),
                    "steps": compile_steps(steps)})
    return out


# ── the linter: the silent failures, made loud ───────────────────────────────

def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) \
        or (isinstance(value, list) and not value)


def _placeholder(value) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_RE.search(value))


def lint(workflows: list) -> list:
    """Find steps that DEPLOY SUCCESSFULLY AND DO NOTHING.

    The internal API validates shape, not meaning. Every finding here returns 200
    from GHL, appears correctly in the builder, and is inert at runtime. This is
    the check that the read-back-after-deploy would otherwise have to catch.

    Returns a list of {level, workflow, step, message}; level is "error" or "warn".
    """
    findings = []

    # A tag condition is inert unless SOMETHING applies the tag. Collect every tag
    # produced anywhere in the spec so consumed-without-producer can be reported.
    produced = set()
    for wf in workflows:
        for s in wf["steps"]:
            if s.get("type") == "add_contact_tag":
                produced.update(s.get("attributes", {}).get("tags") or [])

    for wf in workflows:
        steps = wf["steps"]
        ids = {s["id"] for s in steps}

        def add(level, s, msg):
            findings.append({"level": level, "workflow": wf["name"],
                             "step": s.get("name") or s.get("type"), "message": msg})

        for s in steps:
            a = s.get("attributes") or {}
            t = s.get("type")

            # dangling pointers — a next/parentKey that names no step
            for key in ("next", "parentKey", "parent"):
                targets = s.get(key)
                targets = targets if isinstance(targets, list) else [targets]
                for target in targets:
                    if isinstance(target, str) and target and target not in ids:
                        add("error", s, f"{key} points at {target[:8]}… which is not "
                                        f"a step in this workflow")

            if t == "email":
                if _blank(a.get("template_id")):
                    add("error", s, "template_id is empty — the step deploys and "
                                    "sends nothing. Create the template first.")
                elif _placeholder(a.get("template_id")):
                    add("warn", s, "template_id is still a placeholder")
                if a.get("templatesource") != "email-builder":
                    add("error", s, "templatesource must be \"email-builder\"; it is "
                                    "the join to the saved template")

            elif t in ("remove_from_workflow", "add_to_workflow"):
                if _blank(a.get("workflow_id")):
                    add("error", s, "workflow_id is empty. THIS DEPLOYS FINE AND DOES "
                                    "NOTHING — sibling exclusion silently never "
                                    "happens. Deploy once to mint ids, then re-run.")
                elif _placeholder(a.get("workflow_id")):
                    add("warn", s, "workflow_id is still a placeholder")

            elif t == "event_start_date":
                if _blank(a.get("value")):
                    add("error", s, "anchor value is empty — every event-anchored "
                                    "wait downstream silently never fires")

            elif t == "goto":
                target = a.get("targetNodeId")
                if _blank(target):
                    add("error", s, "targetNodeId is empty")
                elif target not in ids:
                    add("error", s, "targetNodeId names no step in this workflow")

            elif t == "create_opportunity":
                for key in ("pipeline_id", "pipeline_stage_id"):
                    if _blank(a.get(key)):
                        add("error", s, f"{key} is empty — no opportunity is created")
                    elif _placeholder(a.get(key)):
                        add("warn", s, f"{key} is still a placeholder")

            elif t == "wait":
                if a.get("type") == "appointment":
                    start = a.get("appointmentStartAfter") or {}
                    if _blank(start.get("value")) and start.get("value") != 0:
                        add("error", s, "anchored wait has no appointmentStartAfter "
                                        "value. Note the timing does NOT live in "
                                        "startAfter for anchored waits.")
                    if start.get("type") != "minutes":
                        add("warn", s, "anchored wait value should be in MINUTES")
                    if not a.get("appointmentCondition"):
                        add("warn", s, "no appointmentCondition — set \"skip\" or a "
                                       "late entrant receives expired reminders")
                elif a.get("type") == "time":
                    if _blank((a.get("startAfter") or {}).get("value")):
                        add("error", s, "elapsed wait has no startAfter value")

            elif t == "if_else":
                if s.get("nodeType") in ("branch-yes", "branch-no"):
                    if _blank(s.get("next")):
                        add("warn", s, "branch path is empty — nothing happens on "
                                       "this side of the condition")
                    continue
                branches = a.get("branches")
                if _blank(branches):
                    add("error", s, "if_else has no branches. It deploys and NEVER "
                                    "evaluates; every contact takes the fall-through.")
                    continue
                for b in branches:
                    if _blank(b.get("segments")):
                        add("error", s, "branch has segments: [] — deploys, matches "
                                        "nothing, every contact falls through")
                        continue
                    for seg in b["segments"]:
                        for cond in seg.get("conditions") or []:
                            if _blank(cond.get("conditionValue")) \
                                    and cond.get("conditionOperator") != "has_no_value":
                                add("error", s, "a condition has an empty "
                                                "conditionValue")
                            if cond.get("conditionSubType") == "tags":
                                for tag in cond.get("conditionValue") or []:
                                    if tag not in produced:
                                        add("warn", s,
                                            f"condition reads tag {tag!r} but nothing "
                                            f"in this spec produces it. Name the "
                                            f"producer (webinar platform, link-click "
                                            f"trigger, payment) or the branch is "
                                            f"decoration.")
                if s.get("nodeType") == "condition-node" \
                        and not isinstance(s.get("next"), list):
                    add("error", s, "condition node has a single `next` instead of a "
                                    "list of branch-node ids — this is a straight "
                                    "line, not a branch. Use then/else.")

    return findings


# ── transport ────────────────────────────────────────────────────────────────

def read_token(token_arg, token_file: str) -> str:
    """--token, then $GHL_TOKEN_ID, then the token file. Fails loudly."""
    if token_arg:
        return token_arg.strip()
    env_token = os.environ.get("GHL_TOKEN_ID")
    if env_token:
        return env_token.strip()
    path = pathlib.Path(token_file).expanduser()
    if path.is_file():
        token = path.read_text().strip()
        if token:
            return token
    raise SystemExit(
        f"FATAL: no internal token.\n"
        f"  fix: python3 get_token.py --location-id <id>   (writes {token_file})\n"
        f"  or:  --token 'eyJ...'  or  export GHL_TOKEN_ID='eyJ...'\n"
        f"  the PIT does NOT work against the internal workflow API.")


def api(method: str, url: str, token: str, body=None) -> dict:
    """One internal-API call.

    `token-id` header, not Bearer — Bearer returns "Unauthorized" here for every
    token type. curl, not urllib — Cloudflare 403s the default Python UA.
    """
    cmd = ["curl", "-sS", "--max-time", "60", "-X", method, url,
           "-H", f"token-id: {token}",
           "-H", "Content-Type: application/json",
           "-H", "channel: APP",
           "-H", "source: WEB_USER",
           "-H", "Version: 2021-07-28",
           "-A", USER_AGENT]
    if body is not None:
        cmd += ["-d", json.dumps(body)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"FATAL: curl failed (exit {proc.returncode}): "
                         f"{proc.stderr.strip()[:300]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"_raw": proc.stdout[:400]}


def deploy(location_id: str, token: str, workflows: list, state: dict) -> list:
    """Create-or-update each workflow.

    Idempotent through the state file: the internal API happily creates a second
    workflow with the same name, so without remembered ids a re-run litters the
    account with duplicates.
    """
    results = []
    for wf in workflows:
        name = wf["name"]
        wid = state.get(name)

        if wid:
            current = api("GET", f"{INTERNAL_API}/{location_id}/{wid}", token)
            if current.get("_raw") is not None and not current.get("version"):
                print(f"  warn: remembered id {wid} for {name!r} did not read back "
                      f"— it may have been deleted in the UI. Creating a new one.",
                      file=sys.stderr)
                wid = None
            else:
                # PUT must echo the CURRENT version; a stale one loses the write.
                version, verb = current.get("version", 1), "updated"

        if not wid:
            created = api("POST", f"{INTERNAL_API}/{location_id}", token,
                          {"name": name})
            wid = created.get("id") or created.get("_id")
            if not wid:
                print(f"  FAIL create {name!r}: {json.dumps(created)[:300]}",
                      file=sys.stderr)
                results.append({"name": name, "id": None, "ok": False,
                                "steps": len(wf["steps"]),
                                "trigger": wf["trigger"]})
                continue
            version, verb = 1, "created"

        body = {"name": name,
                "workflowData": {"templates": wf["steps"]},
                "version": version}
        res = api("PUT", f"{INTERNAL_API}/{location_id}/{wid}", token, body)
        ok = bool(res.get("_id") or res.get("id"))
        print(f"  {'OK  ' if ok else 'FAIL'} {verb:8s} {name:34s} "
              f"{len(wf['steps'])} steps  id={wid}")
        if not ok:
            print(f"       {json.dumps(res)[:300]}", file=sys.stderr)
        results.append({"name": name, "id": wid, "ok": ok,
                        "steps": len(wf["steps"]), "trigger": wf["trigger"]})
    return results


# ── example spec ─────────────────────────────────────────────────────────────

def example_spec() -> list:
    """A skeleton demonstrating every step schema. All values are placeholders.

    Deliberately generic: no real ids, tags, copy or brand. Replace the
    TEMPLATE_ID placeholders with ids returned by your own template creation, and
    the tag names with your own.
    """
    FROM_E = "{{custom_values.support_email}}"
    FROM_N = "{{custom_values.business_name}}"

    def mail(name, subject):
        return email_step("REPLACE_WITH_TEMPLATE_ID", name, subject, FROM_E, FROM_N)

    return [{
        "name": "EXAMPLE · 1 Registered",
        "trigger": "Form submitted — set this in the UI; triggers are not deployable",
        "steps": [
            tag_step(["your-registered-tag"]),
            event_anchor("{{ custom_values.your_event_datetime_iso }}"),
            mail("Confirmation", "Your seat is confirmed"),
            wait_before(1440, "1 day before the event", days=1),
            mail("Reminder T-24h", "Tomorrow"),
            wait_before(180, "3 hours before the event", hours=3),
            mail("Reminder T-3h", "We begin in three hours"),
        ],
    }, {
        "name": "EXAMPLE · 2 Did not attend",
        "trigger": "Tag added — your-no-show-tag",
        "steps": [
            # leave_workflow() is omitted until you have real ids. After the first
            # deploy, read them out of your --state file and add:
            #   leave_workflow("EXAMPLE · 1 Registered", "<id from --state>")
            mail("Replay ready", "Here is the replay"),
            wait(24, "hours"),
            # A REAL branch: the two paths hang off the branch nodes, so only one
            # of them runs. Steps listed AFTER a branch would be unreachable — put
            # them inside a path.
            branch("Watched the replay?", "your-watched-tag", "Watched",
                   "Not watched",
                   then=[
                       mail("Watched follow-up", "What is holding you up?"),
                       wait(24, "hours"),
                       mail("Last call", "The replay comes down soon"),
                   ],
                   otherwise=[
                       mail("Not watched nudge", "You have not opened it yet"),
                   ]),
        ],
    }, {
        "name": "EXAMPLE · 3 Attended",
        "trigger": "Tag added — your-attended-tag",
        "steps": [
            wait(2, "hours"),
            mail("Post-session", "Was there something I did not answer?"),
            sms_step("Thanks for joining today. Reply STOP to opt out.",
                     "Thank-you SMS"),
            add_note("Attended the live session.", "Note: attended"),
        ],
    }, {
        "name": "EXAMPLE · 4 Closing",
        "trigger": "Tag added — your-registered-tag",
        "steps": [
            wait(48, "hours", label="T+48h"),
            branch("Purchased?", "your-purchased-tag", "Purchased", "Not purchased",
                   then=[
                       leave_all_workflows(),
                       add_note("Purchased — suppressed from the sequence.",
                                "Note: purchased"),
                   ],
                   otherwise=[
                       mail("Closing", "Closing this one out"),
                       create_opportunity("{{contact.first_name}} — follow up",
                                          "REPLACE_WITH_PIPELINE_ID",
                                          "REPLACE_WITH_PIPELINE_STAGE_ID"),
                   ]),
        ],
    }]


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create/update GHL workflows via the internal API. "
                    "Validates by default; --deploy to write.",
        epilog="Needs the internal token-id from get_token.py. The PIT will not "
               "work. Triggers and publishing remain UI steps.")
    ap.add_argument("--spec", help="Path to a workflow spec JSON file.")
    ap.add_argument("--emit-example", action="store_true",
                    help="Print a skeleton spec demonstrating every step schema "
                         "and exit. Writes nothing to GHL.")
    ap.add_argument("--deploy", action="store_true",
                    help="Actually create/update in GHL. Without this, the spec is "
                         "only validated and summarised.")
    ap.add_argument("--location-id",
                    help="GHL location id. Optional — falls back to "
                         "$GHL_LOCATION_ID, then .env.")
    ap.add_argument("--env-file", default=".env",
                    help="Where to read GHL_LOCATION_ID (default .env).")
    ap.add_argument("--token", help="Internal token-id (eyJ...).")
    ap.add_argument("--token-file",
                    default=os.environ.get("GHL_TOKEN_FILE", ".jwt"),
                    help="File holding the token-id (default ./.jwt).")
    ap.add_argument("--state", default=".workflows-deployed.json",
                    help="File remembering name -> workflow id, so re-running "
                         "updates instead of duplicating "
                         "(default ./.workflows-deployed.json).")
    args = ap.parse_args()

    if args.emit_example:
        print(json.dumps(example_spec(), indent=2))
        return 0

    if not args.spec:
        ap.error("nothing to do: pass --spec <file>, or --emit-example to see the "
                 "spec format.")

    workflows = load_spec(args.spec)

    state_path = pathlib.Path(args.state).expanduser()
    state = {}
    if state_path.is_file():
        try:
            prior = json.loads(state_path.read_text())
        except json.JSONDecodeError:
            raise SystemExit(f"FATAL: {state_path} is not valid JSON. Delete it to "
                             f"start fresh (you will then create duplicates unless "
                             f"you remove the old workflows in the UI).")
        rows = prior if isinstance(prior, list) else prior.get("workflows", [])
        state = {r["name"]: r["id"] for r in rows if r.get("id")}

    for wf in workflows:
        kinds = ", ".join(sorted({s["type"] for s in wf["steps"]}))
        known = state.get(wf["name"])
        print(f"  {wf['name']:34s} {len(wf['steps']):>2} steps   [{kinds}]")
        if wf["trigger"]:
            print(f"  {'':34s} trigger (UI, not deployed): {wf['trigger']}")
        if known:
            print(f"  {'':34s} known id: {known} — will UPDATE")

    findings = lint(workflows)
    errors = [f for f in findings if f["level"] == "error"]
    warns = [f for f in findings if f["level"] == "warn"]
    if findings:
        print()
        for f in findings:
            print(f"  {f['level'].upper():5s} {f['workflow']} / {f['step']}: "
                  f"{f['message']}", file=sys.stderr)
    print(f"\n  lint: {len(errors)} error(s), {len(warns)} warning(s)")
    if errors:
        print("  These deploy SUCCESSFULLY and do nothing. Fix them before "
              "--deploy.", file=sys.stderr)

    if not args.deploy:
        print("  validate-only. Nothing was sent. Re-run with --deploy to write.")
        return 1 if errors else 0

    if errors:
        raise SystemExit("FATAL: refusing to deploy with lint errors — every one of "
                         "them would return 200 and then silently do nothing.")
    if warns:
        blocking = [f for f in warns if "placeholder" in f["message"]]
        if blocking:
            raise SystemExit(
                f"FATAL: {len(blocking)} placeholder value(s) still present. "
                f"Replace them; a placeholder id points at nothing and the API "
                f"will not tell you.")

    # A location id is a fact about the account, not a decision: flag, then
    # $GHL_LOCATION_ID, then .env. Only a genuinely absent one stops the deploy.
    try:
        location_id = ghl_ids.location_id(args.location_id, args.env_file)
    except ghl_ids.ResolveError as exc:
        raise SystemExit(f"FATAL: {exc}")
    token = read_token(args.token, args.token_file)

    print()
    results = deploy(location_id, token, workflows, state)

    # Merge rather than overwrite: a failed workflow must not erase the id of one
    # that deployed successfully on an earlier run.
    merged = dict(state)
    for r in results:
        if r.get("id"):
            merged[r["name"]] = r["id"]
    state_path.write_text(json.dumps(
        [{"name": n, "id": i} for n, i in merged.items()], indent=1))

    good = sum(1 for r in results if r["ok"])
    print(f"\n  {good}/{len(results)} deployed  (ids -> {state_path})")
    print("  NOT DONE YET: configure each workflow's trigger in the UI and publish "
          "it. An unpublished workflow with no trigger never runs.")
    return 0 if good == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
