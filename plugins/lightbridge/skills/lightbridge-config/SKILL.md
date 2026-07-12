---
name: lightbridge-config
description: Bootstrap and manage the personal .lightbridge namespace — per-project config at ~/.lightbridge/projects/<project-key>/config.toml (docs-index, repo-links, research, …) and the rest of the user-level ~/.lightbridge/ tree (handoffs, repos.toml). Use when setting up lightbridge config for a repo, enabling or adding a config section, asking what .lightbridge supports, wiring a new config feature, or locating user-level lightbridge state.
metadata:
  version: "2026-07-12"
---

# .lightbridge config

`.lightbridge` is my personal, tool-agnostic config namespace — a stable place my own
scripts and hooks read, separate from any agent's dir (`.claude/`, `.codex/`, `.pi/`).
**Everything is user-level; nothing ever lives inside a repo** (the "local scope" model —
collaborators never see it, no gitignore needed). One file per project:

    ~/.lightbridge/projects/<project-key>/config.toml    # namespaced by [section]

resolved by `scripts/lightbridge` (agent-stuff): project root = git toplevel of cwd,
key = root path with separators → `-`. Run `lightbridge path` in any repo to get its
config path; `lightbridge doctor` audits the whole tree (stale roots, legacy files).

**The one rule — opt-in by section presence.** A feature is on iff its `[section]` exists;
`enabled = false` disables without deleting.

The same tree holds durable, harness-neutral **state**: `projects/<key>/handoffs/` (the
`handoff` skill) and `~/.lightbridge/repos.toml`, the personal name→path repo registry.

Full spec (conventions, sections, keys, who reads them): [`references/catalog.md`](references/catalog.md).

## Bootstrap a project

1. Run `uv run <agent-stuff>/scripts/lightbridge/lightbridge.py path` from the repo — it
   prints the config path and whether it exists.
2. If **absent** → create it from [`assets/config.toml`](assets/config.toml), setting
   `root` to the project root's absolute path and keeping only the sections the user wants.
3. If it **exists** → never overwrite; add only the missing `[section]`(s) the user asked for.
4. Confirm what was written and which reader consumes it (see the catalog).

## Explain / "what can go in .lightbridge?"

Read [`references/catalog.md`](references/catalog.md) and answer from it — conventions,
sections, keys, opt-in semantics, and the reader behind each.

## Add or enable a section

Copy the section's block from `assets/config.toml` (or the catalog) into the project's
`config.toml`. To toggle, set `enabled = true|false` — don't delete a block just to disable it.

## Invent a NEW section (how this skill grows)

When the user and I design a new `.lightbridge` feature, follow
[`references/extending.md`](references/extending.md): build the reader (resolving config
through `scripts/lightbridge`), register it in `catalog.md`, add a template block to
`assets/config.toml`, sync the one-line brief in `agent-instruction/AGENTS.qmd`, bump
`metadata.version`, and validate.

## Source of truth

This skill is the **canonical** spec for `.lightbridge`. Each feature's *internals* live with
its implementation (e.g. the `docs-index` hook README) and are linked from the catalog — not
re-documented here. `AGENTS.qmd` keeps only the brief plus a pointer to this skill.
