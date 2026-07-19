---
summary: Progress tracker for the Codex notebook-tools MCP server — durable design, guarded cell operations, clean-kernel execution, Codex registration, and verification evidence.
read_when:
  - resuming or implementing notebook-tools
  - checking what notebook MCP behavior has landed or remains deferred
  - validating the direct Codex MCP installation and test evidence
---

# Notebook Tools — Progress

Design: [`../design/notebook-tools.md`](../design/notebook-tools.md)
Successor: [`plugin-packaging.md`](plugin-packaging.md)

## Now

The v0.2 direct-STDIO implementation, phase-2 execution, skill, tests, registration, and
post-restart live Codex acceptance are complete.

## Next

Implement the approved native plugin successor tracked in `plugin-packaging.md`; retain
direct registration until the installed plugin passes live acceptance.

## Milestones

- [x] Approved design and progress tracker written before implementation — `32f7768`
- [x] Harness-neutral notebook model, validation, revision, root, and atomic-write layers — `32f7768`
- [x] `notebook_read`, `notebook_create`, and atomic batch `notebook_edit` — `32f7768`
- [x] Codex-oriented notebook skill and direct-registration runbook — `32f7768`
- [x] Focused domain, filesystem, MCP-contract, and mutation tests — `32f7768`
- [x] Clean-kernel `notebook_execute` with bounded results and guarded write-back — `32f7768`
- [x] Synthetic `_playground` tracer and STDIO MCP discovery — `32f7768`
- [x] `uv run bin/validate.py`, focused suite, `just test`, and diff checks green — `32f7768`

## Verification evidence

- `uv run tests/test_notebook_tools.py`: 12 tests passed, including real clean kernels,
  error continuation, timeout, in-memory execution, and atomic write-back.
- `_playground/2026-07-19_notebook-tools-tracer`: `TRACE_OK` through the public FastMCP
  calls; create/edit/execute revisions differed, output was `42`, and final validation
  passed.
- Independent STDIO client: initialized `Notebook Tools`, discovered all four tools, and
  successfully called `notebook_read` through the configured command.
- `codex mcp get notebook-tools`: enabled with root `/Users/kittipos/my_config` and
  `default_tools_approval_mode: writes`.
- `uv run bin/validate.py`: 27 skills plus manifests and script/hook contracts validated.
- `just test`: 183 repository tests passed.
- `uvx ruff check scripts/notebook-tools tests/test_notebook_tools.py` and
  `git diff --check`: passed.

## Live acceptance

- [x] After restarting Codex, the registered MCP exposed all four tools in a new task;
  create, prompt-free reads, guarded dry-run and commit edits, clean-kernel execution, and
  write-back succeeded against `_tests/notebook-tools-live-test/live-test.ipynb`. Final
  revision `5711fe645bef6a53cf22d2fdd534c0b254e0835c6bc23c8f94b5cbf6dd4083e6` passed
  independent `nbformat.validate` with outputs `15` and `total=15`.

## Confirmed contracts

- Direct local STDIO MCP first; native Codex plugin packaging is deferred.
- Explicit configured roots; absolute `.ipynb` paths only.
- Three phase-1 workflow tools; clean-kernel execution is phase 2.
- Cell ids are canonical; all mutations require a content revision.
- Writes are atomic, validated, bounded, and preserve unrelated semantic content.

## Deferred

- Stateful kernels, notebook rendering, rich image return, and conversion workflows.
- Public Plugin Directory submission, apps, hooks, and visual assets.
