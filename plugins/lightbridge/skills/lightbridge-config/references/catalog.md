# .lightbridge catalog

The canonical registry of `.lightbridge/config.toml` sections, plus the cross-cutting
conventions. Adding a section? See [`extending.md`](extending.md).

## Conventions

- **Location:** `<repo>/.lightbridge/config.toml`, committed. (Reserved for later:
  `config.local.toml`, gitignored, for machine/personal overrides — not used yet.)
- **Opt-in by section presence.** A feature activates iff its `[section]` exists.
  `enabled = false` disables it without deleting the block.
- **Format:** TOML; one `[section]` per feature; keys optional unless noted.
- **Scope:** project-level only for now (no user-level merge).
- **Hygiene:** no secrets, tokens, or PHI — repos may be public.

## Sections

### `[docs-index]`

- **Purpose:** inject a compact "read-before-coding" docs map into context at Claude Code
  `SessionStart`.
- **Reader:** `agent-stuff` → `hooks/docs-index-inject` (uses `scripts/docs-index`).
  Internals: `hooks/docs-index-inject/README.md` in this repo.
- **Opt-in:** presence of `[docs-index]`; `enabled = false` to disable.
- **Keys:**
  - `enabled` — bool, default `true`.
  - `dir` — string, default `"docs"`. Docs directory, relative to repo root.
  - `exclude` — list of strings, default `["archive", "research"]`. Subdir names to skip.
- **Notes:** the hook requires explicit `summary` / `read_when` frontmatter (no `description`
  fallback), so website docs (Docusaurus/mkdocs/Quarto) are never surfaced.

<!-- New sections are appended here via the extending.md recipe. -->
