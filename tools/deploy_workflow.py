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
record pulled straight from GHL can be round-tripped. Step `id`, `order` and
`next` are filled in automatically if absent.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import uuid

INTERNAL_API = "https://backend.leadconnectorhq.com/workflow"

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


def link(steps: list) -> list:
    """Steps are a linked list: `order` plus a `next` pointer.

    Missing ids are minted here so a hand-written JSON spec does not have to carry
    uuids. Without order/next the steps deploy as an unordered bag and execution
    order is undefined.
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
                    "steps": link(steps)})
    return out


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
    return [{
        "name": "EXAMPLE · Pre-event sequence",
        "trigger": "Form submitted — set this in the UI; triggers are not deployable",
        "steps": link([
            tag_step(["your-registered-tag"]),
            event_anchor("{{ custom_values.your_event_datetime_iso }}"),
            email_step("REPLACE_WITH_TEMPLATE_ID", "Confirmation",
                       "Your seat is confirmed",
                       "{{custom_values.support_email}}",
                       "{{custom_values.business_name}}"),
            wait_before(1440, "1 day before the event", days=1),
            email_step("REPLACE_WITH_TEMPLATE_ID", "Reminder T-24h",
                       "Tomorrow", "{{custom_values.support_email}}",
                       "{{custom_values.business_name}}"),
            wait_before(180, "3 hours before the event", hours=3),
            email_step("REPLACE_WITH_TEMPLATE_ID", "Reminder T-3h",
                       "We begin in three hours",
                       "{{custom_values.support_email}}",
                       "{{custom_values.business_name}}"),
        ]),
    }, {
        "name": "EXAMPLE · Post-event branch",
        "trigger": "Tag added — your-no-show-tag",
        "steps": link([
            # leave_workflow() is omitted here because it REQUIRES a real id.
            # After the first deploy, read the ids out of your --state file and
            # add: leave_workflow("EXAMPLE · Pre-event sequence", "<id>")
            wait(24, "hours"),
            branch_on_tag("Did they engage?", "your-engaged-tag",
                          "Engaged", "Not engaged"),
            email_step("REPLACE_WITH_TEMPLATE_ID", "Follow-up",
                       "One more thing", "{{custom_values.support_email}}",
                       "{{custom_values.business_name}}"),
        ]),
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
    ap.add_argument("--location-id", default=os.environ.get("GHL_LOCATION_ID"),
                    help="GHL location id. Defaults to $GHL_LOCATION_ID.")
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

    if not args.deploy:
        print("\n  validate-only. Nothing was sent. Re-run with --deploy to write.")
        return 0

    if not args.location_id:
        raise SystemExit("FATAL: --deploy needs a location id "
                         "(--location-id or $GHL_LOCATION_ID).")
    token = read_token(args.token, args.token_file)

    print()
    results = deploy(args.location_id, token, workflows, state)

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
