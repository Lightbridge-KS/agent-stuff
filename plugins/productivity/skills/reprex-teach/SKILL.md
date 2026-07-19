---
name: reprex-teach
description: Teach a concept the reprex way — one minimal, self-contained, actually-run example per concept, diagram before prose, nothing written to the repo. Use when the user invokes it by name (`reprex-teach`) or near-match ("teach me X reprex-style", "minimal lesson on X", "teach me X minimally").
metadata:
  version: "2026-07-19"
---

# Reprex Teach

Teaching style for a learning conversation. Extends the reprex discipline (Jenny
Bryan) from bug reports to lessons: the claim and the evidence travel together.
Ephemeral by design — the conversation is the medium; no files, no state.

## The unit of teaching

One concept per unit, shaped like this:

```
concept named
   │
   ▼
[diagram]                    ← only if the point is structure or flow; one, plain-text or Mermaid
   │
   ▼
minimal runnable example     ← every line load-bearing, runs from zero
   │
   ▼
executed output   #> …       ← you ran it; not imagined
   │
   ▼
2–3 sentences of annotation  ← prose serves the example, never substitutes for it
   │
   ▼
offer the next delta         ← user steers
```

## Rules

- **The example IS the lesson.** Never describe behavior you could demonstrate.
  Explain after showing, not before.
- **Clean-session honesty.** Snippets run from zero: imports shown, no hidden
  state, no "assuming you already have `df`". If it can't run standalone, it
  isn't minimal yet.
- **Every line load-bearing.** If deleting a line doesn't lose the teaching
  point, delete it. Boilerplate is working-memory theft.
- **Run it when running is cheap.** Anything `uv run`-able or shell-runnable:
  execute in the scratchpad and show real output as `#>` comments. When a run
  is expensive (Flutter build, live service), unrun code is acceptable but must
  be labeled `# not run` — never present imagined output as real.
- **Diagram before paragraph.** For structure or flow, one diagram replaces
  three paragraphs. Prose is the fallback channel, not the primary.
- **Progress by delta.** The next example is the previous one plus one visible
  change, like reading a diff. Don't restart from an unrelated example
  mid-thread.
- **No artifacts.** Nothing written to the repo — scratchpad only, for
  execution. If the user wants to keep something, they'll say so.

## Anti-patterns

API tours; "here are N ways to do it" surveys; options not asked for; toy code
that wouldn't actually run; walls of prose before the first example; a second
diagram where one would do.
