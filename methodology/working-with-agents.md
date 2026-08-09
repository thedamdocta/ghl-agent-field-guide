# Working With Agents — Delegating GoHighLevel Work

> **Status:** these practices come from running multi-agent builds on real client work —
> six-agent parallel fan-outs, five-lens review panels, and the repair rounds that
> followed. Every rule here replaced a specific thing that went wrong.

---

## Why this file exists in a GoHighLevel guide

Because most of this work is not one agent typing. It is one agent coordinating several,
and the coordination failures are as expensive as the platform failures — with the extra
problem that a coordination failure produces *confident, well-written, wrong* output
rather than an error.

Three things below are the load-bearing ones:

1. **Ownership is defined by files, not by tasks.**
2. **Browser and API agents are a scarce resource; file-only agents are nearly free.**
3. **An agent's self-report is a lead, not evidence.**

---

## 1. File-level ownership is what prevents collisions

The single practice that made parallel builds work: **give each agent an exclusive list
of files it owns, and let no two lists intersect.**

Not "you handle the date logic, you handle the pickers" — that is a *task* boundary, and
task boundaries leak. Two agents given adjacent tasks will both reasonably decide they
need to touch the shared types file, the shared stylesheet, or the shared config, and
you will get last-writer-wins corruption that no one reports because both agents
succeeded.

Two builds run this way — a six-page parallel rebuild and a six-lane application build —
produced **zero collisions**. The mechanism was not luck or careful merging. It was that
each lane had an explicit file list and no file appeared on two lists.

### How to actually do it

- **Write the shared rules to a spec file first, and have every agent read it.** Palette,
  naming conventions, the component vocabulary, the invariants. Shared knowledge goes in
  a document all lanes read; it does not go in a file two lanes both edit.
- **List the files each agent may create or modify, explicitly, in its prompt.** If an
  agent believes it needs a file outside its list, it must report that rather than edit
  it.
- **Give shared files a single owner.** If four lanes need a change to one shared module,
  that module belongs to one lane, and the other three send it requests. Serialising one
  file is cheaper than reconciling four versions of it.
- **Add a scribe.** One agent that owns the log, the status file, and the handoff notes,
  and writes nothing else. Without it, either every lane writes to the log (collision) or
  nobody does (no record).

### The corollary for reviewers

Review agents get **read-only access**. No writes, no browser, no API. Two reasons: they
must not mutate the artifact they are assessing, and — see below — they must not compete
for the single browser connection.

---

## 2. Budget the resources before you spawn

### RAM is a real constraint and it is checkable

**Check available memory before spawning a fan-out, and reclaim it after.** On the
builds documented here, the working discipline was to hold roughly 5.5–6 GB free
throughout, and to explicitly close out every agent and release its ports at the end —
one teardown reclaimed 7.2 GB.

This sounds like housekeeping and is not. An agent that runs out of memory mid-task does
not necessarily fail loudly; it can produce truncated output, drop a step, or hang in a
way that reads as "still working."

### The cost asymmetry: file-only agents are cheap, browser agents are not

| Agent type | Cost | Parallelism |
|---|---|---|
| File-only (read, write, analyse) | Low — no browser process | Six or more concurrently is fine |
| API-calling | Low, but rate-limited and credential-bound | Parallel is fine; watch for shared token expiry |
| Browser-driving | **High** — a full Chrome per agent, plus a CDP connection | Effectively **one at a time** |

The parallel fan-outs that worked were **file-only**. That was the enabling constraint,
not a limitation: six lanes writing page builders, style systems, and API layers need no
browser at all, because verification is a separate, serial phase.

### Browser work is serial, and there is a deeper reason than RAM

Beyond memory: on this platform, **all frame work must happen inside one connection.**
Frame references die between connections, and the builders are cross-origin SPA iframes
(see `failure-modes.md` §6.3). Two agents sharing one Chrome will invalidate each
other's frame handles. Two agents each launching their own Chrome against the same
authenticated profile will fight over the profile lock.

**One browser agent at a time, holding one connection, doing mount → inspect → act →
verify in a single run.** Plan the pipeline around that, rather than discovering it.

### Which phases parallelise

- **Parallel:** generation, rewriting, analysis, review, mechanical edits across disjoint
  file sets.
- **Serial:** anything touching the browser, anything holding a short-lived credential,
  integration, and final verification.

And estimate in the right unit. "N mechanical edits across N files" is one agent per
batch running concurrently — wall clock is roughly the slowest lane, not the sum. Human-
scale estimates ("half a day") systematically overstate this kind of work and understate
the serial browser phases, which are the actual bottleneck along with any step that
requires a human to click something.

---

## 3. Agent self-reports are LEADS, not evidence

**Re-measure every claim before acting on it.**

This is not distrust of the agents; it is a property of the medium. An agent reporting
on work it did, or on an artifact it reviewed, is producing an assessment, and
assessments have error bars that its confident prose does not display.

From a five-lens review panel run on a real build, where every finding was re-measured
before entering the fix queue:

- **One finding was overstated.** Acting on it directly would have caused two wasted
  edits to code that was fine.
- **One finding was wrongly dismissed** — by me, because I measured the wrong symptom.
  The finding was real. My measurement was aimed at a quantity correlated with the
  defect rather than the defect.

Both directions matter. The failure mode is not "agents exaggerate." It is that **a
report and a measurement are different kinds of object**, and only one of them settles a
question.

### The corollary that saves the most time

**The panel was right and my tooling was wrong, four times out of four.**

Three separate verification scripts in one project were independently defective — one
counted the wrong element types, one measured the wrong region of a document, one had a
regex that false-positived. The reviewers disagreed with each of them and were correct
each time.

So the rule is not "trust the measurement over the agent." It is:

> **Measure the defect, not a symptom of it — and verify your measuring instrument
> against a known-good and a known-bad input before you trust its verdict.**

See "verify your verifier" in `verification.md`.

---

## 4. Give reviewers evidence that is actually current

A review round once scored a defect that had **already been fixed**, because the
screenshots handed to the reviewers were captured mid-edit. The entire verification table
in that round's output was wrong as a result, and reconciling it cost more than the round
saved.

**Capture evidence AFTER the last edit and BEFORE launching the reviewers.** Freeze the
artifact, then capture, then launch. If an edit lands during a review round, the round is
scoring a document that no longer exists.

This applies to any evidence bundle: screenshots, rendered HTML dumps, generated JSON,
diff output.

---

## 5. Panels for judgment, measurement for facts

The review structure that worked: **five seats plus a chair, used for judgment questions
only.** Facts are settled by measurement, never by vote.

The seats used on design work, adaptable to other domains:

| Seat | Brief |
|---|---|
| Contrarian | Argue the direction itself is wrong; name every borrowed or default gesture |
| Executioner | Craft only — alignment, spacing, type, states, accessibility |
| Expansionist | What is **missing**; where restraint became emptiness |
| First-principles | Does this achieve the actual goal for the actual audience? Rewrites, not critique |
| Outsider | Cold naive eye; what would a stranger think this cost? |

Operating rules that make it work:

- **Agreement between seats means nothing. The chair decides.** Five agents agreeing is
  five samples from a correlated distribution, not corroboration.
- **Every seat scores the same dimensions on the same scale**, so the chair can read the
  *spread*. Disagreement between seats is the signal; consensus is noise.
- **Seats get read-only access.** No browser, no API, no writes.
- **Re-measure before queueing a fix.** Every finding, without exception. See §3.
- Loop: review → fix → re-capture → re-review, against an explicit exit criterion, rather
  than an open-ended "make it better."

The value over a single reviewer is not thoroughness — it is **structural coverage of
different failure classes**. A single craft-focused audit re-found the same class of
defect across multiple rounds and improved the score without ever asking whether the
thing worked for its audience. The first-principles and outsider seats catch what a craft
audit structurally cannot.

---

## 6. What to put in an agent's prompt for this platform

Specific to GoHighLevel work, because these are the instructions whose absence produced
bad output:

- **The exclusive file list.** (§1)
- **The shared spec file to read first**, so conventions are not re-derived per lane.
- **The verification standard**, stated as an artifact rather than an adjective. "Done
  means you can paste the rendered-surface URL and the grep result," not "done means
  verified." See the DONE receipt in `verification.md`.
- **The specific silent failure modes their lane can produce.** A lane emitting merge
  tags needs to know unknown tags resolve to the empty string. A lane cloning exemplars
  needs the role-inheritance trap. Handing an agent `failure-modes.md` is cheaper than
  handing it the bug.
- **An explicit instruction to report rather than expand scope.** If an agent concludes
  it needs a file outside its list, or a capability it was not given, that is a report,
  not an action.
- **What NOT to touch.** Live client accounts, production forms, published workflows,
  anything with real contact data. Read-only observation against production is usually
  fine; writes belong on a throwaway object first.

---

## 7. Cheap habits that prevented expensive sessions

**Read the project's own notes before solving anything.** More than once, a capability
was declared missing and hand-built around while working tooling for it already existed
in the same project's history. One grep of the session log corrected it. Search your own
prior work before you search the API.

**Document the pattern immediately after solving it, not at session end.** Sessions end
unpredictably. The knowledge that survives is the knowledge that was written down at the
moment of discovery.

**Prefer text-returning checks over screenshots.** A full interaction loop — event
dispatch, state change, computed style, clipboard capture — can be verified with scripted
DOM inspection returning structured JSON, at zero image cost. Reserve screenshots for
questions where rendered pixels genuinely are the question. Note the one important
exception: it was a *screenshot request* that caught the biggest false victory in this
guide (`verification.md`). The rule is "text for functional questions, pixels for visual
ones" — and "did this actually render" is a visual question.

**Search exhaustively before declaring absence.** Three or more pattern variations —
literal label, formatted label with punctuation, value-shape regex — before saying "not
found." A narrow grep on a structured document produces confident false negatives, and
those poison every decision downstream.

**Use absolute paths.** Working directory does not reliably persist between tool calls in
some harnesses, and path drift has produced real damage — in one case burning a hosting
provider's deployment quota by uploading from the wrong directory.

**Design agent-facing tooling to be zero-setup.** Any tool with a "run the index first"
or "install this before it works" step is a tool that will silently produce wrong results
the day someone forgets the ritual. If a prerequisite exists, the tool should perform it
or fail loudly with a one-line fix — never degrade quietly to a lesser result.

---

## Related

- `verification.md` — the standard an agent's output must meet, and the DONE receipt
- `failure-modes.md` — hand this to any agent writing GoHighLevel payloads
- `discovery.md` — why a read-only observer agent is the safest way to learn a new
  surface
