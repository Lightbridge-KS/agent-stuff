# Analyze: Repository Knowledge Base Assessment

Analyze is the entry point. Before scaffolding, migrating, or auditing, you need to
understand what exists. This reference covers the full analysis workflow.


## Step 1: Scan for Agent Files

Check the repo root (and common alternative locations) for existing agent configuration:

```
Look for:
  AGENTS.md, agents.md
  CLAUDE.md, claude.md
  .cursorrules, .cursor/rules
  .github/copilot-instructions.md
  CONVENTIONS.md, CONTRIBUTING.md
  .editorconfig, .prettierrc (tangential but signals care for consistency)
```

For each file found, note:
- Location and size (lines)
- Whether it's a "map" (short, with pointers) or a "monolith" (long, self-contained)
- Last modified date (if available via git log)
- Whether it references other docs or is standalone


## Step 2: Scan for Documentation Directories

Look for structured documentation:

```
Look for:
  _docs/, doc/, documentation/
  .github/_docs/
  wiki/ (rare but possible)
  design-docs/, adrs/, architecture/
  specs/, product-specs/
  plans/, roadmap/
```

For each directory found, note:
- Structure (flat vs. organized into subdirectories)
- File types present (.md, .txt, .pdf, .rst, etc.)
- Approximate coverage (does it cover architecture? Design? Plans?)
- Internal cross-linking (do files reference each other?)


## Step 3: Scan for Scattered Knowledge

Knowledge often hides in unexpected places:

```
Scattered knowledge sources:
  README.md (root and per-directory)
  Inline code comments (especially file headers, module docstrings)
  TODO/FIXME/HACK comments
  Package manifests (package.json description, pyproject.toml metadata)
  CI/CD configs (.github/workflows/ — reveals build/deploy conventions)
  Commit messages and PR templates
  Changelog / HISTORY files
  Test descriptions (test names often encode domain knowledge)
```

Don't try to read everything — sample strategically. Look at:
- Root README.md (always)
- 2-3 representative module/package READMEs
- File headers of core modules
- The CI pipeline config


## Step 4: Assess Code Structure

Understand the codebase shape to inform what docs are needed:

```
Assess:
  Project type:     monorepo | single-app | library | CLI tool | service
  Languages:        primary + secondary
  Framework:        major frameworks in use
  Module structure:  how is code organized? (by feature, by layer, by domain)
  Dependency flow:   can you identify architectural layers?
  Test coverage:     is there a test directory? What kind of tests?
  Build system:      what tools build/run the project?
```


## Step 5: Produce the Gap Report

The gap report is the primary output of Analyze. Structure it as follows:

```markdown
# Knowledge Base Analysis: [repo-name]

## Summary
- **Overall readiness**: [score]/5 (see Scoring Rubric below)
- **Involvement mode detected**: [collaborative|supervisory|directive|unclear]
- **Recommended action**: [init-from-scratch | migrate-existing | light-touch-audit]

## What Exists
[List each found artifact with a one-line assessment]

## Gaps
[What's missing, organized by the canonical structure categories]

## Scattered Knowledge
[Valuable knowledge found outside a structured location]

## Recommendations
[Prioritized list of next steps, referencing Init, Migrate, or Audit verbs]
```


## Scoring Rubric

Rate the repo's agent-readiness from 0 to 5:

```
0 — No agent docs, no structured documentation at all
1 — A README exists but no agent-specific files or _docs/ directory
2 — An AGENTS.md or equivalent exists but is monolithic or stale
3 — Some structured docs exist, but gaps in coverage or cross-linking
4 — Good _docs/ structure, mostly current, minor gaps
5 — Full canonical structure, well-maintained, progressive disclosure works
```


## Involvement Mode Detection

Infer the human's involvement mode from signals in the repo:

```
Collaborative signals:
  - Design docs with discussion/rationale
  - Detailed commit messages explaining "why"
  - Comments that read like conversations
  - ADRs with alternatives considered

Supervisory signals:
  - PR templates with checklists
  - CODEOWNERS file
  - Branch protection rules referenced
  - Review guidelines

Directive signals:
  - Issue templates as work orders
  - Roadmap or milestone files
  - Status/progress tracking files
  - Minimal inline comments, more spec-driven
```

If unclear, don't guess — ask the user about their preferred involvement mode.


## Example Output

Here's an abbreviated example of a gap report:

```markdown
# Knowledge Base Analysis: my-saas-app

## Summary
- **Overall readiness**: 2/5
- **Involvement mode detected**: collaborative (based on detailed ADRs)
- **Recommended action**: migrate-existing

## What Exists
- `README.md` (48 lines) — good project overview, slightly outdated
- `CLAUDE.md` (12 lines) — exists but minimal, just says "use TypeScript"
- `_docs/architecture.md` (120 lines) — solid but references deleted modules
- `_docs/adr/` (6 files) — well-written ADRs, last updated 3 months ago

## Gaps
- No AGENTS.md or equivalent map file
- No design conventions doc (naming, patterns, error handling)
- No execution plans or task tracking
- No security documentation
- No generated docs (schema, API surface)
- _docs/ lacks an index — agent must guess which file to read

## Scattered Knowledge
- `src/auth/README.md` has critical auth flow documentation
- `package.json` scripts contain undocumented deployment steps
- `.github/workflows/deploy.yml` has inline comments about staging rules

## Recommendations
1. **Migrate** existing docs into canonical structure (high priority)
2. **Init** missing sections: DESIGN.md, SECURITY.md, exec-plans/
3. Consolidate scattered READMEs into _docs/ with cross-references
4. Generate db-schema.md and api-surface.md from code
5. Write a proper AGENTS.md map pointing to all docs
```
