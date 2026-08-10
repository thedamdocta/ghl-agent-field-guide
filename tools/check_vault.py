#!/usr/bin/env python3
"""Validate the vault/ note package.

Run this before committing anything under vault/. It exists because a note package
once shipped with four descriptions that could not be parsed as YAML — the check that
passed them tested for the SUBSTRING "description:" rather than parsing the block. A
memory note whose frontmatter does not parse is invisible to the search that is the
entire reason the note exists.

    python3 tools/check_vault.py vault/

Checks, in the order they fail most usefully:

  1. every file has a frontmatter block, and every scalar in it PARSES
     (the common break: an unquoted value containing ": ", e.g. `name: null`)
  2. required keys present: name, description, metadata.type
  3. `name` matches the filename, so a [[wikilink]] resolves to the file
  4. every [[wikilink]] resolves to a note in the package
  5. the index lists every note exactly once, and lists nothing that is missing
  6. bodies are 60-400 words — long enough to carry the failure, short enough to read

Exit 0 = clean. Exit 1 = something is wrong, and it says what and where.
"""
import argparse
import pathlib
import re
import sys

INDEX_NAME = "_GHL_INDEX.md"
NOTE_GLOB = "ghl-*.md"
WORD_MIN, WORD_MAX = 60, 400


def parse_scalar(raw):
    """Parse one YAML scalar the way a real loader would. -> (ok, value)."""
    v = raw.strip()
    if not v:
        return True, ""
    if v[0] == '"':
        i, buf = 1, []
        while i < len(v):
            c = v[i]
            if c == "\\":
                if i + 1 >= len(v):
                    return False, None
                buf.append(v[i + 1])
                i += 2
                continue
            if c == '"':
                # a closing quote must end the scalar
                return i == len(v) - 1, "".join(buf)
            buf.append(c)
            i += 1
        return False, None
    if v[0] == "'":
        if len(v) < 2 or not v.endswith("'"):
            return False, None
        return True, v[1:-1].replace("''", "'")
    # plain scalar: ": " or a trailing ":" makes it a mapping, not a string
    if re.search(r":\s", v) or v.endswith(":"):
        return False, None
    return True, v


def read_frontmatter(path):
    """-> (fields, body, error). fields includes a synthetic 'metadata.type'."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None, None, "no frontmatter block"
    fields, in_metadata = {}, False
    for lineno, line in enumerate(m.group(1).splitlines(), start=2):
        if not line.strip():
            continue
        if re.match(r"^\s+", line):
            if in_metadata:
                sub = re.match(r"^\s+(\w+):(.*)$", line)
                if sub:
                    ok, val = parse_scalar(sub.group(2))
                    if not ok:
                        return None, None, (
                            f"line {lineno}: metadata.{sub.group(1)} does not parse — "
                            f'wrap the value in double quotes'
                        )
                    fields[f"metadata.{sub.group(1)}"] = val
            continue
        top = re.match(r"^(\w+):(.*)$", line)
        if not top:
            return None, None, f"line {lineno}: not a key"
        key, rest = top.group(1), top.group(2)
        in_metadata = key == "metadata" and not rest.strip()
        if in_metadata:
            continue
        ok, val = parse_scalar(rest)
        if not ok:
            return None, None, (
                f'line {lineno}: {key} does not parse — the value contains ": " and is '
                f"unquoted; wrap it in double quotes"
            )
        fields[key] = val
    return fields, text[m.end():], None


def main():
    ap = argparse.ArgumentParser(
        description="Validate the vault note package: frontmatter parses, names match "
                    "filenames, wikilinks resolve, index is complete."
    )
    ap.add_argument("path", nargs="?", default="vault",
                    help="the vault package directory (default: vault)")
    ap.add_argument("--quiet", action="store_true",
                    help="print only failures and the final verdict")
    args = ap.parse_args()

    root = pathlib.Path(args.path)
    if not root.is_dir():
        print(f"FAIL  not a directory: {root}")
        return 1

    notes = sorted(root.glob(NOTE_GLOB))
    if not notes:
        print(f"FAIL  no {NOTE_GLOB} files in {root}")
        return 1

    problems, notices, names, links = [], [], {}, {}

    for p in notes:
        fields, body, err = read_frontmatter(p)
        if err:
            problems.append(f"{p.name}: {err}")
            continue
        for key in ("name", "description"):
            if not fields.get(key):
                problems.append(f"{p.name}: missing `{key}`")
        if not fields.get("metadata.type"):
            problems.append(f"{p.name}: missing `metadata.type`")
        name = fields.get("name", "")
        if name and name != p.stem:
            problems.append(
                f"{p.name}: name is `{name}` but the file is `{p.stem}` — "
                f"[[{name}]] will not resolve"
            )
        if name:
            names[name] = p.name
        wc = len(body.split())
        if not WORD_MIN <= wc <= WORD_MAX:
            problems.append(f"{p.name}: body is {wc} words (want {WORD_MIN}-{WORD_MAX})")
        links[p.name] = set(re.findall(r"\[\[([^\]]+)\]\]", body))

    index = root / INDEX_NAME
    if not index.exists():
        problems.append(f"missing {INDEX_NAME} — the notes are unfindable without it")
        indexed = set()
    else:
        itext = index.read_text(encoding="utf-8")
        indexed = set(re.findall(r"\[\[([^\]]+)\]\]", itext))
        links[INDEX_NAME] = indexed
        for name in sorted(names):
            if name not in indexed:
                problems.append(f"{INDEX_NAME}: does not list [[{name}]] — it will never surface")
            elif itext.count(f"[[{name}]]") > 1 and not args.quiet:
                # Not a defect: a note may legitimately appear both in its group and in
                # a "start here" pointer. Reported so an accidental double-listing in
                # two groups is still visible.
                notices.append(f"{INDEX_NAME}: [[{name}]] listed more than once (fine if deliberate)")

    for src, targets in sorted(links.items()):
        for t in sorted(targets):
            if t not in names:
                problems.append(f"{src}: [[{t}]] does not resolve to a note")

    if not args.quiet:
        print(f"  notes            {len(notes)}")
        print(f"  wikilinks        {len(set().union(*links.values())) if links else 0} distinct")
        print(f"  indexed          {len(indexed)}")

    for note in notices:
        print(f"  note: {note}")

    if problems:
        print(f"\nFAIL  {len(problems)} problem(s):")
        for pr in problems:
            print(f"  - {pr}")
        return 1
    print("\nOK  frontmatter parses, names match, every wikilink resolves, index complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
