---
name: tidy-first-coder
description: >
  Language-agnostic code tidying based on Kent Beck's "Tidy First?" principles. Analyzes code
  for structural improvement opportunities, proposes ranked tidyings with coupling/cohesion
  analysis, and applies confirmed changes. Use this skill whenever the user mentions tidying,
  cleaning up, or refactoring code. 
metadata:
  version: "2026-07-25"
---

# Tidy First Coder

Tidy code before changing behavior. The idea (from Kent Beck's "Tidy First?") is that small,
safe structural improvements — applied *before* you add features or fix bugs — make the real
change easier, safer, and cheaper. A tidying never alters what the code does; it only changes
how the code is organized.

Think of it like clearing your workbench before starting a project. The project goes faster
when you're not fighting clutter.

## Workflow

Follow three phases: **Analyze → Propose → Apply**. Always present proposals before touching
code — the user decides what gets applied. Skip straight to Apply only if the user explicitly
says "just apply" or "fix it all."

### Phase 1: Analyze

Scan the code for three things:

1. **Tidying opportunities** — match against the Tidying Catalog below
2. **Coupling hotspots** — things connected that shouldn't be (see Coupling Types)
3. **Cohesion gaps** — related logic/data that is scattered apart (see Cohesion Indicators)

Read the code the way a new team member would. Where do you get confused? Where do you have
to jump around? Where would a small change ripple outward? Those are your signals.

### Phase 2: Propose

Present findings in two sections:

**Section A — Coupling & Cohesion Summary**

3-8 bullet points. Be specific — name functions, lines, variables:

- **Coupling hotspots**: which elements are unnecessarily tangled, and what type of coupling
- **Cohesion gaps**: what belongs together but lives apart
- **Change risk**: where a modification would force cascading edits

**Section B — Tidying Proposals**

A prioritized table (highest-impact first):

```
| #  | Pattern            | Location       | Rationale                          |
|----|--------------------|----------------|------------------------------------|
| 1  | Guard Clauses      | fn process:42  | Deep nesting, 4 levels             |
| 2  | Extract Helper     | fn render:78   | Duplicated block (also at ln 112)  |
| 3  | Reading Order      | lines 20-60    | Helper defined after caller        |
```

Then ask the user:
> Apply all, pick specific numbers, or skip?

### Phase 3: Apply

Apply only what the user confirmed. After applying, show a brief summary:

```
## Applied Tidyings

- ✅ #1 Guard Clauses at fn process — removed 2 nesting levels
- ✅ #3 Reading Order — moved helper above caller

No behavioral changes were made.
```

Why keep structural and behavioral changes separate? Because if something breaks after a
tidying, you know the tidying caused it. If you mix tidying with feature work, debugging
becomes a guessing game. This is the single most important discipline in the skill.

---

## Tidying Catalog

Each tidying is small, safe, and reversible. No behavior changes.

### Guard Clauses
- **Rule:** Replace nested `if` with early return/continue/throw.
- **Trigger:** Indentation ≥ 3 levels; null/error checks wrapping the entire body.
```
if cond:              if !cond: return
    ...body...   →    ...body...
```

### Dead Code
- **Rule:** Delete unreachable or unused code.
- **Trigger:** Unreachable branches, commented-out blocks, unused variables/imports/functions.

### Normalize Symmetries
- **Rule:** Make similar code look similar; identical code look identical.
- **Trigger:** Two+ blocks doing the same thing with cosmetic differences.

### New Interface, Old Implementation
- **Rule:** Create the interface you wish you had; implement it by calling the old code.
- **Trigger:** Awkward API called from many places; you want a better signature.

### Reading Order
- **Rule:** Reorder definitions so code reads top-to-bottom (caller before callee, public before private).
- **Trigger:** Reader has to jump around to understand flow.

### Cohesion Order
- **Rule:** Move code that changes together so it sits physically adjacent.
- **Trigger:** Edits frequently span distant parts of a file; related fields/methods are separated by unrelated ones.

### Extract Helper
- **Rule:** Pull a coherent block into its own named function/method.
- **Trigger:** A block does one identifiable sub-task; duplicated logic; a comment explains "what" a block does (the comment becomes the function name).

### Inline
- **Rule:** Replace a trivial helper by putting its body at the call site.
- **Trigger:** Helper called once; indirection costs more than the abstraction gains.

### Chunk Statements
- **Rule:** Add blank lines between groups of statements that do different things.
- **Trigger:** A long run of statements with no visual separation.

### Move Declaration Closer to Use
- **Rule:** Declare variables just before first use, not at the top.
- **Trigger:** Large gap between declaration and use.

### Explaining Variable
- **Rule:** Extract a sub-expression into a named variable that explains intent.
- **Trigger:** Complex boolean, arithmetic, or chained expression.

### Explaining Constant
- **Rule:** Replace magic literals with named constants.
- **Trigger:** Bare numbers/strings whose meaning is not obvious from context.

### One Pile
- **Rule:** Temporarily inline everything into one big block to see the full picture, then re-extract cleanly.
- **Trigger:** Over-fragmented code where the logic is invisible behind too many tiny functions.

### Explicit Parameters
- **Rule:** Replace implicit context (globals, env, config singletons) with explicit parameters.
- **Trigger:** Function depends on external state not visible in its signature.

### Delete Redundant Comments
- **Rule:** Remove comments that restate exactly what the code says.
- **Trigger:** Comment adds no insight beyond reading the code itself.

---

## Coupling & Cohesion Analysis

Understanding structure is what makes tidying strategic rather than cosmetic. When you analyze
code, report coupling and cohesion so the user sees *why* a tidying matters, not just *what*
to change.

### Coupling Types (things to reduce)

Listed from most harmful to least:

| Type          | What it looks like                                       | Why it hurts                               |
|---------------|----------------------------------------------------------|--------------------------------------------|
| **Content**   | One module reaches into another's internals              | Any internal change breaks the caller      |
| **Common**    | Shared global/mutable state                              | Changes radiate unpredictably              |
| **Control**   | Boolean/enum param that switches callee behavior         | Caller must know callee's internal logic   |
| **Stamp**     | Passing a whole struct when only one field is needed      | Creates false dependency on full structure |
| **Temporal**  | Must call A before B (implicit ordering)                 | Fragile sequencing, breaks if reordered    |
| **Data**      | Modules share data via parameters                        | This is normal and acceptable              |

Aim to convert higher types to lower ones. For example, replace a global (Common) with a
parameter (Data).

### Cohesion Indicators (things to increase)

| Indicator            | What to look for                                  |
|----------------------|---------------------------------------------------|
| **Changes together** | Functions/files frequently modified in same commit |
| **Reads together**   | Understanding A requires reading B                 |
| **Data affinity**    | Operates on the same fields or data structures     |
| **Functional unity** | Steps of a single logical task                     |

When cohesion is low, suggest: Cohesion Order, Extract Helper, or moving related code into
a shared module/class.

---

## Constraints

These keep tidying safe and productive:

1. **Language agnostic** — adapt patterns to whatever language is in context. Use idiomatic constructs for that language.
2. **Small and safe** — each tidying should be independently correct. If uncertain about safety, flag it and ask.
3. **Structural only** — tidyings change organization, not behavior. If a change might alter behavior, call it out explicitly so the user can decide.
4. **Reversible** — every tidying can be undone. If one is risky, say so.
5. **One concern at a time** — don't combine unrelated tidyings in a single edit.
6. **Respect existing style** — match the codebase's indentation, naming, and formatting unless the tidying specifically addresses style.

---

## Examples

**Example 1 — User asks to tidy a function:**

```
User: "Can you clean up this function? It's hard to follow."
```

→ Run the full Analyze → Propose → Apply workflow. Start by reading the function, identify
  tidying candidates, present the table, wait for confirmation.

**Example 2 — User is about to add a feature:**

```
User: "I need to add retry logic to this HTTP client."
```

→ If the code is tangled, suggest: "Before adding retry logic, there are a couple of
  tidyings that would make this easier. Want me to propose them?" Then run the workflow.

**Example 3 — User asks about code structure:**

```
User: "Why is this module so hard to change?"
```

→ Focus on the Coupling & Cohesion Summary. Explain what's tangled and why, then offer
  tidying proposals if appropriate.