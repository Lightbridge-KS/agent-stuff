---
name: refactor-analysis
description: >-
  Analyze working code and propose behavior-preserving refactoring candidates — the output
  is a ranked proposal; nothing is edited before the user picks. On "apply", the picks land
  under the skill's landing contract. Not a layering review — for that use `clean-architecture`.
metadata:
  version: "2026-10-18"
---

# Refactor Analysis

Propose **behavior-preserving** structural changes to code that already works. Structure
may change; the **preserve-list** may not: public interface, results (including numerical
identity), error categories, data contracts, ordering, cost on a hot path. The output is a
ranked proposal — nothing is edited before the user picks a card, and the card is the plan:
on *apply*, the picks land under [references/landing.md](references/landing.md). If the
ask adds capability, say so and split it out: feature work is not refactoring.

Vocabulary: `codebase-design` for structure (module, interface, seam, depth, locality,
leverage, the deletion test); `CONTEXT.md` for the domain. ADRs are not re-litigated. Name
a shape by its design pattern when one fits — [references/patterns.md](references/patterns.md).

## Re-entry sweep

If `docs/progress/refactor/` exists, read it before anything else. Prior preserve-lists
bind. Prior rejections are not re-proposed unless the friction has changed. Trackers marked
`status: complete` → ask once, batched, whether to prune them.

## Entry — scope decides the mode

**Narrow** — the user names modules and a hunch ("gather by kind", "simplify this"). Read
them and one hop of callers and callees. The hunch is a hypothesis, not an order: test it
against the worth test, report when it fails, and say what passes instead.

**Broad** — the user names a tree. Walk it with an Explore subagent, organically, noting
friction:

- understanding one concept means bouncing between many small modules;
- a module's interface is nearly as complex as its implementation;
- functions extracted for testability while the bugs hide in how they are called;
- seams that leak — one module reaching into another's internals;
- parts untestable through their current interface.

Apply the deletion test to anything suspected shallow. Rank, end with a **Top
recommendation**, let the user pick, then run narrow mode on the pick.

Either mode ends in a proposal. Nothing is edited until the user picks.

## The worth test

A candidate survives only if it answers *yes* to at least one and breaks nothing on the
preserve-list:

1. Does the new home own one understandable responsibility?
2. Does it remove an edge or a duplicated contract?
3. Do callers get a smaller interface with the same guarantees?
4. Does a likely future change become more local?
5. Can existing behavior be demonstrated through the same seam afterward?

Not evidence: file count, function length, number of records, "cleaner". A candidate that
passes none is dropped, not downgraded.

A candidate that passes but whose seams a scheduled feature is about to define is **Not
yet**: state the trigger (the milestone, a second consumer, a size) and record it, so the
next pass re-examines it when the trigger fires instead of re-arguing it. Do not split
ahead of the feature that will draw the seams; decompose within the file and wait.

## Pinned judgments

Where this skill diverges from your defaults:

- **Ownership first, kind second.** Gather by *owner*. A `types` / `constants` / `utils`
  module that collects by syntax is a smell — unless the kind *is* the owner (physical
  schemas, shared identity aliases).
- **Lift needs two consumers; lower when there is one.** Local policy stays local.
- **An extraction must remove an edge or name an owner.** Show the before/after edges on
  the card. A shorter file is not a benefit.
- **Shallow wrappers fail the deletion test.** Propose inlining, not more extraction.
- **Exactness over idiom.** Keep the explicit loop when identity semantics (large integers,
  boolean-vs-integer, missing values) are load-bearing; the idiomatic rewrite is a
  candidate only with a proof rung that pins those identities.
- **Say what a thing is.** Frozen record, passive carrier, alias — not "value object"
  unless deeply immutable and compared by value. An alias names a representation; it adds
  no invariant.
- **Collapse before introduce.** A classic pattern shape whose verdict is *Replaces* or
  *Simplifies* is a candidate to flatten. Introducing a pattern needs the worth test plus a
  real seam — two adapters; one adapter is a hypothetical seam dressed as a pattern.
- **Compatibility re-exports forward the same object**, never wrapper copies.
- **A scheduled consumer counts; a hypothetical one does not.** "Lift needs two consumers"
  admits a second consumer the tracker's Next already names — the third copy a milestone
  is about to write. "Someone might" is not a consumer.
- **Test oracles are exempt from DRY.** A rule restated inside a gate — the expected byte
  size, the padding rule, a long-VR table — *is* the oracle; sharing the library's rule
  would make the gate agree with its bugs. Keep the copy and say on the card that it is
  deliberate.
- **A facade over a folder is a convention until a test enforces it.** An Extract Module
  behind a Facade ships its fitness test and its structure-doc row, or it is not proposed.
- **Survey and peer claims are hypotheses.** A subagent's finding or another session's
  candidate is re-read in the code before it becomes a card; one that does not survive is
  listed under Rejected with why.
- An ADR conflict is surfaced only when the friction is strong enough to reopen the ADR,
  and is marked on the card.

## Proposal card

One per candidate; cards ordered by dependency between moves (what must land first).
Plain-text sketches; chat is the medium.

```
#N · <level: variable|function|class|module|package> · <move, named>
Where      files / modules touched
Problem    the friction, in locality or leverage terms
After      sketch — import edges or call tree, before → after
Earns it   which worth-test question(s) it answers
Preserve   what must not change — the preserve-list, specific to this move
Behaviour  none · malformed input only · public — anything but none is a question card
Proof      the ladder rung that would show it — references/verification.md
Strength   Strong · Worth exploring · Speculative · Not yet — trigger: <condition>
```

A **question card** is a move the user must rule on before it is a refactor: it changes
what broken input does, or makes a check stricter. It is carded with the rest so the
decision is on record, and it never lands inside a `refactor:` commit.

Broad mode closes with **Top recommendation**: the one card to start with, and why — then
two blocks every broad proposal carries:

- **Rejected** — each dropped or *Not yet* candidate with its reason, so the tracker can
  carry it and the next pass does not re-propose it.
- **Findings outside the refactor** — bugs, invariants that claim a check they do not
  have, doc drift. A bug goes first: its own `fix:` commit, and the owner decides who
  makes it.

Then ask which cards to take forward.

## Handoff

When the user picks, offer to persist the picked cards as a tracker seed at
`docs/progress/refactor/refactor-<topic>.md` with `status: proposed`, so the reasoning
survives the session. Write it only on a yes. Then the card is the plan: a pick that comes
with *apply* lands under [references/landing.md](references/landing.md) — baseline, pin
each Preserve item, move, prove, one commit per card. Without *apply*, stop.

```markdown
---
summary: <Topic> refactor — <what moves>, preserving <the preserve-list in brief>.
read_when:
  - Planning or executing the <topic> refactor; reviewing its evidence
status: proposed
date: YYYY-MM-DD
---
# <Topic> refactor

Parent: [overview](../overview-<name>.md) · Design: <links>

- [ ] <move 1, from card #a>
- [ ] <move 2, from card #b>

Preserve: <the preserve-list, verbatim from the cards>
Proof: <rung per move>

## Evidence

(filled as moves land: gates run, counts, CI run)

On completion: set `status: complete`, then ask whether to prune this tracker.
```

A proposed module named after a concept missing from `CONTEXT.md` → note it for
`domain-modeling`. A candidate the user rejects for a load-bearing reason → offer an ADR,
so the next analysis does not re-propose it.

## Related skills

`codebase-design` (vocabulary) · `clean-architecture` (a finding that is a layer
violation, not a local move) · `domain-modeling` (new names) · `grilling` (a contested
candidate, on request).

---

_Broad mode adapted from `improve-codebase-architecture` in
[mattpocock/skills](https://github.com/mattpocock/skills) (MIT)._
