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

- [x] **Tracker** — this file — `593799c`
- [x] **`scripts/lightbridge/` tool** — canonical resolver (git-toplevel → project-key →
      `~/.lightbridge/projects/<key>/config.toml`) + `path` / `doctor` CLI — `20c040c`
- [x] **Readers refactored** — docs-index-inject, repo-links (+hook), handoff keyed on
      git-toplevel; per-repo walk-up deleted; legacy per-repo file → one-line warning — `5223495`
- [x] **Tests** — test_hooks.py reworked to `LIGHTBRIDGE_STATE_DIR` fixtures; test_repo_links.py
      config into fake home; new test_lightbridge.py; handoff subdir-keying test — `5223495`
- [x] **Docs sweep (agent-stuff)** — lightbridge-config skill (SKILL/catalog/extending/assets),
      research + handoff SKILL.md, 5 hook/script READMEs, README.md, docs/architecture.md,
      research design.md, plugin description strings — `46a95eb`
- [x] **Brief sync (`agent-instruction`)** — AGENTS.qmd §Personal config rewritten, `make build`,
      committed on main — `b3603d9` (agent-instruction)
- [x] **Data migration** — **14** configs (not 10: `--no-ignore` sweep also found
      ramaai-api-specs, RAMAAI-QMS-RD-Retrofit, and two `_tests` fixtures) moved to
      `~/.lightbridge/projects/<key>/config.toml` with `root =`; per-repo `.lightbridge/`
      deleted everywhere; `doctor` clean. Chore commits: RMOS `faffb04` (develop),
      RMOS-InHouse `12f3348` (**main** — repo has no develop branch; deviation from D5
      surfaced to KS), orthanc-test-pacs `c78f50f` (main), RAMAAI-QMS-RD-Retrofit
      `3b3f522` (main; also tracked, not in the original plan)
- [x] **Verified** (2026-07-12) — validate.py + all 7 suites green; live smoke tests:
      docs-index @ agent-stuff injects from home config (tracker listed), repo-links @
      RMOS-InHouse resolves all 4 links, handoff `--journal` from a subdir lands on the
      repo-root key; `lightbridge doctor` → no problems

## Now / Next

- Work complete 2026-07-12; tracker retained as the record of the migration and its contracts.
- Open follow-up: `_tests` fixture READMEs may still describe per-repo opt-in (see Notes).

## Notes

- `RAMAAI-WorkSpace/RAMAAI-QMS-RD-Retrofit` is a symlink into `~/my_ramaai/QMS/`; the
  resolver keys by the physical git toplevel, so both entry paths land on one key.
- The two `_tests` fixtures (docs-index-demo, deep-research-test) were migrated too; their
  READMEs may still describe the old per-repo opt-in — follow-up if they are re-run.

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
