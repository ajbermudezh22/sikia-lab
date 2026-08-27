---
description: Turn a findings document into a spoken 5-minute walkthrough
argument-hint: <path to findings file>
allowed-tools: Read, Write, Edit
---

Source: $ARGUMENTS

Rewrite these findings as something to *say out loud* in 5 minutes, not read from.

Structure:
1. **What this system is** — two sentences, no jargon the interviewer didn't use first.
2. **How I approached it** — three sentences on method and why. Mention what I chose
   *not* to look at and why that was the right call under time pressure.
3. **The trace** — the one path, walked at the level of "and then it hands off to X".
   Keep file references handy but don't read line numbers aloud.
4. **Findings** — lead with the most severe. For each: what it does, the concrete
   failure, what I'd do. Thirty seconds each, maximum.
5. **What I'd do next with a week** — shows judgment about priority, not just detection.
6. **My questions for you** — the real ones.

Rules for the output:
- Short sentences. This is speech.
- Mark anything uncertain with a spoken hedge that is honest but not weak:
  "I didn't verify this, but the shape suggests…"
- No bullet soup. Write it as connected prose I can glance at.
- Put the 3–5 questions at the very bottom in a box I can find fast.
