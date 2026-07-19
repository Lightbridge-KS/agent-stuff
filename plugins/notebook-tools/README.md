# Notebook Tools

Cell-aware Jupyter notebook operations for Codex and Claude, packaged as a skill plus a
local STDIO MCP server. The server reads, creates, edits, and clean-kernel executes
notebooks without making an agent manipulate raw `.ipynb` JSON.

## Requirements

- Python 3.11 or newer, resolved by `uv`.
- An installed Jupyter kernel for `notebook_execute` (normally `python3`).
- A filesystem root supplied by the MCP client, direct registration, or explicit fallback
  configuration.

The PEP 723 entrypoints install their Python dependencies. No project environment or
global Python package install is required.

## Install from the Codex marketplace

Register this repository marketplace once, then install the plugin:

```bash
codex plugin marketplace add <agent-stuff-root>
codex plugin add notebook-tools@lightbridge-tools
```

Restart Codex or start a new task after installation. The plugin launches
`mcp/notebook_mcp.py --use-client-roots`; usable `file://` client roots are authoritative
for each request.

When a client does not expose roots, configure an explicit fail-closed fallback:

```bash
uv run --script <agent-stuff-root>/plugins/notebook-tools/mcp/notebook_roots.py path
uv run --script <agent-stuff-root>/plugins/notebook-tools/mcp/notebook_roots.py add /absolute/project/root
uv run --script <agent-stuff-root>/plugins/notebook-tools/mcp/notebook_roots.py list
uv run --script <agent-stuff-root>/plugins/notebook-tools/mcp/notebook_roots.py remove /absolute/project/root
```

The config uses the platform-native `notebook-tools/config.toml` location. With neither a
usable client root nor configured fallback, every tool fails with
`ROOT_CONFIGURATION_REQUIRED`; the server never defaults to the home directory or `/`.

## Direct MCP registration

Direct registration remains supported and makes repeated static roots authoritative:

```bash
codex mcp add notebook-tools -- \
  uv run --script \
  <agent-stuff-root>/plugins/notebook-tools/mcp/notebook_mcp.py \
  --root /absolute/project/root
```

Keep the generated server block write-aware:

```toml
[mcp_servers.notebook-tools]
command = "uv"
args = [
  "run", "--script",
  "<agent-stuff-root>/plugins/notebook-tools/mcp/notebook_mcp.py",
  "--root", "/absolute/project/root",
]
default_tools_approval_mode = "writes"
```

If a desktop-launched process cannot resolve `uv`, replace the command with the absolute
path reported by `command -v uv`.

## Tool workflow

| Tool | Purpose | Safety annotation |
|---|---|---|
| `notebook_read` | Outline, read, or search cells and obtain a revision | read-only |
| `notebook_create` | Create a new nbformat 4.5 notebook | additive write |
| `notebook_edit` | Guarded atomic batch edit, including dry runs | destructive write |
| `notebook_execute` | Execute from the beginning in a fresh kernel | open-world write |

Use read → edit with `expected_revision` → read again. A stale revision fails safely.
Source edits to code cells clear their old outputs and execution count. Every successful
structured result reports whether its access roots came from `static`, `client`, or
`config` resolution.

## Development

```bash
uv run tests/test_notebook_tools.py
uv run tests/test_codex_plugin.py
uv run bin/validate.py
just test
```

The focused tests use only synthetic notebooks in temporary directories.

## Troubleshooting

- `ROOT_CONFIGURATION_REQUIRED`: open a project root in the MCP client or use the roots
  CLI to add an explicit fallback.
- `OUTSIDE_ALLOWED_ROOT`: open or configure the exact project root; do not widen access
  to `/`.
- `STALE_REVISION`: reread, reconcile the current cells, and retry with the new revision.
- `KERNEL_NOT_FOUND`: install or select a Jupyter kernel and pass its kernelspec name.
- `EXECUTION_TIMEOUT`: raise the per-cell timeout or make the cell bounded.
- Tools missing after configuration: inspect `codex plugin list` or `codex mcp list`,
  verify `uv` resolves, and restart Codex.

Settled behavior lives in
[`../../docs/notebook-tools/design/notebook-tools.md`](../../docs/notebook-tools/design/notebook-tools.md),
with packaging details in
[`../../docs/notebook-tools/design/plugin-packaging.md`](../../docs/notebook-tools/design/plugin-packaging.md).
