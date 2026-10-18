# Moves by level

Fowler's and Beck's catalog names are assumed, not taught. This file holds only the
expansions that diverge from the default, one level at a time, each with a generic sketch.
The test at every level is **locality**: after the move, does a change to one concept have
one home and a small, predictable set of affected tests?

## Variable

Moves: Explaining variable, Explaining constant, shared alias.

- A literal that appears in more than one owner (a reserved column name, a sentinel, a
  physical schema field) gets **one** declaration, owned by the module that defines the
  contract — not a `constants` module that owns nothing.
- A type alias names a representation and nothing more. `Key = tuple[...]` validates no
  field and makes nothing immutable. Propose it for shared vocabulary; never sell it as
  safety.

```
before   "support" as a literal in the row builder, the schema check, and the writer
after    RESERVED = ("support", …) declared once in schemas · three consumers import it
```

## Function

Moves: Extract, Inline, Decompose Conditional, staged decomposition, rename to intent,
eliminate redundant work.

- **Extract by semantic path, not by line count.** Two shapes handled through one
  synthetic loop become two named functions, each with its own invariants visible.
- **Staged decomposition:** every level of expansion gets a named operation
  (expand analyses → partitions → windows → metrics), so nesting reads as a call tree.
- **Inline** when there is one caller and the name adds nothing the body does not say.
- **Rename to intent:** `_mapped()` → `normalize_binary_labels()`, `_names()` →
  `validated_names()`. A name states what the caller receives.
- **Eliminate redundant work** by reusing an already-valid computation — pass the existing
  mask in rather than recomputing it — not by caching.
- **Exactness over idiom.** A rewrite from an explicit loop into the idiomatic form
  (comprehension, vectorized call, pipeline) is a move only when identity semantics —
  large integers, boolean-vs-integer, missing values, error order — are pinned by a proof
  rung. Otherwise the loop stays.

```
plan_cells(…)
├── feature path — one cell per selected column
│   └── validate, project each column independently
└── task path — one cell with aligned required roles
    ├── validate and normalize roles
    ├── enforce label policy on the candidate truth
    ├── intersect eligibility masks
    └── compute support, construct the cell
```

## Class

Moves: passive carrier, declarative contract, frozen record, class-being-born.

- **Passive carrier:** represent information apart from the operation that consumes it;
  identity properties stay with the record, behavior stays with its owner.
- **Declarative contract:** requirements as data an interpreter reads (required roles,
  dtypes, output constraints) — one declaration, many consumers.
- **Frozen is not immutable.** A frozen record blocks attribute reassignment; what it holds
  (a frame, an evaluator) can still mutate. Call it a frozen record or a passive carrier.
  "Value object" is earned only by deep immutability and comparison by value.
- A carrier that keeps growing methods is a class being born — name it after the concept,
  do not keep appending to the record.

## Module

Moves: Extract Module, Move Function, lift, lower.

- **Lift** a definition into a shared module only when two or more consumers need it.
  **Lower** it next to its single consumer when it is local policy.
- The **before/after edge sketch is mandatory** on the card. The benefit is the removed
  edge, not the shorter file.
- **Compatibility re-export:** a public import path that must survive forwards the same
  object. Never a wrapper, never a duplicate definition.
- **Extract Module behind a Facade** — the compound move for one file that has grown
  several concerns that share no state. Its bill of materials, all in one card:
  1. *Split by cohesion.* One file per concern, named for what it owns. The recursive
     core (the walk and the state it carries) stays together even when it is the largest
     piece — a class cannot be spread across files, and a core split by line count is
     worse than the long file.
  2. *The interface is fixed.* The old file becomes the barrel: callers' import path and
     signatures unchanged, re-exported with `show`, never through a wrapper.
  3. *Only boundary-crossing names lose their privacy.* The module's surface for the
     package is not the package's public API; the barrel stays unexported.
  4. *A fitness test.* Only the barrel imports the folder; a planted violation proves the
     test bites. Without it the facade is a convention.
  5. *The structure doc, amended.* The tree line and the "where a change lands" rows — a
     routing table that can now name one file per kind of change is worth-test question 4
     made checkable.

  Lands as two commits: extract within the file (the logic diff, reviewable), then the
  pure move (the diff is moves and renames) — the pure-move diff in
  [verification.md](verification.md) is its proof. *Not yet* when the file is one
  recursive walk with shared state, or when a scheduled feature is about to define the
  seams: decompose within the file and name the trigger. In a language with per-file
  privacy (Dart), `part`-style includes keep the underscores but draw no boundary; the
  fitness test is the boundary.

```
before   read/parser.dart   700 lines: framing · walk · header rules · checks · ambiguity

after    read/parser.dart   barrel — the three entry points, import path unchanged
         read/parse/        walker · header · checks · ambiguity · level · source_reader
         test               only parser.dart imports read/parse/  (fitness test + doc row)
```

```
before   binding → planning → {eligibility, groups, windows}
         (binding imports planning only to obtain a record type)

after    planning ─┐
         binding ──┼→ steps → keys       steps owns the planned-work records,
         executor ─┘                     keys owns the shared identity aliases
```

## Package

Moves: group by ownership into sub-packages, composition root, plan–execute separation,
public facade over a changing implementation.

- **Group by responsibility, never by syntax.** Each sub-package passes the worth test on
  its own: one owner, fewer edges, a smaller interface.
- **Composition root:** one place selects and wires concrete parts; consumers receive
  them. Injection (how a dependency arrives) is not inversion (who owns the contract) —
  passing a concrete object in is injection without inversion.
- **Plan–execute separation:** eager plans validate the whole request before expensive
  work; execution consumes the plan; a result is published only when every contribution
  succeeded. Eager plans keep late validation out of iterators.
- The package root keeps the **public facade** and the compatibility re-exports; the
  sub-packages stay private.

```
before   one flat package — every concern at the root, callers import across all of it

after    _specs/       what is asked           _execution/   plan · bind · run
         _evidence/    assemble · validate · publish
         _plugins/     discover · compose
         root          public facade + compatibility re-exports
```

More folders is not more modularity. The move earns its place when responsibility,
dependencies, and verification become easier to understand *together*.
