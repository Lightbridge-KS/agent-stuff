---
summary: Settled design for the skill-vendor engine — a manifest-driven tool
  (~/.lightbridge/skill-vendors.toml + scripts/skill-vendor) that keeps Vendored
  agent skills in sync with their installed binaries across harness registries.
  One invariant, three knowledge sources (co-shipped / first-party tag / third-party
  attestation), sync + doctor + attest + list.
read_when:
  - implementing or changing scripts/skill-vendor
  - adding a vendored skill entry or a new pin mode
  - changing the skill-vendors.toml schema or doctor semantics
  - wiring registry-invariant checks or lb doctor integration
---

# Skill-Vendor Engine — Design

> Status: approved 2026-07-25 (KS) · Manifest: `~/.lightbridge/skill-vendors.toml` ·
> CLI: `scripts/skill-vendor` (Python 3.11+, `uv run --script`, lightbridge style)

## Goal

Keep every **Vendored** skill (taxonomy: *AGENTS.qmd → Terminology → Skill vendors*)
serving the exact bytes known-good for the **installed binary version**, in every
harness registry (`~/.claude/skills/`, `~/.codex/skills/`), with a doctor that
reports skew honestly. The engine is also the operational drain destination for
Adopted skills being re-wired to their upstream ("re-wire to upstream as Vendored"
= write a manifest entry here).

Out of scope: Authored skills (agent-stuff symlinks, owned by the castle gate),
Harness-provided skills, and anything still sitting on the Adopted shelf.

## The invariant, and its three knowledge sources

The invariant is always the same:

> The skill bytes served to registries are the ones known-good for the installed binary.

What varies per entry is **where the knowledge of "known-good" comes from**:

| Mode | Knowledge source | Pin resolution |
|---|---|---|
| **co-shipped** | vendor guarantees *structurally* — skill and binary in one install unit | symlink into the install tree; correct by construction |
| **first-party detached** | vendor guarantees *by co-versioning* — skill in the binary's repo, tags track releases | worktree at tag `v{installed-version}`; correct by lookup |
| **third-party detached** | **the user attests** — skill repo has its own history; no version mapping exists | worktree at pinned `ref` + recorded `verified-against`; correct by testimony |

The third mode is the load-bearing idea. Many pre-agentic CLIs ship skill-less and
skills get authored afterward; no script can derive a binary→skill-version mapping
upstream never promised. So the pin is an **attestation**: *"skill at ref `a1b2c3d`
was verified by me against binary 2.4.0 on 2026-07-25."* Literal facts, checkable,
and honest about going stale.

The doctor's question is thereby **identical across modes** — *does the installed
binary version match the version the skill is bound to?* — only the fix differs:

- first-party skew → mechanical: `skill-vendor sync <name>`
- third-party skew → human: re-verify the skill against the new binary, then
  `skill-vendor attest <name>`

## Manifest: `~/.lightbridge/skill-vendors.toml`

User-level, **machine-specific** (installed binaries differ per device), never
committed — the `repos.toml` precedent. **Hand-edited in v1** (settled: entries are
~6 plain lines; the `lb init` "never hand-write" doctrine exists for computed keys,
which this file has none of). `attest` is the only machine writer.

Entry key = skill directory name in registries. Mode is selected by **key shape**,
not a `mode =` enum — no redundant field to drift:

- `source = "install-tree"` → co-shipped
- `source = "repo"` + `tag` → first-party detached (`tag` is a template over the
  installed version)
- `source = "repo"` + `ref` (+ `verified-against`, `verified-on`) → third-party
  detached; `tag` and `ref` are mutually exclusive

```toml
[defaults]
registries = ["~/.claude/skills", "~/.codex/skills"]

# ── co-shipped ──────────────────────────────────────────────────
[gog]
binary     = "gog"
source     = "install-tree"
skill-path = "/opt/homebrew/lib/node_modules/openclaw/skills/gog"

# ── first-party detached ────────────────────────────────────────
[crabbox]
binary      = "crabbox"
source      = "repo"
repo        = "~/OSS/OpenClaw-Ecosystem/crabbox"
tag         = "v{version}"
skill-paths = ["skills/crabbox", ".agents/skills/crabbox"]  # probe in order; path moved at 0.40

# ── third-party detached ────────────────────────────────────────
[sometool]
binary           = "sometool"
source           = "repo"
repo             = "~/OSS/sometool-community-skills"
ref              = "a1b2c3d"
verified-against = "2.4.0"       # written by `skill-vendor attest`
verified-on      = 2026-07-25    # written by `skill-vendor attest`
skill-paths      = ["skills/sometool"]
```

Per-entry `registries` overrides `[defaults]`. `version-cmd` defaults to
`<binary> --version`, parsed as first semver in output; overridable for awkward CLIs.

**Co-shipped entries are included deliberately** (settled): sync is a near-no-op,
but doctor then covers the whole Vendored category (e.g. a dangling gog symlink
after an npm prefix change), and the manifest is the complete vendored inventory.

## Engine-owned state

```text
~/.lightbridge/
├── skill-vendors.toml
└── skill-vendors/
    └── worktrees/
        ├── crabbox/      ← git worktree of the entry's repo, detached at v0.40.0
        └── sometool/     ← worktree of the skill repo, detached at a1b2c3d

~/.claude/skills/crabbox → ~/.lightbridge/skill-vendors/worktrees/crabbox/skills/crabbox
~/.codex/skills/crabbox  → (same target)
```

Worktrees live under `~/.lightbridge/` (durable harness-neutral state), not beside
the clones — `main` clones stay free for exploration; one predictable place holds
every pin. Co-shipped entries have no worktree; registry symlinks point straight
into the install tree.

## CLI surface

Standalone `scripts/skill-vendor`, linked onto PATH like `lightbridge`. **Not** an
`lb` subcommand — `lb` resolves per-project config; this is a machine-state engine
doing git operations. They share only the `~/.lightbridge/` tree; `lb doctor` may
later shell out to `skill-vendor doctor` (the stable exit code is the seam).

| Command | Does | Exit |
|---|---|---|
| `sync [name…]` | converge: fetch tags, move worktrees, relink registries | 0 ok / 2 broken |
| `doctor [name…]` | read-only skew + integrity report, incl. registry-wide scan | 0 clean / 1 skew / 2 broken |
| `attest <name>` | stamp `verified-against` = installed version + `verified-on` = today (third-party only) | 0 / 2 |
| `list` | inventory: name, mode, binary version, pinned version, status | 0 |

### Doctor semantics

Per entry:

- binary not on PATH → **broken**
- pin unresolvable (tag missing upstream / ref not checked out / install path gone) → **broken**
- registry symlink missing, not a symlink, or pointing elsewhere → **broken**
- first-party: worktree tag ≠ `tag` template rendered with installed version → **skew** ("run sync")
- third-party: `verified-against` ≠ installed version → **skew** ("re-verify, then attest")
- co-shipped: no version check — correct by construction when the symlink resolves

Registry-wide scan (the *registry invariant* from AGENTS.qmd): every entry of each
registry in `[defaults]` must be a symlink; real directories and dangling symlinks
are violations (**skew, exit 1** — amended 2026-07-25: they are policy drift
awaiting the Adopted-shelf drain, not engine breakage; "broken" stays reserved for
wrong engine-managed entries). Symlinks to homes the engine doesn't manage
(agent-stuff, `~/.agents/skills/`) pass without comment — Authored and Adopted are
not its business. The scan runs only when doctor covers all entries (no names given).

### Failure honesty

No matching tag, or no skill dir at the pinned ref → say so, leave existing
symlinks untouched, exit nonzero. **Never silently fall back to `main`.**

## Implementation notes

- Python 3.11+ single-file script under `uv run --script`, mirroring `lightbridge`
  conventions; `tomllib` for reads. **Typer** CLI (settled 2026-07-25, overriding
  the argparse precedent of the smaller script tools), imported CLI-only inside
  `main()` so the `cmd_*` handlers stay stdlib-pure for in-process tests.
- Reuse: path-loads `lb_resolve.py` only (`toml_str`, `use_utf8_console`) — the one
  lightbridge module siblings may load per its ADR. The attest line-surgery is a
  local ~30-line reimplementation of the `lb_tomledit` approach, not a load of it.
- `attest` writes by targeted line-surgery on the two keys (tomlkit-free), same
  spirit as `lb_tomledit`; untargeted lines come out byte-identical.
- Isolation override: `SKILL_VENDOR_HOME` env (or `--home DIR`) replaces
  `~/.lightbridge` — `LIGHTBRIDGE_STATE_DIR` was not reused because it points at the
  `projects/` subtree, not the lightbridge home.
- Sync order per entry: resolve installed version → resolve pin → create/move
  worktree (`git fetch --tags` first for first-party) → probe `skill-paths` →
  `ln -sfn` each registry.

## Deferred (explicitly not v1)

- **snapshot/url mode** — skills with no repo at all, fetched from a site or
  `/.well-known/agent-skills/` (sha256 digest + `verified-against`). Same
  invariant, fourth knowledge source; schema has room.
- **`add` scaffolder** — revisit if hand-editing proves error-prone.
- **SessionStart doctor hook** — quiet unless skew; only if manual-after-upgrade
  proves forgettable.
- **`lb doctor` integration** — compose via exit codes.
