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

- [x] ADR `0001-modular-lightbridge.md` + this tracker + `lightbridge-cli-design.md`
  multi-module note — `10b9a8c`
- [x] 78-case behavioral baseline captured at `18891f0` (every verb × `--json`/human ×
  refusal paths, `--help` for root + all 11 verbs + 3 `repos` subcommands, doctor's 4
  problem kinds, the `mv` apply path with resulting tree/config/registry)
- [x] `lb_resolve.py` — resolution, `toml_str`, `use_utf8_console`, consts
- [x] `lb_tomledit.py` — the scattered TOML line-surgery engine, gathered
- [x] `lb_catalog.py` + `lb_registry.py`
- [x] `lb_doctor.py` + `lb_mv.py` (incl. `apply_mv` extracted from `cmd_mv`)
- [x] `lb_commands.py` (incl. the deduped `{root, key, config}` JSON preamble)
- [x] `lightbridge.py` trimmed to Typer wiring + `main()` — split landed as `e145759`
- [x] 6 consumers migrated to `lb_resolve.py`
- [x] Tests: per-consumer loading strategy + 2 new invariant guards
- [x] Doc/skill sync + `__version__` → 0.5.0
- [x] Gates: `bin/validate.py` + all suites green
- [x] Behavioral diff sweep vs `18891f0` — zero diffs except `--version`
- [x] Hooks fired by hand + `lb` through the PATH symlink + `lb mv` E2E smoke
- [x] Draft PR opened — [#16](https://github.com/Lightbridge-KS/agent-stuff/pull/16)

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
  *Since v0.6 (#18) `load_registry` joined it* — see [ADR 0001](../adr/0001-modular-lightbridge.md) point 3.
- **`import typer` stays inside `main()`** — now in `lightbridge.py`, for the same reason.
- Surface frozen: verbs, flag spellings, epilog, every application-level message, exit
  taxonomy 0/1/2, JSON shapes, plain click help, bare `lb` → 2.
- CLI-side module filenames keep the `lb_` prefix — they become real `sys.modules` keys in a
  repo that path-loads modules under generic names.

## Deferred (out of v0.5)

- **[#17](https://github.com/Lightbridge-KS/agent-stuff/issues/17)** — `mv`'s idempotent
  re-run does not cover a parent-dir move. Re-running `mv PARENT_OLD PARENT_NEW` after it
  succeeded exits 1 with "nothing in lightbridge references PARENT_OLD" instead of the
  clean no-op. Cause: the verified-noop check in `plan_mv` looks for
  `state_dir/project_key(new)/config.toml`, but a parent dir has no config of its own —
  the configs belong to the repos *beneath* it. **Pre-existing: reproduced identically
  against v0.4 (`18891f0`) in a worktree**, so it is not a regression from this refactor,
  and fixing it is a behavior change. The [`mv` design](../lightbridge-mv.md) advertises a
  verifiable idempotent re-run; for prefix moves it does not hold.
- ~~**[#18](https://github.com/Lightbridge-KS/agent-stuff/issues/18)** — two registry
  readers.~~ **Done in v0.6:** one `load_registry` in `lb_resolve.py`. The two semantic
  differences were not what the issue said — the value-filtering one was not real
  (`resolve_links` already guarded), and the missing-`[repos]` one was a deliberate,
  tested diagnostic that the issue would have deleted. The shared reader distinguishes a
  table-less-but-empty registry (benign `{}`) from one with **misplaced root-level keys**
  (an error naming them and the fix), which is the discriminator neither reader had.
- Unchanged from v0.4: `doctor --fix`; `lb relocate` / multi-machine re-keying, owned by
  [multi-machine sync](../multi-machine-sync.md).
