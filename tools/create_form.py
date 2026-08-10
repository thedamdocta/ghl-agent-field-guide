#!/usr/bin/env python3
"""
create_form.py — create a funnel form, from a built-in seed or by cloning.

WHY THIS EXISTS
---------------
Two rules, both learned from client-visible bugs:

1. USE A NATIVE GHL FORM. A hand-rolled `<form>` inside a custom-code block
   renders perfectly and captures NO leads. A funnel page's form element
   references a real form by id (`extra.formId`) — see `ghl_generator.py`.

2. GIVE EVERY FUNNEL ITS OWN FORM. Pointing a page at a pre-existing,
   generically-named account form ("Registration", "Contact Us") imports that
   form's fields, image, linked header, branding and FIXED WIDTH. In production
   that rendered an unrelated intake form's image, header and submit button inside
   a webinar funnel — and restyling it would have changed every other place that
   form is embedded.

TWO WAYS TO GET A SCHEMA — and an earlier version of this file was wrong about it.

  --seed        Use the built-in minimal schema below. Needs NO donor form.
                This is the right default, and it is what you want on a FRESH
                sub-account, where there is nothing to clone. A form created
                through the UI's "Create form" button is NOT a usable donor
                either: it exists with a real name but its formData is ~520
                bytes of timestamp.

  --clone-from  Copy a WORKING form's formData, drop the fields you do not want,
                rename. Better when you want to inherit an existing form's
                appearance blocks exactly.

THE CORRECTION (2026-08-10). This tool used to say "CLONE, DO NOT HAND-WRITE —
hand-written field dicts miss keys and fail in ways that do not name them", and it
refused to run without a donor. That was wrong, and it stranded anyone starting from
an empty account. The production form this pattern came from was built from
hand-written field dicts, exactly the ones in SEED_FIELDS below. The original notes
DESCRIBED that work as "cloning the field schema" — meaning the schema was learned by
reading an existing form — and the description, not the code, is what got carried
forward. Read the code, not the summary of the code.

THE TWO WARNINGS THAT COST REAL TIME
--------------------------------------
1. `POST /forms/{formId}` 422s IF THE BODY CONTAINS `locationId`. The 422 names
   the offending property, which is the general GHL technique: post a minimal body
   first and let the validator tell you the schema. Note the asymmetry — CREATE
   (`POST /forms/`) REQUIRES `locationId` in the body; UPDATE (`POST /forms/{id}`)
   REJECTS it. Same verb, same route family, opposite requirement.
   Also: `POST /forms/{id}` IS the update route. `PUT` and `PATCH` both 404.

2. THE FORMS LIST RETURNS `name: null` FOR FORMS CREATED VIA THE BACKEND API.
   Any "does my form already exist?" check that matches on NAME will always miss
   and create a DUPLICATE — every run, forever. Match on a STORED ID instead.
   That is what `--id-file` is for, and why this tool refuses to create a second
   form when the id file already holds one.

AUTH: form WRITES are internal API (`token-id`, from `get_token.py`). The forms
LIST is public API (PIT) and is the one endpoint family that genuinely takes
`locationId` in the query.

The form renders INLINE in the page document, not in an iframe (verified by
finding `.ghl-form-wrap` in the main frame), so page CSS reaches it and the submit
button can be unified with your page buttons from the page stylesheet. Do not
assume iframe isolation.

Reminder from `ghl_generator.py`: SUBMIT BEHAVIOUR LIVES ON THE PAGE ELEMENT, not
on the form record. Writing `formAction.actionType` / `redirectUrl` onto the form
record returns 200 and silently does not persist.

USAGE
-----
    # what forms exist? (public API, PIT)
    python3 create_form.py --list

    # dump one form's record so you can inspect / edit the schema you will clone
    python3 create_form.py --dump <sourceFormId> --out source-form.json

    # dry run: show exactly what would be created
    python3 create_form.py --name "Webinar registration" \
        --clone-from-file source-form.json --fields first_name,email,phone

    # do it
    python3 create_form.py --name "Webinar registration" \
        --clone-from-file source-form.json --fields first_name,email,phone \
        --id-file .form-id --apply

Nothing is written without `--apply`. No form ids, names, styles or field sets are
baked in.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

# Verified in production: these exact dicts created a working 3-field form on a live
# account. `standard: True` marks a built-in contact field; `hiddenFieldQueryKey`
# enables URL prefill, which is how a later step can carry values forward.
SEED_FIELDS = [
    {"tag": "first_name", "label": "First name", "placeholder": "First name",
     "required": True, "standard": True, "hiddenFieldQueryKey": "first_name"},
    {"tag": "email", "label": "Email", "placeholder": "Email address",
     "required": True, "standard": True, "hiddenFieldQueryKey": "email"},
    {"tag": "phone", "label": "Phone", "placeholder": "Phone number",
     "required": True, "standard": True, "hiddenFieldQueryKey": "phone",
     "enableCountryPicker": False},
]

SEED_FORM_DATA = {
    "form": {
        "fields": SEED_FIELDS,
        "formAction": "message",
        "formSubmissionEvent": "Submit",
        "formLabelVisible": False,
        "fullScreenMode": False,
        "inputStyleType": "line",
        "fieldCSS": "",
        "customStyle": "",
    }
}


def seed_form_data(field_tags=None) -> dict:
    """The built-in schema, optionally narrowed to a subset of field tags."""
    import copy as _copy
    data = _copy.deepcopy(SEED_FORM_DATA)
    if field_tags:
        wanted = [t.strip() for t in field_tags if t.strip()]
        data["form"]["fields"] = [f for f in data["form"]["fields"]
                                  if f["tag"] in wanted]
        missing = set(wanted) - {f["tag"] for f in data["form"]["fields"]}
        if missing:
            raise SystemExit(
                f"--fields names {sorted(missing)}, which the built-in seed does not "
                f"carry. Seed tags: {[f['tag'] for f in SEED_FIELDS]}. For anything "
                f"else, clone a form that already has the field.")
    return data


PUBLIC_API = "https://services.leadconnectorhq.com"
INTERNAL_API = "https://backend.leadconnectorhq.com"

# Cloudflare 403s python-urllib on GHL hosts. Browser UA, via system curl.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def load_env(env_file: str = ".env") -> dict:
    """Read GHL_PIT / GHL_LOCATION_ID from the environment, then a .env file."""
    values = {}
    path = pathlib.Path(env_file).expanduser()
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip().strip('"').strip("'")
    for key in ("GHL_PIT", "GHL_LOCATION_ID"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


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
        f"  the PIT does NOT work for form writes — those are internal API.")


def curl(args: list, timeout: int = 45) -> str:
    proc = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), "-A", USER_AGENT, *args],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"FATAL: curl failed (exit {proc.returncode}): "
                         f"{proc.stderr.strip()[:300]}")
    return proc.stdout


def internal_headers(token: str) -> list:
    """`token-id`, NOT `Authorization: Bearer` — Bearer returns Unauthorized here."""
    return ["-H", f"token-id: {token}",
            "-H", "channel: APP",
            "-H", "source: WEB_USER",
            "-H", "Version: 2021-07-28",
            "-H", "Content-Type: application/json"]


def list_forms(pit: str, location_id: str) -> list:
    """List forms via the public API.

    This route genuinely takes `locationId` in the QUERY — one of the few that
    does. Most GHL routes want it in the path and 422 otherwise.
    """
    out = curl(["-H", f"Authorization: Bearer {pit}",
                "-H", "Version: 2021-07-28", "-H", "Accept: application/json",
                f"{PUBLIC_API}/forms/?locationId={location_id}&limit=100"])
    try:
        return json.loads(out).get("forms") or []
    except json.JSONDecodeError:
        raise SystemExit(f"FATAL: could not list forms. response: {out[:300]!r}")


def wait_for_form(token: str, form_id: str, tries: int = 8) -> bool:
    """Poll until a just-created form is readable.

    THE BUG THIS FIXES. Create and populate are two calls, and the id is not
    immediately resolvable on the write path. Populating straight after creating
    returns:

        400  "form does not exist or is deleted"

    against an id that was handed to you seconds earlier. Run the identical populate
    by hand a minute later and it returns 201. GHL has read-after-write propagation
    lag — the same lag that makes an early check on a freshly injected PAGE report a
    false mismatch.

    A fixed `sleep` is the wrong shape: too short and it still fails, too long and
    every run pays for the worst case. Poll for the condition instead, and say so
    when it takes a while, so the next person does not think it hung.
    """
    import time
    delay = 0.75
    for attempt in range(1, tries + 1):
        out = curl([*internal_headers(token), f"{INTERNAL_API}/forms/{form_id}"])
        try:
            rec = json.loads(out)
            form = rec.get("form") or rec
            if form.get("_id") == form_id and not form.get("deleted"):
                if attempt > 1:
                    print(f"  form became readable after {attempt} checks")
                return True
        except json.JSONDecodeError:
            pass
        if attempt < tries:
            time.sleep(delay)
            delay = min(delay * 1.6, 6.0)
    return False


def get_form(token: str, form_id: str) -> dict:
    """Read one form record from the internal API.

    UNVERIFIED ROUTE. `GET /forms/{id}` on the internal host has not been
    confirmed against a live account the way create/update/delete have. If it
    returns something that is not a form record, do not fight it: open the form in
    the GHL UI with devtools recording, copy the form record out of the network
    tab into a file, and use --clone-from-file. Capturing the UI doing the work
    beats guessing at routes, every time.
    """
    out = curl([*internal_headers(token), f"{INTERNAL_API}/forms/{form_id}"])
    try:
        doc = json.loads(out)
    except json.JSONDecodeError:
        raise SystemExit(
            f"FATAL: could not read form {form_id}.\n"
            f"  response: {out[:300]!r}\n"
            f"  if the token-id expired, re-run get_token.py. If this route is\n"
            f"  simply not readable, capture the record from the UI's network\n"
            f"  traffic and pass it with --clone-from-file.")
    return doc


def extract_form_data(record: dict) -> dict:
    """Pull `formData` out of whatever shape the record arrived in."""
    for candidate in (record, record.get("form") or {}):
        if isinstance(candidate, dict) and isinstance(candidate.get("formData"), dict):
            return candidate["formData"]
    # Some captures are already the formData itself.
    if isinstance(record.get("form"), dict) and "fields" in record["form"]:
        return record
    raise SystemExit(
        "FATAL: no `formData` in the source record. Expected either a form record "
        "with a .formData object, or a .form wrapper containing one.\n"
        f"  top-level keys seen: {', '.join(sorted(record)[:12])}")


def filter_fields(form_data: dict, keep: list) -> dict:
    """Keep only the named field tags, preserving the requested order.

    Deleting unwanted fields from a cloned schema is safe; ADDING a hand-written
    field dict is not — it will be missing required keys.
    """
    inner = form_data.get("form")
    if not isinstance(inner, dict) or not isinstance(inner.get("fields"), list):
        raise SystemExit("FATAL: source formData has no form.fields list — it is "
                         "not a usable clone source.")
    by_tag = {}
    for field in inner["fields"]:
        tag = field.get("tag") or field.get("name") or field.get("fieldKey")
        if tag:
            by_tag.setdefault(tag, field)
    missing = [t for t in keep if t not in by_tag]
    if missing:
        raise SystemExit(
            f"FATAL: the source form has no field(s) {', '.join(missing)}.\n"
            f"  available tags: {', '.join(sorted(by_tag)) or '(none)'}\n"
            f"  pick a source form that already contains every field you need — "
            f"hand-writing a field dict misses required keys.")
    inner["fields"] = [by_tag[t] for t in keep]
    return form_data


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create a GHL funnel form by cloning an existing form's field "
                    "schema. Match on a STORED ID, never on name.",
        epilog="Writes need the internal token-id (get_token.py). Nothing is "
               "created without --apply.")
    ap.add_argument("--name", help="Name for the new form.")
    ap.add_argument("--seed", action="store_true",
                    help="Use the built-in minimal schema — no donor form needed. "
                         "The right choice on a fresh sub-account.")
    ap.add_argument("--clone-from", metavar="FORM_ID",
                    help="Read this form's schema from the internal API and clone "
                         "it (route is UNVERIFIED — see --clone-from-file).")
    ap.add_argument("--clone-from-file", metavar="FILE",
                    help="Clone the schema from a saved form record JSON. Use this "
                         "when --clone-from cannot read the route.")
    ap.add_argument("--fields", metavar="a,b,c",
                    help="Comma-separated field tags to KEEP from the source, in "
                         "order (e.g. first_name,email,phone). Default: all.")
    ap.add_argument("--id-file", default=".form-id",
                    help="File that remembers the created form id (default "
                         ".form-id). THIS is how re-runs avoid duplicates — the "
                         "forms list returns name: null, so name matching cannot "
                         "work. Gitignore it: it holds a real id.")
    ap.add_argument("--list", dest="do_list", action="store_true",
                    help="List the account's forms and exit.")
    ap.add_argument("--dump", metavar="FORM_ID",
                    help="Print one form record as JSON and exit (use with --out).")
    ap.add_argument("--out", help="Write --dump output here instead of stdout.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually create/update the form. Without this the tool "
                         "only reports.")
    ap.add_argument("--force-new", action="store_true",
                    help="Create a new form even though --id-file already holds an "
                         "id. This is how duplicates happen; be sure.")
    ap.add_argument("--token", help="Internal token-id (eyJ...).")
    ap.add_argument("--token-file",
                    default=os.environ.get("GHL_TOKEN_FILE", ".jwt"),
                    help="File holding the token-id (default ./.jwt).")
    ap.add_argument("--env-file", default=".env",
                    help="Where to read GHL_PIT / GHL_LOCATION_ID (default .env).")
    args = ap.parse_args()

    env = load_env(args.env_file)

    if args.do_list:
        pit, loc = env.get("GHL_PIT"), env.get("GHL_LOCATION_ID")
        if not pit or not loc:
            raise SystemExit("FATAL: --list needs GHL_PIT and GHL_LOCATION_ID "
                             "(environment or .env).")
        forms = list_forms(pit, loc)
        print(f"  {len(forms)} form(s) in location {loc}:")
        nameless = 0
        for form in forms:
            name = form.get("name")
            nameless += name is None
            print(f"    {form.get('id', '?'):<26} {name!r}")
        if nameless:
            print(f"  note: {nameless} form(s) report name: null — that is normal "
                  f"for forms created through the backend API, and it is exactly "
                  f"why you must match on a stored id, never on a name.")
        return 0

    if args.dump:
        token = read_token(args.token, args.token_file)
        record = get_form(token, args.dump)
        dumped = json.dumps(record, indent=2, ensure_ascii=False)
        if args.out:
            out = pathlib.Path(args.out).expanduser()
            out.write_text(dumped, encoding="utf-8")
            print(f"  -> {out}")
        else:
            print(dumped)
        return 0

    if not args.name:
        raise SystemExit(
            "FATAL: nothing to do. Pass --name to create a form, or --list / "
            "--dump to inspect. This tool never creates anything implicitly.")
    if not (args.seed or args.clone_from or args.clone_from_file):
        raise SystemExit(
            "FATAL: no schema source. Choose one:\n"
            "  --seed                      built-in minimal schema, no donor needed.\n"
            "                              The right choice on a fresh sub-account.\n"
            "  --clone-from <formId>       copy a form that already works\n"
            "  --clone-from-file <file>    copy from a dumped record\n"
            "  Inspect what exists: python3 create_form.py --list")

    location_id = env.get("GHL_LOCATION_ID")
    if not location_id:
        raise SystemExit("FATAL: GHL_LOCATION_ID is not set (environment or .env). "
                         "Form CREATE requires it in the body.")
    token = read_token(args.token, args.token_file)

    if args.seed:
        # No donor. The built-in schema was verified in production — see SEED_FIELDS.
        source = {"formData": seed_form_data(
            [f.strip() for f in args.fields.split(",")] if args.fields else None)}
        print("  using the built-in seed schema (no donor form)")
    elif args.clone_from_file:
        path = pathlib.Path(args.clone_from_file).expanduser()
        if not path.is_file():
            raise SystemExit(f"FATAL: no such --clone-from-file: {path}")
        try:
            source = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(f"FATAL: {path} is not valid JSON: {exc}")
    else:
        source = get_form(token, args.clone_from)

    form_data = extract_form_data(source)
    if args.fields and not args.seed:
        keep = [f.strip() for f in args.fields.split(",") if f.strip()]
        form_data = filter_fields(form_data, keep)
    fields = (form_data.get("form") or {}).get("fields") or []

    id_path = pathlib.Path(args.id_file).expanduser()
    existing_id = id_path.read_text().strip() if id_path.is_file() else ""

    print(f"  name:        {args.name!r}")
    print(f"  clone source: {args.clone_from or args.clone_from_file}")
    print(f"  fields:      {', '.join(f.get('tag', '?') for f in fields) or '(none)'}")
    print(f"  id file:     {id_path} "
          f"({'holds ' + existing_id if existing_id else 'empty'})")

    if not args.apply:
        action = "update" if (existing_id and not args.force_new) else "create"
        print(f"\n  (report only — would {action}. Pass --apply to write.)")
        return 0

    if existing_id and not args.force_new:
        form_id = existing_id
        print(f"  reusing remembered form {form_id} (no duplicate created)")
    else:
        # CREATE: locationId is REQUIRED in the body here.
        out = curl([*internal_headers(token), "-X", "POST",
                    "-d", json.dumps({"locationId": location_id,
                                      "name": args.name}),
                    f"{INTERNAL_API}/forms/"])
        try:
            form_id = json.loads(out)["form"]["_id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            print(f"FATAL: form create failed.\n  response: {out[:300]!r}\n"
                  f"  the id is at .form._id on success. If this says "
                  f"unauthorized, the token-id expired — re-run get_token.py.",
                  file=sys.stderr)
            return 1
        print(f"  created form {form_id}")

    # A freshly created id is not immediately resolvable on the write path. Confirm
    # it is readable BEFORE populating, or the populate 400s against an id that was
    # returned seconds ago.
    if not wait_for_form(token, form_id):
        print(f"FATAL: form {form_id} was created but never became readable.\n"
              f"  This is read-after-write lag, not a bad id — the same populate\n"
              f"  usually succeeds if retried. Re-run with --id-file pointing at\n"
              f"  this id to populate it without creating a second form.",
              file=sys.stderr)
        id_path.parent.mkdir(parents=True, exist_ok=True)
        id_path.write_text(form_id)
        return 1

    # UPDATE: `POST /forms/{id}` is the update route — PUT and PATCH both 404.
    # locationId MUST NOT appear in this body: it 422s with
    # "property locationId should not exist", and the 422 names the field.
    body = {"name": args.name, "formData": form_data}
    out = curl([*internal_headers(token), "-X", "POST", "-d", json.dumps(body),
                f"{INTERNAL_API}/forms/{form_id}"])
    accepted = '"formData"' in out or '"_id"' in out
    # The update response does NOT echo the stored formData, so "accepted" only means
    # the request was taken. Read it back — that is the actual verification.
    # The read-back needs the SAME retry as the create. Reading immediately after
    # the write returns the record with an empty formData — so a single check reports
    # "no fields stored" while the fields are, in fact, stored. That false negative is
    # worse than no check at all: it would send you debugging a write that worked.
    persisted = []
    if accepted:
        import time
        delay = 0.75
        for attempt in range(6):
            rec = json.loads(curl([*internal_headers(token),
                                   f"{INTERNAL_API}/forms/{form_id}"]) or "{}")
            form = rec.get("form") or rec
            persisted = (((form.get("formData") or {}).get("form") or {})
                         .get("fields") or [])
            if persisted:
                break
            time.sleep(delay)
            delay = min(delay * 1.6, 5.0)
    print(f"  populate fields: {'OK' if accepted else 'FAILED'}"
          + (f"  — verified stored: {[f.get('tag') for f in persisted]}"
             if persisted else ""))
    if not accepted:
        print(f"    response: {out[:300]!r}\n"
              f"    if it names `locationId`, something re-added it to the update "
              f"body — CREATE needs it, UPDATE rejects it.", file=sys.stderr)
        return 1

    id_path.parent.mkdir(parents=True, exist_ok=True)
    id_path.write_text(form_id)
    print(f"  formId -> {id_path}  ({form_id})")
    print("  next: reference this id from a page form element "
          "(ghl_generator.py form()). Submit behaviour goes on the PAGE element, "
          "not on this record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
