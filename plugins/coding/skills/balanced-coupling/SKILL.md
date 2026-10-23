---
name: balanced-coupling
description: >-
  Apply Vlad Khononov's balanced-coupling lens when explaining dependencies,
  designing module seams, or refactoring change propagation: weigh integration
  strength, distance, and volatility.
metadata:
  version: "2026-10-23"
---

# Balanced coupling

Make likely changes understandable and economical. Coupling enables a system to
work; choose where knowledge is shared and what changing it together costs. Use
Khononov's model at any scale, from functions to systems.

## Read the relationship

Start with a concrete change scenario and the modules it touches. Inspect shared
knowledge, including implicit dependencies with no import or call.

- **Integration strength** — what must the modules know about each other?
  Distinguish intrusive (implementation details), functional (requirements or
  business rules), model (a shared domain representation), and contract coupling
  (an explicit integration agreement that hides deeper knowledge). A public API
  or DTO alone does not establish contract coupling.
- **Distance** — what effort does coordinated change require? Consider code
  location, ownership, teams, repositories, deployment, and runtime interaction.
  Moving files alone may leave the important distance unchanged.
- **Volatility** — how likely is the shared knowledge to change? Use requirements,
  domain direction, and history as evidence. Separate intrinsic change from churn
  caused by dependencies. Quiet code may be stable, or too costly to change. Mark
  unknowns.

## Balance before choosing a pattern

- Strong integration + short distance can be useful cohesion: keep knowledge that
  must evolve together close.
- Weak integration can support greater distance and independent evolution.
- Strong integration + great distance makes cascading changes expensive: compare
  reducing shared knowledge with reducing coordination distance.
- Weakly related responsibilities crowded together may obscure navigation:
  separate when the cognitive benefit earns the additional seams.
- Low volatility may justify retaining an imperfect arrangement. Do not infer
  stability from age or inactivity alone.

Treat these as qualitative judgments, not a numerical score.

## Apply the lens

**Explain:** trace one change through the actual relationships and name the
knowledge that propagates it.

**Design:** compare plausible arrangements against expected changes; label
assumptions about volatility and ownership.

**Refactor:** target a demonstrated imbalance. Compare the smallest useful move
with leaving the design alone. State which dimension changes, what becomes easier,
and what new coordination or abstraction cost appears. Preserve behavior and
verify the affected contracts.

Interfaces, events, services, and duplication do not automatically remove shared
knowledge. Judge the resulting relationship.

Use `codebase-design`'s module/interface/seam vocabulary. Coupling evidence can
challenge a generic pattern heuristic: a stable dependency may need no wrapper;
even one implementation may warrant an adapter to shield callers from volatile
external knowledge. Respect settled project decisions; surface conflicts before
changing them. This lens informs existing architecture and delivery workflows;
it creates no separate artifact.

## Sources

Inspired by Vlad Khononov's *Balancing Coupling in Software Design*:
[Balance](https://coupling.dev/posts/core-concepts/balance/),
[Integration Strength](https://coupling.dev/posts/dimensions-of-coupling/integration-strength/),
[Distance](https://coupling.dev/posts/dimensions-of-coupling/distance/), and
[Volatility](https://coupling.dev/posts/dimensions-of-coupling/volatility/).
