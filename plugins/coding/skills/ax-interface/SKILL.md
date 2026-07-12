---
name: ax-interface
description: >-
  The agent-experience ("AX") lens for any interface an AI agent drives — a CLI, MCP
  server, HTTP/REST API, or library/SDK. Judge an existing surface against the AX
  principles and prescribe prioritized fixes, or apply the principles while designing a
  new agent-facing surface. Use only when the user explicitly invokes it by name
  (`ax-interface`) or near-match ("AX analysis", "agent experience of …",
  "agent-friendly interface").
metadata:
  version: "2026-07-12"
---

# AX Interface

One lens, two directions. **AX** is UX where the user is an AI agent. This skill pins what
that means — so "make it agent-friendly" decompresses the same way every session — and
applies it either direction: *analyze* an existing surface and prescribe fixes, or
*design* a new one with the principles as decisions.

## The core reframe (the thesis)

A human UI is designed for **eyes and hands**. An agent interface is designed for **a
reasoning loop with a finite context window**. The agent never "sees" the tool — it reads
text about it (the spec), emits a structured call, reads text back, and re-reasons.

```
   AGENT (reasons in tokens, finite context)
     │ 1. reads spec (name + description + schema / --help)
     │ 2. decides, emits a STRUCTURED call
     ▼
   TOOL / SYSTEM
     │ 3. returns TEXT result (spends context budget)
     ▼
   AGENT re-reasons ──► next call ──► …
```

Every principle below derives from a constraint in that loop: the spec is the agent's only
onboarding, working memory is finite, and it must self-correct from whatever text returns.
Compressed: *design for a capable but forgetful collaborator who works only through text,
learns the tool only from its description, and pays for every word you send back.*

**Anchor here.** A finding or a design choice that cannot be traced to a loop constraint
is generic API-design advice, not AX — leave it out.

## The seven principles (the payload)

The same table drives both directions: in analyze mode each row is graded against
evidence; in design mode each row is a decision to make explicitly.

| # | Principle | The agent's need | What good looks like — and the hostile anti-pattern |
|---|-----------|------------------|------------------------------------------------------|
| 1 | **Self-documenting affordance** | The spec is the *only* onboarding — no tutorial, no hovering. | Description says *when & why* to use it, *when not*, with an example — not just *what*. Discoverable `--help`; visible enums. ❌ Terse name + one-line "what" with no usage guidance. |
| 2 | **Context economy** | Tokens are scarce; every returned token competes with reasoning. | Filtering / field-selection / pagination; `concise` vs `detailed`; bounded result size. ❌ Dumping raw nested JSON / thousands of lines — *the most common agent-hostile mistake*. |
| 3 | **Right abstraction** | Agents think in *tasks*, not endpoints. | Tools/commands shaped on workflows (`find_user_contact(name)` not `list→get→get`). Count consolidated along task boundaries. ❌ 1:1 REST mirror forcing multi-call chains; or so many tools they bloat context and cause choice paralysis. |
| 4 | **Unambiguous contract** | Shrink the space of "what could I pass" — ambiguity is where a probabilistic caller errs. | Enums over free strings, strong types, explicit required-vs-optional, sane defaults, **documented config precedence (flags → env → file → defaults)**. ❌ Free-text where an enum fits; undocumented precedence; "stringly-typed" params. |
| 5 | **Errors that teach** | An error is a *correction signal* acted on next turn, not a dead end. | Messages that name the bad input, the expected form, and a next move. **Stable exit-code / error-type taxonomy** to branch on. ❌ `400`, `500`, bare `1`, or English prose the agent must scrape. |
| 6 | **Predictable & safe** | Agents retry on timeout and can hallucinate calls. | Idempotency where possible; least privilege; destructive actions gated by explicit confirmation; no hidden side effects; **deterministic core — intelligence lives in the caller**. ❌ Non-idempotent writes that double on retry; silent destructive defaults. |
| 7 | **Composable & verifiable** | Outputs of one call feed inputs of the next; the agent can't watch a UI to trust a write. | Consistent ID formats & units; a read-after-write path; **readable handles beside opaque IDs** (`{id: "usr_8fa2", name: "Jane Smith"}`); **stdout=data / stderr=diagnostics**; structured-by-default output. ❌ Bare UUIDs only; no way to confirm the write landed; data mixed into stderr/log noise. |

Two riders that cut across the rows:

- **Two audiences, one surface.** These principles rarely fight good human DX — context
  economy, teaching errors, and unambiguous contracts improve both. When they do conflict
  (pretty tables vs parseable output), resolve with a mode switch (`--json` / `--plain`),
  never by sacrificing one audience.
- **When the LLM *is* the feature**, embed it behind a deterministic shell: stable I/O
  contract, structured output, the call isolated behind a mockable seam. The surface stays
  predictable even when the core isn't — principle 6 applies to the shell, not the model.

For CLI/SDK surfaces, [`references/agent-friendly-cli-contract.md`](references/agent-friendly-cli-contract.md)
gives ready-made target shapes — cite them as fixes (analyze) or adopt them as defaults (design).

## Mode: analyze or design

Infer the mode from the prompt's verb and repo state; ask when ambiguous.

- **Analyze** — audit an existing surface and prescribe prioritized fixes. Evidence = the
  real surface: command names, flags, tool descriptions, schema fields, endpoint paths,
  error strings, exit codes. Never critique an invented flag — the failure mode is
  confabulating a problem that isn't there.
  Output: `_docs/<system_name>_ax_analysis.md` (snake_case project name; create `_docs/`
  if missing).
- **Design** — apply the principles while shaping a new or changing agent-facing surface.
  Evidence = the user's inputs (PRD, rough design, this conversation). Every principle is
  a **decision**: chosen shape / consciously waived / undecided — don't silently settle
  the undecided ones; they go to "Decisions needed".
  Output: `docs/design/<nn>-ax-interface.md` (next free number) — unless the AX pass is
  one thread of a larger design conversation or another skill's document; then contribute
  the decisions inline and skip the standalone file.

Either way, ground rules:

1. **Ground every claim in the mode's evidence.** Unverifiable → "Open Questions".
2. **Judge from the agent's viewpoint**, not the human's or the implementer's. "Is this
   pretty in a terminal?" is the wrong question. "Can a forgetful, text-only reasoner
   discover it, call it unambiguously, afford the output, and recover from its own
   mistakes?" is the right one.
3. **Significance over completeness.** Cover the touchpoints an agent actually drives;
   skip debug-only commands and dead endpoints unless they reveal a systemic pattern.
4. **Actionable or it's out.** A finding names the principle, the evidence, *why it hurts
   the loop*, and a concrete fix — no fix → it's an observation, label it so. A design
   choice names the principle it serves.
5. **Prioritize by leverage.** Error-message and exit-code hygiene are cheap and
   high-impact; re-shaping the tool set is expensive. Order recommendations accordingly.

## Classify the modality

The modality decides *what evidence you look for* (analyze) or *which mechanics you reach
for* (design). The principles stay constant.

```
CLI / TUI                            MCP SERVER
---------                            ----------
agent = operator via shell           agent = the model itself, native tool-calling
--help text, subcommand/flag tree    tool name + description quality
exit codes, stdout/stderr split      inputSchema (enums, types, required)
--json / --plain / --no-input        result payload size & shape
config precedence                    tool granularity (workflow vs primitive)

HTTP / REST / RPC API                LIBRARY / SDK
---------------------                -------------
agent = client over the wire         agent = code-writer importing it
OpenAPI / schema, status codes       exported signatures, type hints
error-body shape, auth               docstrings, return types, error classes
endpoint vs workflow shape           idempotency, versioning
```

State the classification and its evidence early. **Hybrid** (a lib that ships a CLI, an
app with a public API) is common — cover each surface, label sections clearly.

## Analyze mode: inventory, then audit

Build a faithful map of what an agent touches — not a line-by-line read. If a sibling
`_docs/*_ux_design.md` from `ux-dx-design` exists, **reuse its surface map** instead of
re-deriving it.

1. **Spec sources:** `--help` output, MCP tool list + schemas, OpenAPI/GraphQL schema,
   exported symbols + docstrings. This is the agent's onboarding — read it as the agent
   would.
2. **Output & errors:** sample real outputs and error paths — exit codes, status codes,
   error bodies, validation messages.
3. **One representative call chain:** trace one task end-to-end the way an agent would
   (`discover → call → read result → next call → verify`), noting every round-trip and
   every token-heavy return.

Then grade each principle (✅ solid / ⚠️ partial / ❌ agent-hostile / n·a) and record
findings with evidence.

## Write the document

**Cross-link:** add a "See also" line for sibling lens docs found in the output directory —
`*_ux_design.md`, `*_system_oop_architecture.md`, `*_data_architecture.md`,
`*_agentic_architecture.md` — so the set triangulates one system.

Use this skeleton (analyze mode shown; design mode keeps the same shape with
"Findings" → "Decisions by principle" and "Open Questions" → "Decisions needed").

```markdown
# <Project> — Agent Experience (AX) Analysis

> Source: <repo origin/URL or design inputs> · Date: <date> · Mode: <Analyze | Design> · Interface: <CLI | MCP | API | SDK | Hybrid>
> See also: [UX & DX Design](./<system_name>_ux_design.md)  <!-- omit lines for docs not present -->

## Scorecard
| # | Principle | Grade | One-line verdict |
|---|-----------|-------|------------------|
| 1 | Self-documenting affordance | ✅ / ⚠️ / ❌ | … |
| 2 | Context economy             | … | … |
| … | …                           | … | … |

## 1. Overview
- What the interface is and what an agent uses it to accomplish.
- Interface classification + evidence.
- The representative call chain (how an agent reaches and drives it).

## 2. Findings by Principle
For each non-✅ principle: evidence (real command/tool/endpoint), severity, and *why it
hurts the loop*. Group ✅ principles into a short "What's already solid" paragraph — don't pad.

### Principle N — <name>  [grade]
- **Evidence:** `real.command --flag` / `tool_name` / `GET /path` (file:line where useful).
- **Impact on the loop:** what the agent has to do because of this (extra round-trips,
  wasted tokens, failed retries, ambiguity).
- **Fix:** concrete change.

## 3. Recommendations (ranked by leverage)
Cheap-and-high-impact first. Each with a before/after in the hostile/friendly form:
```
✗ AGENT-HOSTILE   query_table(table, filter_json, raw=true) → 4000 lines, opaque ids, error="500"
✓ AGENT-FRIENDLY  search_studies(patient_id, modality?="CT"|"MR") → top 10 compact rows,
                  "CT Chest — 2026-03-12 (study_id: st_91c, status: reported)",
                  error="No studies for 'p_404'. Check with find_patient(name)."
```

## 4. Open Questions & Notes   <!-- design mode: "Decisions needed" -->
What the evidence cannot determine, assumptions made, choices still open. Uncertainty
goes here — not disguised as a finding.
```

## Quality checklist before finishing

- [ ] Mode and interface modality stated with evidence; hybrid surfaces each covered.
- [ ] Every command/flag/tool/endpoint/error named exists in the mode's evidence.
- [ ] Each finding / design decision ties to a numbered principle and names the loop impact.
- [ ] Every finding has a concrete fix; observations without fixes are labelled as such.
- [ ] Recommendations ranked by leverage, with at least one hostile/friendly before/after.
- [ ] Scorecard present in analyze mode; undecided design choices in "Decisions needed", not silently settled.
- [ ] Sibling lens docs cross-linked if present.
- [ ] Uncertainties live in "Open Questions" / "Decisions needed", not disguised as facts.
- [ ] At most one Markdown file (design mode may contribute inline to a host doc instead).
