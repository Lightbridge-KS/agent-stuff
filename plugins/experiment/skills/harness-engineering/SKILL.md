---
name: harness-engineering
description: >
  Analyze, scaffold, migrate, or audit a repository's knowledge base — the structured _docs/
  directory, AGENTS.md, and supporting artifacts that make coding agents (Claude Code, Codex,
  Cursor, etc.) effective at working in the codebase.
metadata:
  version: "2026-07-26"
---

# Harness Engineering

A harness is the set of constraints, documentation, feedback loops, and context that keeps a
coding agent productive and on-track. Think of it as onboarding material — not for a new hire,
but for an AI agent that starts every session with zero memory.

The core insight: from the agent's perspective, anything it can't access in-context doesn't
exist. Knowledge in Slack threads, Google Docs, or people's heads is invisible. The repository
must be the single source of truth, organized for progressive disclosure.

This skill helps you build and maintain that system of record.


## When to Read Reference Files

This SKILL.md contains the workflow overview and the canonical knowledge base structure.
For detailed instructions on each verb, read the corresponding reference file:

- `references/analyze.md` — Heuristics for scanning repos, gap detection, report format
- `references/init.md` — Scaffolding templates, involvement-mode customization
- `references/migrate.md` — Patterns for consolidating scattered docs
- `references/audit.md` — Staleness detection, drift checking, doc-gardening


## Core Concepts

### Progressive Disclosure

Agents work best with layered context: a small, stable entry point that teaches them where
to look next. Never dump everything into a single giant file.

```
Layer 0: AGENTS.md (~100 lines)        <-- Always in context, a map
Layer 1: _docs/*.md (top-level guides)   <-- Read on-demand per task domain
Layer 2: _docs/*/  (deep references)     <-- Read only when diving deep
Layer 3: Inline code comments           <-- Discovered while working
```

The agent starts at Layer 0, navigates to Layer 1 based on the task, and drills into
Layer 2 only when it needs specifics. This keeps the working context focused.

### Involvement Modes

The human's preferred level of involvement shapes which documents are emphasized and how
decisions are recorded.

```
MODE           WHAT THE HUMAN DOES          WHAT THE AGENT NEEDS
─────────────  ───────────────────────────  ─────────────────────────────
collaborative  Pair-programs, brainstorms,  Rich design-docs/, decision
               co-writes architecture,      logs, brainstorm scratchpads,
               debates naming & patterns    naming conventions doc

supervisory    Reviews PRs, approves        exec-plans/, quality gates,
               plans, gives async feedback  PR checklists, status updates

directive      Sets goals, monitors KPIs,   exec-plans/active/ as work
               reads progress reports,      orders, progress dashboards,
               operates as work-order       tech-debt-tracker, auto-reports
               issuer (Linear/Jira-like)
```

The mode is declared in `_docs/HARNESS.md` and affects:
- Which doc categories are scaffolded with more detail
- How the agent records decisions (inline vs. formal ADR)
- When the agent escalates vs. proceeds autonomously


## Canonical Knowledge Base Structure

This is the target structure. Not every project needs every file — the Analyze verb helps
determine what's relevant.

```
AGENTS.md                          # Layer 0: map (~100 lines)
_docs/
├── HARNESS.md                     # Harness config: mode, agent prefs, meta
├── ARCHITECTURE.md                # System architecture, module boundaries
├── DESIGN.md                      # Design principles, patterns, conventions
├── QUALITY.md                     # Quality criteria, definition of done
├── SECURITY.md                    # Security policies, sensitive areas
│
├── design-docs/                   # Architecture Decision Records
│   ├── index.md                   #   Index with status + summary
│   ├── 001-auth-strategy.md       #   Individual ADRs
│   └── ...
│
├── exec-plans/                    # Execution plans (task-oriented)
│   ├── active/                    #   Currently in-progress
│   ├── completed/                 #   Done (kept for context)
│   └── tech-debt-tracker.md       #   Known debt + remediation
│
├── product-specs/                 # What the product does (for agents)
│   ├── index.md
│   └── ...
│
├── references/                    # External knowledge, baked-in
│   ├── design-system-llms.txt     #   LLM-friendly reference dumps
│   └── ...
│
└── generated/                     # Auto-generated from code/schema
    ├── db-schema.md               #   Database schema snapshot
    └── api-surface.md             #   Public API summary
```


## Agent Adapter Files

The canonical knowledge base lives in `_docs/`. Thin adapter files at the repo root
translate for specific agents:

| Agent          | File              | Role                                      |
|----------------|-------------------|-------------------------------------------|
| Claude Code    | `CLAUDE.md`       | Points to _docs/, adds Claude-specific tips |
| Codex / GPT    | `AGENTS.md`       | Points to _docs/, adds Codex conventions    |
| Cursor         | `.cursorrules`    | Points to _docs/, adds Cursor rules format  |
| Generic        | `AGENTS.md`       | Default fallback                           |

Each adapter is short (~50-100 lines) and follows the same pattern:
1. Project identity (one-liner)
2. Tech stack summary
3. Pointer to `_docs/ARCHITECTURE.md` for structure
4. Pointer to `_docs/DESIGN.md` for conventions
5. Pointer to `_docs/exec-plans/active/` for current work
6. Agent-specific behavioral instructions

The key insight: **never duplicate** content between adapters and _docs/. Adapters are
pointers + agent-specific instructions only.


## The Four Verbs

### 1. Analyze

**Purpose**: Scan an existing repository and produce a gap report showing what knowledge
base exists, what's missing, what's stale, and what the recommended next steps are.

**When to use**: First contact with any repo, or when the user says the agent "keeps
getting confused" about the codebase.

Quick workflow:
1. Scan repo root for existing agent files (AGENTS.md, CLAUDE.md, .cursorrules, etc.)
2. Scan for _docs/ or similar documentation directories
3. Scan for scattered knowledge (README files, inline TODOs, doc comments)
4. Assess code structure (monorepo? modules? layers?)
5. Produce a gap report with recommendations

Read `references/analyze.md` for detailed heuristics, scoring rubric, and report format.


### 2. Init

**Purpose**: Scaffold a new knowledge base for a project, tailored to its tech stack,
size, and the human's involvement mode.

**When to use**: New projects, or after Analyze reveals that starting fresh is easier
than migrating.

Quick workflow:
1. Ask: tech stack, project type, involvement mode (if not already known)
2. Generate AGENTS.md (or CLAUDE.md) as the Layer 0 map
3. Generate _docs/HARNESS.md with configuration
4. Generate _docs/ARCHITECTURE.md from code inspection
5. Generate remaining docs based on involvement mode priorities
6. Generate agent adapter files as requested

Read `references/init.md` for templates and mode-specific customization.


### 3. Migrate

**Purpose**: Consolidate existing scattered documentation into the canonical structure.

**When to use**: After Analyze reveals useful docs that are disorganized or duplicated.

Quick workflow:
1. Inventory all existing documentation (from Analyze output or fresh scan)
2. Map each source to its target location in the canonical structure
3. Present the migration plan to the human for approval
4. Execute: move, merge, deduplicate, and rewrite for agent legibility
5. Update all internal cross-references
6. Generate the Layer 0 map (AGENTS.md) pointing to new locations

Read `references/migrate.md` for migration patterns and conflict resolution.


### 4. Audit

**Purpose**: Check the knowledge base for staleness, drift from code, orphaned refs,
and coverage gaps.

**When to use**: Periodically, or when the user suspects docs are outdated.

Quick workflow:
1. Compare _docs/ against actual code structure
2. Check for referenced files/modules that no longer exist
3. Check for new modules/features with no documentation
4. Check dates/timestamps for staleness signals
5. Produce an audit report with fix recommendations
6. Optionally, auto-fix simple issues (broken links, stale refs)

Read `references/audit.md` for the audit checklist and auto-fix patterns.


## Principles

These guide every action this skill takes:

1. **The repo is the system of record.** If it's not in the repo, it doesn't exist
   for the agent. Push knowledge into versioned, co-located artifacts.

2. **Map, don't encyclopedia.** AGENTS.md is a table of contents (~100 lines). Deep
   knowledge lives in _docs/. This prevents context overload.

3. **Progressive disclosure.** Agents should receive exactly the context they need for
   the current task — no more, no less.

4. **Don't duplicate, point.** Adapter files point to _docs/. Docs cross-reference each
   other. A fact should live in exactly one place.

5. **Machine-legible first.** Write for agents first, humans second. Use consistent
   headings, predictable file names, and structured formats. But keep it readable for
   humans too — agents and humans share the same repo.

6. **Encode the why.** Don't just state rules — explain reasoning. Agents with context
   on *why* a pattern exists make better judgment calls in novel situations.

7. **Living, not static.** Documentation is a feedback loop. When the agent struggles,
   treat it as a signal to improve the knowledge base.
