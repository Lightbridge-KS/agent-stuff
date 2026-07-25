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
  Non-goals exception, See-also; multi-machine-sync relocate note) + this tracker
- [ ] `lightbridge.py`: module-level helpers — `set_root`, `rename_registry_paths`,
  `plan_mv`, `cmd_mv` (injectable `ask`, `--yes`/`--dry-run`/`--json`)
- [ ] `lightbridge.py`: Typer wiring for `mv` in `main()`; `--yes` help text carries the
  agent warning
- [ ] `lightbridge.py`: doctor `stale`/`key-mismatch` messages teach `lb mv`
- [ ] Tests: `MvCliTest` + helper tests (mode matrix, guard, prefix, collisions,
  idempotence, style-preserving rewrites)
- [ ] Skill/catalog sync: SKILL.md verb line + "Moving or renaming a repo" section +
  version bump; catalog.md verb list + moved-repo trade-off text
- [ ] Gates: `bin/validate.py` + all suites green
- [ ] E2E smoke in scratch dirs (move, parent-prefix move, idempotent re-run)
- [ ] Draft PR opened

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
