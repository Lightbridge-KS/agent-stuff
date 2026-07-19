# notebook-tools

Cell-aware Jupyter notebook operations for Codex, exposed as a local STDIO MCP server.
The server reads, creates, edits, and clean-kernel executes notebooks without asking an
agent to manipulate raw `.ipynb` JSON.

## Requirements

- Python 3.11 or newer, resolved by `uv`.
- One or more existing absolute allowed roots.
- An installed Jupyter kernel for `notebook_execute` (normally `python3`).

The PEP 723 entrypoint installs its own Python dependencies. No project environment or
global Python package install is required.

## Run

```bash
uv run --script scripts/notebook-tools/notebook_mcp.py \
  --root /absolute/project/root
```

Repeat `--root` to allow additional projects. The server refuses relative paths, non-
notebook paths, and paths that resolve through symlinks outside these roots.

| Tool | Purpose | Safety annotation |
|---|---|---|
| `notebook_read` | Outline, read, or search cells and obtain a revision | read-only |
| `notebook_create` | Create a new nbformat 4.5 notebook | additive write |
| `notebook_edit` | Guarded atomic batch edit, including dry runs | destructive write |
| `notebook_execute` | Execute from the beginning in a fresh kernel | open-world write |

The normal workflow is read → edit with `expected_revision` → read again. A stale
revision fails safely. Source edits to code cells clear their old outputs and execution
count.

## Register with Codex

Use the absolute `uv` and script paths because a desktop-launched process may have a
smaller `PATH` than an interactive shell:

```bash
codex mcp add notebook-tools -- \
  /Users/kittipos/.local/bin/uv run --script \
  /Users/kittipos/my_config/agent-stuff/scripts/notebook-tools/notebook_mcp.py \
  --root /Users/kittipos/my_config
```

Then keep the generated server block in `~/.codex/config.toml` write-aware:

```toml
[mcp_servers.notebook-tools]
command = "/Users/kittipos/.local/bin/uv"
args = [
  "run", "--script",
  "/Users/kittipos/my_config/agent-stuff/scripts/notebook-tools/notebook_mcp.py",
  "--root", "/Users/kittipos/my_config",
]
default_tools_approval_mode = "writes"
```

Restart Codex after changing MCP configuration, then confirm `notebook_read`,
`notebook_create`, `notebook_edit`, and `notebook_execute` appear. Read calls should not
ask for approval; create/edit/execute calls remain write-aware. To add a project, append
another `"--root", "/absolute/project"` pair and restart Codex.

## Development

```bash
uv run tests/test_notebook_tools.py
uv run bin/validate.py
just test
```

The focused tests use only synthetic notebooks in temporary directories.

## Troubleshooting

- `OUTSIDE_ALLOWED_ROOT`: register the notebook's project root explicitly; do not widen
  the root to `/`.
- `STALE_REVISION`: reread, reconcile the current cells, and retry with the new revision.
- `KERNEL_NOT_FOUND`: install or select a Jupyter kernel and pass its kernelspec name.
- `EXECUTION_TIMEOUT`: raise the per-cell timeout or make the cell bounded.
- Tools missing after configuration: run `codex mcp list`, check the absolute command and
  script paths, and restart Codex.

Settled behavior lives in
[`../../docs/notebook-tools/design/notebook-tools.md`](../../docs/notebook-tools/design/notebook-tools.md).
