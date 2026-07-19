---
name: notebook-tools
description: >-
  Use the local notebook-tools MCP server to create, inspect, edit, and execute Jupyter
  notebooks through stable cell-aware operations. Use whenever a Codex task directly
  changes or runs an .ipynb notebook and these MCP tools are available.
metadata:
  version: "2026-07-19"
---

# Notebook Tools

Drive notebooks through the `notebook_*` MCP tools. Keep reasoning in the agent and use
the deterministic tool surface for notebook structure, validation, concurrency, and
execution.

## Workflow

1. Call `notebook_read` in outline mode before changing an existing notebook.
2. Address cells by returned id. An index is context, not a durable write address.
3. Build one ordered `notebook_edit` batch with the returned revision. Use `dry_run` when
   the batch is broad, structural, or hard to inspect mentally.
4. Commit the same reconciled batch with the current revision, then reread the changed
   cells and confirm the new revision.
5. When outputs are part of the deliverable, call `notebook_execute`. Treat it as arbitrary
   code execution even when `write_back=false`; use write-back only with a fresh revision.

For a new notebook, use `notebook_create` with narrative markdown and small orchestration
cells. Put heavy or reusable logic in `src/`, verify that logic independently, and let the
notebook import it.

## Guardrails

- Never edit raw `.ipynb` JSON while the MCP server is available.
- Never reuse a stale revision after any external or tool-driven notebook change.
- Expect replacement of code source to clear its execution count and outputs.
- A legacy temporary cell handle is safe for the immediately guarded edit; use the
  returned persisted-id mapping afterward.
- Execute from the beginning or through a chosen cell. Do not assume hidden kernel state.
- Keep outputs bounded. Save important plots to files when they need visual inspection.

If a path falls outside configured roots, surface the exact project root that needs adding
instead of weakening the filesystem boundary.
