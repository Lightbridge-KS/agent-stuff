---
summary: Settled phase-3 design for packaging notebook-tools as a canonical Codex and Claude plugin with portable, fail-closed root discovery.
read_when:
  - implementing or changing native notebook-tools plugin packaging
  - changing plugin manifests, marketplace entries, root discovery, or installation
  - migrating between direct MCP registration and installed plugin use
---

# Notebook Tools — Native Plugin Packaging

> Status: approved 2026-07-19 · Target: 0.3.0 · Marketplace: repo-local

## Goal

Make one installable `notebook-tools` plugin the canonical owner of the workflow skill and
STDIO MCP server. Installing the plugin should expose both capabilities without maintained
copies, hard-coded user paths, or a weaker filesystem boundary.

```text
agent-stuff marketplace
  -> plugins/notebook-tools
     -> notebook-tools skill
     -> notebook-tools STDIO MCP
        -> static roots (direct mode)
        -> MCP client roots (plugin mode)
        -> explicit user roots config (fallback)
```

Codex and Claude manifests live beside the same skill and server. The existing coding
plugin no longer owns a notebook-tools copy.

## Canonical bundle

```text
plugins/notebook-tools/
├── .codex-plugin/plugin.json
├── .claude-plugin/plugin.json
├── .mcp.json
├── README.md
├── skills/notebook-tools/SKILL.md
└── mcp/
    ├── notebook_mcp.py
    ├── notebook_roots.py
    └── notebook_tools/*.py
```

The Codex manifest owns version `0.3.0`; the MCP entrypoint reads it for `--version`.
The bundle declares `skills` and `mcpServers`, but no apps, hooks, or visual assets. The
repo-local Codex marketplace is `.agents/plugins/marketplace.json`, named
`lightbridge-tools`, with `AVAILABLE` installation and `ON_INSTALL` authentication policy.
The existing Claude marketplace gains a standalone notebook-tools entry.

`.mcp.json` launches `uv run --script ./mcp/notebook_mcp.py --use-client-roots` with the
plugin root as `cwd`. It contains no absolute user or repository paths. `uv` is an explicit
runtime prerequisite.

## Root resolution

Two startup modes are mutually exclusive:

1. Repeated `--root ABSOLUTE_PATH` retains direct-registration behavior. Static roots are
   authoritative; client and user-config roots are not added.
2. `--use-client-roots` is plugin mode. Each tool request asks the MCP client for roots.

Plugin-mode precedence is:

```text
valid MCP file roots -> user roots config -> ROOT_CONFIGURATION_REQUIRED
```

Client roots must use `file://`, resolve to existing directories, and survive symlink
resolution. Valid client roots replace rather than union with broader configured roots.
Refreshing roots for each call follows workspace changes without stateful subscriptions.

The fallback file uses the platform-native user config directory and this schema:

```toml
schema_version = 1
roots = ["/absolute/project/root"]
```

`notebook_roots.py path|list|add|remove` owns the file. It accepts only existing absolute
directories, stores resolved unique paths, performs idempotent changes, and atomically
replaces the config. Missing or malformed configuration fails closed. Home and `/` are
never implicit defaults.

Services are cached by canonical root tuple so each root set retains in-process path
locks. Every successful tool result adds bounded access provenance:

```json
{"access": {"root_source": "static", "root_count": 1}}
```

Allowed values are `static`, `client`, and `config`. No new notebook workflow tool is
introduced. `ROOT_CONFIGURATION_REQUIRED` is the only new stable public error code.

## Migration and rollout

The server, README, and skill move into the bundle; old source locations are removed.
Tests and direct-registration instructions follow the canonical path. Plugin installation
uses the repo marketplace, then a new Codex task proves discovery, roots, approval policy,
and the full synthetic notebook workflow.

Direct `mcp_servers.notebook-tools` registration remains active during the plugin trial.
It is removed only after the installed plugin passes create, read, guarded edit, execution,
write-back, outside-root denial, and approval checks. Failure keeps the direct server and
records a blocker; it never broadens roots or downgrades write approval.

## Validation

Repository validation covers both marketplace formats, strict semver, plugin-to-companion
paths, relative path closure, required Codex policy fields, version consistency, and the
absence of hard-coded user roots. The plugin-creator validator provides the local Codex
ingestion preflight. CI runs root-resolution, config CLI, MCP contract, and existing
notebook behavior tests on Python 3.11.

## Non-goals

- Public Plugin Directory submission or workspace-admin publication.
- Apps, OAuth, hooks, icons, screenshots, or custom UI.
- Bundling `uv`, Python, or Jupyter kernels.
- Default access to the user's home directory or filesystem root.
- Changes to cell mutation or clean-kernel execution semantics.

## Acceptance

- One canonical bundle validates for Codex and Claude and installs from the repo catalog.
- An installed Codex plugin discovers the skill and all four MCP tools using relative paths.
- Static, client, and configured roots all enforce the same symlink-safe path policy.
- Reads remain prompt-free; create, edit, dry-run, and execute remain write-aware.
- The installed plugin passes live synthetic notebook acceptance before direct registration
  is removed.
