---
summary: Progress tracker for the Codex notebook-tools MCP server — durable design, guarded cell operations, clean-kernel execution, Codex registration, and verification evidence.
read_when:
  - resuming or implementing notebook-tools
  - checking what notebook MCP behavior has landed or remains deferred
  - validating the direct Codex MCP installation and test evidence
---

# Notebook Tools — Progress

Design: [`../design/notebook-tools.md`](../design/notebook-tools.md)

## Now

The v0.2 direct-STDIO implementation, phase-2 execution, skill, tests, tracer, and local
Codex registration are complete in the working tree.

## Next

Restart Codex so the already-running desktop task reloads MCP configuration, then confirm
the final approval UX: reads do not prompt and create/edit/execute remain write-aware.

## Milestones

- [x] Approved design and progress tracker written before implementation — commit: pending
- [x] Harness-neutral notebook model, validation, revision, root, and atomic-write layers — commit: pending
- [x] `notebook_read`, `notebook_create`, and atomic batch `notebook_edit` — commit: pending
- [x] Codex-oriented notebook skill and direct-registration runbook — commit: pending
- [x] Focused domain, filesystem, MCP-contract, and mutation tests — commit: pending
- [x] Clean-kernel `notebook_execute` with bounded results and guarded write-back — commit: pending
- [x] Synthetic `_playground` tracer and STDIO MCP discovery — commit: pending
- [x] `uv run bin/validate.py`, focused suite, `just test`, and diff checks green — commit: pending

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

## Remaining live check

- [ ] After restarting Codex, confirm reads do not prompt and writes do prompt. The current
  task cannot hot-reload a server registered after task startup.

## Confirmed contracts

- Direct local STDIO MCP first; native Codex plugin packaging is deferred.
- Explicit configured roots; absolute `.ipynb` paths only.
- Three phase-1 workflow tools; clean-kernel execution is phase 2.
- Cell ids are canonical; all mutations require a content revision.
- Writes are atomic, validated, bounded, and preserve unrelated semantic content.

## Deferred

- Native `.codex-plugin` and marketplace packaging.
- Stateful kernels, notebook rendering, rich image return, and conversion workflows.
