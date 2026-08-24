---
name: lightbridge-config
description: >-
  Bootstrap and manage the personal .lightbridge namespace — per-project config sections
  plus user-level state (handoffs, plans, repos.toml, graph.toml, keys.toml). Use when
  setting up or extending lightbridge config for a repo, enabling or adding a section,
  asking what .lightbridge supports, or locating user-level lightbridge state. For
  linking repos in the cross-repo graph, use the repo-graph skill; for running
  inference with personal LLM API keys, use the llm-keys skill.
metadata:
  version: "2026-08-24"
---

# .lightbridge config

`.lightbridge` is my personal, tool-agnostic config namespace — a stable place my own
scripts and hooks read, separate from any agent's dir (`.claude/`, `.codex/`, `.pi/`).
**Everything is user-level; nothing ever lives inside a repo** (the "local scope" model —
collaborators never see it, no gitignore needed). One file per project:

    ~/.lightbridge/projects/<project-key>/config.toml    # namespaced by [section]

resolved by `scripts/lightbridge` (agent-stuff): project root = git toplevel of cwd,
key = root path with separators → `-`.

**The one rule — opt-in by section presence.** A feature is on iff its `[section]` exists;
`enabled = false` disables without deleting.

The same tree holds durable, harness-neutral **state**: `projects/<key>/handoffs/` (the
`handoff` skill), `projects/<key>/plans/` (approved plan-mode plans, filed by
`hooks/plan-capture`), `~/.lightbridge/repos.toml` (the personal name→path repo
registry), `~/.lightbridge/graph.toml` (the cross-repo graph — typed edges between
registered repos; spec: the **repo-graph** skill), and `~/.lightbridge/keys.toml` +
`secrets.toml` (personal LLM API keys: agent-readable catalog + injected-only values;
spec: the **llm-keys** skill).

Full spec (conventions, sections, keys, who reads them): [`references/catalog.md`](references/catalog.md).

## The CLI does the mechanical work

`scripts/lightbridge` owns creating and auditing a config — **don't hand-write one.**
Linked onto PATH as `lightbridge` / `lb` (see its README); otherwise
`uv run <agent-stuff>/scripts/lightbridge/lightbridge.py <verb>`.

```bash
lb status                # FIRST MOVE for "what's lightbridge doing here?" — one dashboard
lb init                  # create this project's config; detects docs/ → [docs-index]
lb init research plans   # or name sections; --dry-run to preview
lb add research          # extend an existing config (skips sections already there)
lb show [SECTION]        # print the stored config (or one block); --json to parse
lb enable|disable NAME   # flip a section's `enabled` in place (idempotent)
lb sections              # what can go in a config, and who reads it
lb path                  # where this project's config lives (+ exists?)
lb repos list|add|rm     # manage ~/.lightbridge/repos.toml (add never clobbers a name)
lb graph …               # the cross-repo graph — see the repo-graph skill
lb key …                 # personal LLM API keys — see the llm-keys skill
lb mv OLD NEW            # move/rename a repo (or parent dir) + repair all bookkeeping
lb doctor                # audit the whole tree (stale roots, legacy files)
```

`init` never clobbers an existing config (exit 1 — use `add`), and `add` /
`enable` / `disable` are idempotent, so all are safe to re-run. Report back what was
written and which reader consumes it.

## Explain / "what can go in .lightbridge?"

Read [`references/catalog.md`](references/catalog.md) and answer from it — conventions,
sections, keys, opt-in semantics, and the reader behind each. (`lb sections` gives the
one-line version.)

## Enable or disable a section

`lb add <name>` appends a section; `lb enable <name>` / `lb disable <name>` toggle one in
place (a line edit — comments survive). Never delete a block just to disable it, and don't
hand-edit `enabled` — the CLI owns that key.

## Moving or renaming a repo

Everything in `~/.lightbridge` is keyed by repo path, so a move/rename breaks config
silently. **One command repairs everything** — whether the user is about to move
("I'm moving X to Y") or already did ("I moved X to Y"):

    lb mv OLD NEW            # OLD still exists → performs the move too; OLD gone → repair only

It re-keys `projects/<key>/` (config + handoffs + plans travel), rewrites `root`, and
fixes matching `repos.toml` paths — parent-dir moves re-key every project beneath in one
shot. Never hand-edit these files. Preview with `--dry-run`. Non-interactive runs need
`--yes` — **pass it only when the user explicitly instructed this move.** A note about
`~/.claude/projects/<old-key>` (Claude Code session state) may print — that is left for
the user to migrate deliberately. Design: `docs/lightbridge/lightbridge-mv.md` (agent-stuff).

## Invent a NEW section (how this skill grows)

When the user and I design a new `.lightbridge` feature, follow
[`references/extending.md`](references/extending.md): build the reader (resolving config
through `scripts/lightbridge`), register it in `catalog.md`, add its template block to
`SECTIONS` in `scripts/lightbridge/lb_catalog.py`, sync the one-line brief in
`agent-instruction/AGENTS.qmd`, bump `metadata.version`, and validate.

## Source of truth

This skill is the **canonical** spec for `.lightbridge`. Each feature's *internals* live with
its implementation (e.g. the `docs-index` hook README) and are linked from the catalog — not
re-documented here. `AGENTS.qmd` keeps only the brief plus a pointer to this skill.
