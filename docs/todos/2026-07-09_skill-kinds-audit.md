# Ticket: Skill-kinds audit of all skills

- **Status:** **audit executed 2026-07-09** (5 Opus subagents + main-agent verification; full record in `_playground/2026-07-09_skill-kinds-audit/NOTES.md`, gitignored — fix backlog below is the durable output). Fixes are a separate triggered step.

## Results — fix backlog (prioritized)

- **P1 defects (verified by main agent):**
  - dcmtk: `references/transfer-syntax-uids.md` lists legacy dcmcjpeg encoder flags (`+e1`=Baseline, `+e2`, `+e4`, `+e7`) contradicting the correct table in `references/image-codecs.md` (`+eb`/`+ee`/`+el`/`+e1`); also phantom `dcmcjp2k`/`dcmdjp2k` in `dcmdata.md` (DCMTK ships no JPEG 2000 codec).
  - explain-data-architecture: trailing `</content></invoke>` tool-call junk at EOF. Optional machinery: teach `bin/validate.py` to reject stray tag garbage in skill bodies.
- **P2 contract tightening:** `handoff` is an underspecified contract — pin a filename scheme and required section schema (currently only "suggested skills" is mandated; "OS temp dir" is vague).
- **P3 dead-weight trims (biggest first):** c4-architect reference tier (~700 of 1211 lines re-teach C4/DDD; glossary duplicated); explain-family shared scaffolding (~60–80 lines × 4 doc-siblings — factor into one shared contract or trim per file; keep the filename/cross-link protocol coordinated); writing-great-skills SKILL↔GLOSSARY duplication (~40–50 lines); research `modules/general-web.md` + parts of `report-style.md`; ax-interface-analysis generic rubric; codebase-design testability snippets; explain-as-notebook test-pairing block.
- **P4 description pass** (bloated → short trigger phrase): ax-interface-analysis, c4-architect, explain-agentic-system, explain-as-notebook, orthanc-api (worst violation), research.
- **P5 doc hygiene:** `docs/research-skill-design/design.md` has verified spec drift (`supports:` vs implemented `fragment_ids`, phantom `quarto-book`, stale citation notation) — drop field-level schemas from the design doc, point to SKILL.md/`research_kit.py` as canonical; dcmtk gains an explicit "verified against DCMTK 3.7.x" line.

**Classification outcome (22 skills):** 7 contract-primary (all pinned except handoff), 9 concept-primary (fresh ones keep; June-era ones trim), 2 pure reference (cache ok; dcmtk has the P1 defect), plus compositions/mixed. Full verdict table in the playground NOTES.md. Notable: slicer-cli classified contract (not reference as predicted) — its value is the user's own tool's stable error-code/exit-code protocol; orthanc-api is the freshness-guard exemplar (per-fact `≥ version` gating).
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
- Overlap/redundancy — no known suspects remain; the grill cluster is resolved (see below).
- Misfiled value (concept wrapper around a contract, etc.).
- Router quality of each `description` vs the repo SKILL.md contract ("short trigger phrase, not documentation").

## Already resolved (2026-07-09) — do not re-litigate

- **Clean Architecture cluster:** legacy orphans (`hybrid-architecture-expert` ×2, `python-clean-architect`, `dotnet-clean-architect`, `clean-architecture-expert` agent) deprecated → replaced by one concept-kind skill `plugins/coding/skills/clean-architecture/` (commit `1f0bbea`). Audit it as a fresh skill only.
- **Domain-modeling cluster:** orphans `domain-model` (pre-split monolith of `grilling` + `domain-modeling`) and `ubiquitous-language` (competing `UBIQUITOUS_LANGUAGE.md` contract vs canonical `CONTEXT.md`) archived; successors already canonical. Deliberate omissions in current `CONTEXT-FORMAT.md` (relationships/cardinality, example dialogue, flagged-ambiguities section) were confirmed as intentional slimming — don't re-add without user say-so.
- **Grill cluster:** `grill-me` deleted — pure alias of `grilling` (one-line wrapper, failed the deletion test; user confirmed no muscle-memory need). `grilling` (concept) and `grill-with-docs` (composition of `grilling` + `domain-modeling`) both keep.
- **`commit-push-pr`:** audited and rewritten 2026-07-09 (contract-kind, 53 → 29 lines; competence deleted, main-branch and dry-gates joints pinned). Audit as a fresh skill only.
- Legacy copies archived in `my_config/_archive/agent-skills/plugins/coding/skills/`; three broken `ramaai-*` symlinks deleted. All four agent dirs (`~/.claude`, `~/.codex`, `~/.pi`, `~/.agents`) verified symmetric — every skill a live symlink into agent-stuff.

## Method

Fan out ~5 parallel subagents (one per plugin) with the rubric to pre-classify; the main agent re-reads every borderline or negative verdict before it lands. Subagents propose, main agent judges.

## Deliverable

Verdict table (skill · kind · health · one-line reason) + prose findings in chat; persist to `_playground/YYYY-MM-DD_skill-kinds-audit/NOTES.md`. Durable conclusions promote to `docs/`; fixes to skills are a **separate triggered step**, never part of the audit run.
