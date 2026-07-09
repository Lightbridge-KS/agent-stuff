---
name: ax-interface-analysis
description: >-
  Analyze the agent experience ("AX") of an interface an AI agent drives — a CLI,
  MCP server, HTTP/REST API, or library/SDK — against the principles of what makes
  a system easy for a reasoning-loop agent to use, and prescribe prioritized fixes.
  Use this skill only when the user explicitly invokes it by name
  (`ax-interface-analysis`) or near-match mentioning.
metadata:
  version: "2026-07-09"
---

# AX Interface Analysis

Evaluate how good an interface is **for an AI agent to drive**, and prescribe how to improve
it. Where `explain-ux-dx-design` *describes* a user-facing surface neutrally, this skill
*judges* it from one specific viewpoint — the agent in the loop — and produces an audit plus
ranked recommendations. The output is a single Markdown report that renders on GitHub.

## The core reframe (the thesis)

A human UI is designed for **eyes and hands**. An agent interface is designed for **a reasoning
loop with a finite context window**. The agent never "sees" the tool — it reads text about it
(the spec), emits a structured call, reads text back, and re-reasons.

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
**Keep the analysis anchored here** — that is what stops it drifting into generic API-design
advice. The compressed form: *design for a capable but forgetful collaborator who works only
through text, learns the tool only from its description, and pays for every word you send back.*

## Core principles (how to run the analysis)

1. **Ground every finding in the actual surface.** Cite real command names, flags, tool
   descriptions, schema fields, endpoint paths, error strings, exit codes. Never critique an
   invented flag. The main failure mode is confabulating a problem that isn't there.
2. **Judge from the agent's viewpoint, not the human's or the implementer's.** "Is this
   pretty in a terminal?" is the wrong question. "Can a forgetful, text-only reasoner discover
   it, call it unambiguously, afford the output, and recover from its own mistakes?" is the
   right one.
3. **Significance over completeness.** Audit the touchpoints an agent actually drives. Skip
   debug-only commands and dead endpoints unless they reveal a systemic pattern.
4. **Every finding is actionable.** A finding names the principle, the evidence, the severity,
   *why it hurts the loop*, and a concrete fix. No fix → it's an observation, not a finding.
5. **Prioritize by leverage.** Error-message and exit-code hygiene are cheap and high-impact;
   re-shaping the tool set is expensive. Order recommendations accordingly.
6. **One file.** Always write a single Markdown report.

## Step 1 — Classify the interface

The modality decides *what evidence you go looking for*. The rubric (Step 3) stays constant.

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
endpoint vs workflow shape           naming idioms, example snippets
idempotency, versioning              read-after-write affordances
```

State the classification and its evidence early. **Hybrid** (e.g. a lib that ships a CLI, or
an app with a public API) is common — cover each surface and label sections clearly.

## Step 2 — Inventory the surface (don't read everything)

Build a faithful map of what an agent touches. If a sibling `_docs/*_ux_design.md` from
`explain-ux-dx-design` exists, **reuse its surface map** instead of re-deriving it.

1. **Spec sources:** `--help` output, MCP tool list + schemas, OpenAPI/GraphQL schema,
   exported symbols + docstrings. This is the agent's onboarding — read it as the agent would.
2. **Manifests:** `package.json` (`bin`, `exports`), `pyproject.toml` (`[project.scripts]`),
   MCP server registration, route mounts. Reveals the declared surface.
3. **Output & errors:** sample real outputs and error paths — exit codes, status codes, error
   bodies, validation messages, log/diagnostic channels.
4. **Representative call chain:** trace one task end-to-end the way an agent would
   (`discover → call → read result → next call → verify`), noting every round-trip and every
   token-heavy return.

The goal is a map of the agent-facing surface, not a line-by-line audit.

## Step 3 — Audit against the AX rubric

The seven principles below are the payload. For each: assess, grade (✅ solid / ⚠️ partial /
❌ agent-hostile / `n/a`), and record findings with evidence. **Bold** items are concrete
mechanics — they are the *evidence* for the principle, not separate principles. Match evidence
to the modality from Step 1. For CLI/SDK targets, the bundled
[`references/agent-friendly-cli-contract.md`](references/agent-friendly-cli-contract.md) gives
ready-made target shapes to cite.

| # | Principle | The agent's need | What to look for (and the hostile anti-pattern) |
|---|-----------|------------------|--------------------------------------------------|
| 1 | **Self-documenting affordance** | The spec is the *only* onboarding — no tutorial, no hovering. | Description says *when & why* to use it, *when not*, with an example — not just *what*. Discoverable `--help`; visible enums. ❌ Terse name + one-line "what" with no usage guidance. |
| 2 | **Context economy** | Tokens are scarce; every returned token competes with reasoning. | Filtering / field-selection / pagination; `concise` vs `detailed`; bounded result size. ❌ Dumping raw nested JSON / thousands of lines — *the most common agent-hostile mistake*. |
| 3 | **Right abstraction** | Agents think in *tasks*, not endpoints. | Tools/commands shaped on workflows (`find_user_contact(name)` not `list→get→get`). Count consolidated along task boundaries. ❌ 1:1 REST mirror forcing multi-call chains; or so many tools they bloat context and cause choice paralysis. |
| 4 | **Unambiguous contract** | Shrink the space of "what could I pass" — ambiguity is where a probabilistic caller errs. | Enums over free strings, strong types, explicit required-vs-optional, sane defaults, **documented config precedence (flags → env → file → defaults)**. ❌ Free-text where an enum fits; undocumented precedence; "stringly-typed" params. |
| 5 | **Errors that teach** | An error is a *correction signal* acted on next turn, not a dead end. | Messages that name the bad input, the expected form, and a next move. **Stable exit-code / error-type taxonomy** to branch on. ❌ `400`, `500`, bare `1`, or English prose the agent must scrape. |
| 6 | **Predictable & safe** | Agents retry on timeout and can hallucinate calls. | Idempotency where possible; least privilege; destructive actions gated by explicit confirmation; no hidden side effects; **determinism — no embedded LLM in the tool**. ❌ Non-idempotent writes that double on retry; silent destructive defaults. |
| 7 | **Composable & verifiable** | Outputs of one call feed inputs of the next; the agent can't watch a UI to trust a write. | Consistent ID formats & units; a read-after-write path; **readable handles beside opaque IDs** (`{id: "usr_8fa2", name: "Jane Smith"}`); **stdout=data / stderr=diagnostics**; structured-by-default output. ❌ Bare UUIDs only; no way to confirm the write landed; data mixed into stderr/log noise. |

## Step 4 — Write the report

**Filename:** `_docs/<system_name>_ax_analysis.md` (`<system_name>` = repo/project in
snake_case). Create `_docs/` if absent.

**Cross-link:** add a "See also" line for any sibling docs found in `_docs/` —
`*_ux_design.md`, `*_system_oop_architecture.md`, `*_data_architecture.md` — so the set forms a
triangulated view of one system.

Use this skeleton. Lead with the scorecard so the shape is visible at a glance; keep prose
tight.

```markdown
# <Project> — Agent Experience (AX) Analysis

> Source: <repo origin/URL if known> · Analyzed: <date> · Interface: <CLI | MCP | API | SDK | Hybrid>
> See also: [UX & DX Design](./<system_name>_ux_design.md)  <!-- omit lines for docs not present -->

## Scorecard
| # | Principle | Grade | One-line verdict |
|---|-----------|-------|------------------|
| 1 | Self-documenting affordance | ✅ / ⚠️ / ❌ | … |
| 2 | Context economy             | … | … |
| 3 | Right abstraction           | … | … |
| 4 | Unambiguous contract        | … | … |
| 5 | Errors that teach           | … | … |
| 6 | Predictable & safe          | … | … |
| 7 | Composable & verifiable     | … | … |

## 1. Overview
- What the interface is and what an agent uses it to accomplish.
- Interface classification + evidence (Step 1).
- The representative call chain traced in Step 2 (how an agent reaches and drives it).

## 2. Findings by Principle
For each non-✅ principle: evidence (real command/tool/endpoint), severity, and *why it hurts
the loop*. Group ✅ principles into a short "What's already solid" paragraph — don't pad.

### Principle N — <name>  [grade]
- **Evidence:** `real.command --flag` / `tool_name` / `GET /path` (file:line where useful).
- **Impact on the loop:** what the agent has to do because of this (extra round-trips, wasted
  tokens, failed retries, ambiguity).
- **Fix:** concrete change.

## 3. Recommendations (ranked by leverage)
Ordered cheap-and-high-impact first. Each with a before/after in the agent-hostile/friendly form.

1. **<fix>** — <one line why it's high leverage>
   ```
   ✗ AGENT-HOSTILE   query_table(table, filter_json, raw=true) → 4000 lines, opaque ids, error="500"
   ✓ AGENT-FRIENDLY  search_studies(patient_id, modality?="CT"|"MR") → top 10 compact rows,
                     "CT Chest — 2026-03-12 (study_id: st_91c, status: reported)",
                     error="No studies for 'p_404'. Check with find_patient(name)."
   ```

## 4. Open Questions & Notes
What couldn't be determined from the surface, assumptions made, areas needing a deeper look.
Uncertainty goes here — not disguised as a finding.
```

## Quality checklist before finishing

- [ ] Interface classified with evidence; hybrid surfaces each covered.
- [ ] Scorecard present at the top, one grade per principle (✅/⚠️/❌/n·a).
- [ ] Every command/flag/tool/endpoint/error named in the report exists in the surface.
- [ ] Each finding ties to a numbered principle, cites real evidence, and names the loop impact.
- [ ] Every finding has a concrete fix; observations without fixes are labelled as such.
- [ ] Recommendations ranked by leverage, with at least one before/after in the hostile/friendly form.
- [ ] Sibling `_docs/` docs cross-linked if present.
- [ ] Uncertainties live in "Open Questions", not disguised as facts.
- [ ] Exactly one Markdown file, written to `_docs/`.
