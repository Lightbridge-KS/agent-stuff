---
summary: Progress tracker for the lightbridge CLI v0.3 build — the argparse → Typer
  migration. Same 9-verb surface, plain click help, shell completion, stdlib-pure module
  import preserved for importers. Milestones with commit SHAs.
read_when:
  - resuming or continuing the lightbridge CLI Typer migration
  - checking why the CLI layer is built inside main() before touching it
---

# lightbridge CLI v0.3 — progress

Design (the spec): [`../lightbridge-cli-design.md`](../lightbridge-cli-design.md) —
v0.2 surface unchanged; v0.3 swaps the wiring layer argparse → Typer. Decisions settled
2026-07-17 (KS): plain click help (`rich_markup_mode=None`), shell completion ON.
Branch: `refactoring/lb-typer`.

## Milestones

- [x] Tracker created (this file)
- [x] `lightbridge.py`: CLI layer migrated to Typer inside `main()`; `parse_args` deleted;
  handlers take typed params; `path`/`doctor` bodies become `cmd_path`/`cmd_doctor` — `35e9d4c`
- [x] `lightbridge.py`: PEP 723 deps → `["typer>=0.27"]` · `__version__ = "0.3.0"` — `35e9d4c`
- [x] Sections as a `SectionName` enum on `init`/`add`/`enable`/`disable` — 3.11 argparse
  workaround in `cmd_init` deleted; one shape for all four verbs — `35e9d4c`
- [x] Tests: two new contract tests (bare `lb` → exit 2; `--help` has no rich box chars);
  existing suite green — `35e9d4c`
- [x] Gates: `bin/validate.py` + all 8 suites green (171 tests, 2026-07-17)
- [x] Behavioral diff sweep: 37 cases vs the v0.2 baseline — zero exit-code diffs; only
  parser-generated text (help pages, version, usage errors) differs
- [x] Docs sync: design doc §6-P4 / §8-5 wording, Non-goals note on rich help;
  README/skill grepped for drift — none
- [x] Draft PR opened — [#5](https://github.com/Lightbridge-KS/agent-stuff/pull/5)

## Confirmed contracts

- **Module import stays stdlib-pure.** `import typer` lives inside `main()` only:
  `handoff.py`, `plan_store.py`, `repo_links.py`, and hooks `exec_module` this file in
  their own `dependencies = []` envs — a top-level typer import crashes all of them.
  The PEP 723 block is inert under importlib, so declaring typer there is safe.
- Module API frozen for importers (unchanged from v0.2): `project_key`, `repo_root`,
  `config_path`, `load_config` (3-tuple), `legacy_config`, `STATE_DIR_ENV`, `SECTIONS`.
- Surface frozen: verbs, flag spellings (`--start/--json/--registry/--state-dir/--dry-run`),
  epilog text, all application-level messages, exit taxonomy 0/1/2, bare `lb` → 2.
- Help output is plain click (`rich_markup_mode=None`) — no box-drawing/padding when
  piped; locked by a test.
- Verified on typer 0.27.0: usage errors (bare, unknown command, missing arg,
  bad choice) all exit 2.
- **Typer ≥0.27 is click-free** — no `click.Choice`; section choices are the
  `SectionName` enum (module-level, stdlib), mirrored against `SECTIONS` by an
  import-time assert. Don't reintroduce a click import.

## Deferred (out of v0.3)

- Unchanged from v0.2: `doctor --fix`, `lb sync`/`relocate` — owned by
  [multi-machine sync](../multi-machine-sync.md).
- Dynamic section-name completion beyond `click.Choice` (custom completers) — not needed.
