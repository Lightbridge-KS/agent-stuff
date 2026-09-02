---
name: generative-ui
description: >-
  Decide how an agent emits UI — Controlled, Declarative or Open-ended, chosen per
  surface — and specify the catalog and composition contracts that keep it predictable.
  Use when designing or reviewing the UI layer of an agentic system, when an agent's
  output should be more than chat text, or whenever generative UI, agentic UI, A2UI,
  AG-UI, MCP Apps or json-render come up. For the surface an agent *drives*, use
  `ax-interface`; for the organs inside the agent, `agentic-architecture`.
metadata:
  version: "2026-09-02"
---

# Generative UI

**Generative UI** is the surface an agent *emits*: the agent decides, per turn, what the
user sees instead of returning text. The craft is not letting the model draw; it is
deciding **how much of the drawing the model may do**, surface by surface, and writing
that decision down as two contracts the runtime enforces.

The failure this skill prevents: hand a model a component catalog and ask it to "compose
the experience", and the same intent yields a different layout every run, with drifting
copy. Not a model failure — an unconstrained contract.

## 1. Two orthogonal questions

Settle these separately; conflating them is the first mistake.

| question | options |
|---|---|
| **Where does the UI run?** | your own application · a super-host (Claude, ChatGPT, Gemini, VS Code…) via MCP Apps · both |
| **What does the model emit?** | *selects* a prebuilt component · *assembles* blocks from a catalog · *generates* markup |

**Container ≠ payload.** An MCP Apps iframe inside a super-host is an Open-ended *container*,
but the payload you ship into it can still be Controlled or Declarative: your prebuilt
bundle hydrated from typed tool results. Classify the payload; the container only sets the
security posture (§6).

## 2. The spectrum — pick per surface, not per product

```
              ◀── more control                          more flexibility ──▶
tier      CONTROLLED              DECLARATIVE                 OPEN-ENDED
agent…    selects a component     assembles a layout          generates the UI
from…     your prebuilt comps     your catalog of blocks      nothing (HTML/CSS/JS)
emits…    tool call + props       UI-as-data (JSON/JSONL)     code, into a sandbox
great     the few surfaces that   the long tail of screens;   3rd-party apps inside a
for       must be pixel-perfect   internal / enterprise       super-host; one-off visuals
gives up  generation              pixel-perfection, some      determinism, uniform look,
                                  determinism                 the security perimeter
```

**Rubric.** For each surface ask, in order:

1. Would a wrong or varying rendering harm someone or breach a rule? → **Controlled**.
2. Is it one of your few most-used, brand-defining screens? → **Controlled**.
3. Does it live inside someone else's host, or need a visual nobody could pre-design? → **Open-ended**, sandboxed.
4. Otherwise → **Declarative**. This is today's default: UI as data keeps the design system, streams, caches, crosses web/mobile, and is safe by construction because the client renders only what it already owns.

**House defaults** (Radiology AI Unit; override explicitly when a project differs):

- Clinical or deterministic result surfaces (findings, reports, measurements, anything a clinician acts on) → **Controlled only**.
- Analytics, exploration, internal dashboards → **Declarative**.
- **Open-ended never touches PHI.** Generated markup runs in a sandbox with no patient data in reach.

## 3. Procedure

Run the steps in order. Each ends on a checkable criterion; the output is one design
section (template in §8) that a `surface-architecture` or `agentic-architecture` doc can
embed, or `docs/design/generative-ui.md` on its own.

1. **Frame.** Answer the two questions for the product. *Done when* both answers are written with a one-line reason each.
2. **Inventory surfaces.** List every distinct thing the agent may show, then place each on the spectrum with the rubric. *Done when* every surface has a tier and the reason names the rubric line that fired. One tier across a whole *product* deserves a second look; a single screen may legitimately be all Controlled. Do not invent a surface to fill a tier.
3. **Catalog contract** (§4) for every Controlled and Declarative surface. *Done when* each component entry has all required fields and at least two representative queries.
4. **Composition contract** (§5) for every Declarative surface. *Done when* every template slot lists its eligible component categories and no slot is unconstrained.
5. **Security posture** (§6), one line per tier in use. *Done when* the Open-ended row names its sandbox and its data boundary.
6. **Determinism plan** (§7). *Done when* the consistency check is specified with N and the fields compared.
7. **Protocol.** Name the transport and format per tier from `references/protocols.md`, then **verify versions against current docs** before quoting any. *Done when* each protocol carries a `verified:` date or an explicit "unverified".

## 4. Catalog contract

The catalog is the contract between the agent and the UI: **whatever the client
advertises, the agent may use — nothing else.** Every property matters; get this wrong
and nothing downstream can save you. Curation is the work.

Per component entry:

- `name`, one-line purpose
- props: type, **required / optional**, allowed values or ranges, default
- **actions** the component can raise (typed; what each sends back to the agent)
- **data references**: does the component take literal values, a path into tool output, or both
- **representative queries**: 2–5 phrasings of the intent this component answers, for semantic matching
- **constraints**: cardinality (one per surface? repeatable?), which slots it may occupy, mobile behaviour
- **copy rules**: which strings the agent may write and which are fixed (labels, units, disclaimers)

Layout elements (templates, slots, sub-slots) are catalog entries too, with their own attributes.

## 5. Composition contract

A catalog alone yields random placement. Constrain arrangement with a second hierarchy,
borrowed from atomic design:

```
Template (page layout)
└── Slot          header · main · rail · footer …
    └── Sub-slot  ordered regions inside a slot
        └── eligible component categories   e.g. "choose one: KpiCard | Chart | Table"
```

- Codify "what good looks like": a small set of named templates per intent family, not free layout.
- Because the pipeline starts from data, resolve **bottom-up**: components → sub-slots → slots → template.
- Every slot names its eligible categories and cardinality. An unconstrained slot is where drift enters.

## 6. Security posture

Treat model-generated UI code as **third-party code** and trust it exactly that much.

| tier | posture |
|---|---|
| Controlled | secure by default — the agent only invokes what you shipped |
| Declarative | defense in depth for free: you own the components, values are decoupled from markup, so image-exfiltration, hidden forms and front-end supply-chain vectors are blocked at the renderer. Still validate the UI message against the catalog schema before rendering. |
| Open-ended | mandatory sandbox (MCP Apps: double iframe). State what the iframe can reach: no session tokens, no PHI, message-passing only. Slower and less uniform; accept that consciously. |

Every approach has a risk profile. Write the one you accepted.

## 7. Determinism plan

Determinism is a dial; set it deliberately.

- **Consistency check**: run the same intent N times (N ≥ 5) and diff the *layout* (which components, which slots) **and the copy** (numbers, periods, labels). Wording drifts as readily as layout: constrain both.
- **Human gate**: an agent-composed surface that changes state (order, config, report) gets an approve step before it goes live.
- **Structured output over tool calls** for the UI message itself: schema-checked, streamed in chunks, with a text-only fallback and repair-on-the-fly for malformed generations. Tool calls carry data; the UI message is its own channel.
- Pin model and temperature where the same intent must reproduce.

## 8. Output template

```markdown
## Generative UI

**Runs in:** <own app | super-host | both> — <reason>
**Model emits:** <per tier below>

| surface | tier | rubric line | protocol (verified) |
|---|---|---|---|

### Catalog
<entries per §4, or link to the schema file>

### Composition
<templates → slots → eligible categories per §5>

### Security posture
<one line per tier in use>

### Determinism plan
<consistency check with N and fields; human gates>

### Open questions
<💡 items only a human can settle: taste, hard-to-reverse choices>
```

## 9. Pitfalls seen in production

- Letting the model compose from the catalog with no composition contract → four layouts for one intent.
- Constraining layout but not copy → "Q1" becomes "January to March".
- Choosing one tier for the whole product → either a static app with a chat box, or an unshippable demo.
- Shipping Open-ended because the demo worked → a business cannot control what it cannot predict.
- Forgetting the people shift: designers and PMs now define schema, catalog, rules and intent, not pixels. Budget for it.

## References

- `references/protocols.md` — the protocol landscape with a `verified:` date. Fetch current docs before quoting versions.
- `references/sources.md` — the talks this skill distils, with one line per lesson.
