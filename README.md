# agent-stuff

[![90% Vibe_Coded](https://img.shields.io/badge/90%25-Vibe_Coded-ff69b4?style=for-the-badge&logo=claude&logoColor=white)](https://github.com/ai-ecoverse/vibe-coded-badge-action)

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
/plugin install lightbridge@lightbridge-skills
/plugin install productivity@lightbridge-skills
/plugin install research@lightbridge-skills
```

`/plugin marketplace update lightbridge-skills` refreshes the catalog later.

## Scripts

Standalone CLIs an agent runs inside the project it's working in. Each is a self-contained
`uv run --script` with its own README.

- **[`scripts/docs-index`](scripts/docs-index)** — print a compact, read-before-coding
  index of a repo's `docs/` from each file's frontmatter (`summary` / `read_when`). A
  Python+`uv` port of Peter Steinberger's `docs-list.ts`.
- **[`scripts/lightbridge`](scripts/lightbridge)** — the canonical resolver and CLI for
  user-level `.lightbridge` project config (`~/.lightbridge/projects/<key>/config.toml`).
  Every other script and hook here reads its opt-in state through this one.
- **[`scripts/handoff`](scripts/handoff)** — handoff storage for a repo: a pulled journal
  and a pushed inbox, so one session (or a sibling repo) can leave the next one a note.
- **[`scripts/plan-store`](scripts/plan-store)** — durable, project-keyed, status-bearing
  plans; the filing system Claude Code's plan mode never had.
- **[`scripts/repo-links`](scripts/repo-links)** — resolve a repo's declared cross-repo
  links to verified local paths, so personal paths never get committed.

## Hooks

Event hooks for **Claude Code and Codex** — `SessionStart` for the context injectors,
`PreToolUse`/`PostToolUse(ExitPlanMode)` for the plan pair. Each is described by an
agent-neutral [`hook.toml`](hooks/docs-index-inject/hook.toml); the installer renders it into
every agent's registration form (Claude `settings.json`, Codex `hooks.json` / `config.toml`)
with paths resolved. It only prints — it never edits settings:

```sh
uv run bin/install.py --hooks
```

- **[`hooks/docs-index-inject`](hooks/docs-index-inject)** — a `SessionStart` hook that
  injects the project's docs index into context automatically, pairing with `docs-index`.
  **Registered once** (user settings) but **opt-in per project**: it only fires where a
  `[docs-index]` section is declared in the project's user-level lightbridge config
  (`~/.lightbridge/projects/<key>/config.toml`), so repos with no docs —
  or a website `docs/` — are untouched. (Codex additionally requires trusting the hook via
  `/hooks`.)
- **[`hooks/repo-links-inject`](hooks/repo-links-inject)** — a `SessionStart` hook that
  injects the repo's resolved cross-repo links, pairing with `repo-links`. Dead links
  surface as warnings; no registry on the machine means silence.
- **[`hooks/handoff-inject`](hooks/handoff-inject)** — a `SessionStart` hook that announces
  the handoffs pushed at this repo, pairing with `handoff`, so an agent learns a sibling
  repo changed something it depends on *before* touching code.
- **[`hooks/plan-capture`](hooks/plan-capture)** — `PostToolUse(ExitPlanMode)`; files the
  **approved** plan into the project's plan store instead of Claude Code's flat
  `~/.claude/plans/`. Pairs with `plan-store`.
- **[`hooks/plan-gate`](hooks/plan-gate)** — `PreToolUse(ExitPlanMode)`; **opt-in**
  auto-approve for the plan dialog. Silent unless `[plans].auto_approve = true`.

All five are registered once in user settings and fail open and quiet when they have
nothing to contribute. Four gate on a lightbridge config section (`[docs-index]`,
`[repo-links]`, `[plans]`); `handoff-inject` needs no section — it stays silent until a
handoff is actually pushed at the repo.

## Develop

```sh
uv run bin/validate.py        # SKILL.md + manifests + scripts/hooks contracts
just test                     # the whole tests/ suite (8 files)
```

Editing guide and contracts: [`CLAUDE.md`](CLAUDE.md) (a.k.a. `AGENTS.md`). Design
rationale: [`docs/architecture.md`](docs/architecture.md). CI runs the validator and tests
on every PR.

## License

[MIT](LICENSE) © Kittipos S. ([Lightbridge-KS](https://github.com/Lightbridge-KS))
