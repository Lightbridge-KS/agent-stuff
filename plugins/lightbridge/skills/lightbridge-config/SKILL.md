---
name: lightbridge-config
description: Bootstrap and manage the personal .lightbridge/ config namespace in a repo — create or extend .lightbridge/config.toml, explain its sections (docs-index, …), and register new sections as they're invented. Use when setting up .lightbridge, enabling or adding a config section, asking what .lightbridge supports, or wiring a new per-repo config feature.
metadata:
  version: "2026-07-06"
---

# .lightbridge config

`.lightbridge/` is my personal, tool-agnostic per-repo config namespace — a stable place my
own scripts and hooks read, separate from any agent's dir (`.claude/`, `.codex/`, `.pi/`).
One file: `.lightbridge/config.toml`, namespaced by `[section]`.

**The one rule — opt-in by section presence.** A feature is on iff its `[section]` exists;
`enabled = false` disables without deleting. So the folder is safe to carry across many repos.

Full spec (sections, keys, who reads them): [`references/catalog.md`](references/catalog.md).

## Bootstrap a repo

1. If `<repo>/.lightbridge/config.toml` is **absent** → create it from
   [`assets/config.toml`](assets/config.toml).
2. If it **exists** → never overwrite; add only the missing `[section]`(s) the user asked for.
3. Confirm what was written and which reader consumes it (see the catalog).

## Explain / "what can go in .lightbridge?"

Read [`references/catalog.md`](references/catalog.md) and answer from it — sections, keys,
opt-in semantics, and the reader behind each.

## Add or enable a section

Copy the section's block from `assets/config.toml` (or the catalog) into the repo's
`config.toml`. To toggle, set `enabled = true|false` — don't delete a block just to disable it.

## Invent a NEW section (how this skill grows)

When the user and I design a new `.lightbridge/` feature, follow
[`references/extending.md`](references/extending.md): build the reader, register it in
`catalog.md`, add a template block to `assets/config.toml`, sync the one-line brief in
`agent-instruction/AGENTS.qmd`, bump `metadata.version`, and validate.

## Source of truth

This skill is the **canonical** spec for `.lightbridge/`. Each feature's *internals* live with
its implementation (e.g. the `docs-index` hook README) and are linked from the catalog — not
re-documented here. `AGENTS.qmd` keeps only the brief plus a pointer to this skill.
