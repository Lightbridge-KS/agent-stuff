---
name: writing-great-skills
description: Reference for writing and editing skills well — the vocabulary and principles that make a skill predictable.
disable-model-invocation: true
metadata:
  version: "2026-07-09"
---

A skill exists to wrangle determinism out of a stochastic system. **Predictability** — the
agent taking the same _process_ every run, not producing the same output — is the root
virtue; every lever below serves it.

**Bold terms** are defined in [`GLOSSARY.md`](GLOSSARY.md) — the single source of truth for
every definition. This file is the decision spine only; when a term needs its full meaning,
read it there.

## Invocation

Default to **user-invoked** (`disable-model-invocation: true`) — zero **context load**. Pay
for **model-invocation** only when the agent must reach the skill on its own, or another
skill must reach it. When user-invoked skills multiply past what you can remember, cure the
piled-up **cognitive load** with a **router skill**.

## Writing the description

A model-invoked **description** does two jobs — state what the skill is, and list the
**branches** that trigger it. Every word adds context load, so it earns even harder pruning
than the body:

- **Front-load the skill's leading word** — the description is where it does its invocation work.
- **One trigger per branch.** Synonyms renaming a single branch are **duplication**; collapse them.
- **Cut identity that's already in the body.**

## Information hierarchy

Place each piece of content on the ladder — **in-skill step** → **in-skill reference** →
**disclosed reference** behind a **context pointer** — and make these decisions:

- Every step ends on a **completion criterion**: checkable, and exhaustive where it matters.
- Disclose by **branch**: inline what every branch needs; push behind a pointer what only
  some branches reach. The pointer's *wording* decides when and how reliably it fires.
- **Co-locate**: a concept's definition, rules, and caveats under one heading.
- Push too little down and the top bloats; push too much and you hide must-have material.
  That tension is the whole decision. (_This skill is all reference — a flat peer-set is a
  fine arrangement, not a smell._)

## When to split

**Granularity** spends one of the two loads per cut, so split only when the cut earns it:

- **By invocation** — when a distinct **leading word** should trigger the piece on its own,
  or another skill must reach it.
- **By sequence** — when visible **post-completion steps** cause *observed* **premature
  completion** and the criterion can't be sharpened further. Hiding only works across a
  real context boundary.

## Pruning

- Keep each meaning in a **single source of truth**.
- Check every line for **relevance**.
- Hunt **no-ops** sentence by sentence, not just line by line; when a sentence fails the
  test, delete it whole rather than trimming words. Be aggressive — most prose that fails
  should go, not be rewritten.

## Leading words

Hunt for passages begging to **collapse** into a single pretrained token:

- "fast, deterministic, low-overhead" → _tight_ (one quality restated across a phase → one word).
- "a loop you believe in" → _red_ (a fuzzy gate → a binary observable state).

You win twice: fewer tokens, and a sharper hook for the agent to hang its thinking on.
Assume every skill is carrying restatements that leading words retire — go find them.

## Diagnosing a misbehaving skill

Match the symptom to its failure mode — **premature completion**, **duplication**,
**sediment**, **sprawl**, **no-op** — each defined beside its cure in the glossary.

---

_Adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)._
