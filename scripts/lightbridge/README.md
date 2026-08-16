# lightbridge

The canonical resolver for user-level `.lightbridge` project config — the **"local scope"**
model — plus the CLI that creates, inspects, and audits it.

Personal workflow config never lives inside a repo (collaborators would see it, or every repo
would need a gitignore entry). Each project's config sits in the user-level tree, keyed by the
project's root path — the same mechanism Claude Code uses for local-scoped MCP servers:

```
~/.lightbridge/projects/<project-key>/
├── config.toml     ← resolved by this tool
└── handoffs/       ← sibling state (scripts/handoff)
```

## Resolution rule (the one implementation)

```
repo_root   = git rev-parse --show-toplevel of the start dir
              (fallback: the start dir itself, for non-git projects)
project-key = repo_root with path separators → "-"
              (the ~/.claude/projects encoding; Windows drops the drive colon)
config      = <state-dir>/<project-key>/config.toml
```

Readers (`hooks/docs-index-inject`, `scripts/repo-links`, `scripts/handoff`) **import
`lb_resolve.py`** (path-relative `importlib`, like the hooks already load their scripts) —
nothing reimplements root/key/config resolution. That module is the *only* one they load;
see "Module layout" below. `$LIGHTBRIDGE_STATE_DIR` overrides the default
`~/.lightbridge/projects` (used by the tests).

Every config carries a top-level `root = "/abs/path"` key. The key encoding is lossy and a
moved repo silently orphans its config, so `doctor` needs the original path to detect
staleness. Readers ignore `root`.

## PATH shim (optional, recommended)

The CLI always works by absolute path, with no setup:

```bash
uv run <agent-stuff>/scripts/lightbridge/lightbridge.py path
```

For daily use, link it into a directory on your `PATH` — `lightbridge` is the canonical
name, `lb` the short one:

```bash
ln -s "$PWD/scripts/lightbridge/lightbridge.py" ~/.local/bin/lightbridge
ln -s "$PWD/scripts/lightbridge/lightbridge.py" ~/.local/bin/lb
```

The `#!/usr/bin/env -S uv run --script` shebang carries through the symlink, so no wrapper
is needed. Use a **real PATH executable**, not a shell alias: an alias is invisible to an
agent's non-interactive shell, and this CLI has two users.

## CLI

```bash
lightbridge status                  # one-shot dashboard: config, sections, state, registry
lightbridge init                    # create this project's config — never clobbers
lightbridge init docs-index research
lightbridge init --dry-run          # print it instead of writing it
lightbridge add research            # append section(s) to an existing config
lightbridge show                    # print the stored config; `show SECTION` for one block
lightbridge enable research         # flip a section's `enabled` in place (or `disable`)
lightbridge sections                # what can go in a config, and who reads it
lightbridge path                    # this project's config path (+ exists?)
lightbridge path --start DIR        # another project's
lightbridge repos list              # manage ~/.lightbridge/repos.toml
lightbridge repos add NAME PATH     # register a repo — never clobbers a name
lightbridge repos rm NAME
lightbridge graph init              # seed ~/.lightbridge/graph.toml (types vocabulary)
lightbridge graph show [NAME]       # graph summary, or one node's projected ego view
lightbridge graph types             # the edge vocabulary + direction readings
lightbridge graph link A B --type T # declare one edge — the reverse projects automatically
lightbridge graph unlink|set A B    # remove / edit an edge in place
lightbridge graph doctor            # audit the graph; exit 1 on problems
lightbridge graph mermaid           # flowchart to stdout
lightbridge graph html --out FILE   # self-contained interactive viz
lightbridge mv OLD NEW              # move/rename a repo (or parent dir) + repair all bookkeeping
lightbridge doctor                  # audit the whole tree; exit 1 on problems
```

Every verb takes `--json`; the project-scoped verbs (`status` / `init` / `add` / `show` /
`enable` / `disable` / `path`) take `--start DIR`; `status`, `repos`, `graph`, `mv`, and
`doctor` take `--registry FILE`; `status` and every `graph` verb take `--graph FILE`.
Graph design: [`docs/lightbridge/lightbridge-graph.md`](../../docs/lightbridge/lightbridge-graph.md);
agent-facing usage: the `repo-graph` skill.

**Status** is the read path — one bounded dashboard instead of a `path → cat → parse → ls`
chain: root, key, config, each present section with its `enabled` state (unknown tables
flagged), sibling-state counts with the tool that owns each (`handoffs … — handoff.py`,
`plans … — plan_store.py`), and whether the registry exists. Counts only — it never
reaches into the siblings' logic. Exit 0 even when the config is absent (absence is a
state, and the output names `init`); exit 1 only when the config exists but is unreadable.

**Bootstrap.** `init` writes the `root` marker plus the sections you name (positional,
same shape as `add`). With none it **detects**: a repo with a `docs/` dir gets
`[docs-index]` — and the output says so, so nothing is inferred silently. It refuses to
touch an existing config (exit 1); `add` is the way to extend one, and skips sections
already present rather than duplicating them. Both are safe to re-run.

**Show / enable / disable** never rewrite the file: `show` prints it verbatim (`--json`
parses it; no defaults injected — those live with each reader, per the catalog), and
`enable`/`disable` are targeted line edits of the one `enabled` key, so comments and
layout survive. Toggling is idempotent (`unchanged`, exit 0); a missing section teaches
`add` instead.

**Repos** owns the personal registry `~/.lightbridge/repos.toml` (per machine, never
committed): `add` creates the file on first use and refuses to overwrite an existing name
(exit 1 — `rm` first); a path that doesn't exist yet registers with a note (pre-clone is
legitimate); `list` marks dead paths instead of hiding them.

**Mv** repairs what a repo move/rename breaks (everything here is keyed by path): re-keys
`projects/<key>/` with its state, rewrites the `root` marker, and fixes matching
`repos.toml` paths — prefix-matched, so a parent-dir move re-keys every project beneath.
OLD still on disk → it performs the move too; already moved → bookkeeping only. Confirms
on a TTY; non-interactive runs need `--yes` (agents: only under explicit human
instruction); `--dry-run` previews the blast radius; a completed move re-runs as a clean
no-op. Full contract: `docs/lightbridge/lightbridge-mv.md`.

**Sections.** The emittable templates live in `SECTIONS` (in `lb_catalog.py`); what each
key *means* is the `lightbridge-config` skill's `references/catalog.md`, the canonical spec.
A test asserts the two describe the same set of sections, so neither can grow alone.

**Doctor** flags, per config: `unreadable` (bad TOML), `missing-root` (no `root` key),
`stale` (`root` no longer exists on disk), `key-mismatch` (folder name ≠ key of `root`);
plus `legacy` — a pre-migration `<repo>/.lightbridge/config.toml` found under any path in
`~/.lightbridge/repos.toml` (no longer read by anything; migrate and delete).

Exit codes: `0` ok, including an idempotent no-op · `1` refused (`doctor` found problems,
`init`/`repos add` would clobber, the config/section/name a verb needs is absent or
unreadable) · `2` usage.

## Module layout

Since v0.5 this tool is flat sibling modules rather than one file (nine since v0.6,
when `lb_graph.py` joined). The boundary is
**the library is the read path; the CLI owns the write path** — decision and rationale in
[`docs/lightbridge/adr/0001-modular-lightbridge.md`](../../docs/lightbridge/adr/0001-modular-lightbridge.md).

| file | holds |
|---|---|
| `lb_resolve.py` | **the read path** — resolution, graph reader + projection, `toml_str`, `use_utf8_console` |
| `lb_tomledit.py` | surgical TOML line edits (comments and layout survive) |
| `lb_catalog.py` | `SECTIONS`, `SectionName`, config-document assembly |
| `lb_registry.py` | `~/.lightbridge/repos.toml` |
| `lb_graph.py` | `~/.lightbridge/graph.toml` — document model, edge surgery, audit, viz |
| `lb_doctor.py` | the tree audit |
| `lb_mv.py` | `plan_mv` + `apply_mv` |
| `lb_commands.py` | the `cmd_*` verb handlers |
| `lightbridge.py` | Typer wiring + `main()` — **the entrypoint, not importable** |

Two rules, both enforced by `tests/test_lightbridge.py::ResolveModuleContractTest`:

1. **`lb_resolve.py` is the only module a reader path-loads**, so it imports stdlib only and
   no siblings — hooks `exec_module` it inside `dependencies = []` PEP 723 envs where
   neither would resolve.
2. **`lightbridge.py` is never imported.** It pulls in typer and its siblings at module
   scope; path-loading it from a hook would crash.

Sibling imports work because `uv run --script` puts the *symlink-resolved* script directory
on `sys.path[0]` — so they hold through the `~/.local/bin/lb` shim too. The `lb_` filename
prefix is deliberate: these names become real `sys.modules` keys in a repo where several
tools path-load modules under generic names.
