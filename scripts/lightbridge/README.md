# lightbridge

The canonical resolver for user-level `.lightbridge` project config — the **"local scope"**
model — plus a small `path` / `doctor` CLI.

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

## CLI

```bash
lightbridge.py path                 # this project's config path (+ exists?)
lightbridge.py path --start DIR     # another project's
lightbridge.py path --json
lightbridge.py doctor               # audit the whole tree; exit 1 on problems
lightbridge.py doctor --json
```

`doctor` flags, per config: `unreadable` (bad TOML), `missing-root` (no `root` key),
`stale` (`root` no longer exists on disk), `key-mismatch` (folder name ≠ key of `root`);
plus `legacy` — a pre-migration `<repo>/.lightbridge/config.toml` found under any path in
`~/.lightbridge/repos.toml` (no longer read by anything; migrate and delete).

Config **schema** (sections, keys, opt-in semantics) is not this tool's concern — see the
`lightbridge-config` skill (`plugins/lightbridge/skills/lightbridge-config/`), the canonical
spec.

Exit codes: `0` ok · `1` `doctor` found problems · `2` usage.
