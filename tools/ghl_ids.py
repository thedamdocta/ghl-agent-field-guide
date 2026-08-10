#!/usr/bin/env python3
"""
ghl_ids.py — find the ids instead of demanding them.

WHY THIS EXISTS. Every tool here used to want a 20-character location id, funnel id
and page id typed on the command line. All three are discoverable from the account
with one API call each, so making an agent hunt for them, copy them, and paste them
between steps was pure friction — and friction is where an inheriting agent gives up.

THE RULE THIS ENCODES: refuse to INVENT, never refuse to LOOK UP.

  * A name you did not give is never guessed. `create_form.py --name` still refuses
    when no name is passed, because a form name is a decision only you can make.
  * An id you did not give is looked up, because an id is a fact about the account.
  * When the lookup finds SEVERAL real candidates, it raises and lists them. Picking
    one for you would be guessing between real options, which is how the wrong page
    gets overwritten.
  * When the lookup finds exactly ONE, it uses it. There is nothing to guess.

Every resolution is printed the moment it happens:

    resolved funnel "Launch"  -> <id>   (matched by name)
    resolved page   "Opt-in"  -> <id>   (matched by name)

so a WRONG resolution is visible in the transcript rather than silent.

USE IT AS A LIBRARY

    import ghl_ids
    loc  = ghl_ids.location_id(args.location_id)         # flag -> env -> .env
    pit  = ghl_ids.private_token()
    fn   = ghl_ids.resolve_funnel(pit, loc, args.funnel or args.funnel_id or None)
    pg   = ghl_ids.resolve_page(pit, loc, fn.id, args.page or args.page_id or None)
    print(ghl_ids.report("funnel", fn))

USE IT AS A COMMAND

    python3 ghl_ids.py                        # what is this account? list everything
    python3 ghl_ids.py --funnel "Launch"      # resolve one funnel, print its pages
    python3 ghl_ids.py --funnel "Launch" --page "Opt-in" --json
    python3 ghl_ids.py --refresh              # ignore the on-disk cache
    python3 ghl_ids.py --self-test            # offline fixture tests, no credentials

THE TWO ENDPOINTS, EXACTLY AS VERIFIED

    GET services.leadconnectorhq.com/funnels/funnel/list?locationId=<loc>&limit=20
        -> {"funnels": [{"_id", "name", "steps": [...]}, ...]}

    GET services.leadconnectorhq.com/funnels/page
            ?funnelId=<f>&locationId=<loc>&limit=20&offset=0
        -> a BARE ARRAY of {"_id", "name", "funnelId", "stepId"}

TWO TRAPS, BOTH LIVE-CONFIRMED:

  1. The page route returns a BARE ARRAY. It is NOT wrapped in {"pages": [...]} the
     way the rest of the API wraps its collections. A parser that reaches for a
     "pages" key gets None, reports "no pages", and makes a perfectly healthy
     endpoint look broken. That single wrong assumption is why this route had a
     reputation for not working.
  2. ALL FOUR query params on the page route are required. Drop locationId or drop
     offset and it 422s — it does not fall back to a default.

Requests go through the system `curl` with a browser User-Agent. Cloudflare 403s
Python's default urllib User-Agent on GHL hosts; that 403 reads like an auth failure
and sends you to regenerate a token that was fine.

CACHE. Lookups are memoised to ./.ghl-ids.json for an hour so a five-step build does
not re-query five times. Pass --refresh (or refresh=True) after you create a funnel
or page. The cache holds ids and names from YOUR account — it is gitignored, and it
should stay that way.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import NamedTuple

PUBLIC_API = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"

# Cloudflare 403s python-urllib on GHL hosts. Browser UA, via system curl.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

HERE = pathlib.Path(__file__).resolve().parent
CACHE_NAME = ".ghl-ids.json"
CACHE_TTL = 3600  # seconds; --refresh bypasses it

# A GHL object id is 20 characters of base62. Mongo-style 24-char hex ids show up on
# a few older objects, so accept those too.
_ID_20 = re.compile(r"\A[A-Za-z0-9]{20}\Z")
_ID_24 = re.compile(r"\A[0-9a-f]{24}\Z")


class ResolveError(RuntimeError):
    """Something could not be resolved, and guessing would be worse than stopping."""


class Resolved(NamedTuple):
    id: str
    name: str          # "" when an id was passed through without a lookup
    how: str           # human-readable provenance, printed so mistakes are visible


# ── credentials ──────────────────────────────────────────────────────────────

def load_env(env_file: str = ".env") -> dict:
    """Read a .env into a dict. Real environment variables win over the file.

    Looks in the given path, then next to this script, then the current directory —
    an agent that runs `python3 tools/ghl_ids.py` from the repo root should not have
    to think about which directory the .env is relative to.
    """
    values: dict = {}
    candidates = [pathlib.Path(env_file).expanduser()]
    if not pathlib.Path(env_file).is_absolute():
        candidates += [HERE / env_file, pathlib.Path.cwd() / env_file]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values.setdefault(key.strip(), val.strip().strip('"').strip("'"))
        break
    for key in ("GHL_PIT", "GHL_LOCATION_ID", "GHL_TOKEN_ID"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def location_id(explicit: str = None, env_file: str = ".env") -> str:
    """--location-id, then $GHL_LOCATION_ID, then .env. One-line fix if absent."""
    if explicit and explicit.strip():
        return explicit.strip()
    found = load_env(env_file).get("GHL_LOCATION_ID")
    if found and found.strip():
        return found.strip()
    raise ResolveError(
        "no location id.\n"
        "  fix: export GHL_LOCATION_ID=<the 20-char id in your GHL URL>\n"
        "       app.gohighlevel.com/v2/location/<THIS_PART>/dashboard\n"
        "  or pass --location-id <id>, or put it in .env (see .env.example).")


def private_token(explicit: str = None, env_file: str = ".env") -> str:
    """The Private Integration Token, used for the two read-only lookup routes."""
    if explicit and explicit.strip():
        return explicit.strip()
    found = load_env(env_file).get("GHL_PIT")
    if found and found.strip():
        return found.strip()
    raise ResolveError(
        "no GHL_PIT, so ids cannot be looked up.\n"
        "  fix: export GHL_PIT=<token>   (sub-account Settings -> Private "
        "Integrations)\n"
        "  or pass the ids explicitly with --funnel-id / --page-id.")


# ── the two lookup routes ────────────────────────────────────────────────────

def _curl(url: str, pit: str, timeout: int = 45) -> str:
    proc = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), "-A", USER_AGENT,
         "-H", f"Authorization: Bearer {pit}",
         "-H", f"Version: {API_VERSION}",
         "-H", "Accept: application/json",
         url],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise ResolveError(f"curl failed (exit {proc.returncode}) on "
                           f"{url.split('?')[0]}: {proc.stderr.strip()[:200]}")
    return proc.stdout


def _parse(raw: str, what: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ResolveError(f"{what}: response was not JSON. "
                           f"first 200 chars: {raw[:200]!r}\n"
                           f"  a Cloudflare HTML page here means the request went "
                           f"out without a browser User-Agent.")


def _rows(data, wrapper_keys, what: str) -> list:
    """Accept a bare array OR a wrapped collection, because GHL does both.

    The page route returns a BARE ARRAY; the funnel route wraps in "funnels".
    Handling only the wrapped shape is the bug that made /funnels/page look dead.
    """
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in wrapper_keys:
            if isinstance(data.get(key), list):
                return [r for r in data[key] if isinstance(r, dict)]
        message = data.get("message") or data.get("error")
        if message:
            raise ResolveError(f"{what}: API said {message!r}. "
                               f"A 401/403 here means the PIT is wrong or is not "
                               f"scoped to this location.")
        return []
    raise ResolveError(f"{what}: unexpected response type "
                       f"{type(data).__name__}.")


def list_funnels(pit: str, loc: str, timeout: int = 45) -> list:
    """GET /funnels/funnel/list — returns {"funnels": [...]}."""
    url = f"{PUBLIC_API}/funnels/funnel/list?locationId={loc}&limit=20"
    return _rows(_parse(_curl(url, pit, timeout), "funnel list"),
                 ("funnels", "data"), "funnel list")


def list_pages(pit: str, loc: str, funnel_id: str, timeout: int = 45) -> list:
    """GET /funnels/page — returns a BARE ARRAY.

    All four query params are mandatory. Omitting locationId or offset returns 422,
    not a defaulted result.
    """
    url = (f"{PUBLIC_API}/funnels/page?funnelId={funnel_id}&locationId={loc}"
           f"&limit=20&offset=0")
    return _rows(_parse(_curl(url, pit, timeout), "page list"),
                 ("pages", "data"), "page list")


# ── cache ────────────────────────────────────────────────────────────────────

def cache_path(explicit: str = None) -> pathlib.Path:
    return pathlib.Path(explicit or os.environ.get("GHL_IDS_CACHE")
                        or CACHE_NAME).expanduser()


def _cache_read(path: pathlib.Path) -> dict:
    try:
        blob = json.loads(path.read_text())
        return blob if isinstance(blob, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _cache_write(path: pathlib.Path, blob: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(blob, indent=1))
    except OSError:
        pass  # the cache is an optimisation; never fail a build over it


def _fresh(node: dict) -> bool:
    return bool(node.get("items")) and \
        (time.time() - float(node.get("fetched") or 0)) < CACHE_TTL


def _slim(rows: list) -> list:
    out = []
    for row in rows:
        rid = row.get("_id") or row.get("id")
        if rid:
            out.append({"_id": rid, "name": row.get("name") or ""})
    return out


def funnels(pit: str, loc: str, refresh: bool = False, cache: str = None,
            timeout: int = 45) -> list:
    """Cached list_funnels."""
    path = cache_path(cache)
    blob = _cache_read(path)
    node = (blob.get(loc) or {}).get("funnels") or {}
    if not refresh and _fresh(node):
        return node["items"]
    items = _slim(list_funnels(pit, loc, timeout))
    blob.setdefault(loc, {})["funnels"] = {"fetched": int(time.time()),
                                           "items": items}
    _cache_write(path, blob)
    return items


def pages(pit: str, loc: str, funnel_id: str, refresh: bool = False,
          cache: str = None, timeout: int = 45) -> list:
    """Cached list_pages."""
    path = cache_path(cache)
    blob = _cache_read(path)
    node = ((blob.get(loc) or {}).get("pages") or {}).get(funnel_id) or {}
    if not refresh and _fresh(node):
        return node["items"]
    items = _slim(list_pages(pit, loc, funnel_id, timeout))
    per_funnel = blob.setdefault(loc, {}).setdefault("pages", {})
    per_funnel[funnel_id] = {"fetched": int(time.time()), "items": items}
    _cache_write(path, blob)
    return items


# ── resolution ───────────────────────────────────────────────────────────────

def looks_like_id(value: str) -> bool:
    """True for a 20-char base62 id (or a 24-char hex one)."""
    v = (value or "").strip()
    return bool(_ID_20.match(v) or _ID_24.match(v))


def _listing(rows: list) -> str:
    return "\n".join(f'    "{r["name"]}"  {r["_id"]}' for r in rows)


def _pick(rows: list, name_or_id: str, kind: str, scope: str,
          flag: str) -> Resolved:
    """Shared matcher. `kind` is "funnel"/"page", `scope` names where we looked."""
    rows = [r for r in rows if r.get("_id")]

    if name_or_id:
        wanted = name_or_id.strip().casefold()
        hits = [r for r in rows if (r.get("name") or "").strip().casefold() == wanted]
        if len(hits) == 1:
            return Resolved(hits[0]["_id"], hits[0]["name"], "matched by name")
        if len(hits) > 1:
            raise ResolveError(
                f'{len(hits)} {kind}s in {scope} are named "{name_or_id}". '
                f'Names are not unique in GHL, so pass the id instead:\n'
                f'{_listing(hits)}\n'
                f'  fix: {flag}-id <id>')
        raise ResolveError(
            f'no {kind} named "{name_or_id}" in {scope}. '
            f'{len(rows)} {kind}(s) there:\n{_listing(rows) or "    (none)"}\n'
            f'  the match is case-insensitive but otherwise exact — check for a '
            f'trailing space or a renamed {kind}.')

    if not rows:
        raise ResolveError(
            f"{scope} has no {kind}s, so there is nothing to resolve. "
            f"Create one first, then re-run with --refresh.")
    if len(rows) == 1:
        return Resolved(rows[0]["_id"], rows[0]["name"],
                        f"only {kind} in {scope}")
    raise ResolveError(
        f'{len(rows)} {kind}s in {scope} — say which one. Guessing between real '
        f'{kind}s is how the wrong one gets overwritten:\n{_listing(rows)}\n'
        f'  fix: {flag} "<name>"   or   {flag}-id <id>')


def resolve_funnel(pit: str, loc: str, name_or_id: str = None,
                   refresh: bool = False, cache: str = None,
                   timeout: int = 45) -> Resolved:
    """A 20-char id passes straight through; a name is matched case-insensitively;
    nothing at all resolves only when the account has exactly one funnel."""
    if name_or_id and looks_like_id(name_or_id):
        return Resolved(name_or_id.strip(), "", "explicit id")
    return _pick(funnels(pit, loc, refresh, cache, timeout),
                 name_or_id, "funnel", "this location", "--funnel")


def resolve_page(pit: str, loc: str, funnel_id: str, name_or_id: str = None,
                 refresh: bool = False, cache: str = None,
                 timeout: int = 45) -> Resolved:
    """Same rules as resolve_funnel, scoped to one funnel."""
    if name_or_id and looks_like_id(name_or_id):
        return Resolved(name_or_id.strip(), "", "explicit id")
    if not funnel_id:
        raise ResolveError("cannot resolve a page without a funnel. "
                           "Pass --funnel \"<name>\" or --funnel-id <id>.")
    return _pick(pages(pit, loc, funnel_id, refresh, cache, timeout),
                 name_or_id, "page", "this funnel", "--page")


def report(kind: str, res: Resolved) -> str:
    """The one line every tool prints, so a wrong resolution is never silent."""
    label = f'"{res.name}"' if res.name else "(by id)"
    return f"  resolved {kind:<6} {label:<26} -> {res.id}   ({res.how})"


# ── offline self-test ────────────────────────────────────────────────────────

def _self_test() -> int:
    """Fixture-only. No network, no credentials, no live account touched."""
    import tempfile

    F_ONE = [{"_id": "fnl00000000000000001", "name": "Launch"}]
    F_MANY = [{"_id": "fnl00000000000000001", "name": "Launch"},
              {"_id": "fnl00000000000000002", "name": "Evergreen"}]
    F_DUPE = [{"_id": "fnl00000000000000001", "name": "Launch"},
              {"_id": "fnl00000000000000002", "name": "launch"}]
    P_MANY = [{"_id": "pge00000000000000001", "name": "Opt-in",
               "funnelId": "fnl00000000000000001", "stepId": "stp00000000000001"},
              {"_id": "pge00000000000000002", "name": "Thank You",
               "funnelId": "fnl00000000000000001", "stepId": "stp00000000000002"}]
    LOC = "loc00000000000000001"

    results = []

    def check(name, fn):
        try:
            fn()
            results.append((True, name, ""))
        except AssertionError as exc:
            results.append((False, name, str(exc) or "assertion failed"))
        except Exception as exc:  # noqa: BLE001
            results.append((False, name, f"{type(exc).__name__}: {exc}"))

    real_curl = globals()["_curl"]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="ghl-ids-selftest-"))

    class Stub:
        """Stands in for _curl. Counts calls so cache behaviour is observable."""

        def __init__(self, funnels_payload, pages_payload):
            self.funnels_payload = funnels_payload
            self.pages_payload = pages_payload
            self.calls = 0

        def __call__(self, url, pit, timeout=45):
            self.calls += 1
            if "/funnels/page" in url:
                for param in ("funnelId=", "locationId=", "limit=", "offset="):
                    assert param in url, f"page URL missing {param} (422 in prod)"
                return json.dumps(self.pages_payload)
            return json.dumps(self.funnels_payload)

    def install(stub):
        globals()["_curl"] = stub
        return stub

    def fresh_cache(tag):
        return str(tmp / f"{tag}.json")

    try:
        # 1. exact-id passthrough must not query at all
        def t_passthrough():
            stub = install(Stub({"funnels": F_MANY}, P_MANY))
            res = resolve_funnel("pit", LOC, "fnl00000000000000001",
                                 cache=fresh_cache("t1"))
            assert res.id == "fnl00000000000000001", res
            assert res.how == "explicit id", res
            assert stub.calls == 0, f"queried the API for an id we were handed"
        check("exact-id passthrough (no API call)", t_passthrough)

        # 2. name match
        def t_name():
            install(Stub({"funnels": F_MANY}, P_MANY))
            res = resolve_funnel("pit", LOC, "Evergreen", cache=fresh_cache("t2"))
            assert res.id == "fnl00000000000000002", res
            assert res.how == "matched by name", res
        check("funnel matched by name", t_name)

        # 3. case-insensitivity
        def t_case():
            install(Stub({"funnels": F_MANY}, P_MANY))
            res = resolve_funnel("pit", LOC, "eVeRgReEn", cache=fresh_cache("t3"))
            assert res.id == "fnl00000000000000002", res
        check("name match is case-insensitive", t_case)

        # 4. single funnel auto-selects
        def t_single():
            install(Stub({"funnels": F_ONE}, P_MANY))
            res = resolve_funnel("pit", LOC, None, cache=fresh_cache("t4"))
            assert res.id == "fnl00000000000000001", res
            assert "only funnel" in res.how, res
        check("single funnel auto-selects", t_single)

        # 5. several funnels -> raise, listing them
        def t_ambiguous():
            install(Stub({"funnels": F_MANY}, P_MANY))
            try:
                resolve_funnel("pit", LOC, None, cache=fresh_cache("t5"))
            except ResolveError as exc:
                assert "Launch" in str(exc) and "Evergreen" in str(exc), exc
                assert "fnl00000000000000002" in str(exc), exc
                return
            raise AssertionError("guessed between two real funnels")
        check("ambiguous funnels raise and list both", t_ambiguous)

        # 6. duplicate names -> raise, demand the id
        def t_dupe():
            install(Stub({"funnels": F_DUPE}, P_MANY))
            try:
                resolve_funnel("pit", LOC, "Launch", cache=fresh_cache("t6"))
            except ResolveError as exc:
                assert "--funnel-id" in str(exc), exc
                return
            raise AssertionError("picked one of two identically named funnels")
        check("duplicate names raise and demand an id", t_dupe)

        # 7. not found -> raise, listing what IS there
        def t_missing():
            install(Stub({"funnels": F_MANY}, P_MANY))
            try:
                resolve_funnel("pit", LOC, "Nope", cache=fresh_cache("t7"))
            except ResolveError as exc:
                assert "no funnel named" in str(exc), exc
                assert "Launch" in str(exc), exc
                return
            raise AssertionError("invented a funnel that does not exist")
        check("unknown name raises and lists the real ones", t_missing)

        # 8. THE BUG: /funnels/page returns a BARE ARRAY, not {"pages": [...]}
        def t_bare_array():
            install(Stub({"funnels": F_ONE}, P_MANY))   # pages payload IS a list
            rows = list_pages("pit", LOC, "fnl00000000000000001")
            assert len(rows) == 2, rows
            assert rows[0]["_id"] == "pge00000000000000001", rows
            res = resolve_page("pit", LOC, "fnl00000000000000001", "Thank You",
                               cache=fresh_cache("t8"))
            assert res.id == "pge00000000000000002", res
        check("bare-array page response parses", t_bare_array)

        # 9. wrapped page response still parses (defensive, if GHL ever wraps it)
        def t_wrapped():
            install(Stub({"funnels": F_ONE}, {"pages": P_MANY}))
            rows = list_pages("pit", LOC, "fnl00000000000000001")
            assert len(rows) == 2, rows
        check("wrapped page response also parses", t_wrapped)

        # 10. single page in a funnel auto-selects
        def t_single_page():
            install(Stub({"funnels": F_ONE}, [P_MANY[0]]))
            res = resolve_page("pit", LOC, "fnl00000000000000001", None,
                               cache=fresh_cache("t10"))
            assert res.id == "pge00000000000000001", res
            assert "only page" in res.how, res
        check("single page auto-selects", t_single_page)

        # 11. cache stops the second query; --refresh forces it
        def t_cache():
            stub = install(Stub({"funnels": F_ONE}, P_MANY))
            path = fresh_cache("t11")
            resolve_funnel("pit", LOC, None, cache=path)
            assert stub.calls == 1, stub.calls
            resolve_funnel("pit", LOC, None, cache=path)
            assert stub.calls == 1, f"cache missed: {stub.calls} calls"
            resolve_funnel("pit", LOC, None, cache=path, refresh=True)
            assert stub.calls == 2, f"--refresh did not re-query: {stub.calls}"
        check("cache hit, then --refresh re-queries", t_cache)

        # 12. an API error payload becomes a readable error, not an empty list
        def t_api_error():
            install(Stub({"message": "Invalid JWT"}, P_MANY))
            try:
                resolve_funnel("pit", LOC, None, cache=fresh_cache("t12"))
            except ResolveError as exc:
                assert "Invalid JWT" in str(exc), exc
                return
            raise AssertionError("swallowed an API error as 'no funnels'")
        check("API error surfaces as an error", t_api_error)

        # 13. location_id precedence: explicit > env > .env > raise
        def t_location():
            env_path = tmp / "dotenv"
            env_path.write_text("GHL_LOCATION_ID=loc00000000000000009\n")
            saved = os.environ.pop("GHL_LOCATION_ID", None)
            try:
                assert location_id("loc00000000000000001",
                                   str(env_path)) == "loc00000000000000001"
                assert location_id(None, str(env_path)) == "loc00000000000000009"
                os.environ["GHL_LOCATION_ID"] = "loc00000000000000002"
                assert location_id(None, str(env_path)) == "loc00000000000000002"
                os.environ.pop("GHL_LOCATION_ID")
                try:
                    location_id(None, str(tmp / "does-not-exist"))
                except ResolveError as exc:
                    assert "GHL_LOCATION_ID" in str(exc), exc
                else:
                    raise AssertionError("no location id, but no error either")
            finally:
                os.environ.pop("GHL_LOCATION_ID", None)
                if saved is not None:
                    os.environ["GHL_LOCATION_ID"] = saved
        check("location_id precedence and error", t_location)

        # 14. looks_like_id boundaries
        def t_shape():
            assert looks_like_id("fnl00000000000000001")
            assert looks_like_id("0123456789abcdef01234567")   # 24-char hex
            assert not looks_like_id("Launch")
            assert not looks_like_id("Opt-in Page")
            assert not looks_like_id("")
            assert not looks_like_id("short")
        check("id shape detection", t_shape)

        # 15. report() prints the id and the provenance
        def t_report():
            line = report("funnel", Resolved("fnl00000000000000001", "Launch",
                                             "matched by name"))
            assert "Launch" in line and "matched by name" in line, line
            assert "fnl00000000000000001" in line, line
        check("report() shows what was resolved and how", t_report)

    finally:
        globals()["_curl"] = real_curl

    failed = [r for r in results if not r[0]]
    for ok, name, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail
                                                         else ""))
    print(f"\n  {len(results) - len(failed)}/{len(results)} passed"
          f"   (fixtures only — no network, no account touched)")
    return 1 if failed else 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Resolve GHL location / funnel / page ids from names, or list "
                    "what is there. Read-only: this tool never writes to GHL.",
        epilog="Every other tool here imports this, so `--funnel \"Name\"` works "
               "everywhere `--funnel-id` does.")
    ap.add_argument("--location-id", help="Sub-account id (or $GHL_LOCATION_ID, "
                                          "or .env).")
    ap.add_argument("--funnel", help="Funnel NAME (case-insensitive).")
    ap.add_argument("--funnel-id", help="Funnel id, if you already have it.")
    ap.add_argument("--page", help="Page NAME (case-insensitive).")
    ap.add_argument("--page-id", help="Page id, if you already have it.")
    ap.add_argument("--pit", help="Private Integration Token (or $GHL_PIT, .env).")
    ap.add_argument("--env-file", default=".env", help="Where to read credentials "
                                                       "(default .env).")
    ap.add_argument("--refresh", action="store_true",
                    help="Ignore the on-disk cache and re-query.")
    ap.add_argument("--cache", help=f"Cache file (default ./{CACHE_NAME}).")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="Emit machine-readable JSON instead of a report.")
    ap.add_argument("--self-test", action="store_true",
                    help="Run the offline fixture tests and exit. No credentials "
                         "needed, no network, no account touched.")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    try:
        loc = location_id(args.location_id, args.env_file)
        pit = private_token(args.pit, args.env_file)
        common = dict(refresh=args.refresh, cache=args.cache)

        want_funnel = args.funnel_id or args.funnel
        if not want_funnel and not args.as_json:
            # No funnel asked for: show the account instead of failing on ambiguity.
            rows = funnels(pit, loc, **common)
            print(f"  location {loc}")
            print(f"  {len(rows)} funnel(s):")
            for row in rows:
                print(f'    "{row["name"]}"  {row["_id"]}')
            if len(rows) != 1:
                print("\n  pass --funnel \"<name>\" to see its pages.")
                return 0
            want_funnel = rows[0]["_id"]

        fn = resolve_funnel(pit, loc, want_funnel, **common)
        pg = None
        if args.page_id or args.page:
            pg = resolve_page(pit, loc, fn.id, args.page_id or args.page, **common)

        if args.as_json:
            out = {"locationId": loc, "funnelId": fn.id,
                   "funnelName": fn.name or None, "funnelHow": fn.how}
            if pg:
                out.update({"pageId": pg.id, "pageName": pg.name or None,
                            "pageHow": pg.how})
            print(json.dumps(out, indent=1))
            return 0

        print(f"  location {loc}")
        print(report("funnel", fn))
        if pg:
            print(report("page", pg))
        else:
            rows = pages(pit, loc, fn.id, **common)
            print(f"  {len(rows)} page(s) in that funnel:")
            for row in rows:
                print(f'    "{row["name"]}"  {row["_id"]}')
        return 0
    except ResolveError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
