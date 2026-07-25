# Migrate: Consolidate Scattered Documentation

Migrate transforms existing disorganized documentation into the canonical knowledge base
structure. It preserves valuable knowledge while reorganizing it for agent legibility.


## Prerequisites

Run Analyze first (or use its output). You need:
- An inventory of all existing documentation
- The gap report identifying what's scattered and what's missing
- The target involvement mode (from user or detection)


## Migration Principles

1. **Preserve, don't discard.** Move content to the right location rather than deleting.
   If something is truly obsolete, archive it (_docs/archived/) rather than removing it.

2. **Merge, don't scatter.** If three README files discuss auth, merge them into one
   section of the appropriate doc, with a single source of truth.

3. **Rewrite for agent legibility.** Casual prose ("we decided to...") should become
   structured documentation with clear headings, predictable format, and explicit
   cross-references. But preserve the reasoning — the "why" is valuable context.

4. **Show the plan first.** Always present the migration plan to the human before
   executing. Reorganizing docs is disruptive — the human should approve.

5. **Maintain git history.** When possible, use `git mv` rather than delete+create,
   so the file history is preserved.


## Step 1: Build the Migration Map

For each existing documentation source, determine its target:

```
Source                          -->  Target
────────────────────────────────     ────────────────────────────────
Root README.md                  -->  Keep (update with _docs/ pointers)
AGENTS.md (monolithic)          -->  Split into AGENTS.md (map) + _docs/*
CLAUDE.md                       -->  Preserve as adapter, extract content to _docs/
module/README.md (arch info)    -->  Merge into _docs/ARCHITECTURE.md
module/README.md (usage info)   -->  Merge into _docs/product-specs/ or keep in-place
ADR files                       -->  Move to _docs/design-docs/
API docs                        -->  Move to _docs/references/ or _docs/generated/
CONTRIBUTING.md                 -->  Extract conventions to _docs/DESIGN.md, keep shell
CHANGELOG.md                    -->  Keep in place (not part of agent knowledge base)
Inline TODO/FIXME               -->  Consolidate into _docs/exec-plans/tech-debt-tracker.md
```


## Step 2: Present the Migration Plan

Show the human a clear plan before touching anything:

```markdown
# Migration Plan: [repo-name]

## Files to Move
| Source | Target | Action |
|--------|--------|--------|
| `_docs/old-arch.md` | `_docs/ARCHITECTURE.md` | rename + restructure |
| `src/auth/README.md` | `_docs/ARCHITECTURE.md` (auth section) | merge |
| ... | ... | ... |

## Files to Create (new)
| File | Content source |
|------|---------------|
| `AGENTS.md` | Extracted from monolithic CLAUDE.md |
| `_docs/HARNESS.md` | New (harness configuration) |
| ... | ... |

## Files to Leave in Place
| File | Reason |
|------|--------|
| `CHANGELOG.md` | Not agent knowledge base material |
| `LICENSE` | Standard, no change needed |

## Estimated Effort
- [X] files to move/merge
- [Y] files to create
- [Z] cross-references to update
```


## Step 3: Execute the Migration

Process files in dependency order to avoid broken cross-references:

```
Execution order:
1. Create directory structure (_docs/ and subdirectories)
2. Create _docs/HARNESS.md (meta-configuration)
3. Migrate architecture docs --> _docs/ARCHITECTURE.md
4. Migrate design/convention docs --> _docs/DESIGN.md
5. Migrate ADRs --> _docs/design-docs/
6. Migrate specs --> _docs/product-specs/
7. Migrate plans/tasks --> _docs/exec-plans/
8. Move reference material --> _docs/references/
9. Generate _docs/generated/* from code (if applicable)
10. Create/update AGENTS.md (Layer 0 map)
11. Update agent adapter files
12. Update root README.md with pointers to _docs/
13. Fix all internal cross-references
```


## Step 4: Handle Merge Conflicts

When multiple sources cover the same topic:

**Strategy: Most-recent-and-complete wins, others supplement.**

1. Identify the most complete and current source as the primary
2. Scan other sources for unique information not in the primary
3. Merge unique information into the primary, attributed with source
4. If sources contradict, flag for human resolution:

```markdown
<!-- MIGRATION NOTE: Conflicting information from two sources.
     Source A (src/auth/README.md, 2024-08): says JWT tokens expire in 1h
     Source B (_docs/old-auth.md, 2025-01): says JWT tokens expire in 24h
     Please resolve which is current. -->
```


## Step 5: Rewrite for Agent Legibility

When migrating content, improve its structure for agent consumption:

**Before (human-conversational):**
```markdown
We talked about this in the team meeting and decided to go with PostgreSQL
instead of MongoDB because we need transactions and our data is pretty
relational. Also Jake pointed out that our ORM works better with SQL.
```

**After (agent-legible):**
```markdown
## Database: PostgreSQL

**Decision**: Use PostgreSQL over MongoDB.

**Rationale**:
- Transactional consistency required for core business operations
- Data model is primarily relational
- ORM compatibility (SQLAlchemy) is stronger with SQL databases

See also: `_docs/design-docs/003-database-choice.md` for the full ADR.
```

Preserve the reasoning but restructure for scannability.


## Step 6: Post-Migration Verification

After migration, verify:

1. **All cross-references resolve.** Every `See also:` and `See _docs/...` pointer
   targets a file that exists.
2. **AGENTS.md map is complete.** Every _docs/ file is reachable from the Layer 0 map.
3. **No orphaned files.** No documentation files left in old locations without a
   redirect or removal note.
4. **Git status is clean.** All moves/renames are staged. Summarize changes for
   the human before committing.

Present a post-migration summary:
```markdown
# Migration Complete

## Stats
- Moved: [X] files
- Merged: [Y] files into [Z] targets
- Created: [W] new files
- Flagged for human review: [N] conflicts

## Action items for human
- [ ] Resolve conflicts marked with MIGRATION NOTE
- [ ] Review _docs/ARCHITECTURE.md for accuracy
- [ ] Confirm involvement mode in _docs/HARNESS.md
```
