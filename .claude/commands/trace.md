---
description: Trace a single code path end-to-end with line citations
argument-hint: <entry point or behavior to trace>
allowed-tools: Read, Glob, Grep, Bash, TodoWrite
---

Trace: $ARGUMENTS

Follow this one path through every hop. Do not summarize the architecture — walk it.

For each step give: `file.py:line` → what happens there → what is passed onward.

Call out explicitly:
- Every branch, and what triggers each side
- Every external call, with its timeout (or "no timeout" if there isn't one)
- Every place an exception could escape, and where it would land
- Every piece of state mutated along the way

End with the shortest honest answer to: "what breaks this path?"
