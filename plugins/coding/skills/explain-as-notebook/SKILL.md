---
name: explain-as-notebook
description: >-
  Decompose a function, method, class, or module of an existing codebase into a
  runnable notebook that explains it top-down — each piece executed on concrete
  inputs with real output shown inline. Use when the user
  invokes it by name (`explain-as-notebook`) or near-match mentioning.
metadata:
  version: "2026-07-15"
---

# Explain as Notebook

Take one piece of an **existing** codebase and produce a single **runnable notebook**
that explains it by *executing the real code* on concrete mock inputs — not by describing
it in prose. The reader scrolls top-down: a call-graph map first, then each method / line
defined, run, and its actual output shown inline.

This is the inverse of the "prototype in a notebook, then promote to production" workflow.
Here the production code already exists; the skill explodes it back into the inspectable,
input→output form so a human can understand it down to the actual logic.

## Core principles

1. **Show the proof, don't assert it.** Every output in the notebook is *executed*, never
   hand-typed. If a cell claims a value, that value came from running the cell. This is the
   whole point — a static explanation already exists in the docstring.
2. **Instrument the real code; don't paraphrase it.** Import and call the *actual* symbols
   from the codebase. The notebook must not contain a simplified re-implementation that can
   silently drift from the source. (See the Hybrid rule for the one exception.)
3. **Significance over completeness.** A trivial one-line delegate is shown whole in one
   cell. Only genuinely complex code (branches, loops, regex, index math, comprehensions,
   recursion) is unrolled into line-groups. Don't generate noise.
4. **One notebook per target.** A class, a function, or a module → one artifact.
5. **Faithful or flagged.** If a line cannot run standalone and you must inline a stand-in,
   mark it explicitly so the reader knows it is not the verbatim source.

## Step 1 — Locate and read the target

1. Resolve what the user pointed at: a function, a method, a class, or a whole module/file.
   If ambiguous, ask which one.
2. Read the **real source** of the target and of everything it directly calls. Build the
   call graph outward from *each method/function* until you know what every helper it calls
   *returns* — then stop. That "I know its return value" point is the boundary, not a fixed
   number of levels. Don't drill into stdlib or third-party internals.
3. Note the target's signature, type hints, and any docstring examples — these seed the
   mock inputs in Step 4.

## Step 2 — Pick the notebook format by language

Detect the target file's language and choose the artifact:

| Language        | Format | Kernel / tooling |
|-----------------|--------|------------------|
| Python          | `.ipynb` | Python (ipykernel) |
| **R**           | **`.qmd`** | Quarto (knitr) |
| Other (JS/TS, Julia, Ruby, …) | `.ipynb` | that language's Jupyter kernel (e.g. tslab, IJulia) |

For Python `.ipynb`, defer the **edit → execute → verify mechanics** to the
`notebook-literate-python` skill (NotebookEdit → `nbconvert --execute` → NotebookRead). For
`.qmd`, author the Quarto doc and render it (`quarto render`) to verify. For other kernels,
use the same loop with that kernel.

## Step 3 — Classify each piece by complexity (depth rule)

Decide, per method/function, whether to show it whole or unroll it. Default to the shallowest
form that still reveals the logic:

```
SHOW WHOLE (one cell: input → call → output)        UNROLL INTO LINE-GROUPS
------------------------------------------          -----------------------
- thin delegate / one-liner wrapper                 - conditional branches that change result
- pure pass-through to another function             - loops / comprehensions / recursion
- trivial getter / formatter                        - regex, parsing, index / offset math
- already obvious from its signature                - multi-step transforms where intermediates matter
```

When unrolling, group lines into small logical chunks (2–5 lines) that each compute one
intermediate worth seeing — not strictly one cell per physical line. Cap pathological cases
(deep recursion, huge loops): run a couple of representative iterations and say so in a
markdown note rather than unrolling everything.

## Step 4 — Author the notebook

Structure, top to bottom:

1. **Title + call-graph map (markdown).** Open with the target name and an ASCII call tree
   so the reader has the skeleton before any code. Add a one-line "how to read this" note.

   ```
   slugify(text)                      ← entry
     ├─ _strip_accents(text)          → ascii text
     ├─ re.sub(r"[^\w]+", "-", s)     → dash-joined
     └─ s.strip("-").lower()          → final slug
   ```

2. **Setup cell (code).** Import the **real** symbols under test. Prefer importing the
   installed package; if the project isn't installed, insert the repo root on the path and
   import from there. Keep it to imports + any shared mock data.

3. **Hierarchy as markdown headers.** Mirror the code's structure with header levels so the
   notebook outline *is* the call graph:
   - `## ClassName` / `## module` — role in one line.
   - `### method_name()` — what it does and why; then its code cell(s).
   - `#### line-group label` — for unrolled chunks inside a complex method.

   Put a short markdown cell (what / why, 1–3 sentences) **above** each code cell. Let the
   header hierarchy carry the structure; keep prose tight.

4. **Each code cell follows define → run → show:**
   - Construct a small, realistic mock input **inferred from the target's own
     signature/types/docstring** (not invented domain trivia).
   - Call the real symbol, or run the real line(s) with concrete values bound.
   - Surface the result — and for unrolled groups, every intermediate variable — as the
     cell's output (a bare expression, or `print()` for multi-value steps).
   - Reuse a mock input across cells when continuity helps the reader follow one example
     through the call chain.

### The Hybrid fidelity rule

Run the verbatim source lines wherever they can execute. Two situations come up:

**Dominant case — instrumenting a whole method.** You construct a real instance, then copy
the method's verbatim source lines into a cell with `self.X` bound to that instance's
attributes. This is reconstruction, but faithful. Don't tag every such cell as `inlined:`
(that's noise). Instead:
- Label the cell once: `# Verbatim source lines N-M, with self.X bound to <instance>`.
- **Prove it matches** by asserting the reconstruction equals the real call, e.g.
  `assert reconstructed == extractor.extract(text)` — a stronger guarantee than a comment.

**Exception — a single line that can't run standalone** (needs closure/private state or a
value only produced mid-method, and you can't bind it). Inline a faithful stand-in and flag
*that line*:

```python
# inlined: real line is `self._compiled.search(text)`; reconstructing the compiled pattern here
pattern = re.compile(r"[^\w]+", re.IGNORECASE)
match = pattern.search(text)
match  # show it
```

Never silently substitute. The reader must be able to tell executed-real from reconstructed.

### Pairing unit tests as interactive examples (opt-in, off by default)

**Default: off.** Only when the user explicitly asks (e.g. "include the tests", "pair the
unit tests", "show each test variation live") — then follow
[references/test-pairing.md](references/test-pairing.md). When off, ignore tests entirely.

## Step 5 — Execute and verify

Run the whole notebook on a fresh kernel. Every cell must execute cleanly and every shown
output must be real. Fix any cell that errors (usually an import path or an under-specified
mock). For `.qmd`, render with Quarto and confirm it completes.

**Execution prerequisites (the most common failure point):**
- If the kernel/`nbconvert` isn't in the project env, provision it ephemerally rather than
  installing into the project — e.g. with uv:
  `uv run --with jupyter --with nbconvert --with ipykernel jupyter nbconvert --to notebook --execute --inplace <path>`.
- The kernel binds loopback ports, so execution must run with the command sandbox disabled.
  This and the rest of the loop are exactly what `notebook-literate-python` covers (see its
  gotchas) — load that skill before running, don't rederive it here.

## Output location

Default: `_dev/explain/explain-<slug>.<ext>`, where `<slug>` is the target name in
snake_case (`<ext>` = `ipynb`, or `qmd` for R). Create the directory if it does not exist.
Accept an explicit output path argument that overrides this default. These are **scratch
explainer artifacts**, not committed docs — if the repo doesn't already ignore the output
dir, mention that the user may want to gitignore it.

## Quality checklist before finishing

- [ ] Notebook opens with the ASCII call-graph map.
- [ ] Header hierarchy mirrors the real class/function structure.
- [ ] Every symbol imported/called exists in the codebase (no invented names).
- [ ] Trivial pieces shown whole; only complex ones unrolled (no noise).
- [ ] Every output was executed on a fresh kernel — none hand-typed.
- [ ] Any inlined/reconstructed line is flagged with an `inlined:` comment.
- [ ] Mock inputs derive from the target's own signature/types/docstring.
- [ ] Exactly one artifact, at the resolved output path.
- [ ] Test-pairing only if the user opted in; if on, asserts are shown as live tables with
      `# expect:` comments and exceptions are caught (never abort the run).
