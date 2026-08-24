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
  tokens, or PHI — *except* `~/.lightbridge/secrets.toml`, which exists precisely to be
  the one 0600, harness-deny-listed location for personal LLM API key values (spec: the
  **llm-keys** skill).

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
- **Reader:** `agent-stuff` → `plugins/research/skills/research-deep/SKILL.md` reads this
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

<!-- New sections are appended here via the extending.md recipe. -->

### Retired sections

- **`[repo-links]`** (retired 2026-08-16) — per-project link declarations moved to the
  central **cross-repo graph**, `~/.lightbridge/graph.toml`: one typed edge per
  relationship, both repos' session views projected from it. Spec: the **repo-graph**
  skill; manage with `lb graph link|unlink|set|show|doctor`. A leftover section is no
  longer read and earns a one-line deprecation warning from `repo_links.py` and the
  SessionStart hook.

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
    design; it is the node namespace of the cross-repo graph. Managed by
    `lb repos list|add|rm` (`add` never clobbers an existing name).
  - `~/.lightbridge/graph.toml` — the **cross-repo graph**: `[types.<name>]` vocabulary
    (each type's `inverse` + default `backlink` mode) and `[[edge]]` blocks connecting
    registered repo names. One edge per relationship; both repos' injected session
    views project from it. Its *presence* is the per-machine opt-in for link injection.
    Managed by `lb graph init|link|unlink|set|show|types|doctor|mermaid|html`;
    spec: the **repo-graph** skill.
  - `~/.lightbridge/keys.toml` + `~/.lightbridge/secrets.toml` — **personal LLM API
    keys**, split in two layers: `keys.toml` is the agent-readable catalog (one
    `[keys.<name>]` per key: `provider`, `env`, `scope`; named per scope —
    `openai-personal`, `openai-image-gen`); `secrets.toml` holds the values (flat
    `[secrets]` table, mode 0600, deny-listed in the agent harness) and is consumed
    only by `lb key run NAME -- CMD`, which injects into a child process env and
    execs — no verb prints a value and there is no `key get`. Managed by
    `lb key ls|add|rm|run|doctor`; spec: the **llm-keys** skill, ADR 0003.
- **Consumers:**
  - `lightbridge` resolver (agent-stuff `scripts/lightbridge`) — the canonical
    root/key/config resolution every reader imports, plus the CLI that writes, inspects,
    and audits configs (`status` · `init` · `add` · `show` · `enable`/`disable` ·
    `sections` · `path` · `repos` · `graph` · `key` · `mv` · `doctor`; linked onto PATH as `lb`).
  - `handoff` skill (agent-stuff `plugins/productivity`) — writes
    `projects/<key>/handoffs/<YYYY-MM-DD_HHMM>_<slug>.md`. The filename/frontmatter contract
    lives in that skill, not re-documented here.
  - `repo-links` reader (agent-stuff `scripts/repo-links` + `hooks/repo-links-inject`) —
    projects the session repo's ego view (outgoing edges, backlinks, compact mentions)
    from `graph.toml`, paths verified via `repos.toml`. Graph absent → readers stay
    silent.
- **Trade-off (accepted):** nothing in the repo means nothing travels with a clone —
  config does not follow the repo to another machine. A moved/renamed repo is repaired
  with `lb mv OLD NEW` (`lightbridge doctor` detects the orphan and names the fix).
  Sync `projects/*/config.toml` via private dotfiles if it must roam; `handoffs/` is
  conversation-derived — keep it local.
- **Hygiene:** never committed anywhere; may hold conversation-derived content, so treat the
  tree as private. No secrets or PHI regardless — `secrets.toml` being the one deliberate
  exception (0600, deny-listed, injected-only; see above).
- **Growth:** a new user-level feature registers its subtree in this list and keeps its
  internals with the consumer — the [`extending.md`](extending.md) spirit applied to state.
