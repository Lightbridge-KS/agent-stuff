---
summary: Settled design for the Codex notebook-tools MCP server — its cell-aware tool contract, filesystem boundary, atomic writes, bounded results, and clean-kernel execution model.
read_when:
  - implementing or changing notebook-tools MCP schemas or behavior
  - changing notebook path safety, cell identity, revisions, or atomic saves
  - changing notebook execution, output handling, or Codex registration
---

# Notebook Tools — Design

> Status: approved 2026-07-19 · Interface: local STDIO MCP · Runtime: Python 3.11+ via `uv`

## Goal

Give Codex deterministic, cell-aware operations for Jupyter notebooks without raw JSON
surgery. The first release combines the OpenClaw implementation's safety invariants with
the Pi extension's smaller workflow-level tool surface.

```text
Codex
  -> MCP tool call
Notebook MCP adapter
  -> notebook domain service
     -> nbformat validation
     -> guarded atomic filesystem write
     -> clean nbclient kernel (execution tool only)
```

The MCP adapter owns schemas, annotations, and compact results. Notebook mutation and
execution code do not depend on Codex or the MCP runtime.

## Tool surface

### `notebook_read`

Read and validate one absolute `.ipynb` path. It supports:

- `mode = outline | cells` (`outline` by default);
- targeted `cell_ids`, or source search with `query` (mutually exclusive);
- `offset` pagination with at most 50 cells by default;
- optional source and text-output previews.

Results include the content-derived notebook `revision`, nbformat and kernel facts,
validation warnings, and cells with current index, stable id, `id_persisted`, type,
preview, source hash, execution count, and output count. Source previews are capped at 80
lines per cell. Outputs are off by default; when requested, at most five items and 2,000
text characters per cell are returned. Rich MIME payloads are represented by MIME type and
size, never by model-visible base64.

Annotations: read-only, idempotent, closed-world.

### `notebook_create`

Create an nbformat 4.5 notebook from structured markdown, code, and raw cells. The default
kernel is `python3` / `Python 3` / `python`. Existing paths are never overwritten. Code
cells start with `execution_count = null` and no outputs. The result returns the initial
revision and generated cell ids.

Annotations: write, additive, non-idempotent, closed-world.

### `notebook_edit`

Apply an ordered list of `replace`, `insert_before`, `insert_after`, `delete`,
`move_before`, `move_after`, and `clear_outputs` operations. `expected_revision` is
required. The entire batch is computed and validated in memory before any write; one bad
operation aborts the batch. `dry_run` returns the proposed change set without writing.

Replacing or converting a cell to code clears execution artifacts. `clear_outputs` with no
cell id affects every code cell. A committed edit returns the new revision, change summary,
and any legacy-handle-to-persisted-id mapping.

Annotations: write, destructive, non-idempotent, closed-world, including dry runs so host
approval remains conservative.

### `notebook_execute` (phase 2)

Start a fresh Jupyter kernel and execute cells in notebook order, optionally stopping after
one cell id. There are no reusable or hidden kernel sessions. Defaults:

- kernel from an explicit override, then notebook metadata;
- notebook parent as working directory;
- 120-second timeout per cell;
- `allow_errors = false`;
- `write_back = false`.

In-memory execution leaves the notebook file unchanged but may still have arbitrary code
side effects. `write_back = true` requires `expected_revision`, then uses the same guarded
atomic save path. Cancellation or timeout shuts the kernel down. Results contain bounded
per-cell status and output summaries plus the first execution failure.

Annotations: write, destructive, non-idempotent, open-world.

## Shared contracts

### Paths and roots

The server refuses to start without at least one repeated absolute `--root`. Tool paths
must be absolute and end in `.ipynb`. Paths and their existing or prospective parents are
resolved through symlinks and must remain under an allowed root. The initial local Codex
registration allows only `/Users/kittipos/my_config`; other roots are explicit additions,
never hard-coded defaults.

### Cell identity

Persisted nbformat 4.5 cell ids are the canonical write address. For a legacy cell without
an id, reads return a deterministic temporary handle and `id_persisted = false`. A guarded
write can use that handle; before committing, the server assigns valid unique ids to every
legacy cell and returns the mapping. Derived ids stay stable between a dry run and its
commit while the revision is unchanged. Indexes are presentation only.

### Revisions and atomic writes

`revision` is the SHA-256 of the exact notebook bytes read. Each path has an in-process
lock. A write re-reads and re-hashes the file immediately before replacement, validates the
candidate with `nbformat`, serializes with one-space indentation without sorting keys,
writes a sibling temporary file, preserves the original mode, flushes and fsyncs it,
replaces with `os.replace`, and fsyncs the parent directory. Failed writes remove the temp
file and leave the original intact. Unknown notebook, cell, attachment, and metadata fields
are preserved; nbformat validation relaxes only additional properties so future/vendor
fields survive while known structure is still checked.

### Results and errors

Each result carries a short text summary plus bounded `structuredContent`. Expected
failures set MCP `isError` and return:

```json
{"ok": false, "error": {"code": "STALE_REVISION", "message": "...", "recovery": "..."}}
```

Stable codes are `OUTSIDE_ALLOWED_ROOT`, `NOTEBOOK_NOT_FOUND`, `INVALID_NOTEBOOK`,
`UNSUPPORTED_NBFORMAT`, `CELL_NOT_FOUND`, `STALE_REVISION`, `INVALID_OPERATION`,
`KERNEL_NOT_FOUND`, `EXECUTION_TIMEOUT`, and `CELL_EXECUTION_ERROR`.

The server instructions lead with the read-before-edit workflow, revision guard, cell ids,
code-output clearing, and prohibition on raw JSON edits. The installed skill adds the
human-plus-agent workflow without copying schemas from the server.

## Non-goals

- Stateful or shared kernel sessions.
- Visual notebook rendering or a custom Codex UI.
- Notebook-to-script conversion or multi-notebook batch migrations.
- Native Codex plugin packaging in v0.1 or v0.2.
- Backups or persistent lock sidecars next to user notebooks.

## Acceptance

- Codex can create, inspect, search, batch-edit, and clean-kernel execute synthetic
  notebooks through MCP without raw JSON.
- Read tools are marked read-only; write and execution tools participate in Codex's
  write-approval policy.
- Stale revisions, invalid batches, path escapes, execution failures, and save failures do
  not modify the notebook.
- Successful mutations and write-back execution validate and reload before success.
- All outputs are bounded and all fixtures are synthetic, with no PHI or private data.
