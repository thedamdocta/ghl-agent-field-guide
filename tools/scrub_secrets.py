#!/usr/bin/env python3
"""
scrub_secrets.py — pre-publication scan for a knowledge repo derived from client work.

Why this exists: a knowledge base like this one is written by copying lessons out of
real client projects. That is exactly the process most likely to carry an account id,
a CDN URL or a client's name along with the lesson. This is the gate that runs before
anything is pushed.

It looks for two classes of thing:

  1. LITERALS you supply — your actual token, your actual location id, your client's
     name. A generic scanner cannot know these, and they are the ones that matter most.
     Pass them with --secret (repeatable) or point at an env file with --env-file.

  2. PATTERNS that look like credentials or platform object ids regardless of value.

Two design notes worth keeping if you adapt this:

  * A NOISY SCANNER IS A USELESS SCANNER. The first version of this flagged the public
    API base URL and the API version string, because they happened to live in the same
    .env as the real token. Twenty-one false positives will train you to skim the
    output, which is how a real one gets through. Public constants are excluded, and
    the object-id pattern requires mixed case AND a digit so it stops matching English
    camelCase identifiers like `appointmentCondition`.

  * FAIL CLOSED. Exit code 1 on any finding, so it can gate a commit hook or CI.

Usage:
  python3 scrub_secrets.py PATH
  python3 scrub_secrets.py PATH --env-file ../project/.env --secret "Client Name"
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

# Values that are public platform constants, never secrets, and which commonly sit in
# the same .env as real credentials.
PUBLIC_CONSTANTS = {
    "https://services.leadconnectorhq.com",
    "https://backend.leadconnectorhq.com",
    "2021-07-28",
}

# A brand palette is an identifier too. This was learned the hard way: the client's
# accent hex shipped inside an HTML example and the scan missed it because only ONE
# of their colours was on the secret list. If you are sanitising work done for a
# client, pass EVERY colour in their palette with --secret, not just the obvious one.
PATTERNS = {
    "brand palette hex (pass yours via --secret)":
        r"(?i)#(?:0B0B0D|B08A5E|17131A|DBA49E|EDE6DF|837C74|2A2226)\b",
    "private integration token":
        r"pit-[0-9a-f]{8}-[0-9a-f-]{4,}",
    "JWT / bearer token":
        r"eyJ[A-Za-z0-9_-]{20,}",
    "OpenAI-style key":
        r"sk-[A-Za-z0-9]{20,}",
    "GitHub token":
        r"gh[pousr]_[A-Za-z0-9]{20,}",
    "AWS access key":
        r"AKIA[0-9A-Z]{16}",
    "platform CDN asset (embeds an account id)":
        r"assets\.cdn\.filesafe\.space/[A-Za-z0-9]{15,}",
    # A GoHighLevel object id is 20 chars, mixed case, with at least one digit.
    # All three conditions are needed or this matches ordinary camelCase words.
    "20-char platform object id":
        r"\b(?=[A-Za-z0-9]{20}\b)(?=[^\s]*[a-z])(?=[^\s]*[A-Z])(?=[^\s]*[0-9])[A-Za-z0-9]{20}\b",
    "email address":
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "absolute home path":
        r"/(?:Users|home)/[a-z][a-z0-9_-]*/",
}

# Placeholders and documentation examples that are supposed to be there.
ALLOW = re.compile(
    r"(?i)("
    r"example\.(com|org|net)|your-?(email|token|key)|<YOUR_[A-Z_]+>|"
    r"\{[a-zA-Z]+Id\}|\{id\}|noreply@|"
    r"pit-0{8}|x{8,}|0{16,}|"
    r"/Users/username/|/home/user/"
    r")"
)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist"}


def load_env_secrets(path: pathlib.Path) -> list[str]:
    out = []
    for line in path.read_text().splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        _, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value and len(value) > 8 and value not in PUBLIC_CONSTANTS:
            out.append(value)
    return out


def scan(root: pathlib.Path, secrets: list[str]) -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(p in SKIP_DIRS for p in path.parts):
            continue
        try:
            text = path.read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(root))

        for secret in secrets:
            if secret in text:
                findings.append((rel, "LITERAL SECRET", secret[:16] + "…"))

        for label, pattern in PATTERNS.items():
            for match in re.finditer(pattern, text):
                fragment = match.group(0)
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.start())
                line = text[line_start:line_end if line_end != -1 else None]
                if ALLOW.search(fragment) or ALLOW.search(line):
                    continue
                findings.append((rel, label, fragment[:48]))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="directory to scan")
    ap.add_argument("--env-file", action="append", default=[],
                    help="read real secret VALUES from this .env (repeatable). "
                         "The file itself is never scanned or copied.")
    ap.add_argument("--secret", action="append", default=[],
                    help="an exact string that must not appear — a client name, an "
                         "account id (repeatable)")
    args = ap.parse_args()

    root = pathlib.Path(args.path).resolve()
    if not root.is_dir():
        sys.stderr.write(f"ERROR: not a directory: {root}\n")
        return 2

    secrets = list(args.secret)
    for env_path in args.env_file:
        p = pathlib.Path(env_path).expanduser()
        if not p.is_file():
            sys.stderr.write(f"ERROR: --env-file not found: {p}\n")
            return 2
        secrets += load_env_secrets(p)

    if not secrets:
        sys.stderr.write(
            "NOTE: no --secret or --env-file given, so only generic patterns are\n"
            "      checked. Your own account ids and client names will NOT be caught.\n\n")

    findings = scan(root, secrets)
    if not findings:
        print(f"CLEAN — {root} has nothing flagged.")
        return 0

    seen = set()
    unique = [f for f in findings if not (f in seen or seen.add(f))]
    print(f"{len(unique)} finding(s) — DO NOT PUBLISH until these are resolved:\n")
    for rel, label, fragment in unique:
        print(f"  {rel:44s} {label:28s} {fragment}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
