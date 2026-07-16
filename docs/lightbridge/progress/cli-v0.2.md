---
summary: Progress tracker for the lightbridge CLI v0.2 build — status/show/enable/disable/repos
  verbs, positional init, CI gap fix, and docs sync. Milestones with commit SHAs, plus the
  cross-repo follow-up.
read_when:
  - resuming or continuing the lightbridge CLI v0.2 work
  - checking what v0.2 shipped vs deferred before changing the lightbridge CLI
---

# lightbridge CLI v0.2 — progress

Design (the spec): [`../lightbridge-cli-design.md`](../lightbridge-cli-design.md) — settled
2026-07-16, all five decisions resolved. Branch: `feat/lightbridge-cli-v0.2`.

## Milestones

- [x] Design doc settled (`docs/lightbridge/lightbridge-cli-design.md`)
- [x] `lightbridge.py`: `init` → positional sections (drop `--sections`) — `1bdbeaf`
- [x] `lightbridge.py`: section block line-edit helper (slice / set-enabled) — `1bdbeaf`
- [x] `lightbridge.py`: `show [SECTION]` — `1bdbeaf`
- [x] `lightbridge.py`: `enable` / `disable SECTION` — `1bdbeaf`
- [x] `lightbridge.py`: `status` (dashboard; counts + owning-tool pointers) — `1bdbeaf`
- [x] `lightbridge.py`: `repos list|add|rm` — `1bdbeaf`
- [x] `lightbridge.py`: help epilog (siblings + skill) · `__version__ = "0.2.0"` — `1bdbeaf`
- [x] Tests: migrate `--sections` tests; Show/Toggle/Status/Repos CLI classes (45 total) — `1bdbeaf`
- [x] CI: add `test_lightbridge.py` + `test_handoff_hook.py` to `validate.yml` — `542eb51`
- [x] Docs sync: `scripts/lightbridge/README.md`, `SKILL.md` (+version), `catalog.md`
- [x] Gates: `bin/validate.py` + full `just test` green (8 suites, 169 tests, 2026-07-16)
- [x] E2E verification (throwaway `LIGHTBRIDGE_STATE_DIR` flow + read-only `status` on the real tree)
- [x] Draft PR opened — [#4](https://github.com/Lightbridge-KS/agent-stuff/pull/4)

## Confirmed contracts

- Module API frozen for importers: `project_key`, `repo_root`, `config_path`,
  `load_config` (3-tuple), `legacy_config`, `STATE_DIR_ENV`, `SECTIONS`.
- Exit taxonomy unchanged: 0 ok (incl. idempotent no-op) · 1 refused/problem · 2 usage.
- `enable/disable` and `repos add/rm` are line edits — comments/layout survive, never a
  TOML rewrite.
- `status` never imports sibling tools — glob counts + pointer only.
- `show` injects no defaults (defaults live with readers + catalog).

## Deferred (out of v0.2)

- `doctor --fix` and `stale` vs `not-on-this-machine` — owned by
  [multi-machine sync](../multi-machine-sync.md).
- `lb sync` / `lb relocate` — same.

## Follow-up after merge

- [ ] `agent-instruction/AGENTS.qmd:116` — update CLI verb list to v0.2 set; `make build`.
