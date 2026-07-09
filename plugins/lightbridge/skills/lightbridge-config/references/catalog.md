# .lightbridge catalog

The canonical registry of `.lightbridge/config.toml` sections, plus the cross-cutting
conventions. Adding a section? See [`extending.md`](extending.md).

## Conventions

- **Location:** `<repo>/.lightbridge/config.toml`, committed. (Reserved for later:
  `config.local.toml`, gitignored, for machine/personal overrides — not used yet.)
- **Opt-in by section presence.** A feature activates iff its `[section]` exists.
  `enabled = false` disables it without deleting the block.
- **Format:** TOML; one `[section]` per feature; keys optional unless noted.
- **Scope:** `config.toml` is project-level only (no user-level merge). Durable user-level
  *state* lives under `~/.lightbridge/` — see "User level" below.
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
  - `include` — list of strings, default `["CONTEXT.md", "CONTEXT-MAP.md"]`. Extra files
    **outside** `dir` (relative to repo root) to index too — surfaced as a separate
    "Domain context (repo root)" group. Missing files are skipped; `[]` suppresses them.
- **Notes:** the hook requires explicit `summary` / `read_when` frontmatter (no `description`
  fallback), so website docs (Docusaurus/mkdocs/Quarto) are never surfaced. The `include`
  default targets the `domain-modeling` skill's `CONTEXT.md` / `CONTEXT-MAP.md`, so they
  appear with no extra config once they carry that frontmatter.

### `[research]`

- **Purpose:** per-repo defaults for the `research` skill (deep-research sessions) — where
  sessions live, preferred backends, output format, and local corpora offered to the
  planner.
- **Reader:** `agent-stuff` → `plugins/research/skills/research/SKILL.md` reads this
  section at plan time; when absent, the skill's capability probe + scoping questions
  cover everything.
- **Opt-in:** presence of `[research]`; `enabled = false` to disable.
- **Keys:**
  - `enabled` — bool, default `true`.
  - `dir` — string, default `"docs/research"`. Parent dir for session folders.
  - `output` — string, default `"markdown"`. `"quarto"` → `report.qmd` + generated
    `references.bib` (`@key` citations), rendered to self-contained HTML by default.
  - `backends` — list of strings, default: probed at plan time. Preference order, e.g.
    `["pubmed-mcp", "websearch"]`.
  - `searcher_model` — string, default `"sonnet"`. Model tier for searcher subagents;
    `"inherit"` matches the session model. Seeds `execution.searcher_model` in `plan.md`.
  - `verifier_model` — string, default `"sonnet"`. Model tier for verifier subagents;
    `"inherit"` matches the session model. Seeds `execution.verifier_model` in `plan.md`.
  - `corpus` — list of strings, default `[]`. Local corpus dirs (reserved for the future
    local-corpus module).
- **Notes:** section present → near-zero-question planning; paths may be `~`-relative.

<!-- New sections are appended here via the extending.md recipe. -->

## User level (`~/.lightbridge/`)

Durable, harness-neutral state that must outlive a session and work across every harness
(Claude Code, Codex, Pi, …) — the user-level sibling of the per-repo folder, mirroring the
`.claude/` vs `~/.claude/` split. Not config: there is no user-level `config.toml` (yet);
each feature owns a subtree registered here.

- **Layout:** `~/.lightbridge/projects/<project-key>/` — per-project state, keyed by the
  absolute project path with path separators replaced by `-` (the same encoding as
  `~/.claude/projects`), e.g. `-Users-kittipos-my_config-agent-stuff`. On Windows, drop the
  drive colon (`C:\Users\x` → `-C-Users-x`).
- **Consumers:**
  - `handoff` skill (agent-stuff `plugins/productivity`) — writes
    `projects/<key>/handoffs/<YYYY-MM-DD_HHMM>_<slug>.md`. The filename/frontmatter contract
    lives in that skill, not re-documented here.
- **Hygiene:** never committed anywhere; may hold conversation-derived content, so treat the
  tree as private. No secrets or PHI regardless.
- **Growth:** a new user-level feature registers its subtree in this list and keeps its
  internals with the consumer — the [`extending.md`](extending.md) spirit applied to state.
