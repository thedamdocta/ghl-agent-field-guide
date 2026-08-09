#!/usr/bin/env python3
"""
ghl_mcp.py — a small client for GoHighLevel's own MCP server.

THIS IS THE HIGHEST-LEVERAGE TOOL IN THIS DIRECTORY. Read this docstring before
you write a single line of GHL integration code.

WHY IT MATTERS
--------------
The normal failure mode of an agent working against GHL is endpoint guessing:
inventing a plausible REST path, getting a 404 or a 422, guessing again, burning
an hour. GHL publishes an MCP server that fronts a generated catalogue of its
entire public API. It answers three questions directly:

    search_operations(query)      -> which operations exist for this concept?
    describe_operation(op_id)     -> exact method, path, and parameter schema
    execute_operation(op_id, ...) -> run it

That replaces guessing entirely. ALWAYS search the catalogue before concluding a
capability is missing, and always describe an operation before calling it. The
catalogue is generated from the API itself, so it is correct in a way that any
model's memory of GHL's REST surface is not.

ENDPOINT AND AUTH
-----------------
    POST https://services.leadconnectorhq.com/mcp/anthropic/v2
      Authorization: Bearer <GHL_PIT>
      locationId:    <GHL_LOCATION_ID>
      Accept:        application/json, text/event-stream

Auth is the PIT (Private Integration Token), created in the sub-account under
Settings -> Private Integrations. Scope it to what you actually need.

The PIT reaches the PUBLIC API only. It does NOT reach
backend.leadconnectorhq.com — funnel page autosave and workflow CRUD live there
and need the internal `token-id` (see get_token.py). Do not waste time trying the
PIT against those; it returns "Unauthorized".

RULES LEARNED THE HARD WAY — EACH ONE COST REAL TIME
-----------------------------------------------------
1. RESPONSES ARE SSE. The server answers with `text/event-stream`, so the body is
   a series of `data: {...}` lines, not one JSON document. Parse accordingly.
   `json.loads(response_body)` fails here and the error looks like a server fault
   when it is a transport misunderstanding.

2. THE PAYLOAD IS DOUBLE-WRAPPED. JSON-RPC envelope -> result.content[] -> a
   `text` part that is ITSELF a JSON string. You must parse twice to reach the
   API's actual response.

3. WRITES REQUIRE AN `idempotencyKey`. Omit it and you get a 400 that names the
   field. This client generates one automatically for any non-read operation; you
   can override it. Passing a STABLE key is how you make a retry safe — same key,
   same logical write.

4. `locationId` GOES IN THE PATH, NEVER THE QUERY. In the query it returns
   `422 "property locationId should not exist"`. In practice: build params as
   `{"path": {"locationId": loc, ...}, "body": {...}}`. Note the location also
   goes in the HTTP header — that is separate and both are required.

5. A RESOLVED REQUEST IS NOT A PERMITTED ONE. `dryRun: true` comes back with
   `authorizationVerified: false` — it validates the SHAPE of your call, not your
   token's scopes. The only proof a scope exists is one real call. Standard move:
   create one throwaway record, confirm, remove it.

6. THE PIT CAN CREATE AND UPDATE BUT OFTEN CANNOT DELETE. Delete returns
   401 "token is not authorized for this scope" on several resources even when
   create succeeds on the same resource. Where the resource supports it, retire
   records by setting `archived: true` instead of deleting.

7. WHAT THE MCP DOES NOT COVER. As of this writing: no `create-workflow`
   (workflow ops are read + contact membership only), and funnel pages are
   read-only. Those two need the internal API — `deploy_workflow.py` and
   `inject_page.py`. Re-check with `search` before you believe this; the
   catalogue grows.

8. CURL, NOT urllib. Cloudflare 403s the default Python user agent on GHL hosts.
   Every request here goes through the system `curl` with a browser UA. This is
   not superstition; swapping to urllib reintroduces the 403.

USAGE — CLI
-----------
    python3 ghl_mcp.py search "email template"
    python3 ghl_mcp.py describe create-email-template
    python3 ghl_mcp.py locations
    python3 ghl_mcp.py execute GET-all-or-email-sms-templates \
        --params '{"query": {"limit": 10}}'
    python3 ghl_mcp.py execute create-email-template --yes \
        --params-file body.json --idempotency-key my-stable-key

Read operations run freely. WRITE operations refuse to run without `--yes`.

USAGE — AS A LIBRARY
--------------------
    from ghl_mcp import GHLMCP, load_env

    pit, loc = load_env()
    ghl = GHLMCP(pit, loc)
    print(ghl.search_operations("custom value"))
    print(ghl.describe_operation("create-custom-value"))
    ghl.execute_operation(
        "create-custom-value",
        {"path": {"locationId": loc}, "body": {"name": "x", "value": "y"}},
    )

Credentials come from the environment or a `.env` file. Nothing is hardcoded.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid

MCP_ENDPOINT = "https://services.leadconnectorhq.com/mcp/anthropic/v2"

# A browser UA. Cloudflare 403s python-urllib/x.y on GHL hosts — see rule 8.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Operation ids that only read. Everything else is treated as a write: it gets an
# idempotencyKey automatically and the CLI demands --yes before running it.
READ_PREFIXES = ("get-", "get_", "GET-", "list-", "search-", "fetch-", "describe-")


class GHLMCPError(RuntimeError):
    """Raised for transport failures and for errors the server reports.

    Deliberately loud. A silent empty dict from a failed call is the single
    easiest way to spend an afternoon debugging the wrong layer.
    """


def load_env(env_file: str = ".env") -> tuple:
    """Return (pit, location_id) from the process environment or a .env file.

    Real environment variables win over the file. Fails loudly with the exact
    variable names when something is missing — an empty PIT otherwise surfaces
    much later as an opaque 401.
    """
    values = {}
    path = pathlib.Path(env_file).expanduser()
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip().strip('"').strip("'")

    pit = os.environ.get("GHL_PIT") or values.get("GHL_PIT")
    loc = os.environ.get("GHL_LOCATION_ID") or values.get("GHL_LOCATION_ID")

    missing = [n for n, v in (("GHL_PIT", pit), ("GHL_LOCATION_ID", loc)) if not v]
    if missing:
        raise GHLMCPError(
            "missing credential(s): " + ", ".join(missing) + "\n"
            "  fix: export them, or copy .env.example to .env and fill it in.\n"
            "  GHL_PIT         — sub-account Settings -> Private Integrations\n"
            "  GHL_LOCATION_ID — the 20-char id in your GHL URL:\n"
            "                    app.gohighlevel.com/v2/location/<THIS>/..."
        )
    return pit, loc


def is_write(operation_id: str) -> bool:
    """Best-effort read/write classification, used for the --yes gate.

    Errs toward calling something a write. A read wrongly gated behind --yes
    costs one flag; a write wrongly treated as a read costs a live record.
    """
    return not operation_id.lower().startswith(
        tuple(p.lower() for p in READ_PREFIXES))


class GHLMCP:
    """Minimal client for the three meta-tools that matter."""

    def __init__(self, pit: str, location_id: str,
                 endpoint: str = MCP_ENDPOINT, timeout: int = 60,
                 verbose: bool = False) -> None:
        if not pit or not location_id:
            raise GHLMCPError("GHLMCP needs both a PIT and a location id.")
        self.pit = pit
        self.location_id = location_id
        self.endpoint = endpoint
        self.timeout = timeout
        self.verbose = verbose

    # ── transport ────────────────────────────────────────────────────────────

    def _post(self, payload: dict) -> str:
        """POST one JSON-RPC envelope; return the raw (SSE) body.

        curl, not urllib — Cloudflare 403s the default Python UA on GHL hosts.
        """
        cmd = [
            "curl", "-sS", "--max-time", str(self.timeout),
            "-X", "POST", self.endpoint,
            "-H", f"Authorization: Bearer {self.pit}",
            "-H", f"locationId: {self.location_id}",
            "-H", "Content-Type: application/json",
            # Without this Accept header the server may answer in a shape this
            # parser does not expect. Ask for both; parse whichever arrives.
            "-H", "Accept: application/json, text/event-stream",
            "-A", USER_AGENT,
            "-d", json.dumps(payload),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise GHLMCPError(
                f"curl failed (exit {proc.returncode}): "
                f"{proc.stderr.strip()[:300] or 'no stderr'}")
        if not proc.stdout.strip():
            raise GHLMCPError(
                "empty response from the MCP endpoint. Usual causes: an expired or "
                "wrong GHL_PIT, or a location id the PIT has no access to.")
        return proc.stdout

    @staticmethod
    def _parse_sse(raw: str) -> dict:
        """Unwrap SSE -> JSON-RPC -> content[].text -> the API's own JSON.

        Three layers, and each one has bitten someone:
          layer 1  `data: {...}` lines, possibly several, concatenated
          layer 2  the JSON-RPC envelope: {"result": {"content": [...]}}
          layer 3  content[i].text is a JSON *string* holding the real response
        """
        data_lines = [ln[len("data: "):] for ln in raw.splitlines()
                      if ln.startswith("data: ")]
        body = "".join(data_lines) if data_lines else raw.strip()

        try:
            envelope = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GHLMCPError(
                f"could not parse the response as JSON ({exc}).\n"
                f"  first 400 chars: {raw[:400]!r}\n"
                f"  if this looks like HTML, you were served a Cloudflare block "
                f"page — check the User-Agent.") from exc

        if isinstance(envelope, dict) and envelope.get("error"):
            raise GHLMCPError(f"MCP returned an error: "
                              f"{json.dumps(envelope['error'])[:400]}")

        result = envelope.get("result") if isinstance(envelope, dict) else None
        if not isinstance(result, dict):
            return envelope if isinstance(envelope, dict) else {"_raw": envelope}

        text = "".join(part.get("text", "")
                       for part in result.get("content", [])
                       if isinstance(part, dict))
        if not text:
            return result

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Some meta-tools answer in prose (search results, for one). Not an
            # error — hand it back verbatim rather than pretending it is JSON.
            return {"_text": text}

    def call_tool(self, name: str, arguments: dict) -> dict:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}}
        if self.verbose:
            print(f"  -> {name} {json.dumps(arguments)[:200]}", file=sys.stderr)
        return self._parse_sse(self._post(payload))

    # ── the three meta-tools ─────────────────────────────────────────────────

    def search_operations(self, query: str, limit: int = 20) -> dict:
        """Find operations by concept. START HERE, every time.

        Search broadly and by the business noun ("email template", "custom value",
        "contact tag"), not by a REST path you imagine exists. The catalogue names
        operations in its own style — for example a listing operation may be
        `GET-all-or-<resource>` rather than `list-<resource>`, which no amount of
        guessing produces.
        """
        return self.call_tool("search_operations",
                              {"query": query, "limit": limit})

    def describe_operation(self, operation_id: str) -> dict:
        """Exact method, path, and parameter schema for one operation.

        ALWAYS do this before a first call. It tells you which arguments belong in
        `path`, which in `query`, and which in `body` — the distinction behind the
        422 that says a property "should not exist".
        """
        return self.call_tool("describe_operation", {"operationId": operation_id})

    def execute_operation(self, operation_id: str, params: dict,
                          idempotency_key=None) -> dict:
        """Run an operation.

        `params` mirrors the schema from describe_operation, normally:

            {"path": {"locationId": loc, ...}, "query": {...}, "body": {...}}

        locationId goes in `path`. In `query` it is a 422 (see rule 4).

        Writes get an idempotencyKey automatically. Pass your own STABLE key to
        make retries safe: the same key for the same logical write means a retry
        after a network blip updates rather than duplicates. The auto-generated
        key is unique per call, which is safe for a first attempt and useless for
        deduplicating a retry — so pass your own whenever a retry is plausible.
        """
        args = {"operationId": operation_id, "params": params}
        if idempotency_key is None and is_write(operation_id):
            idempotency_key = f"{operation_id}-{uuid.uuid4().hex[:12]}-{int(time.time())}"
        if idempotency_key:
            args["idempotencyKey"] = idempotency_key
        return self.call_tool("execute_operation", args)

    def list_locations(self) -> dict:
        """Locations this PIT can see. Good first call to prove auth works."""
        return self.call_tool("list_locations", {})

    # ── convenience ──────────────────────────────────────────────────────────

    def paginate(self, operation_id: str, params: dict, rows_at: str,
                 page_size: int = 100, limit_key: str = "limit",
                 skip_key: str = "skip"):
        """Walk a paginated list operation and yield rows.

        `rows_at` is a dotted path into the response, e.g. "data.templates".
        Stops on a short page. Guarded against a server that ignores paging and
        returns the same full page forever.
        """
        skip, seen = 0, 0
        while True:
            page = dict(params)
            query = dict(page.get("query") or {})
            query[limit_key] = page_size
            query[skip_key] = skip
            page["query"] = query

            resp = self.execute_operation(operation_id, page)
            node = resp
            for part in rows_at.split("."):
                node = (node or {}).get(part) if isinstance(node, dict) else None
            rows = node or []
            if not rows:
                return
            for row in rows:
                yield row
            seen += len(rows)
            if len(rows) < page_size:
                return
            skip += page_size
            if seen > 100_000:  # a server ignoring `skip` would loop forever
                raise GHLMCPError(
                    f"pagination exceeded 100k rows on {operation_id} — the server "
                    f"is probably ignoring '{skip_key}'. Aborting rather than "
                    f"looping forever.")


# ── CLI ──────────────────────────────────────────────────────────────────────

def _pp(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main() -> int:
    # Global flags live in a parent parser attached to BOTH the top level and
    # every subcommand, so `--env-file x search q` and `search q --env-file x`
    # both work. default=SUPPRESS is load-bearing: without it the subparser would
    # re-apply its own defaults and wipe a value given before the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--env-file", default=argparse.SUPPRESS,
                        help="Path to a .env file (default ./.env). Real "
                             "environment variables take precedence.")
    common.add_argument("--location-id", default=argparse.SUPPRESS,
                        help="Override the location id for this call.")
    common.add_argument("--timeout", type=int, default=argparse.SUPPRESS)
    common.add_argument("-v", "--verbose", action="store_true",
                        default=argparse.SUPPRESS)

    ap = argparse.ArgumentParser(
        parents=[common],
        description="Client for GoHighLevel's MCP server. "
                    "search -> describe -> execute. Never guess an endpoint.",
        epilog="Credentials: $GHL_PIT and $GHL_LOCATION_ID, or a .env file "
               "(see .env.example).",
    )

    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("search", parents=[common],
                       help="search_operations — find ops by concept")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("describe", parents=[common],
                       help="describe_operation — schema for one op")
    p.add_argument("operation_id")

    p = sub.add_parser("locations", parents=[common],
                       help="list_locations — proves the PIT works")

    p = sub.add_parser("execute", parents=[common],
                       help="execute_operation — run an operation")
    p.add_argument("operation_id")
    p.add_argument("--params", help="JSON params object, e.g. "
                                    "'{\"path\":{\"locationId\":\"...\"}}'")
    p.add_argument("--params-file", help="File containing the JSON params object.")
    p.add_argument("--idempotency-key",
                   help="Stable key so a retry updates instead of duplicating.")
    p.add_argument("--yes", action="store_true",
                   help="REQUIRED for write operations. Without it, a write is "
                        "printed and refused.")

    args = ap.parse_args()
    # SUPPRESS means unspecified flags are absent from the namespace entirely.
    env_file = getattr(args, "env_file", ".env")
    override_loc = getattr(args, "location_id", None)
    timeout = getattr(args, "timeout", 60)
    verbose = getattr(args, "verbose", False)

    try:
        pit, loc = load_env(env_file)
    except GHLMCPError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    if override_loc:
        loc = override_loc

    client = GHLMCP(pit, loc, timeout=timeout, verbose=verbose)

    try:
        if args.cmd == "search":
            _pp(client.search_operations(args.query, args.limit))
        elif args.cmd == "describe":
            _pp(client.describe_operation(args.operation_id))
        elif args.cmd == "locations":
            _pp(client.list_locations())
        elif args.cmd == "execute":
            if args.params and args.params_file:
                print("FATAL: pass --params or --params-file, not both.",
                      file=sys.stderr)
                return 1
            raw = args.params
            if args.params_file:
                raw = pathlib.Path(args.params_file).read_text()
            if raw is None:
                print("FATAL: execute needs --params or --params-file. Run "
                      f"`describe {args.operation_id}` to see the schema.",
                      file=sys.stderr)
                return 1
            try:
                params = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"FATAL: --params is not valid JSON: {exc}", file=sys.stderr)
                return 1
            if not isinstance(params, dict):
                print("FATAL: params must be a JSON object.", file=sys.stderr)
                return 1

            if is_write(args.operation_id) and not args.yes:
                print(f"REFUSED: {args.operation_id} looks like a WRITE and --yes "
                      f"was not given.\n"
                      f"  would send: {json.dumps(params)[:300]}\n"
                      f"  re-run with --yes to actually perform it.",
                      file=sys.stderr)
                return 2

            _pp(client.execute_operation(args.operation_id, params,
                                         args.idempotency_key))
    except GHLMCPError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
