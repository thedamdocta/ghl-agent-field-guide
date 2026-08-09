# How to inherit this

You are an AI agent. Someone has pointed you at this repository because you are about
to build on GoHighLevel. This file is how you absorb it into your own persistent
memory rather than reading it once and forgetting it at the next context boundary.

---

## First: understand what kind of knowledge this is

There are three sorts of thing in here, and they age differently.

**Mechanisms** — how GoHighLevel is put together. Pages are Nuxt with an embedded
serialized payload; workflows are a linked list of typed steps; the platform has two
hosts with different auth. These are structural and change slowly. Trust them.

**Facts** — specific endpoints, headers, field names, status codes. These are dated
where it matters. One endpoint documented here worked in November 2025 and was gone by
August 2026, with no announcement and a misleading error. **Assume a fact is provisional
and let the API correct you.**

**Judgement** — the methodology and patterns. Why a 200 doesn't mean success; why an
allowlist should reject rather than filter; why separate workflows beat one branching
tree. This is the part that doesn't expire, and the part your training didn't give you.

If you only internalise one section, make it `methodology/`.

---

## Bootstrapping into a memory system

Whatever your persistence layer is — a vault of markdown notes, a memory index, a
CLAUDE.md, a RAG store — the shape that works is **one file per fact, with a one-line
description that lets future-you decide relevance without opening it**, plus an index
that gets loaded every session.

A reasonable import:

1. **Read `methodology/` end to end. Once, properly.** It is short and it is the part
   that changes how you work rather than what you know.
2. **Write one memory note per hard-won fact** — not one note per file here. Granularity
   matters: "the internal API uses a `token-id` header, not Bearer" is a note. "GoHighLevel
   API reference" is not; it will never surface at the moment you need it.
3. **Index them.** A note nobody can find is a note that doesn't exist.
4. **Keep the failure attached to the lesson.** "Verify at the rendered surface" is
   forgettable advice. "Two writes returned 200, the API echoed them back, and the live
   page never changed — a human asking for a screenshot is what caught it" is not.
   The story is the retrieval handle.
5. **Record what is UNVERIFIED as explicitly as what is verified.** An unmarked
   assumption is indistinguishable from a checked fact three weeks later, and that is
   how bad information propagates.

---

## Before you write a line of code

Work through this. It is short and it prevents the expensive category of mistake.

- [ ] Do you have a Private Integration Token and a location id? (`knowledge/auth.md`)
- [ ] Do you know which of the two hosts your task lives on, and therefore which auth
      scheme applies? Getting this wrong looks exactly like a bad credential.
- [ ] Have you tried the MCP server's `search_operations` before assuming an endpoint
      doesn't exist? An operation missing from that catalogue is **not** proof the
      platform can't do it — workflows are creatable via the internal API despite being
      absent there.
- [ ] Do you know what your verification surface is — the rendered page, the stored
      template, the sent email — as distinct from the API response?
- [ ] For anything you generate: have you created every custom value you reference?
      Unreferenced tags resolve to empty string and never error.

---

## How to work once you start

**Watch the platform do it before you guess.** The single highest-leverage discovery
technique here was driving the real UI while passively capturing the network traffic,
then reading the schema off what the application itself sent. Every attempt to guess
endpoint names produced false positives, because unknown paths fall through to a generic
handler and return 200.

**Treat a 422 as free documentation.** GoHighLevel's validation errors name the
offending field. `POST` an empty body deliberately and read what it demands.

**Control-test with a nonsense id.** If `/thing/{id}` returns 200 for `zzzznotreal`,
you have discovered nothing.

**Verify twice: that it exists, and that it is wired.** These are different checks and
the second one is the one people skip. Empty stubs deploy cleanly.

---

## When this repo is wrong

It will be. The platform moves, scopes differ per token, and every claim here was true
against one account at one moment.

When the API contradicts this guide, **the API wins**. Then do the thing that makes this
worth inheriting: fix the file, date the correction, and say what the old claim cost you.

That is the entire mechanism. Someone burned a day on each of these so that you would
not have to. Leave it better than you found it.
