---
summary: Decision to split scripts/lightbridge into eight flat sibling modules with a single
  path-loaded read-path module, after verifying that `uv run --script` puts the
  symlink-resolved script directory on sys.path[0]. Narrows the frozen importer API to
  resolution only and makes lightbridge.py a non-importable entrypoint.
read_when:
  - adding a module to scripts/lightbridge/ or deciding where a new lightbridge function belongs
  - changing how a hook or sibling script imports lightbridge's resolver
  - reintroducing a top-level non-stdlib import or a sibling import into the path-loaded module
  - wondering why the CLI entrypoint may not be imported
---

# ADR 0001 — Modular `scripts/lightbridge`

## Status

Accepted 2026-07-25. Supersedes the single-file layout that v0.1–v0.4 grew.

## Context

`scripts/lightbridge/lightbridge.py` reached **1504 lines** at v0.4. 826 of them (55%) are
CLI — `cmd_*` handlers plus Typer wiring — that no importer needs. Two seams had gone wrong:

- The **TOML line-edit engine** was scattered across three unrelated banners: `toml_str`,
  `section_span`/`set_enabled`, `append_repo`/`remove_repo`, `set_root`/
  `rename_registry_paths`. One idea with one invariant — *untouched lines stay
  byte-identical* — filed in three places.
- **`plan_mv` was pure planning with no `apply_mv`.** The apply half sat inline in `cmd_mv`,
  interleaved with the TTY guard and printing, leaving the plan/apply design half-realized
  and the filesystem mutation untestable without a TTY.

The blocker on splitting was believed to be the load protocol: six consumers
(`scripts/handoff/handoff.py`, `scripts/plan-store/plan_store.py`,
`scripts/repo-links/repo_links.py`, and hooks `plan-gate`, `docs-index-inject`,
`repo-links-inject`) load the file **by path** via `importlib` `exec_module`, inside their own
`dependencies = []` PEP 723 environments. Relative imports fail under `exec_module`, and the
module must stay stdlib-pure — which is why `import typer` lives inside `main()`.

That blocker was measured rather than assumed. `uv run --script` puts the
**symlink-resolved** script directory on `sys.path[0]` — verified both by direct invocation
and through the `~/.local/bin/lb` symlink. So a sibling `import` works from the entrypoint.

The constraint is therefore much narrower than it looked:

> Exactly **one** file must be `exec_module`-safe — the one consumers path-load. It must be
> stdlib-pure *and* import no siblings. Every other file in the folder is reachable by plain
> `import` from the entrypoint.

The six consumers use only the **read path**: resolution, plus `toml_str` and
`use_utf8_console`. Every writer — render, append, `set_enabled`, `set_root`, registry
mutation, `doctor`, `mv` — is CLI-only.

## Decision

Split into **eight flat sibling modules**, drawing the boundary at *the library is the read
path; the CLI owns the write path*:

```
lb_resolve.py   [PATH-LOADED] resolution, toml_str, use_utf8_console, consts
lb_catalog.py   SECTIONS, CONFIG_HEADER, SectionName, describe,
                detect/present_sections, render_config, append_sections
lb_tomledit.py  generic TOML line surgery
lb_registry.py  repos.toml document
lb_doctor.py    tree audit
lb_mv.py        plan_mv + apply_mv
lb_commands.py  cmd_* handlers
lightbridge.py  typer wiring + main()   (entrypoint: shebang + PEP 723 stay here)

lb_resolve ← lb_tomledit ← {lb_catalog, lb_registry} ← {lb_doctor, lb_mv}
                                  ↓
                           lb_commands ← lightbridge.py
     ↑
6 consumers (exec_module — same protocol, new filename)
```

Binding consequences of that shape:

1. **`lb_resolve.py` is the only path-loaded module.** It imports stdlib only and no
   siblings. Both properties are locked by a test that AST-walks its top-level imports —
   this is the invariant the whole layout rests on.
2. **`lightbridge.py` is not importable.** It is the entrypoint and nothing else. A test
   asserts no file under `hooks/` or `scripts/` path-loads it.
3. **The frozen importer API narrows to resolution only:** `project_key`, `repo_root`,
   `config_path`, `load_config` (3-tuple), `legacy_config`, `legacy_warning`,
   `default_state_dir`, `DEFAULT_STATE_DIR`, `STATE_DIR_ENV`, `toml_str`,
   `use_utf8_console`. This amends v0.3's Confirmed contracts, which also listed
   `SECTIONS` — verified that no hook or script imports it; only
   `tests/test_lightbridge.py` did. Keeping catalog data in the path-loaded module would
   have forced a vaguer name and left the catalog-driven config assembly homeless.
4. **The `lb_` filename prefix is load-bearing.** CLI-side modules are reached by plain
   `import`, so their filenames become real `sys.modules` keys — and this repo path-loads
   modules under generic names throughout (`"lightbridge"`, `"repo_links"`,
   `"docs_index"`). A bare `mv.py` or `registry.py` would be a collision waiting to happen.
5. **The surface does not move.** Verbs, flag spellings, epilog, every application-level
   message, exit taxonomy 0/1/2, JSON shapes, and plain click help all carry over from
   v0.2/v0.3/v0.4 unchanged. Locked by a 78-case behavioral diff sweep against `18891f0`.

Two deepenings the split made obvious ship with it: `apply_mv` extracted out of `cmd_mv`,
and the `{root, key, config}` JSON preamble — duplicated across `bootstrap_json`,
`cmd_toggle`, `cmd_status`, `cmd_path` — reduced to one helper function (a function, not a
Presenter class).

## Consequences

- Each module's name is true, so where a new function belongs is answerable without reading
  the file. The scattered TOML engine becomes one deep module with one stated invariant.
- The six consumers change one constant each (`lightbridge.py` → `lb_resolve.py`) and load
  ~180 lines instead of 1504.
- Adding a section, a verb, or a repair now touches one or two named modules, not a
  1500-line file — the growth that produced this ADR is no longer concentrated.
- Two new failure modes exist and are therefore tested, not documented-and-hoped: a
  non-stdlib or sibling import creeping into `lb_resolve.py`, and a consumer path-loading
  the entrypoint again.
- The cutover is hard, in one PR, with no re-export bridge: a bridge would keep
  `lightbridge.py` importable, which is exactly the invariant being established. All six
  consumers live in this repo; there is no external consumer.
- `apply_mv` is now testable without a TTY, which is what made the v0.4 guard awkward to
  cover.

## Rejected alternatives

- **Single file, better banners.** Zero risk and zero migration, but the seams stay
  invisible and every subsequent version concentrates in the same file. At 55% CLI the
  single file was buying only the load protocol — and the protocol turned out to need one
  *small* file, not one big one.
- **Two files (core + cli).** Gets the library boundary for six one-line edits, but leaves
  the CLI half at ~950 lines — the largest chunk barely improved.
- **Package with an `__init__.py` façade.** Relative imports under `exec_module` need a
  `sys.modules` pre-registration dance before `exec_module` runs, adding a fragile step to
  every consumer; and `scripts/lightbridge/` already owns the name, so the package would
  collide with its own directory. Flat sibling modules get the same decomposition with none
  of it.
- **Keeping `SECTIONS` in the path-loaded module** to preserve v0.3's contract verbatim.
  Rejected: the contract exists to protect real importers, and no importer used it.
  Honouring it literally would have cost the core module its honest name and left
  `render_config`/`append_sections`/`detect_sections`/`present_sections` in the handler
  module as a grab-bag.

## See also

- [CLI surface & AX design](../lightbridge-cli-design.md) — the frozen surface this refactor
  preserves.
- [`lb mv` design](../lightbridge-mv.md) — the spec `lb_mv.py` implements.
- [v0.5 progress tracker](../progress/cli-v0.5.md) — milestones for this change.
- [v0.3 progress tracker](../progress/cli-v0.3.md) — the Confirmed contracts this ADR
  amends (point 3).
