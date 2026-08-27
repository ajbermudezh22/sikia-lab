---
description: Onboard into an unfamiliar codebase and produce a cited findings document
argument-hint: <path-or-repo-name> [focus area]
allowed-tools: Read, Glob, Grep, Bash, Write, Edit, TodoWrite
---

Target: $1
Focus (optional): $2

Work this in order. Write to `notes/findings-$1.md` **as you go**, not at the end —
if we run out of time, a half-finished document with real citations beats a complete
document written from memory.

## 1. Shape (fast, ~5 min of tool calls)

Get the map before any detail:
- Dependency manifest, Python version, entry points, CI config
- Directory tree two levels deep, with file counts and rough line counts
- `git log --oneline -30` and `git shortlog -sn | head` — what's moving, who moves it
- Test layout: what's covered, what conspicuously isn't

Write this as a "Shape" section. State what kind of system this is in two sentences.

## 2. Trace one request end-to-end

Pick the single most important path (if the focus area names one, use it; otherwise
pick the one the README or the busiest module points at). Follow it through **every**
hop — entry, validation, business logic, external calls, persistence, response.

Produce a numbered trace where every step cites `file.py:line`. Where the path
branches on error, say what happens on each branch.

## 3. Find the seams

Every place the system talks to something it does not control: external APIs, the
database, the filesystem, the clock, background tasks, websockets. For each one ask:
- What happens when it's slow? When it fails? When it returns something malformed?
- Is there a timeout? A retry? A fallback? Is the retry bounded?
- Is the failure observable — does anything log or alert?

This section is where the real findings come from.

## 4. Findings

Each finding gets this shape, and nothing more:

**[severity] Short claim** — `path/file.py:line`
> What the code does (observation, no interpretation).
> Why it matters (concrete failure scenario: given this input/state, this breaks).
> What I'd do (one sentence, clearly labeled as a recommendation).

Severity is one of `correctness`, `resilience`, `performance`, `clarity`.

Rules:
- Never state a finding without a line citation. If you're inferring, write
  "**Unverified:**" in front of it and say what you'd need to check.
- Rank by severity. Three real findings beat twelve speculative ones.
- If you looked for a problem in some area and did *not* find one, say so — negative
  results are information and show coverage.

## 5. Questions for the author

End with 3–5 questions that a genuinely curious engineer would ask — things the code
cannot answer on its own: intent, constraints, history, what they already know is
broken. These are the questions to ask in the Q&A.

Do not pad. Stop when the useful content stops.
