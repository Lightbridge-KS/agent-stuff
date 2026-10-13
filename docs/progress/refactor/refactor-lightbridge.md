---
summary: Shared Lightbridge refactoring tracker — command ownership, preserved CLI contracts, verification evidence, and deferred fleet/graph decomposition.
read_when:
  - Planning or implementing a refactor of the lb scripts
  - Reviewing Lightbridge compatibility or refactoring evidence
status: active
date: 2026-10-13
---

# Lightbridge refactoring

Design: [CLI](../../lightbridge/lightbridge-cli-design.md) ·
[module history](../../lightbridge/adr/0001-modular-lightbridge.md) ·
[fleet](../../lightbridge/lightbridge-fleet.md) ·
[graph](../../lightbridge/lightbridge-graph.md).

This tracker spans independent refactoring slices. Completing one slice does not
retire the tracker or authorize a deferred slice. No new ADR is required for the
command-package refactor; current design documentation records the revised layout.

## Shared preserve-list

- CLI flags, defaults, help, stdout/stderr, messages, JSON ordering, exit codes,
  refusal precedence, idempotency, and resulting files remain unchanged.
- Handler signatures and injected `runner`/`ask` seams remain unchanged. Key child
  exit codes pass through, including 127 for failed execution; secret values never
  appear in command output and secret writes precede catalog writes.
- Targeted TOML edits preserve unrelated text; moves retain confirmation and
  filesystem ordering. The dashboard stays offline and reads key metadata only.
- Fleet orchestration, receipts, dry-run behavior, and the streamed node program
  remain unchanged.
- `lb_resolve.py` remains standalone, stdlib-only and sibling-free; the CLI
  entrypoint and installation method remain unchanged. No version/schema change.

## Now

### Slice 1 — command package

Status: in progress. Scope: candidate #1 only.

Approved structure: `lb_commands/{project,repos,graph,keys,fleet,move}.py` plus an
explicit compatibility facade. Project owns configuration, sections, path, dashboard
and doctor. Move owns its confirmation and presentation. Feature helpers stay local.

- `row()` belongs beside `paint()` in `lb_style`; project JSON helpers stay with
  project commands. Public helpers/constants and handlers retain same-object exports.
- Registry-opening diagnostics become `repos.open_registry`; graph linking is the
  only command-family consumer of another command module. No internal facade imports.
- Keep eager imports, ordinary functions, and existing domain modules. No new
  dependencies, wrappers, classes or discovery machinery.

- [x] Establish isolated baseline and representative differential cases.
- [x] Split commands and preserve imports, signatures and object identity.
- [x] Verify dependency rules, negative controls and installed invocation.
- [x] Add affected suites and recursive package syntax checking to CI.
- [x] Update current implementation documentation; retain historical ADRs/trackers.
- [x] Run validation, full tests, syntax checks and whitespace checks.
- [ ] Commit locally; no push or PR.

Proof: behavioral differential runs (outputs, exits, ordered JSON and filesystem
effects), existing regression suites, export identity/signature checks, architecture
tests with violating fixtures, and a copied-tree/symlink invocation outside the repo.
Fleet fixtures must isolate home directories and skill registries.

### Evidence

- Baseline: 290 tests across Lightbridge (90), graph (50), keys (68), fleet (41),
  fleet hook (14), and repo links (27), all passed with isolated homes. An initial
  run inherited `NO_COLOR`, causing three color-test failures; clearing the external
  color override restored the expected test environment without a production change.
- The same 290 tests passed after extraction. The new command suite passed 11 tests:
  same-object exports, 32 historical callable signatures, import graph and negative
  controls, and copied-tree invocation through an executable symlink outside the repo.
- Differential run: 63 CLI cases, zero differences in stdout/stderr, exit codes,
  ordered JSON, file bytes and modes; only fixture paths and timestamps normalized.
  Cases include all command families, refusals/no-ops, dry runs, forced color,
  key execution (including exits 7/127), fleet reports/failures, and move application.
- AST comparison: all 49 original functions retain their signatures and bodies,
  allowing only the approved `_open_registry` → `open_registry` rename.
- Fleet tests now isolate subprocess homes so default registry pruning cannot reach
  the invoking account's skill links. Real SSH and real key data are not used.
- Full local `just test`: 24 suites, 619 tests reported, 608 passed and 11 skipped
  (7 optional de-identification live tests; 4 optional rich-document live tests).
  The strengthened package-ownership check was rerun afterward: all 11 command tests
  passed. No unresolved baseline failures remain.
- `uv run bin/validate.py`, Ruff checks/formatting for new modules and the command
  suite, recursive Lightbridge syntax compilation, and `git diff --check` passed.
- Resolver, graph/fleet/key/move implementations and historical ADRs are unchanged.
  CI configuration includes the affected suites, but hosted CI has not run.
- Implementation commit: pending local commit.

## Deferred

- Candidate #2: separate fleet node program, transport and hub state. Not approved
  for implementation.
- Candidate #3: separate graph document operations from visualization. Not approved
  for implementation.

## Next

Complete slice 1. Future approved lb refactors append slices to this same tracker.
