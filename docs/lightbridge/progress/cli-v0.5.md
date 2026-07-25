---
summary: Progress tracker for the lightbridge CLI v0.5 build — splitting the 1504-line
  lightbridge.py into eight flat sibling modules with one path-loaded read-path module.
  No surface change; locked by a 78-case behavioral diff sweep. Milestones with commit SHAs.
read_when:
  - resuming or continuing the lightbridge modularization
  - deciding which module a new lightbridge function belongs in
  - checking what CLI v0.5 shipped vs deferred before changing scripts/lightbridge
---

# lightbridge CLI v0.5 — progress

Design (the decision): [`../adr/0001-modular-lightbridge.md`](../adr/0001-modular-lightbridge.md)
— accepted 2026-07-25 (KS). Eight flat sibling modules; `lb_resolve.py` is the only
path-loaded one; `lightbridge.py` becomes a non-importable entrypoint; the frozen importer
API narrows to resolution only. Surface unchanged. Branch: `refactor/lightbridge-modular`.

The unlock: `uv run --script` puts the **symlink-resolved** script directory on
`sys.path[0]` (verified directly and through the `~/.local/bin/lb` symlink), so only *one*
file must be `exec_module`-safe — not the whole tool.

## Milestones

- [ ] ADR `0001-modular-lightbridge.md` + this tracker + `lightbridge-cli-design.md`
  multi-module note
- [ ] 78-case behavioral baseline captured at `18891f0` (every verb × `--json`/human ×
  refusal paths, `--help` for root + all 11 verbs + 3 `repos` subcommands, doctor's 4
  problem kinds, the `mv` apply path with resulting tree/config/registry)
- [ ] `lb_resolve.py` — resolution, `toml_str`, `use_utf8_console`, consts
- [ ] `lb_tomledit.py` — the scattered TOML line-surgery engine, gathered
- [ ] `lb_catalog.py` + `lb_registry.py`
- [ ] `lb_doctor.py` + `lb_mv.py` (incl. `apply_mv` extracted from `cmd_mv`)
- [ ] `lb_commands.py` (incl. the deduped `{root, key, config}` JSON preamble)
- [ ] `lightbridge.py` trimmed to Typer wiring + `main()`
- [ ] 6 consumers migrated to `lb_resolve.py`
- [ ] Tests: per-consumer loading strategy + 2 new invariant guards
- [ ] Doc/skill sync + `__version__` → 0.5.0
- [ ] Gates: `bin/validate.py` + all suites green
- [ ] Behavioral diff sweep vs `18891f0` — zero diffs except `--version`
- [ ] Hooks fired by hand + `lb` through the PATH symlink + `lb mv` E2E smoke
- [ ] Draft PR opened

## Confirmed contracts

Carried over from v0.4 unless noted:

- **Exactly one path-loaded module.** `lb_resolve.py` imports stdlib only and no siblings;
  locked by an AST-walk test. This is the invariant the layout rests on.
- **`lightbridge.py` is not importable** — entrypoint only; locked by a test asserting no
  file under `hooks/` or `scripts/` path-loads it.
- **Importer API narrows to resolution only** (amends v0.3): `project_key`, `repo_root`,
  `config_path`, `load_config` (3-tuple), `legacy_config`, `legacy_warning`,
  `default_state_dir`, `DEFAULT_STATE_DIR`, `STATE_DIR_ENV`, `toml_str`,
  `use_utf8_console`. `SECTIONS` leaves the importer API — nothing imported it.
- **`import typer` stays inside `main()`** — now in `lightbridge.py`, for the same reason.
- Surface frozen: verbs, flag spellings, epilog, every application-level message, exit
  taxonomy 0/1/2, JSON shapes, plain click help, bare `lb` → 2.
- CLI-side module filenames keep the `lb_` prefix — they become real `sys.modules` keys in a
  repo that path-loads modules under generic names.

## Deferred (out of v0.5)

- `scripts/repo-links/repo_links.py` keeps its own `load_registry`, whose semantics differ
  from `lb_registry`'s (errors on a missing `[repos]` table; no non-string filtering).
  Reconciling them changes `repo-links-inject` behavior, so it is out of scope for a
  no-behavior-change refactor. Worth a follow-up: two registry readers is exactly the
  duplication the one-implementation rule forbids.
- Unchanged from v0.4: `doctor --fix`; `lb relocate` / multi-machine re-keying, owned by
  [multi-machine sync](../multi-machine-sync.md).
