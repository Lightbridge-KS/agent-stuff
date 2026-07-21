# .lightbridge catalog

The canonical registry of lightbridge `config.toml` sections, plus the cross-cutting
conventions. Adding a section? See [`extending.md`](extending.md).

## Conventions

- **Location:** `~/.lightbridge/projects/<project-key>/config.toml` — user-level,
  per-project, **never inside the repo** (the "local scope" model: collaborators never
  see it, and no gitignore entry is needed). Create it with `lb init` and locate it with
  `lb path` (agent-stuff `scripts/lightbridge`, the canonical resolver — it also owns the
  emittable template for every section below, so configs are never hand-written).
- **Keying:** `<project-key>` = the project root's absolute path with path separators
  replaced by `-` (the `~/.claude/projects` encoding; Windows drops the drive colon).
  The root is `git rev-parse --show-toplevel` of the session's cwd — cwd itself for
  non-git dirs — so sessions launched from a subdirectory land on the same key.
- **`root` key:** every config carries a top-level `root = "/abs/path"`. The key
  encoding is lossy and a moved repo silently orphans its config; `lightbridge doctor`
  uses `root` to flag stale entries. Readers ignore it.
- **Opt-in by section presence.** A feature activates iff its `[section]` exists.
  `enabled = false` disables it without deleting the block.
- **Format:** TOML; one `[section]` per feature; keys optional unless noted.
- **Hygiene:** the tree is personal and never committed anywhere; still no secrets,
  tokens, or PHI.

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
  - `include` — list of strings, default `["CONTEXT.md", "CONTEXT-MAP.md", "VISION.md"]`.
    Extra files **outside** `dir` (relative to repo root) to index too — surfaced as a
    separate "Charter docs (repo root)" group. Missing files are skipped; `[]` suppresses them.
- **Notes:** the hook requires explicit `summary` / `read_when` frontmatter (no `description`
  fallback), so website docs (Docusaurus/mkdocs/Quarto) are never surfaced. The `include`
  default targets the root charter docs — the `domain-modeling` skill's `CONTEXT.md` /
  `CONTEXT-MAP.md` plus `VISION.md` — so they appear with no extra config once they carry
  that frontmatter.

### `[research]`

- **Purpose:** per-project defaults for the `research` skill (deep-research sessions) — where
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

### `[plans]`

- **Purpose:** file every **approved** plan-mode plan into
  `~/.lightbridge/projects/<key>/plans/`, with a project key, a git sha, and a lifecycle —
  and, optionally, auto-approve Claude Code's plan gate.
- **Reader:** `agent-stuff` → `hooks/plan-capture` (`PostToolUse(ExitPlanMode)`) and
  `hooks/plan-gate` (`PreToolUse(ExitPlanMode)`), both over `scripts/plan-store`.
  Internals: `scripts/plan-store/README.md` in this repo.
- **Opt-in:** presence of `[plans]`; `enabled = false` to disable.
- **Keys:**
  - `enabled` — bool, default `true`.
  - `auto_approve` — bool, default **`false`**. `true` makes `plan-gate` return
    `permissionDecision: "allow"`, so the approval dialog never renders. Read
    `hooks/plan-gate/README.md` first: it costs you plan iteration ("keep planning with
    feedback"), the post-approval mode choice, and the last checkpoint before writes.
- **Notes:** Claude Code already writes *every* plan it drafts to
  `~/.claude/plans/<codename>.md` — flat across all repos, randomly named, no frontmatter,
  no outcome. This section keeps only what you **approved**, keyed per project. The
  approval signal is `PostToolUse`, which fires iff `ExitPlanMode` actually executed;
  rejecting a plan files nothing. Plans are captured from the file at `planFilePath` (the
  user may edit the plan in the dialog, so `tool_input.plan` is only the pre-edit draft).

  **Not a replacement for `docs/progress/`.** A tracker is shared, committed, zoomed-out
  checkbox state collaborators audit — it belongs in the repo. A plan is private,
  zoomed-in, one-off execution detail; Claude Code itself writes it to a user-level path.
  This is the *ephemeral* layer given a filing system, and it links up to the tracker.

  **Recovering past plans:** `plan_store.py backfill` reconstructs approved plans from
  Claude Code's transcripts (`--dry-run` first; idempotent; opt-in honored, so it reports
  the projects it skipped rather than creating configs for them).

### `[repo-links]`

- **Purpose:** declare *logical* links to sibling repos this project references (upstream
  counterpart, live test service, OSS reference clone), resolved to verified absolute
  paths and injected at Claude Code `SessionStart`. Replaces hand-maintained path lists
  in `CLAUDE.local.md`.
- **Reader:** `agent-stuff` → `hooks/repo-links-inject` (uses `scripts/repo-links`).
  Internals: `hooks/repo-links-inject/README.md` in this repo.
- **Opt-in:** presence of `[repo-links]`; `enabled = false` to disable. Additionally
  gated on the **personal registry** `~/.lightbridge/repos.toml` (see "User level") —
  registry absent → the hook stays silent.
- **Keys:**
  - `enabled` — bool, default `true`. Must precede the first `[[repo-links.link]]`
    (TOML attaches later keys to the last `[[table]]` otherwise).
  - `link` — array of tables (`[[repo-links.link]]`), each:
    - `name` — string, **required**. Logical repo name, resolved via the registry.
      Never a path.
    - `role` — string, optional. Free-form relationship (`upstream`, `oss-reference`,
      `live-test-service`, …).
    - `note` — string, optional. One line on why/when the linked repo matters.
- **Notes:** the section carries no filesystem paths — the name→path mapping lives in
  `~/.lightbridge/repos.toml`. A declared name missing from the registry, or a
  registered path that no longer exists, injects a compact WARNING line — the rot
  detector dead `CLAUDE.local.md` paths never had. Audit on demand:
  `scripts/repo-links/repo_links.py --check`.

<!-- New sections are appended here via the extending.md recipe. -->

## User level (`~/.lightbridge/`)

The whole lightbridge tree is user-level: durable, harness-neutral config and state that
must outlive a session and work across every harness (Claude Code, Codex, Pi, …). Each
feature owns a subtree **or file** registered here.

- **Layout:**
  - `~/.lightbridge/projects/<project-key>/` — per-project config **and** state, keyed
    per the Conventions above:
    - `config.toml` — the project's config (the Sections in this catalog).
    - `handoffs/` — the `handoff` skill's journal + inbox.
  - `~/.lightbridge/repos.toml` — the personal repo registry: one `[repos]` table mapping
    logical repo names to local paths (`~`-relative or absolute). Machine-specific by
    design; its *presence* is the per-machine opt-in for `[repo-links]` resolution.
    Managed by `lb repos list|add|rm` (`add` never clobbers an existing name).
- **Consumers:**
  - `lightbridge` resolver (agent-stuff `scripts/lightbridge`) — the canonical
    root/key/config resolution every reader imports, plus the CLI that writes, inspects,
    and audits configs (`status` · `init` · `add` · `show` · `enable`/`disable` ·
    `sections` · `path` · `repos` · `doctor`; linked onto PATH as `lb`).
  - `handoff` skill (agent-stuff `plugins/productivity`) — writes
    `projects/<key>/handoffs/<YYYY-MM-DD_HHMM>_<slug>.md`. The filename/frontmatter contract
    lives in that skill, not re-documented here.
  - `repo-links` reader (agent-stuff `scripts/repo-links` + `hooks/repo-links-inject`) —
    resolves the names declared in a project's `[repo-links]` section against
    `repos.toml`. File absent → readers stay silent.
- **Trade-off (accepted):** nothing in the repo means nothing travels with a clone —
  config does not follow the repo to another machine, and a moved/renamed repo orphans
  its entry (run `lightbridge doctor`). Sync `projects/*/config.toml` via private
  dotfiles if it must roam; `handoffs/` is conversation-derived — keep it local.
- **Hygiene:** never committed anywhere; may hold conversation-derived content, so treat the
  tree as private. No secrets or PHI regardless.
- **Growth:** a new user-level feature registers its subtree in this list and keeps its
  internals with the consumer — the [`extending.md`](extending.md) spirit applied to state.
