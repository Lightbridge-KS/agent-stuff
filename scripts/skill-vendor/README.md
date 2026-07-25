# skill-vendor

Keep **Vendored** agent skills in sync with their installed binaries, across harness
skill registries (`~/.claude/skills/`, `~/.codex/skills/`). The taxonomy this tool
mechanizes lives in the user-level AGENTS.md (*Terminology → Skill vendors*); the
settled design is [`docs/skill-vendor/design.md`](../../docs/skill-vendor/design.md).

The invariant: **the skill bytes served to registries are the ones known-good for the
installed binary.** The manifest's key shape selects where "known-good" comes from:

| Mode | Manifest shape | Pin |
|---|---|---|
| co-shipped | `source = "install-tree"` + `skill-path` | symlink into the install unit — correct by construction |
| first-party detached | `source = "repo"` + `tag = "v{version}"` | worktree at the tag rendered from `<binary> --version` |
| third-party detached | `source = "repo"` + `ref` | worktree at the pinned ref + user attestation (`verified-against` / `verified-on`) |

## Manifest

`~/.lightbridge/skill-vendors.toml` — hand-edited, machine-specific, never committed
(`attest` is the only machine writer). Worktrees live under
`~/.lightbridge/skill-vendors/worktrees/<name>`.

```toml
[defaults]
registries = ["~/.claude/skills", "~/.codex/skills"]

[crabbox]                        # entry key = skill dir name in registries
binary      = "crabbox"
source      = "repo"
repo        = "~/OSS/OpenClaw-Ecosystem/crabbox"
tag         = "v{version}"
skill-paths = ["skills/crabbox", ".agents/skills/crabbox"]   # probed in order

[gog]
binary     = "gog"
source     = "install-tree"
skill-path = "/opt/homebrew/lib/node_modules/openclaw/skills/gog"
```

Optional per entry: `registries` (overrides defaults), `version-cmd` (default
`<binary> --version`; first `x.y.z` in its output wins).

## Usage

```bash
skill-vendor list                # inventory: name, mode, versions, status (always exit 0)
skill-vendor doctor              # read-only report; includes the registry-invariant scan
skill-vendor sync                # converge: fetch tags, move worktrees, relink registries
skill-vendor sync crabbox        # one entry
skill-vendor attest sometool     # third-party only: stamp verified-against/-on
skill-vendor doctor --json       # machine-readable, same exit codes
```

Run after every binary upgrade (`brew upgrade crabbox` → `skill-vendor sync crabbox`);
`doctor` catches the forgotten case.

## Exit codes

- **0 clean** — every entry serves its known-good bytes.
- **1 skew** — drift with a named fix: first-party behind the binary (*run sync*),
  third-party attestation stale (*re-verify, then attest*), or registry-invariant
  violations (real directories / dangling symlinks in a registry — policy drift
  awaiting the Adopted-shelf drain, not engine breakage).
- **2 broken** — an engine-managed piece is wrong or unusable: binary not on PATH,
  tag/ref unresolvable, no SKILL.md at the pin, registry link missing or pointing
  elsewhere, unreadable manifest, usage errors.

**Failure honesty:** an unresolvable pin (e.g. the tag for a freshly upgraded binary
isn't published yet) reports broken and leaves existing symlinks untouched — never a
silent fallback to a repo's `main`.

## PATH shim (optional, recommended)

```bash
ln -s "$PWD/scripts/skill-vendor/skill_vendor.py" ~/.local/bin/skill-vendor
```

The `#!/usr/bin/env -S uv run --script` shebang carries through the symlink. Use a real
PATH executable, not a shell alias — an alias is invisible to an agent's non-interactive
shell. Zero-setup alternative: `uv run <agent-stuff>/scripts/skill-vendor/skill_vendor.py …`.

## Testing

```bash
uv run tests/test_skill_vendor.py
```

Env override for isolation: `SKILL_VENDOR_HOME` replaces `~/.lightbridge` (or pass
`--home DIR`).
