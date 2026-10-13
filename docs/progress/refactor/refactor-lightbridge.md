---
summary: Shared Lightbridge refactoring tracker — command, fleet and graph package ownership, preserved contracts, and verification evidence.
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
retire the tracker or authorize a deferred slice. No new ADR is required for these
refactors; current design documentation records the revised layouts.

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

Status: complete. Scope: candidate #1 only. Implementation: `7c91252`.

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
- [x] Commit locally; no push or PR — `7c91252`.

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
- Implementation commit: `7c91252` (`refactor(lightbridge): split command handlers by ownership`).
  Committed locally; no push or PR.

## Slice 2 — fleet mechanics package

Status: complete. Baseline: `88ad30d`. Scope: candidate #2 only. Implementation: `7a72ab8`.

Approved structure: `lb_fleet/{node_program,transport,hub}.py` and an explicit
same-object compatibility facade. Node program owns the template, rendering and
report parsing; transport owns SSH and unreachable classification; hub owns the
inventory seed/selection, local Git and atomic receipts. No cross-owner imports,
facade imports, command dependencies, new dependencies or behavior changes.
Readers remain in standalone `lb_resolve.py`; command orchestration stays in
`lb_commands/fleet.py`. The template and rendered programs remain byte-identical.

Preserve the shared contracts above, including all pulls before any apply and all
applies before verification, inventory order, refusal precedence, runner defaults,
exit mappings, last-report-marker precedence and receipt failure cleanup.

- [x] Capture isolated baseline and characterize ordering, transport, parsing and receipts.
- [x] Extract the three owners and preserve public exports/signatures.
- [x] Prove template/rendered bytes, CLI behavior and filesystem parity.
- [x] Extend architecture checks with negative controls and installed invocation.
- [x] Update current documentation without changing historical ADRs or trackers.
- [x] Run affected suites, validation, full tests, recursive syntax and Ruff checks.
- [x] Commit locally and record evidence/reference; no push or PR — `7a72ab8`.

Proof requirements: temporary homes/registries, local Git fixtures and fake SSH;
old/new stdout, stderr, exits, ordered JSON and filesystem effects; same-object
exports and baseline signatures; dependency/cycle rejection; copied-tree symlink
execution outside the checkout without repository PYTHONPATH. Only fixture paths
and nondeterministic timestamps may be normalized. Discovered behavior defects
remain separate from this refactor.

### Slice 2 evidence

- Baseline: all 301 tests across the seven affected suites passed with isolated
  homes. Seven new characterization tests passed against the original module
  before extraction; the package-contract suite subsequently grew from 11 to 26 tests.
- All 316 affected tests passed after extraction. Tests cover 26 same-object
  exports, 15 baseline callable signatures, template/rendered-program SHA-256
  equality, transport exception mappings, last-marker parsing, phase ordering and
  atomic-receipt failure cleanup (including interruption).
- All 14 original function ASTs and all 10 constant-assignment ASTs match exactly.
  The rendered program also passes a Python 3.8 syntax parse; runtime execution was
  tested with the local interpreter, not a separate Python 3.8 installation.
- Differential evidence: 31 fleet CLI cases execute against local Git worlds and
  fake SSH; 63 broader CLI cases cover all command families. Both runs have zero
  differences in stdout/stderr, exits, ordered JSON and resulting file bytes/modes.
  Fleet comparisons also check Git state and the streamed program hash. Only
  fixture paths and nondeterministic timestamps are normalized. Initial broader
  comparison included a cold-cache `uv` installation message; rerunning both sides
  with warm dependency caches removed that harness noise without a code change.
- Architecture tests recognize both package roots and reject cross-owner, facade,
  command/entrypoint, transitive and cyclic dependencies using negative fixtures.
  Copied-tree invocation from an unrelated directory through an `lb` symlink
  executes status and reinstall through fake SSH and verifies the resulting receipt.
  The standalone resolver-loading regression remains in the affected suite.
- Full local `just test`: 24 suites, 634 tests reported, 623 passed and 11 skipped
  (7 optional de-identification live tests; 4 optional rich-document live tests).
  Validation, recursive Lightbridge syntax compilation, Ruff checks/formatting for
  the new package and expanded contract suite, and whitespace checks passed.
  No unresolved baseline failures remain. Resolver, command implementation, graph,
  key and move code and historical ADRs/trackers are unchanged.
- The existing CI entries already run the expanded suite and recursively compile
  Lightbridge packages; no duplicate gates were added. Hosted CI has not run.
- Implementation commit: `7a72ab8` (`refactor(lightbridge): split fleet mechanics by ownership`).
  Committed locally; no push or PR.

## Slice 3 — graph document and visualization package

Status: complete. Baseline: `d63e945`. Scope: candidate #3 only. Implementation: `31db422`.

Approved structure: `lb_graph/{document,visualization}.py` with an explicit facade
re-exporting the 20 existing public functions, enums and constants as the same
objects. Document owns vocabulary, edge edits, semantics and audit. Visualization
owns node grouping, shared visualization data, Mermaid and the inline HTML template.
The sole intra-package edge is `visualization → document.effective_mode`.
No facade, command, fleet or entrypoint imports from implementation modules.

Preserve the shared contracts and all targeted TOML bytes, vocabulary/enum order,
backlink fallback behavior, audit finding order, visualization ordering and exact
Mermaid/HTML output. Keep `edge_sentence`, `effective_mode` and resolver projection
separate. No new dependencies, asset loading, wrappers, schema or behavior changes.
Graph readers/projection remain in standalone `lb_resolve.py`; command orchestration
stays in `lb_commands/graph.py`. Completed command/fleet implementations stay intact.

- [x] Capture isolated baseline and characterize document edits, semantics, audit and visualization.
- [x] Extract document/visualization owners and preserve public identity/signatures.
- [x] Verify AST equality, full output bytes and CLI/filesystem differential parity.
- [x] Extend architecture negative controls and copied-tree/symlink installation tests.
- [x] Update current documentation; preserve historical trackers and ADRs.
- [x] Run seven affected suites, full tests, validation, recursive syntax and Ruff checks.
- [x] Commit locally and record evidence/reference; no push or PR — `31db422`.

Proof requirements: temporary homes and explicit graph/registry fixtures; warm
old/new dependency caches; stdout/stderr/exits, ordered JSON, TOML/HTML bytes and
file modes; enum identity/member order; exact template/output hashes; dependency
and cycle rejection. Normalize only fixture paths and nondeterministic timestamps.
Any discovered behavior fixes remain outside this slice.

### Slice 3 evidence

- Baseline: all 316 tests across seven affected suites passed with isolated homes.
  Five new characterization tests passed against the original module before
  extraction. They cover four document layouts (including CRLF and missing final
  newline), 25 backlink/direction cases, three complete visualization outputs and
  three audits with exact message/finding order.
- All 328 affected tests passed after extraction; the package-contract suite grew
  from 26 to 38 tests. Checks pin 20 facade exports, 13 function signatures, both
  enum identities/member orders, seed constants and complete HTML/template hashes.
- All 15 original function ASTs, both enum class ASTs and all seven constant
  assignment ASTs match exactly. The inline HTML template is byte-identical.
- Differential evidence: 153 graph CLI cases (plain, JSON and forced color plus
  enum/help checks) and 63 broader CLI cases, zero differences in stdout/stderr,
  exit status, ordered JSON and resulting TOML/HTML/file bytes and modes. Both
  dependency caches were warm; only fixture paths were normalized. The graph run
  includes 84 successes, 63 refusals/problems and six usage errors.
- Architecture checks allow only `visualization → document`, rejecting reverse,
  facade, command/fleet/entrypoint, transitive and cyclic imports with negative
  fixtures. Existing command/fleet rules remain in force.
- Copied-tree invocation through an `lb` symlink outside the checkout creates,
  links and edits a graph, exercises backlink enum choices, and compares complete
  Mermaid/HTML output. No repository PYTHONPATH is used. Standalone resolver and
  repo-links projection regressions remain in the affected suites.
- Full local `just test`: 24 suites, 646 tests reported, 635 passed and 11 skipped
  (7 optional de-identification live tests; 4 optional rich-document live tests).
  Validation, recursive Lightbridge syntax compilation, Ruff checks/formatting for
  the new package and expanded contract suite, and whitespace checks passed.
  No unresolved baseline failures remain.
- Resolver, TOML substrate, command and fleet implementations and historical
  ADRs/trackers are unchanged. Existing CI entries cover the expanded tests and
  recursive compilation; hosted CI has not run.
- Implementation commit: `31db422` (`refactor(lightbridge): split graph document and visualization`).
  Committed locally; no push or PR.

## Deferred

No further refactoring candidates are approved beyond Slice 3.

## Next

Slices 1, 2 and 3 are complete. Future approved lb refactors append slices to this
active tracker; completing these slices does not retire it or authorize additional
refactoring work.
