---
summary: Why agent-stuff is structured the way it is — content (skills/subagents/scripts/hooks) vs machinery, the distribution model, and the contracts each content type follows.
read_when:
  - adding or changing a skill, subagent, script, or hook
  - modifying the installer, validator, packager, or the targets.toml agent registry
  - understanding the repo layout or distribution model
  - packaging a skill as a .zip/.skill for upload to claude.ai
---

# Architecture: agent-stuff

This repo solves one problem: agent workflows — skills (CLI usage, references, review
checklists), standalone scripts, and hooks — get hand-copied between projects and drift.
The fix is a single canonical repository plus cheap distribution into each agent.

It is a superset of the earlier `agent-skills` repo. The skills half is adapted from the
OpenClaw `agent-skills` layout, with three changes for a **public, personal** collection,
then extended with two more kinds of content (scripts, hooks):

1. **Dual distribution** — a Claude Code **plugin marketplace** *and* a `uv` installer,
   both reading the same files (see "Distribution model").
2. **Categorized by domain**, where **each domain is its own plugin** (see "Domain =
   plugin").
3. **Public hygiene** — MIT licensed; no secrets, PHI, or internal hostnames.

## Three ideas

1. **Single source of truth.** Every skill has exactly one canonical home:
   `plugins/<domain>/skills/<name>/SKILL.md`. Everything else derives from it.
2. **Cheap distribution.** Skills install into a target the agent reads from — via the
   plugin system, or a small installer that symlinks (dev) or copies (portable).
3. **Thin contract + enforcement gate.** Every skill follows a minimal frontmatter
   contract, checked by a validator that runs in CI on every change.

## Two namespaces

```
content (the product)                     machinery (ships + checks content)
─────────────────────                     ─────────────────────────────────
plugins/  →  skills + subagents, each      bin/    →  installer, validator,
             domain a plugin                          + targets.toml (agent registry)
scripts/  →  standalone agent CLIs         tests/  →  installer + hook + packager
hooks/    →  SessionStart hooks (Claude               test suites
             Code + Codex)
```

The split is the same idea the old repo had (`plugins/` vs `scripts/`), widened: there
are now **four content types** the agent consumes, and the machinery moved to `bin/` so
the word `scripts/` can mean "things the agent runs" — matching how steipete's
`agent-scripts` is organized.

A folder under `plugins/<domain>/skills/` is a skill **iff it contains `SKILL.md`**.
Discovery is `glob("plugins/*/skills/*/SKILL.md")` — the filesystem is the index. No
registry, no manifest to keep in sync (beyond the marketplace listing of domains).
The same "filesystem is the index" rule holds for the other types: a **file** under
`plugins/<domain>/agents/` ending in `.md` is a subagent; a folder under `scripts/` is
a tool; a folder under `hooks/` is a hook; each carries its contract (`README.md`,
`hook.toml`, frontmatter), enforced by the validator.

## Scripts and hooks

- **`scripts/<tool>/`** — a standalone CLI an agent runs *inside whatever repo it is
  working in* (not this one). The seed is `docs-index`, a Python+`uv` port of steipete's
  `docs-list.ts`: it reads a project's `docs/` frontmatter and prints a compact
  "read-before-coding" map. Each tool is self-contained (PEP 723 `uv run --script`) with a
  `README.md`.
- **`hooks/<hook>/`** — a `SessionStart` event hook (Claude Code **and** Codex, which share
  the same wire format) described by an agent-neutral `hook.toml`. `docs-index-inject` runs
  the `docs-index` logic and injects the map as `additionalContext` — the deterministic tool
  stays the core, the hook is thin wiring that reuses its paired script. It is **registered
  once** (user-level settings) but **opt-in per project**: it only fires where a
  `[docs-index]` section is declared in the project's user-level lightbridge config —
  `~/.lightbridge/projects/<key>/config.toml`, resolved by `scripts/lightbridge`; nothing
  lives inside the repo — so a single global registration is safe across repos with no docs
  or a website `docs/`. `uv run bin/install.py --hooks` *renders* `hook.toml` into each agent's
  registration block (Claude `settings.json`; Codex `hooks.json` / inline `config.toml`, which
  also needs a one-time `/hooks` trust) with paths resolved — it only prints, never edits.

## Subagents (`plugins/<domain>/agents/<name>.md`)

A subagent is a Claude Code custom-agent definition: YAML frontmatter (`name`,
`description`, optional `model`, `color`, …) over a Markdown body that becomes the
agent's system prompt. Unlike a skill it is a **single file, not a folder** — mirroring
Claude Code's own convention (`~/.claude/agents/*.md`, plugin `agents/*.md`).

Three decisions shape the type:

1. **Claude-only, by data.** Codex subagents are TOML with a different field set
   (`developer_instructions`, `sandbox_mode`, vendor-specific `model`), so a copy can
   never be correct — shipping there would need a render step, like hooks. Until that
   exists, exclusion is expressed in `targets.toml`: only targets that declare an
   `agents` dir receive subagents (no key → skipped, no error).
2. **Two channels, one asymmetry.** The plugin marketplace discovers `agents/*.md`
   automatically but namespaces the identity (`productivity:mech`, invoked as
   `@agent-productivity:mech`) and **silently ignores** `hooks`, `mcpServers`, and
   `permissionMode` (the validator warns when a subagent uses them). The `uv` installer
   symlinks the file into `~/.claude/agents/`, keeping the bare name (`@agent-mech`).
   Don't consume the same subagent through both channels on one machine — you'd
   register it twice under two names.
3. **Not packageable.** claude.ai takes skill uploads only; subagents have no upload
   channel, so `bin/package.py` deliberately ignores them.

The contract (enforced by `bin/validate.py`): `name` == filename stem; non-empty
`description` (it is Claude Code's auto-delegation router — an opt-in-only agent must
say so *in the description*); `model`, if pinned, is a known alias (`opus`, `sonnet`,
`haiku`, `fable`, `inherit`) or a `claude-*` id; no name collision with Claude Code
built-ins (`Explore`, `Plan`, `general-purpose`, …) or across domains (the installer
flattens all subagents into one directory); no `<domain>/<name>` clash with a skill
(skills and subagents share the installer's address space).

A subagent must earn its keep through what a skill cannot do — context isolation, tool
restriction, model/effort override, parallelism — never through persona text. The body
is written like a contract: input expectations, execution rules, output format.

## Domain = plugin

This is the key decision that lets one tree serve three consumers without duplication.

Claude Code discovers a plugin's skills under `<plugin-root>/skills/<name>/SKILL.md`. By
rooting each domain plugin at `plugins/<domain>/`, the skill path becomes
`plugins/<domain>/skills/<name>/SKILL.md` — which is *also* a clean, browse-able
"categorized by domain" tree, and *also* what the `uv` installer globs.

```
plugins/coding/
  .claude-plugin/plugin.json        ← makes "coding" an installable plugin
  skills/example-skill/SKILL.md
```

Adding a domain = a new `plugins/<domain>/.claude-plugin/plugin.json` + an entry in
`.claude-plugin/marketplace.json`. Adding a skill = a new `SKILL.md` under that domain.

## The contract

`SKILL.md` opens with YAML frontmatter:

| Field         | Required | Purpose                                                |
| ------------- | -------- | ------------------------------------------------------ |
| `name`        | yes      | Stable identifier; **must equal the folder name** (kebab-case). |
| `description` | yes      | Router trigger — when should the agent load this skill? |
| `metadata`    | no       | Free-form map; `version: "YYYY-MM-DD"` recommended.    |

Claude Code itself only requires `description`; we additionally enforce `name == folder`
so the marketplace and `uv` installer agree on identity. `validate_skills.py` enforces the
machine-checkable half; `CLAUDE.md` carries the human half (no secrets, no PHI, terse
operational bodies).

## Distribution model

```
CANONICAL (this repo)                          CONSUMERS
─────────────────────                          ─────────
plugins/coding/skills/example-skill/
        │
        ├─ plugin marketplace ───────────────► /plugin install coding@lightbridge-skills
        ├─ symlink (uv installer, macOS/Linux) ─► <agent>/skills/example-skill  (live edits)
        └─ copy    (uv installer, Windows)      ─► <agent>/skills/example-skill  (static snapshot)
```

- **Plugin marketplace** — `.claude-plugin/marketplace.json` lists each domain plugin.
  Users add the marketplace once, then install/disable per domain (Claude Code only).
- **Symlink** — live: editing the canonical skill is instantly visible. Default on
  macOS/Linux. Zero drift.
- **Copy** — static snapshot. Default on Windows (symlinks need admin/Developer Mode) and
  good for portable/locked-down setups. Re-run the installer to refresh.

`bin/install.py` resolves `--mode auto` to symlink/copy by OS, and guards `--force`
with a real-path check so it can never delete the canonical source.

### Multi-agent targets (the registry)

Which agents the installer can target is **data, not code**: `bin/targets.toml` maps an
agent name to the directory it reads skills from. Each entry becomes a `--<name>` flag;
several can be combined in one run, and `--all` installs into every agent **present** on
the machine (detected by whether the parent of its skills dir exists — so it is safe to run
anywhere). Adding an agent is one TOML block, no Python change.

```toml
[claude]  skills = "~/.claude/skills"   agents = "~/.claude/agents"
[codex]   skills = "~/.codex/skills"    # no `agents` key → no subagents
[pi]      skills = "~/.pi/agent/skills"
[agents]  skills = "~/.agents/skills"   # shared cross-agent convention
```

The optional `agents` key is the same registry idea applied to subagents: its
**presence** opts a target into receiving `plugins/*/agents/*.md` files (symlinked or
copied flat, one file per subagent). Targets without the key skip subagents with a
notice — the degrade-vs-skip decision is data, not code.

The `agents` entry is the emerging `~/.agents/skills` convention several tools read — one
install there can serve more than one agent. A skill is a plain `SKILL.md`, so placement is
format-agnostic: as each agent's skill support matures, the files are already where it looks.

### Packaging for upload (`bin/package.py`)

The claude.ai web app is a fourth consumer, but it takes a skill as an **uploaded file**,
not an installed folder — and one skill at a time. `bin/package.py` discovers skills with
the same `plugins/*/skills/*/SKILL.md` glob and zips one self-contained archive per skill
into `dist/` (gitignored build output), keyed by the skill's bare name:

```
dist/dcmtk.zip
└── dcmtk/                # single top-level folder == skill name
    ├── SKILL.md
    └── references/...
```

- Archives are **byte-reproducible** — entries are sorted and stamped with a fixed 1980 ZIP
  epoch, so re-running yields identical bytes (clean diffs, cacheable CI).
- A **`.skill`** file is byte-identical to the `.zip` (`--skill`); `--versioned` names
  archives by frontmatter `version`. `--domain <domain>` packages one plugin domain.
- All-in-one bundling is intentionally omitted — the upload dialog takes a single skill.

`just package` validates before packaging, so a broken frontmatter contract fails fast
rather than shipping.

## Why Python / uv

The tools are small (glob + symlink/copy, frontmatter parsing, a docs walk), and `uv` gives
one cross-platform install with PEP 723 inline dependencies (`# /// script`) — `uv run`
fetches PyYAML / reads `tomllib` (stdlib ≥3.11) on demand, no virtualenv to manage.
Identical behavior on macOS, Windows, and Linux. Standalone `scripts/` and `hooks/` use the
same `uv run --script` convention, so everything in the repo runs the same way.

## CI gate

`.github/workflows/validate.yml` runs on every PR and push to `main`:

1. `uv run bin/validate.py` — skill frontmatter + manifests + scripts/hooks contracts.
2. `uv run tests/test_install.py` — installer guard + multi-agent tests.
3. `uv run tests/test_hooks.py` — hook opt-in gating tests.
4. `py_compile` — syntax check of all Python under `bin/`, `scripts/`, `hooks/`, `tests/`.

## Future enhancements

- Auto-generate the README "Skills" table from frontmatter.
- Cut git tags once skills stabilize; populate `metadata.version` consistently.
- Per-skill plugins (finer-grained install) if any single skill outgrows its domain.
