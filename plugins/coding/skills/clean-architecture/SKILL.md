---
name: clean-architecture
description: How I apply Clean Architecture + DDD — pragmatic, right-sized by complexity tier, reconciled with deep modules. Use when designing, reviewing, or refactoring a codebase's architecture or layering, deciding how much architecture a project needs, or whenever Clean Architecture / DDD / SOLID comes up.
metadata:
  version: "2026-07-09"
---

# Clean Architecture (hybrid, right-sized)

You already know Clean Architecture, DDD, and SOLID — this skill does not teach them. It pins **my expansion** of those terms: where my defaults diverge from the textbook, how much architecture a project earns, and how these principles reconcile with deep modules.

**The stance:** the end goal is code that *fits the human brain* — maintainable, testable, adaptable — with the principles as steering, never as compliance. Purity loses to pragmatism at every tie-break. Delete before you add.

## The gate: tier before pattern

Never recommend a pattern before placing the project in a tier. If the tier is unclear, ask — using this matrix, not free-form questions:

```
Indicator          │ Simple        │ Modular          │ Full Clean
───────────────────┼───────────────┼──────────────────┼──────────────────
Business rules     │ Few/trivial   │ Moderate         │ Many/intricate
Data relationships │ Simple CRUD   │ Some logic       │ Rich domain
Team size          │ 1–2 devs      │ 3–5 devs         │ 5+ devs
Expected lifespan  │ <1 year       │ 1–3 years        │ 3+ years
Change frequency   │ Rare          │ Occasional       │ Frequent
───────────────────┼───────────────┼──────────────────┼──────────────────
Shape              │ Single module │ core/infra/api   │ Domain → App →
                   │ functional ok │ split            │ Adapters → Infra
Interfaces         │ None/minimal  │ Key seams only   │ All volatile seams
DI                 │ Direct use    │ Constructor DI   │ Full + Composition Root
```

**DDD depth is a separate dial**, not implied by the tier: *minimal* (entities with behavior, value objects, repository interfaces) → *standard* (+ domain services, explicit aggregates) → *full* (+ domain events, bounded contexts, ACLs). A Full-Clean project can run minimal DDD. Turn the dial up only when the domain has real invariants and aggregate relationships — ask when unclear.

## Reconciliation with deep modules

This skill composes with `codebase-design` (deep modules); use its vocabulary — module, interface, seam, adapter, depth — when discussing structure. When the two pull apart:

- **Layers place the macro seams** (domain ↔ infrastructure); **depth governs every module** within and across them.
- When SOLID nudges toward shallow wrappers or classitis, **depth wins**. Distrust an interface with a single implementation that won't vary: one adapter means a hypothetical seam, two means a real one.
- Apply the **deletion test** to every abstraction the tier suggests before adding it: if deleting it makes complexity vanish rather than reappear in callers, it was a pass-through.

## Overengineering tripwires

Flag these on sight — in my own requests too, and push back:

- Repository pattern over simple CRUD with no business logic
- Abstraction layers that only pass through
- DI for stable dependencies (stdlib, well-known libs) or single-implementation classes
- DTOs mirroring entities 1:1 with no transformation

The fix is removal, not renaming.

## Review severity

When reviewing a codebase against this skill, order findings:

1. **Critical** — domain imports infrastructure (fix now)
2. **High** — business logic stranded in controllers/UI (refactor soon)
3. **Medium** — SOLID violations, anemic domain model where invariants exist
4. **Low** — naming/organization drift (improve gradually)

Refactors preserve behavior — each step passes existing tests.

## Decision points — ask, never silently pick

- Tier or DDD depth ambiguous → ask with the matrix.
- Pattern with real tradeoffs (CQRS, domain events, specification, …) → present options with tradeoffs; I choose.
- Language-specific choices marked **ask** in the references below.

## Language conventions

Only the pinned choices — everything else, use your own knowledge:

- **Python** → [references/python.md](references/python.md)
- **.NET / C#** → [references/dotnet.md](references/dotnet.md)
