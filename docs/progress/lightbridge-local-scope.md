---
summary: Canonical progress tracker for the .lightbridge "local scope" migration — eliminating
  per-repo .lightbridge/config.toml in favor of ~/.lightbridge/projects/<project-key>/config.toml,
  with milestones, commit SHAs, and the confirmed contracts (D1–D5) that bind the implementation.
read_when:
  - resuming or continuing the .lightbridge local-scope migration
  - changing where any lightbridge reader (docs-index, repo-links, handoff, research) resolves config
  - checking whether a .lightbridge location/keying behavior is a confirmed contract before changing it
---

# Progress: .lightbridge local scope (kill per-repo config)

Plan of record: approved plan 2026-07-12 (this file is its durable successor). Spec home:
`plugins/lightbridge/skills/lightbridge-config/` (catalog.md is the canonical spec once updated).

**Why:** per-repo `.lightbridge/config.toml` leaks personal config into shared repos —
collaborators see it or every repo needs gitignore surgery. Nothing in it ever benefited
teammates. Adopt the Claude Code "local scope" model: config lives in `~/.lightbridge`,
keyed by project path; repos stay completely clean.

## Milestones

- [ ] **Tracker** — this file
- [ ] **`scripts/lightbridge/` tool** — canonical resolver (git-toplevel → project-key →
      `~/.lightbridge/projects/<key>/config.toml`) + `path` / `doctor` CLI
- [ ] **Readers refactored** — docs-index-inject, repo-links (+hook), handoff keyed on
      git-toplevel; per-repo walk-up deleted; legacy per-repo file → one-line warning
- [ ] **Tests** — test_hooks.py reworked to `LIGHTBRIDGE_STATE_DIR` fixtures; test_repo_links.py
      config into fake home; new test_lightbridge.py; handoff subdir-keying test
- [ ] **Docs sweep (agent-stuff)** — lightbridge-config skill (SKILL/catalog/extending/assets),
      research + handoff SKILL.md, 5 hook/script READMEs, README.md, docs/architecture.md,
      plugin description strings
- [ ] **Brief sync (`agent-instruction`)** — AGENTS.qmd §Personal config rewritten, `make build`,
      commit on main
- [ ] **Data migration** — 10 configs moved to `~/.lightbridge/projects/<key>/config.toml`
      (`root =` added); per-repo `.lightbridge/` deleted; chore commits: RMOS + RMOS-InHouse
      on `develop`, orthanc-test-pacs + agent-stuff on `main`
- [ ] **Verified** — validate.py + full test suite green; hook smoke tests with real payloads
      (docs-index @ agent-stuff, repo-links @ RMOS-InHouse, handoff from a subdir); `doctor` clean

## Now / Next

- Now: build `scripts/lightbridge/` (resolver + CLI).
- Next: refactor readers + tests, then docs sweep, then migration.

## Confirmed contracts (bind the implementation)

- **D1 — Location:** `~/.lightbridge/projects/<project-key>/config.toml`; same TOML schema and
  section-presence opt-in as before. Per-repo `.lightbridge/` support removed entirely — no
  precedence chain, no fallback; a stray per-repo file only earns a one-line deprecation warning.
- **D2 — Keying:** project-key = absolute path of `git rev-parse --show-toplevel` (fallback: cwd
  for non-git dirs), encoded with the existing `project_key()` rule (separators → `-`, Windows
  drive colon dropped). Handoff switches from raw cwd to the same rule — one keying rule for the
  whole `~/.lightbridge` tree.
- **D3 — Staleness:** every config carries top-level `root = "/abs/path"`. Readers ignore it;
  `lightbridge doctor` uses it to flag orphans (the key encoding is lossy).
- **D4 — One resolver:** `scripts/lightbridge/lightbridge.py` is the only implementation of
  root/key/config resolution; hooks and scripts import it (path-relative importlib), never
  reimplement it.
- **D5 — Migration commits:** removals committed in every tracked repo — RMOS and RMOS-InHouse on
  `develop`; orthanc-test-pacs, agent-stuff, agent-instruction on `main`. No pushes.
- **Env override:** `LIGHTBRIDGE_STATE_DIR` (existing handoff contract) points at the
  `~/.lightbridge/projects` equivalent for tests; the resolver honors it.

## Open questions

- (none — D1–D5 settled with KS 2026-07-12)
