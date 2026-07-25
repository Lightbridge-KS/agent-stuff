# Init: Scaffold a Repository Knowledge Base

Init creates the knowledge base structure from scratch (or fills in gaps after Analyze).
The output adapts to the project's tech stack, size, and the human's involvement mode.


## Step 1: Gather Project Context

Before scaffolding, confirm these inputs (ask if not already known):

```
Required:
  - Project name and one-line description
  - Primary language(s) and framework(s)
  - Project type: app | library | CLI | service | monorepo
  - Involvement mode: collaborative | supervisory | directive

Helpful (infer from code if possible):
  - Module/package structure
  - Database? API? Frontend?
  - External dependencies that need documentation
  - Deployment target (cloud, self-hosted, etc.)
```


## Step 2: Generate HARNESS.md

This is the meta-configuration for the knowledge base itself. It lives at `_docs/HARNESS.md`.

```markdown
# Harness Configuration

## Project
- **Name**: [project-name]
- **Type**: [app|library|CLI|service|monorepo]
- **Stack**: [e.g., Python 3.12, FastAPI, PostgreSQL, React]

## Involvement Mode
- **Mode**: [collaborative|supervisory|directive]
- **Review style**: [inline|pr-based|async-report]

## Agent Preferences
- **Primary agent**: [Claude Code|Codex|Cursor|generic]
- **Adapter files**: [list which adapters are generated]

## Knowledge Base Layout
[Describe which _docs/ sections are active and why]

## Conventions
- Design decisions recorded in: _docs/design-docs/
- Execution plans tracked in: _docs/exec-plans/active/
- Generated docs refreshed by: [manual|script|CI]
```


## Step 3: Generate the Layer 0 Map

The AGENTS.md (or CLAUDE.md) is the agent's entry point. Keep it ~100 lines.

Template structure:

```markdown
# [Project Name]

[One-paragraph project description: what it does, who it's for, key constraints]

## Tech Stack
[Bulleted list: language, framework, database, deployment]

## Architecture
See `_docs/ARCHITECTURE.md` for the full system map.

[2-3 sentence summary: e.g., "Layered architecture with strict dependency flow:
Types -> Config -> Repo -> Service -> Runtime -> UI. Each domain module is
self-contained with its own models, services, and tests."]

## Key Conventions
See `_docs/DESIGN.md` for full design conventions.

[5-10 most critical rules, e.g.:]
- [Naming convention]
- [Error handling pattern]
- [Testing approach]
- [Import/dependency rules]

## Current Work
See `_docs/exec-plans/active/` for current execution plans.

## Documentation Map
- `_docs/ARCHITECTURE.md` — System structure, module boundaries, dependency flow
- `_docs/DESIGN.md` — Design principles, naming, patterns, code style
- `_docs/QUALITY.md` — Quality criteria, testing strategy, definition of done
- `_docs/SECURITY.md` — Security policies, auth patterns, sensitive areas
- `_docs/design-docs/` — Architecture Decision Records (see index.md)
- `_docs/exec-plans/` — Task plans: active/, completed/, tech-debt-tracker.md
- `_docs/product-specs/` — Product behavior specs (see index.md)
- `_docs/references/` — External reference material for agent context
- `_docs/generated/` — Auto-generated docs (schema, API surface)
```


## Step 4: Generate Docs by Involvement Mode

All modes get the base set. The involvement mode determines which docs get **extra depth**.

### Base Set (all modes)

| File                     | Content                                     |
|--------------------------|---------------------------------------------|
| `_docs/ARCHITECTURE.md`   | Module map, dependency flow, layer rules     |
| `_docs/DESIGN.md`         | Naming, patterns, error handling, style      |
| `_docs/HARNESS.md`        | Harness configuration (see Step 2)           |

### Collaborative Mode Additions

Collaborative humans co-author the knowledge base. Emphasize:

| File                             | Why                                         |
|----------------------------------|---------------------------------------------|
| `_docs/design-docs/index.md`      | ADRs for every significant decision          |
| `_docs/design-docs/core-beliefs.md` | Team's engineering philosophy              |
| `_docs/DESIGN.md` (extended)      | Extra detail on naming, patterns, rationale  |

Template for `_docs/design-docs/NNN-title.md`:
```markdown
# [Decision Title]
- **Status**: proposed | accepted | superseded
- **Date**: YYYY-MM-DD
- **Context**: [What problem or question prompted this decision]
- **Decision**: [What we chose and why]
- **Alternatives considered**: [What else we evaluated]
- **Consequences**: [What changes as a result]
```

### Supervisory Mode Additions

Supervisory humans review work. Emphasize quality gates and clear plans:

| File                             | Why                                         |
|----------------------------------|---------------------------------------------|
| `_docs/QUALITY.md` (extended)     | PR checklist, review criteria, DoD           |
| `_docs/exec-plans/active/`        | Detailed plans for agent to follow           |
| `_docs/exec-plans/plan-template.md` | Standardized plan format                   |

Template for `_docs/exec-plans/active/plan-title.md`:
```markdown
# [Plan Title]
- **Status**: not-started | in-progress | review | done
- **Goal**: [What this accomplishes]
- **Scope**: [What's in and out]
- **Steps**:
  1. [Step with clear success criteria]
  2. [Step ...]
- **Quality gate**: [What must pass before marking done]
- **Escalation**: [When to ask the human]
```

### Directive Mode Additions

Directive humans operate through work orders. Emphasize status and autonomy:

| File                                | Why                                       |
|-------------------------------------|-------------------------------------------|
| `_docs/exec-plans/active/` (primary) | Work orders as the main interface          |
| `_docs/exec-plans/tech-debt-tracker.md` | Agent-maintained debt log              |
| `_docs/QUALITY.md`                    | Automated quality criteria                |
| `_docs/generated/` (populated)        | Auto-generated context the agent needs    |

Template for directive work orders in `_docs/exec-plans/active/`:
```markdown
# WO-[number]: [Title]
- **Priority**: P0 | P1 | P2 | P3
- **Status**: queued | in-progress | blocked | done
- **Objective**: [Clear goal statement]
- **Acceptance criteria**:
  - [ ] [Criterion 1]
  - [ ] [Criterion 2]
- **Constraints**: [Boundaries the agent must respect]
- **Notes**: [Any additional context]
- **Progress log**:
  - [date]: [what was done]
```


## Step 5: Generate Agent Adapter Files

Generate adapters for the requested agents. Each adapter follows the same skeleton
but with agent-specific behavioral instructions appended.

### Claude Code (CLAUDE.md) specifics:
```
# Additional instructions for Claude Code
- Read _docs/ARCHITECTURE.md before making structural changes
- When creating new modules, follow the patterns in _docs/DESIGN.md
- Record significant decisions in _docs/design-docs/
- Update _docs/exec-plans/ when completing or starting tasks
```

### Codex (AGENTS.md) specifics:
```
# Agent instructions
- Start every task by reading relevant _docs/ files
- Use gh CLI for PR operations
- Run local tests before requesting review
- Update documentation when changing public interfaces
```

### Cursor (.cursorrules) specifics:
```
# Cursor-specific rules
- Follow conventions in _docs/DESIGN.md
- Reference _docs/ARCHITECTURE.md for module boundaries
- Check _docs/exec-plans/active/ for current priorities
```

Reminder: adapters are pointers + behavior, never content duplication.


## Step 6: Verify and Summarize

After generating all files:
1. Verify all cross-references resolve (every pointer in AGENTS.md has a target)
2. Count total files generated
3. Present a summary to the human showing what was created and why
4. Suggest immediate next steps (e.g., "populate design-docs as you make decisions")
