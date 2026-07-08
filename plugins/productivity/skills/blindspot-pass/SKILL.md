---
name: blindspot-pass
description: Map the user's relevant unknown unknowns for a task before planning, then help them sharpen the request. Use when the user asks for a "blindspot pass", says they know little about the area they're about to change, or wants to find out what they don't know before prompting or planning.
metadata:
  version: "2026-07-08"
---

I'm about to work in territory I don't know well. Do a pre-work reconnaissance pass: map my **relevant unknown unknowns** — not a general codebase tour, only what would change my approach or my prompt.

Explore the target area first; ground every finding in what's actually there, not in what's typical.

Deliver three things:

1. **What I don't know that matters** — existing modules, constraints, conventions, gotchas in the target area, ranked by how much they'd reshape the work.
2. **Questions I should be asking** but haven't.
3. **A sharper version of my request**, rewritten with the above.

This is a framing pass — not a plan, not an implementation. Deliver the three outputs and stop; don't start building.

Natural order: blindspot pass → plan mode → grilling. A blindspot pass earns me the right to have a plan; grilling stress-tests the plan I have.
