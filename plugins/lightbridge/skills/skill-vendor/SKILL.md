---
name: skill-vendor
description: >-
  Keep vendored agent skills in sync with their installed binaries via the skill-vendor
  CLI. Use after upgrading a skill-shipping CLI (brew/npm), when a registry skill drifts
  from its binary, or when asked to add, pin, attest, or audit a vendored skill.
metadata:
  version: "2026-08-15"
---

# skill-vendor

`skill-vendor` keeps **Vendored** skills (third-party skills that ship with or track an
installed binary — see the `skill-taxonomy` skill for the full vendor taxonomy) serving the
exact bytes known-good for that binary, symlinked into the harness registries
(`~/.claude/skills/`, `~/.codex/skills/`).

The invariant: **served skill bytes match the installed binary version.** The manifest's
key shape selects where "known-good" comes from:

| Mode | Manifest shape | Pin |
|---|---|---|
| co-shipped | `source = "install-tree"` + `skill-path` | symlink into the install unit |
| first-party detached | `source = "repo"` + `tag = "v{version}"` | worktree at the tag matching `<binary> --version` |
| third-party detached | `source = "repo"` + `ref` | pinned ref + user attestation (`verified-against`/`-on`) |

## When to act

- **A skill-shipping binary was upgraded** (e.g. `brew upgrade crabbox`) →
  `skill-vendor sync <name>`.
- **A new vendored skill should be served** → add an entry to
  `~/.lightbridge/skill-vendors.toml` by hand (running any verb without a manifest
  prints a copyable sample), then `sync`.
- **Health check / "is anything stale?"** → `skill-vendor doctor` (read-only; also
  scans registries for the symlink-only invariant).
- **A third-party skill was re-verified against a new binary version** →
  `skill-vendor attest <name>` (the only machine writer of the manifest).

Trust the CLI to teach the rest: `skill-vendor --help`, and every error names the
next move.

## Contract

- Exit codes: **0** clean · **1** skew (drift with a named fix — run `sync`, or
  re-verify + `attest`; also registry-invariant violations) · **2** broken (missing
  binary/tag/skill, bad links, unreadable manifest). Stable — safe to branch on.
- Failure-honest: an unresolvable pin (unpublished tag, no SKILL.md) leaves existing
  symlinks untouched; never a silent fallback to a repo's `main`.
- Worktrees live under `~/.lightbridge/skill-vendors/worktrees/<name>` — never edit
  them; they are detached checkouts owned by the engine.
- Authored skills (this repo's `plugins/`) are **not** the engine's business: they are
  co-shipped by co-location and served by plain symlinks.

Deep docs: `scripts/skill-vendor/README.md` (usage) and `docs/skill-vendor/design.md`
(the settled design) in the agent-stuff repo.
