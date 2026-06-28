# agent-stuff

Reusable building blocks for AI coding agents — **skills**, standalone **scripts**, and
**hooks** — written once and shared everywhere.

Works with [Claude Code](https://docs.claude.com/en/docs/claude-code),
[Codex](https://developers.openai.com/codex/), [Pi](https://github.com/), and any agent
that reads skills from a directory. A skill is a plain `SKILL.md`; the installer projects
the same source files into whichever agents you use.

```
plugins/   skills, grouped by domain (each domain = a Claude Code plugin)
scripts/   standalone CLIs an agent runs inside the repo it's working in
hooks/     Claude Code event hooks
bin/       machinery: installer, validator, tests, and the agent-target registry
```

## Install skills

Requires [`uv`](https://docs.astral.sh/uv/):

```sh
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```sh
git clone https://github.com/Lightbridge-KS/agent-stuff.git
cd agent-stuff

uv run bin/install.py --list            # skills + which agents are detected
uv run bin/install.py --all --dry-run   # preview, no writes
uv run bin/install.py --all             # install all skills into every agent present
```

Target specific agents (combine freely), or any directory:

```sh
uv run bin/install.py --claude                 # ~/.claude/skills      (Claude Code)
uv run bin/install.py --codex                  # ~/.codex/skills       (Codex)
uv run bin/install.py --pi                      # ~/.pi/agent/skills    (Pi)
uv run bin/install.py --agents                  # ~/.agents/skills      (shared convention)
uv run bin/install.py --claude --codex --pi    # several at once
uv run bin/install.py --target ~/some/dir      # a custom directory

uv run bin/install.py --claude coding/c4-architect   # one skill
uv run bin/install.py --claude --domain radiology    # a whole domain
```

`--mode` defaults to `auto`: **symlink** on macOS/Linux (edits in this checkout are live),
**copy** on Windows. Override with `--mode symlink|copy`. `--force` replaces an installed
skill (guarded so it can never delete the source).

**Agents are configured in [`bin/targets.toml`](bin/targets.toml)** — one block per agent.
Add a new agent there and its `--<name>` flag appears automatically; no code change.

### Claude Code plugin marketplace (Claude Code only)

```text
/plugin marketplace add Lightbridge-KS/agent-stuff
/plugin install coding@lightbridge-skills
/plugin install radiology@lightbridge-skills
```

`/plugin marketplace update lightbridge-skills` refreshes the catalog later.

## Scripts

Standalone CLIs an agent runs inside the project it's working in. Each is a self-contained
`uv run --script` with its own README.

- **[`scripts/docs-index`](scripts/docs-index)** — print a compact, read-before-coding
  index of a repo's `docs/` from each file's frontmatter (`summary` / `read_when`). A
  Python+`uv` port of Peter Steinberger's `docs-list.ts`.

## Hooks

Claude Code event hooks, each with a `settings.json` snippet to register it. Print the
snippets with paths resolved (the installer never edits settings):

```sh
uv run bin/install.py --hooks
```

- **[`hooks/docs-index-inject`](hooks/docs-index-inject)** — a `SessionStart` hook that
  injects the project's docs index into context automatically, pairing with `docs-index`.
  **Registered once** (user settings) but **opt-in per repo**: it only fires where a
  `[docs-index]` section is declared in `.lightbridge/config.toml`, so repos with no docs —
  or a website `docs/` — are untouched.

## Develop

```sh
uv run bin/validate.py        # SKILL.md + manifests + scripts/hooks contracts
uv run tests/test_install.py  # installer guards + multi-agent tests
uv run tests/test_hooks.py    # hook opt-in gating
```

Editing guide and contracts: [`CLAUDE.md`](CLAUDE.md) (a.k.a. `AGENTS.md`). Design
rationale: [`docs/architecture.md`](docs/architecture.md). CI runs the validator and tests
on every PR.

## License

[MIT](LICENSE) © Kittipos S. ([Lightbridge-KS](https://github.com/Lightbridge-KS))
