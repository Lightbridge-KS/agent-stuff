---
name: codebase-blueprint
description: >-
  The reconciliation pass between a settled design and the first line of code. Read the
  design docs, hunt the places they disagree with each other and with the chosen framework,
  then compile the object model that must satisfy all of them at once — turning prose rules
  into machine-checked invariants and amending upstream docs it contradicts. Use when design
  is settled and you are about to build, or when the user invokes it by name
  (`codebase-blueprint`) or near-match.
metadata:
  version: "2026-07-13"
---

# Codebase Blueprint

The design lenses each produce a document that is internally coherent. **The codebase is
the one place where all of them — and the framework they chose — must be simultaneously
true.** Nothing before this point is forced to notice that they disagree, because nothing
before this point has to build an object that satisfies all of them at once.

That is this skill's job. The layer diagram and the class model are the *forcing function*,
not the value. **The findings are the value.** A blueprint that reports no findings almost
certainly skipped Phase 1.

## Where it sits

```
design fluid    ─►  c4-architect · system-architecture · data-architecture · surface-architecture
design settled  ─►  codebase-blueprint   ← you are here: reconcile, then compile
code exists     ─►  improve-codebase-architecture
```

Design mode only — it runs *before* code exists. To document structure that already ships,
use `system-architecture` in explain mode.

## Inputs

Every design doc in the repo (`docs/design/`, `_docs/`, a PRD, this conversation) **and the
vendored docs of the framework actually chosen**. The framework is an input, not context.
If the design docs are still fluid, stop and send the user back to the design lenses — this
lens reconciles settled claims and has nothing to bite on otherwise.

## Phase 1 — Reconcile (do this before writing a single section)

Read everything, then hunt for the disagreements **between** documents. That is where the
findings are; they are almost never a fact missing from one doc. Two mechanical passes catch
what careful reading does not — run both, they are cheap:

- **Verb → action → field.** Every user-facing verb the UX/DX doc promises must land on a
  use case, which must land on a field in the data model. A verb that lands nowhere is a
  promise with no schema. (In the case this skill was built from, this is how "regenerate
  and branch" was caught with no parent pointer anywhere in the store.)

- **Framework reality check.** Every capability the design promises, confirmed against the
  **vendored docs of the framework actually chosen** — read them, do not recall them. Model
  memory of a fast-moving library is exactly where this fails silently: you confidently
  specify a component against an API that moved, and ship a control that never renders.
  A locked framework decision plus a reasonable design promise can be individually sound and
  jointly impossible.

When a framework cannot afford a promise, the move is usually to **pull the capability
inside a layer you own**, not to swap the framework. Own the model, hand the framework only
what its API actually takes, write the small adapter yourself.

Emit the findings as a list, with the two docs (or doc × framework) that collide, before
proposing any structure.

## Phase 2 — Elicit what the docs left open

The forks below are the questions the blueprint **cannot compile without**. They are not a
questionnaire. For each one:

- if the design docs settle it, **cite where and move on** — a settled decision is not
  yours to re-open;
- if it does not apply to this system, say so in one line and drop it;
- otherwise **ask** — arriving with a proposed default and the consequence of choosing
  wrong, so the user is confirming a judgement rather than answering a quiz.

Batch every open fork into **one** round-trip. Never silently default one: a silent default
here is a structural decision the user never made, and it will be discovered as a rewrite.

| Fork | The question | Why the blueprint can't dodge it |
|------|--------------|----------------------------------|
| **Use-case ownership** | What sequences the side effects — and does it also hold the state they mutate? Candidates: the entry point, a use-case object, the state container, the domain entity, the repository. | The most load-bearing structural question in anything with a store, a session, a transaction, or a cache. Get it wrong and every call site knows too much. |
| **Failure model** | How does failure travel — exceptions, result types, error codes — and what taxonomy does the *user* see? | It decides **every signature in the system**. The UX doc gives you user-facing states; it never gives you the propagation mechanism. |
| **Boundary thickness** | May the framework's types cross into your domain, or does a layer you own sit in between? | This is where a locked framework quietly eats your design (Phase 1's reality check finds the collision; this fork decides the price you pay for it). |
| **Wiring & substitution** | Where does the concrete get chosen — and can a test choose differently? | Decides whether the seams are seams **in fact** or only in principle. If a test cannot substitute at the seam, there is no seam. |
| **Tree axis** | Grouped by layer, or by feature/vertical slice? | Decides the tree, and therefore "where a change lands." Often already fixed upstream — check the container doc before asking. |
| **Concurrency & atomicity** | What is shared, what runs at the same time, what is the unit of atomicity? | Skip outright for a single-threaded CLI. Load-bearing everywhere else, and invisible until it corrupts something. |

**Prescriptiveness** — one more fork, about the artifact rather than the system. Pinned code
signatures (the doc becomes a contract the code must satisfy) or a conceptual model only (the
doc stays a design artifact and ages gracefully). **Propose conceptual**, and ask: pinned
signatures rot on contact with the first refactor, and the invariants table already carries
the claims worth enforcing. Pin only for a deliberately spec-driven build.

## Phase 3 — Write

One Markdown file by default: `docs/structure/<nn>-codebase-blueprint.md` (next free number;
create `docs/structure/` if missing). It lives beside the design docs, not among them — they
are its *input*, and it has standing to amend them. Split into `<nn>-codebase-map.md` (the
layout) and `<nn>-class-model.md` (the objects) in the same directory when one file would run
long enough that nobody reads the second half; offer the split, don't agonize over it.
Cross-link the design lens docs under the title, and let diagrams carry the structure —
Mermaid conventions as in `system-architecture` (fenced blocks, `flowchart` for layers,
`classDiagram` for the object model, ≤ ~15 nodes).

The skeleton — layers, tree with one line of ownership per file, domain types, seams and
collaborators, composition root, one or two flows at object granularity — you already know
how to write. Four sections do not come free, and they are why this document exists:

- **The import matrix, and the tool that checks it.** Rows import columns. Worth writing
  *only* because a linter rule enforces it in CI. **A layering rule that lives only in a
  document is already broken.**
- **Where a change lands.** For every task a developer will actually be asked to do, is
  there exactly one obvious file? The cheapest possible test of whether the structure is
  real — for the human and for the agent that will navigate it.
- **What is deliberately absent.** Name the ceremony you did *not* build and why: no
  service layer, no hooks junk drawer, no barrel files, no `IFoo` + `FooImpl` + `FooFactory`.
  Write this section against your own reflexes — it is the one you will skip.
- **The invariants table.** Every checkable claim the blueprint makes, starred where a tool
  checks it. **Turning a prose rule into a grep or a lint rule is this skill's signature
  move**; a one-line grep in the dry gates catches, forever, what a document merely asserts.

## Phase 4 — Amend upstream (part of done, not an afterthought)

Reconciliation invalidates claims in the docs it reconciled. Go back and mark them **in
place** — `(amended)`, with a link to the deciding entry — and keep a decisions table that
says loudly which entries overrule which design doc. A blueprint that silently diverges from
the docs it corrects is worse than the original contradiction, because now only one of the
two knows.

**But the standing to amend has a bias, and you must correct for it.** This lens sees the
schema cost of a feature clearly and its product value not at all — it will argue against
what is expensive to build regardless of what it is worth to use. So: an amendment that
changes **structure** you apply; an amendment that changes **behavior** you surface to the
user as a question. Never quietly delete a feature on cost grounds.

## Compose, do not restate

Call the vocabulary skills; this document is not the place to re-teach them.
`codebase-design` for depth, seams, and the deletion test — it is what stops you adding a
service layer out of reflex. `clean-architecture` for how much layering the tier earns.
`domain-modeling` when the ubiquitous language is still moving.

## Before finishing

- [ ] Phase 1 ran before any structure was proposed, and the findings list is in the doc.
- [ ] The framework reality check read the vendored docs, not memory — say which files.
- [ ] Every promised verb lands on an action and a field, or is listed as blocking.
- [ ] Every fork is either cited to a design doc, dropped as N/A, or asked — none defaulted.
- [ ] Import matrix has an enforcing tool; invariants table stars what is machine-checked.
- [ ] "What is deliberately absent" is written and non-empty.
- [ ] Upstream docs amended in place; behavior amendments raised as questions, not applied.
