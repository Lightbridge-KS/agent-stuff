# Audit: Knowledge Base Health Check

Audit checks the knowledge base for staleness, drift, and coverage gaps. It's the
"doc-gardening" function — run periodically to prevent the knowledge base from rotting.


## When to Audit

- Periodically (suggest monthly for active projects)
- After major refactors or feature additions
- When the agent reports confusion or makes incorrect assumptions
- When the human says "docs feel outdated"


## The Audit Checklist

Work through these checks in order. Each check produces findings that feed into the
final audit report.

### Check 1: Structural Integrity

Verify the knowledge base skeleton is intact:

```
[ ] AGENTS.md (or equivalent adapter) exists at repo root
[ ] _docs/ directory exists with expected subdirectories
[ ] _docs/HARNESS.md exists and is consistent with actual setup
[ ] _docs/ARCHITECTURE.md exists
[ ] _docs/DESIGN.md exists
[ ] All directories referenced in AGENTS.md actually exist
[ ] All files referenced in AGENTS.md actually exist
[ ] index.md files exist in directories that need them
```

### Check 2: Cross-Reference Integrity

Find broken links and orphaned references:

```
For every "See _docs/..." or "See also:" reference in the knowledge base:
  - Does the target file exist?
  - Does the target heading/section exist? (if linking to a section)
  - Is the reference bidirectional where it should be?

For every file in _docs/:
  - Is it reachable from AGENTS.md (directly or via index.md)?
  - If not reachable, is it intentionally deep (Layer 2+)?
```

### Check 3: Code-Documentation Drift

Compare documentation claims against actual code:

```
Architecture drift:
  - Does ARCHITECTURE.md mention modules that no longer exist?
  - Are there new modules not mentioned in ARCHITECTURE.md?
  - Do dependency flow claims match actual import patterns?

Convention drift:
  - Do naming conventions in DESIGN.md match actual code patterns?
  - Are deprecated patterns still documented as current?

API drift (if _docs/generated/ exists):
  - Does db-schema.md match actual schema?
  - Does api-surface.md match actual endpoints?
```

To check drift efficiently, compare document content against code structure:
- List all top-level directories/modules in the codebase
- Cross-reference against modules mentioned in ARCHITECTURE.md
- Flag discrepancies in both directions (doc mentions ghost module, or module has no doc)

### Check 4: Staleness Detection

Check for documents that may be outdated:

```
Signals of staleness:
  - File not modified in >3 months (check git log)
  - References to technologies/versions no longer in use
  - TODO or FIXME items that have been resolved in code
  - "Planned" or "upcoming" items that are now shipped or abandoned
  - exec-plans/active/ plans that should be in completed/
  - Version numbers that don't match current release
```

### Check 5: Coverage Gaps

Identify areas of the codebase with insufficient documentation:

```
For each major module/domain:
  - Is it mentioned in ARCHITECTURE.md?
  - Does it have relevant design docs or product specs?
  - Are its key interfaces documented?
  - Are its architectural boundaries clear?

For recent changes (check git log for last month):
  - Were significant changes accompanied by doc updates?
  - Are new features reflected in product-specs/?
  - Are new decisions reflected in design-docs/?
```

### Check 6: Involvement Mode Alignment

Check that the knowledge base matches the declared involvement mode:

```
If collaborative:
  - Are design-docs being regularly created?
  - Do recent decisions have ADRs?

If supervisory:
  - Are exec-plans up to date?
  - Is QUALITY.md being followed (check recent PRs)?

If directive:
  - Are work orders in exec-plans/active/ current?
  - Is tech-debt-tracker.md maintained?
  - Are progress logs in work orders updated?
```


## The Audit Report

Structure the output as follows:

```markdown
# Knowledge Base Audit: [repo-name]
**Date**: YYYY-MM-DD
**Overall health**: [healthy | needs-attention | degraded]

## Summary
- Structural issues: [count]
- Broken references: [count]
- Drift detected: [count]
- Stale documents: [count]
- Coverage gaps: [count]

## Findings

### Critical (fix now)
[Issues that actively confuse the agent or cause errors]

### Warning (fix soon)
[Issues that degrade agent effectiveness]

### Info (fix when convenient)
[Minor issues, nice-to-haves]

## Recommended Fixes
[Prioritized list of actions, some of which can be auto-fixed]

## Auto-Fixable Issues
[Issues the agent can fix right now with human approval]
- [ ] Update module list in ARCHITECTURE.md (add: X, remove: Y)
- [ ] Move completed plan from active/ to completed/
- [ ] Fix broken reference in design-docs/index.md
```


## Auto-Fix Patterns

Some issues can be fixed automatically (with human approval):

| Issue                              | Auto-fix                                    |
|------------------------------------|---------------------------------------------|
| Broken cross-reference             | Update path to correct location              |
| Completed plan in active/          | Move to completed/                           |
| Missing file in index.md           | Add entry to index                           |
| New module not in ARCHITECTURE.md  | Add stub entry with TODO for human           |
| Stale generated doc                | Re-generate from code                        |

Always present auto-fixes as a batch for human approval before executing. Never
silently modify documentation — the human should know what changed and why.
