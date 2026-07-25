---
summary: Progress tracker for the lightbridge CLI v0.4 build — the `lb mv OLD NEW`
  move/rename repair verb. Design doc + tracker first, then implementation, tests,
  and skill/catalog sync. Milestones with commit SHAs.
read_when:
  - resuming or continuing the `lb mv` build
  - checking what CLI v0.4 shipped vs deferred before changing `lb mv`
---

# lightbridge CLI v0.4 — progress

Design (the spec): [`../lightbridge-mv.md`](../lightbridge-mv.md) — one new verb,
`lb mv OLD NEW`, settled 2026-07-25 (KS, grilling session): move + repair modes, uniform
prefix semantics, TTY confirm + `--yes` guard (first exception to the no-TTY non-goal),
merge-state/error-on-config collisions, surgical line-edit rewrites, verified-idempotent
re-run. Branch: `feat/lb-mv`.

## Milestones

- [x] Design doc `lightbridge-mv.md` + amendments (cli-design cheat sheet, §8-4 note,
  Non-goals exception, See-also; multi-machine-sync relocate note) + this tracker — `2baef19`
- [x] `lightbridge.py`: module-level helpers — `set_root`, `rename_registry_paths`,
  `plan_mv`, `cmd_mv` (injectable `ask`, `--yes`/`--dry-run`/`--json`) — `ab4975e`
- [x] `lightbridge.py`: Typer wiring for `mv` in `main()`; `--yes` help text carries the
  agent warning — `ab4975e`
- [x] `lightbridge.py`: doctor `stale` message teaches `mv`. (Deviation from plan:
  `key-mismatch` keeps its message — `mv` matches on `root`, which is *correct* in a
  key-mismatch, so `mv` cannot repair that rot; only `stale` names it.) — `ab4975e`
- [x] Tests: `MvHelperTest` + `MvCliTest` (20 tests: mode matrix, guard, prefix,
  collisions, idempotence, style-preserving rewrites). The case-rename test caught a
  real bug — on case-insensitive APFS the *state-dir* re-key is itself case-only and
  read as a config collision; fixed with a samefile guard in plan + execute — `ab4975e`
- [x] Skill/catalog sync: SKILL.md verb line + "Moving or renaming a repo" section +
  version bump; catalog.md verb list + moved-repo trade-off text; tool README;
  AGENTS.qmd brief (agent-instruction `c0d0fdb`) — `e7444b1`
- [x] Gates: `bin/validate.py` + all 10 suites green (213 tests, 2026-07-25)
- [x] E2E smoke in scratch dirs: single move (dry-run → non-TTY refusal → --yes →
  doctor clean → idempotent re-run exit 0) and parent-prefix move re-keying 2 projects +
  2 registry entries; `/var` vs `/private/var` symlink spellings matched via resolve
- [x] Draft PR opened — [#15](https://github.com/Lightbridge-KS/agent-stuff/pull/15)

## Confirmed contracts

- Unchanged from v0.3: stdlib-pure module import (`import typer` inside `main()` only);
  module API frozen for importers; exit taxonomy 0/1/2; plain click help.
- Rewrites are targeted line edits — comments, ordering, and `~`-style spellings survive
  (same temperament as `enable`/`disable` and `repos add/rm`).
- `mv` matching normalizes via `expanduser().resolve()`; `repos.toml` values themselves
  stay stored-as-typed.
- `mv` never writes outside `~/.lightbridge` except the requested filesystem move itself;
  other harnesses' path-keyed state (`~/.claude/projects/<key>`) is reported, never touched.

## Deferred (out of v0.4)

- `lb relocate` / multi-machine re-keying — owned by
  [multi-machine sync](../multi-machine-sync.md); becomes sugar over `mv` internals.
- `doctor --fix` — doctor teaches `lb mv` instead.
- A `--claude` migration flag for `~/.claude/projects` state — only if note-only ever bites.
