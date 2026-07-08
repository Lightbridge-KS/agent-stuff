# Ticket: Skill-kinds audit of all skills

- **Status:** todo (deferred 2026-07-09 — user will trigger; audit only, no edits)
- **Scope:** every `plugins/*/skills/*/SKILL.md` (22 skills at time of writing: coding 12, productivity 5, radiology 3, research 1, lightbridge 1) + their `references/` subfiles
- **Anchor:** the **Skill kinds** taxonomy in `agent-instruction/AGENTS.qmd` → Terminology (concept / contract / reference). Read it before starting.

## Procedure

**1. Classify each skill.** Read the full SKILL.md body (descriptions often read conceptual while the body is a state machine). Assign primary kind by *where the value lives*, secondary if mixed, one-line evidence quote per call.

**2. Kind-specific health check:**

| Kind | Test | Verdicts |
|---|---|---|
| Concept | Dead-weight: does the body encode the user's idiosyncratic expansion, or generic best practice a frontier model does by default from the name alone? | `keep` / `trim` (name the default parts) / `dead weight` |
| Contract | Pinned-ness: artifacts, paths, formats, phase transitions exact or hand-wavy? Underspecified contract = cost without predictability. | `pinned` / `underspecified` (name the loose joints) |
| Reference | Retrieval: freshness risk (version pins? rot rate?) + should it become a retrieval pointer instead of cached facts? Also note **stability class** — how fast the underlying tool churns. | `cache ok` / `add freshness guard` / `convert to retrieval` |

**3. Cross-cutting findings:**
- Overlap/redundancy — known suspects: three grill variants (`grilling`, `grill-me`, `grill-with-docs`) → consolidation candidates. Note: `grill-with-docs` is a one-line composition of `grilling` + `domain-modeling`, so the real question is only `grilling` vs `grill-me`.
- Misfiled value (concept wrapper around a contract, etc.).
- Router quality of each `description` vs the repo SKILL.md contract ("short trigger phrase, not documentation").

## Already resolved (2026-07-09) — do not re-litigate

- **Clean Architecture cluster:** legacy orphans (`hybrid-architecture-expert` ×2, `python-clean-architect`, `dotnet-clean-architect`, `clean-architecture-expert` agent) deprecated → replaced by one concept-kind skill `plugins/coding/skills/clean-architecture/` (commit `1f0bbea`). Audit it as a fresh skill only.
- **Domain-modeling cluster:** orphans `domain-model` (pre-split monolith of `grilling` + `domain-modeling`) and `ubiquitous-language` (competing `UBIQUITOUS_LANGUAGE.md` contract vs canonical `CONTEXT.md`) archived; successors already canonical. Deliberate omissions in current `CONTEXT-FORMAT.md` (relationships/cardinality, example dialogue, flagged-ambiguities section) were confirmed as intentional slimming — don't re-add without user say-so.
- Legacy copies archived in `my_config/_archive/agent-skills/plugins/coding/skills/`; three broken `ramaai-*` symlinks deleted. All four agent dirs (`~/.claude`, `~/.codex`, `~/.pi`, `~/.agents`) verified symmetric — every skill a live symlink into agent-stuff.

## Method

Fan out ~5 parallel subagents (one per plugin) with the rubric to pre-classify; the main agent re-reads every borderline or negative verdict before it lands. Subagents propose, main agent judges.

## Deliverable

Verdict table (skill · kind · health · one-line reason) + prose findings in chat; persist to `_playground/YYYY-MM-DD_skill-kinds-audit/NOTES.md`. Durable conclusions promote to `docs/`; fixes to skills are a **separate triggered step**, never part of the audit run.
