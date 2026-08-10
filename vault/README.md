---
name: ghl-vault-readme
description: This folder is a drop-in package of 51 atomic GoHighLevel memory notes; copy the ghl-*.md files into your vault and add _GHL_INDEX.md to your index.
metadata:
  type: reference
---

# The vault package

51 atomic memory notes distilled from this repository — one file per fact, each with a
one-line `description` stating the fact itself, so it surfaces when your memory search
hits it rather than only when you remember to re-read a document.

A repo gets read once. A vault gets surfaced at the moment of need. Long prose does not
retrieve: an agent searching *"why is my token unauthorized"* needs a hit, not a 400-line
file. Every note keeps the failure that taught it attached, because the story is the
retrieval handle.

## Install

1. Copy the `ghl-*.md` files into your vault or memory directory.
2. Copy `_GHL_INDEX.md` too, and paste its lines into your own index — the file your
   session-start protocol already loads. That is the step that makes them findable.
3. Search normally. Notes cross-link to each other with wiki-style double-bracket links,
   so one hit pulls its neighbours in with it.

Every `name` is prefixed `ghl-` so nothing collides with your own notes. `type: reference`
is a platform fact; `type: feedback` is a working-practice lesson.

Designed for an Obsidian-style vault, and it works in any one-file-per-fact memory system
— the frontmatter is three fields and the body is plain markdown.

## Adding or editing a note

Run `python3 ../tools/check_vault.py .` before you commit one. It parses the
frontmatter properly rather than looking for the word `description`, which is how four
unparseable notes shipped here once — a value containing `": "` and left unquoted reads
as a nested mapping, not a string, and the note silently stops being findable. If a
description contains a colon followed by a space, wrap the whole value in double quotes.

## Trust

Every claim came from live observation against a real account, and anything unverified
says **UNVERIFIED** in the sentence. The platform ships continuously and these notes do
not: when the API contradicts a note, the API wins. Fix the note and say what the old
claim cost. Start with [[ghl-two-hosts-two-schemes]] and
[[ghl-do-not-trust-a-recorded-fact]].
