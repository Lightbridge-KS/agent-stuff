# CONTEXT.md Format

## Structure

```md
---
summary: Ubiquitous language — the domain glossary for this repo.
read_when:
  - introducing, renaming, or disambiguating a domain term
  - naming a type, class, module, or function after a domain concept
---

# {Context Name}

{One or two sentence description of what this context is and why it exists.}

## Language

**Order**:
{A one or two sentence description of the term}
_Example_: {Optional — one sentence showing a concrete case or contrast the definition alone leaves open}
_Avoid_: Purchase, transaction

**Invoice**:
A request for payment sent to a customer after delivery.
_Example_: An order shipped in two boxes still produces one invoice, not two.
_Avoid_: Bill, payment request

**Customer**:
A person or organization that places orders.
_Avoid_: Client, buyer, account
```

## Rules

- **Be opinionated.** When multiple words exist for the same concept, pick the best one and list the others under `_Avoid_`.
- **Keep definitions tight.** One or two sentences max. Define what it IS, not what it does.
- **Add an `_Example_` only where the definition alone leaves a plausible misreading** — the term's boundary with a neighbour is subtle, the term is compositional or abstract, or the definition carries a counter-intuitive rule. Self-evident terms get none; an example on every term illustrates nothing. One sentence, drawn from this project's domain, no code or field names. Prefer a contrast when the point is a distinction ("one invoice, not two"). A bare list of instances stays inline in the definition ("such as X or Y"); the line is for a scenario or a contrast.
- **Only include terms specific to this project's context.** General programming concepts (timeouts, error types, utility patterns) don't belong even if the project uses them extensively. Before adding a term, ask: is this a concept unique to this context, or a general programming concept? Only the former belongs.
- **Group terms under subheadings** when natural clusters emerge. If all terms belong to a single cohesive area, a flat list is fine.
- **Keep the YAML frontmatter.** The `summary` / `read_when` header is index metadata, not glossary content — it lets the `docs-index` hook surface this file in the "read before coding" map. It doesn't violate the "glossary and nothing else" rule; the body still holds only terms.

## Single vs multi-context repos

**Single context (most repos):** One `CONTEXT.md` at the repo root.

**Multiple contexts:** A `CONTEXT-MAP.md` at the repo root lists the contexts, where they live, and how they relate to each other:

```md
---
summary: Context map — the bounded contexts in this repo, where each lives, and how they relate.
read_when:
  - working across more than one bounded context
  - deciding which context a change belongs to
---

# Context Map

## Contexts

- [Ordering](./src/ordering/CONTEXT.md) — receives and tracks customer orders
- [Billing](./src/billing/CONTEXT.md) — generates invoices and processes payments
- [Fulfillment](./src/fulfillment/CONTEXT.md) — manages warehouse picking and shipping

## Relationships

- **Ordering → Fulfillment**: Ordering emits `OrderPlaced` events; Fulfillment consumes them to start picking
- **Fulfillment → Billing**: Fulfillment emits `ShipmentDispatched` events; Billing consumes them to generate invoices
- **Ordering ↔ Billing**: Shared types for `CustomerId` and `Money`
```

The skill infers which structure applies:

- If `CONTEXT-MAP.md` exists, read it to find contexts
- If only a root `CONTEXT.md` exists, single context
- If neither exists, create a root `CONTEXT.md` lazily when the first term is resolved

When multiple contexts exist, infer which one the current topic relates to. If unclear, ask.
