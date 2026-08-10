#!/usr/bin/env python3
"""
check_docs.py — verify every documented command against the real parsers.

WHY THIS EXISTS
---------------
An agent inheriting this repo followed `knowledge/building-from-scratch.md` and hit
two commands that referenced flags no parser had:

    create_steps.py  --name "Opt-in"      # the flag is --step NAME:PATH
    inject_page.py   --file page.json     # the flag is --page-data

Step 4 of the golden path and step 7, the write. Both load-bearing, back to back, in
the one file called "building from scratch". It concluded the tools were broken and
handed the work back to a human. The tools were fine. The documentation had been
written from memory of what the tools *should* take, and never run.

This is the same failure this repo keeps making in different clothes: the description
and the artifact drift, and the description is what ships. A prose rule ("check your
examples") does not survive a tired session. A check that fails does.

Run it before every commit. Wire it into CI if you have one.

    python3 tools/check_docs.py .

Exit 1 on any mismatch, so it can gate a commit hook.

WHAT IT CATCHES
  * a documented flag no parser defines
  * a documented tool file that does not exist
  * a relative markdown link pointing at a missing file

WHAT IT DOES NOT CATCH
  It does not execute anything, so it cannot tell you a command is semantically
  wrong — only that it could not possibly parse. That is the cheap half, and it is
  the half that was failing.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

# `python3 tools/foo.py --a --b` or `python3 foo.py ...`, possibly line-continued
CMD = re.compile(r"python3\s+(?:tools/)?([a-z_]+\.py)((?:[^\n`]|\\\n)*)")
FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")
LINK = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def strip_quoted(tail: str) -> str:
    """Blank out quoted argument VALUES before hunting for flags.

    `--root-vars '{"--gp-ground":"#fff"}'` contains two things that look like flags
    and are CSS custom-property names inside a JSON value. Flagging them is a false
    positive, and false positives are how a checker teaches you to ignore it — the
    exact failure mode this file exists to prevent.
    """
    return QUOTED.sub(lambda m: " " * len(m.group(0)), tail)


SUBCMD = re.compile(r"^\s{2,}\{([a-z,|-]+)\}", re.M)


def parser_flags(tool: pathlib.Path) -> set[str] | None:
    """Every flag a tool accepts — including its SUBCOMMANDS' flags.

    Top-level `--help` on a subcommand parser does not list the subcommands' own
    options, so checking only that produces false positives on perfectly correct
    documentation. A noisy checker trains you to skim its output, which is how the
    real failure gets through — the same lesson scrub_secrets.py carries.
    """
    def flags_of(argv):
        try:
            out = subprocess.run([sys.executable, str(tool), *argv],
                                 capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None, ""
        if out.returncode != 0:
            return None, ""
        return set(FLAG.findall(out.stdout)), out.stdout

    top, help_text = flags_of(["--help"])
    if top is None:
        return None
    for group in SUBCMD.findall(help_text):
        for sub in group.split(","):
            sub = sub.strip()
            if not sub:
                continue
            sub_flags, _ = flags_of([sub, "--help"])
            if sub_flags:
                top |= sub_flags
    return top


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".", help="repo root (default: .)")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    tools_dir = root / "tools"
    if not tools_dir.is_dir():
        sys.stderr.write(f"ERROR: no tools/ under {root}\n")
        return 2

    cache: dict[str, set[str] | None] = {}
    problems: list[str] = []
    checked = 0

    for md in sorted(root.rglob("*.md")):
        if ".git" in md.parts:
            continue
        text = md.read_text(errors="ignore")
        rel = md.relative_to(root)

        # documented commands
        for name, tail in CMD.findall(text):
            tool = tools_dir / name
            if not tool.is_file():
                problems.append(f"{rel}: references tools/{name}, which does not exist")
                continue
            if name not in cache:
                cache[name] = parser_flags(tool)
            known = cache[name]
            if known is None:
                problems.append(f"{rel}: tools/{name} --help failed; cannot verify")
                continue
            for flag in FLAG.findall(strip_quoted(tail)):
                checked += 1
                if flag not in known:
                    problems.append(
                        f"{rel}: `{name} {flag}` — no such flag. "
                        f"Accepts: {', '.join(sorted(known)[:8])}…")

        # relative links
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (md.parent / target.split("#")[0]).exists():
                problems.append(f"{rel}: dead link -> {target}")

    if problems:
        print(f"{len(problems)} problem(s):\n")
        for p in problems:
            print(f"  {p}")
        print(f"\n({checked} documented flags checked)")
        return 1

    print(f"OK — {checked} documented flags all exist, no dead links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
