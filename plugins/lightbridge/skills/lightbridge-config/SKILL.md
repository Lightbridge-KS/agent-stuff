---
name: lightbridge-config
description: Bootstrap and manage the personal .lightbridge namespace — per-project config at ~/.lightbridge/projects/<project-key>/config.toml (docs-index, repo-links, research, …) and the rest of the user-level ~/.lightbridge/ tree (handoffs, repos.toml). Use when setting up lightbridge config for a repo, enabling or adding a config section, asking what .lightbridge supports, wiring a new config feature, or locating user-level lightbridge state.
metadata:
  version: "2026-07-13"
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
`handoff` skill) and `~/.lightbridge/repos.toml`, the personal name→path repo registry.

Full spec (conventions, sections, keys, who reads them): [`references/catalog.md`](references/catalog.md).

## The CLI does the mechanical work

`scripts/lightbridge` owns creating and auditing a config — **don't hand-write one.**
Linked onto PATH as `lightbridge` / `lb` (see its README); otherwise
`uv run <agent-stuff>/scripts/lightbridge/lightbridge.py <verb>`.

```bash
lb init                  # create this project's config; detects docs/ → [docs-index]
lb init --sections research,repo-links   # or name them; --dry-run to preview
lb add repo-links        # extend an existing config (skips sections already there)
lb sections              # what can go in a config, and who reads it
lb path                  # where this project's config lives (+ exists?)
lb doctor                # audit the whole tree (stale roots, legacy files)
```

`init` never clobbers an existing config (exit 1 — use `add`), and `add` is idempotent, so
both are safe to re-run. Report back what was written and which reader consumes it.

## Explain / "what can go in .lightbridge?"

Read [`references/catalog.md`](references/catalog.md) and answer from it — conventions,
sections, keys, opt-in semantics, and the reader behind each. (`lb sections` gives the
one-line version.)

## Enable or disable a section

`lb add <name>` appends a section. To toggle one, set `enabled = true|false` in the config —
don't delete the block just to disable it.

## Invent a NEW section (how this skill grows)

When the user and I design a new `.lightbridge` feature, follow
[`references/extending.md`](references/extending.md): build the reader (resolving config
through `scripts/lightbridge`), register it in `catalog.md`, add its template block to
`SECTIONS` in `scripts/lightbridge/lightbridge.py`, sync the one-line brief in
`agent-instruction/AGENTS.qmd`, bump `metadata.version`, and validate.

## Source of truth

This skill is the **canonical** spec for `.lightbridge`. Each feature's *internals* live with
its implementation (e.g. the `docs-index` hook README) and are linked from the catalog — not
re-documented here. `AGENTS.qmd` keeps only the brief plus a pointer to this skill.
