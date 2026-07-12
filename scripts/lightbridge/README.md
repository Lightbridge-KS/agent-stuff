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

Readers (`hooks/docs-index-inject`, `scripts/repo-links`, `scripts/handoff`) **import this
module** (path-relative `importlib`, like the hooks already load their scripts) — nothing
reimplements root/key/config resolution. `$LIGHTBRIDGE_STATE_DIR` overrides the default
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
lightbridge init                    # create this project's config — never clobbers
lightbridge init --sections docs-index,research
lightbridge init --dry-run          # print it instead of writing it
lightbridge add repo-links          # append section(s) to an existing config
lightbridge sections                # what can go in a config, and who reads it
lightbridge path                    # this project's config path (+ exists?)
lightbridge path --start DIR        # another project's
lightbridge doctor                  # audit the whole tree; exit 1 on problems
```

Every verb takes `--json`; `init` / `add` / `path` take `--start DIR`.

**Bootstrap.** `init` writes the `root` marker plus the sections you name. With no
`--sections` it **detects**: a repo with a `docs/` dir gets `[docs-index]` — and the output
says so, so nothing is inferred silently. It refuses to touch an existing config (exit 1);
`add` is the way to extend one, and skips sections already present rather than duplicating
them. Both are safe to re-run.

**Sections.** The emittable templates live in `SECTIONS` (in `lightbridge.py`); what each
key *means* is the `lightbridge-config` skill's `references/catalog.md`, the canonical spec.
A test asserts the two describe the same set of sections, so neither can grow alone.

**Doctor** flags, per config: `unreadable` (bad TOML), `missing-root` (no `root` key),
`stale` (`root` no longer exists on disk), `key-mismatch` (folder name ≠ key of `root`);
plus `legacy` — a pre-migration `<repo>/.lightbridge/config.toml` found under any path in
`~/.lightbridge/repos.toml` (no longer read by anything; migrate and delete).

Exit codes: `0` ok, including an idempotent no-op · `1` refused (`doctor` found problems,
`init` would clobber, `add` found no config) · `2` usage.
