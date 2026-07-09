# agent-stuff (Lightbridge-KS)

A **public, personal** collection of reusable building blocks for coding agents (Claude
Code, Codex, Pi, …): **skills**, **subagents**, standalone **scripts**, and **hooks**.
This repo is the **single source of truth** — written once here, shared everywhere via a
Claude Code plugin marketplace or a small `uv` installer.

> This file is the canonical editing guide. `CLAUDE.md` is a symlink to it.

## The one rule

The filesystem is the index — there is no separate registry to keep in sync:

- a folder under `plugins/<domain>/skills/` is a **skill** if it contains `SKILL.md`;
- a file under `plugins/<domain>/agents/` ending in `.md` is a **subagent**;
- a folder under `scripts/` is a **tool** (carries a `README.md`);
- a folder under `hooks/` is a **hook** (carries a `README.md` + `hook.toml`).

## Layout

```
plugins/<domain>/skills/<name>/SKILL.md   # SKILLS — canonical, one folder per skill
plugins/<domain>/agents/<name>.md         # SUBAGENTS — one file per agent (Claude-only)
plugins/<domain>/.claude-plugin/plugin.json
.claude-plugin/marketplace.json           # lists every domain plugin
scripts/<tool>/                           # standalone agent CLIs (Python + uv)
hooks/<hook>/                             # Claude Code event hooks
bin/                                      # MACHINERY (not content): installer, validator,
  install.py  targets.toml                #   and the agent-target registry
  validate.py
tests/                                    # test suite (test_install.py, test_hooks.py)
docs/architecture.md                      # how and why this repo is structured
.github/workflows/validate.yml            # CI gate on every PR and push to main
```

Content (`plugins/`, `scripts/`, `hooks/`) is what an agent consumes; `bin/` is the
machinery that ships and checks it. See `docs/architecture.md` for the rationale.

## Domain = plugin (skills)

Each domain folder under `plugins/` is **one Claude Code plugin**, listed in
`.claude-plugin/marketplace.json`. This lets the same tree serve three consumers:

- **Plugin marketplace** — Claude Code discovers a plugin's skills at
  `plugins/<domain>/skills/<name>/SKILL.md`.
- **`uv` installer** — `bin/install.py` globs `plugins/*/skills/*/SKILL.md`.
- **Raw browsing** — the tree reads as a clean by-domain catalog on GitHub.

To **add a domain**: create `plugins/<domain>/.claude-plugin/plugin.json` and a matching
entry in `marketplace.json`. To **add a skill**: create
`plugins/<domain>/skills/<name>/SKILL.md`.

## SKILL.md contract

```yaml
---
name: <kebab-case-name>          # MUST equal the folder name
description: <short trigger phrase: when should the agent load this skill>
metadata:
  version: "YYYY-MM-DD"          # recommended; validator warns if absent
---

# <Skill Title>

<Operational, terse body. Steps the agent runs. Prefer calling helper scripts
under scripts/ for repeatable logic.>
```

- `name` and `description` are **required and non-empty**. Claude Code itself only requires
  `description`; we also enforce `name == folder` so the marketplace and the installer
  agree on identity.
- `description` is a **router trigger** — short and specific, not full documentation.
- Skill bodies stay operational and terse, not essay-like.

## Subagent contract (`plugins/<domain>/agents/<name>.md`)

A Claude Code custom-agent definition — YAML frontmatter over a Markdown body that
becomes the agent's system prompt. **One file per subagent, Claude-only** (Codex agents
are TOML with different fields; targets opt in via an `agents` key in `bin/targets.toml`).

```yaml
---
name: <kebab-case-name>          # MUST equal the filename stem
description: <delegation trigger; if opt-in-only, say so HERE — this is the router>
model: opus                      # optional: opus|sonnet|haiku|fable|inherit|claude-*
metadata:
  version: "YYYY-MM-DD"          # recommended; validator warns if absent
---

<Body = system prompt. Write it as a contract (input expectations, execution
rules, output format), never persona text.>
```

- A subagent earns its keep through what a skill cannot do: **context isolation, tool
  restriction, model/effort override, parallelism**. A persona around knowledge the
  model already has gets deleted.
- No name collisions: with Claude Code built-ins (`Explore`, `Plan`, `general-purpose`,
  …), with other subagents in any domain, or with a same-domain skill.
- `hooks`, `mcpServers`, `permissionMode` are silently ignored by the plugin
  marketplace channel — the validator warns if used.
- Not packageable (claude.ai has no subagent upload); `bin/package.py` ignores them.

## Scripts contract (`scripts/<tool>/`)

- A self-contained CLI an agent runs **inside whatever repo it is working in** — not this
  one. Python, executed as a `uv run --script` (PEP 723 inline deps), per the global
  Python conventions.
- Every tool folder has a `README.md`: what it does, usage, exit codes, and how to wire it
  into a project.
- Design for the agent as a user: token-economical output, `--json` when a hook or tool
  will consume it, stable exit codes, errors that name the next move.

## Hooks contract (`hooks/<hook>/`)

- A `SessionStart`-style event hook (Claude Code + Codex) plus an agent-neutral `hook.toml`
  descriptor. Every hook folder has a `README.md` **and** a `hook.toml` (`event`, `command`,
  optional `matcher`/`statusMessage`).
- `bin/install.py --hooks` **renders** `hook.toml` into each agent's registration block
  (Claude `settings.json`, Codex `hooks.json` / `config.toml`) and only prints them — nothing
  silently edits user settings.
- Keep the hook thin: reuse the paired `scripts/` tool as the source of truth rather than
  duplicating logic. Fail open and quiet when there is nothing to contribute.

## Editing rules

- **This repo is PUBLIC.** No secrets, tokens, credentials, API keys — and no PHI / patient
  data — ever. No internal hostnames or private URLs. Anonymized fixtures only.
- Edit the canonical source here first. Never hand-edit a copy installed elsewhere — update
  here, then re-install / re-sync.
- Keep content generally reusable; repo-specific product skills belong in the repo they
  describe.
- **Validate after every edit:** `uv run bin/validate.py`

## Tooling

Python, executed via [`uv`](https://docs.astral.sh/uv/) (self-contained scripts with PEP
723 inline deps — no virtualenv). Identical on macOS, Windows, Linux. Min Python 3.11
(`tomllib` for the target registry).

- `uv run bin/validate.py` — enforce the SKILL.md + manifest + scripts/hooks contracts.
- `uv run bin/install.py --list` — list skills and detected agents.
- `uv run bin/install.py --all` — install all skills into every agent present on the machine.
- `uv run bin/install.py --claude --codex --pi` — install into specific agents.
- `uv run bin/package.py --list` — list packageable skills.
- `uv run bin/package.py` — package every skill into `dist/` (one archive per skill).
- `uv run bin/package.py <skill>` / `--domain <domain>` — package one skill or one domain.
- `uv run tests/test_install.py` — installer guard + multi-agent tests.
- `uv run tests/test_hooks.py` — hook opt-in gating tests.
- `uv run tests/test_package.py` — packager layout + reproducibility tests.

Agent install targets live in `bin/targets.toml` — add an agent there (one block), no code
change. A top-level `justfile` wraps the common recipes (`just validate`, `just package`,
`just install`, `just test`, `just clean`).

**Packaging for claude.ai.** The web app takes one skill at a time as a `.zip` (or `.skill`).
`bin/package.py` emits one self-contained, byte-reproducible archive per skill into `dist/`
(gitignored) — a single top-level folder named after the skill. Add `--skill` for a
byte-identical `.skill`, `--versioned` to name by frontmatter `version`, `--dry-run` to
preview. `just package` validates first.