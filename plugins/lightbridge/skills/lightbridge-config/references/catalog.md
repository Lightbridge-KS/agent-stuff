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

### `[repo-links]`

- **Purpose:** declare *logical* links to sibling repos this project references (upstream
  counterpart, live test service, OSS reference clone), resolved to verified absolute
  paths and injected at Claude Code `SessionStart`. Replaces hand-maintained path lists
  in `CLAUDE.local.md`.
- **Reader:** `agent-stuff` → `hooks/repo-links-inject` (uses `scripts/repo-links`).
  Internals: `hooks/repo-links-inject/README.md` in this repo.
- **Opt-in:** presence of `[repo-links]`; `enabled = false` to disable. Additionally
  gated on the **personal registry** `~/.lightbridge/repos.toml` (see "User level") —
  registry absent → the hook stays silent, so the committed section imposes nothing on
  other machines.
- **Keys:**
  - `enabled` — bool, default `true`. Must precede the first `[[repo-links.link]]`
    (TOML attaches later keys to the last `[[table]]` otherwise).
  - `link` — array of tables (`[[repo-links.link]]`), each:
    - `name` — string, **required**. Logical repo name, resolved via the registry.
      Never a path.
    - `role` — string, optional. Free-form relationship (`upstream`, `oss-reference`,
      `live-test-service`, …).
    - `note` — string, optional. One line on why/when the linked repo matters.
- **Notes:** the committed section carries no filesystem paths — the name→path mapping
  lives per machine in `~/.lightbridge/repos.toml`. A declared name missing from the
  registry, or a registered path that no longer exists, injects a compact WARNING
  line — the rot detector dead `CLAUDE.local.md` paths never had. Audit on demand:
  `scripts/repo-links/repo_links.py --check`.

<!-- New sections are appended here via the extending.md recipe. -->

## User level (`~/.lightbridge/`)

Durable, harness-neutral state that must outlive a session and work across every harness
(Claude Code, Codex, Pi, …) — the user-level sibling of the per-repo folder, mirroring the
`.claude/` vs `~/.claude/` split. Not config: there is no user-level `config.toml` (yet);
each feature owns a subtree **or file** registered here.

- **Layout:**
  - `~/.lightbridge/projects/<project-key>/` — per-project state, keyed by the
    absolute project path with path separators replaced by `-` (the same encoding as
    `~/.claude/projects`), e.g. `-Users-kittipos-my_config-agent-stuff`. On Windows, drop the
    drive colon (`C:\Users\x` → `-C-Users-x`).
  - `~/.lightbridge/repos.toml` — the personal repo registry: one `[repos]` table mapping
    logical repo names to local paths (`~`-relative or absolute). Machine-specific by
    design; its *presence* is the per-machine opt-in for `[repo-links]` resolution.
- **Consumers:**
  - `handoff` skill (agent-stuff `plugins/productivity`) — writes
    `projects/<key>/handoffs/<YYYY-MM-DD_HHMM>_<slug>.md`. The filename/frontmatter contract
    lives in that skill, not re-documented here.
  - `repo-links` reader (agent-stuff `scripts/repo-links` + `hooks/repo-links-inject`) —
    resolves the names declared in a repo's committed `[repo-links]` section against
    `repos.toml`. File absent → readers stay silent, so committed sections are inert on
    machines that haven't opted in.
- **Hygiene:** never committed anywhere; may hold conversation-derived content, so treat the
  tree as private. No secrets or PHI regardless.
- **Growth:** a new user-level feature registers its subtree in this list and keeps its
  internals with the consumer — the [`extending.md`](extending.md) spirit applied to state.
