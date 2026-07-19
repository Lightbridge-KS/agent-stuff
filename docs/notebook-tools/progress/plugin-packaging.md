---
summary: Phase-3 progress tracker for canonical notebook-tools plugin packaging, dynamic roots, marketplace installation, and direct-MCP cutover.
read_when:
  - implementing or resuming notebook-tools native plugin packaging
  - checking packaging, root-resolution, installation, or cutover status
---

# Notebook Tools — Plugin Packaging Progress

Design: [`../design/plugin-packaging.md`](../design/plugin-packaging.md)
ADR: [`../adr/0001-dynamic-plugin-roots.md`](../adr/0001-dynamic-plugin-roots.md)
Predecessor: [`mvp.md`](mvp.md)

## Now

Phase-3 functional acceptance is complete through the installed marketplace plugin. Codex
desktop currently uses the explicit one-project config fallback because it supplies no MCP
client roots.

## Next

Confirm write-approval prompts in a normal interactive task whose runtime policy permits
approvals; delegated acceptance could verify annotations and behavior but not display UI.

## Milestones

- [x] Phase-3 design, ADR, and successor tracker landed before implementation — commit: `ed9d54d`
- [x] Canonical `plugins/notebook-tools` bundle and source migration — commit: `b894e00`
- [x] Codex and Claude manifests plus repo marketplace entries — commit: `b894e00`
- [x] Static/client/config root resolver and user roots CLI — commit: `b894e00`
- [x] Repository plugin validation and focused tests — commit: `b894e00`
- [x] Installed-plugin discovery, root denial, and notebook live acceptance — runtime: `2026-07-19`
- [x] Direct MCP registration removed after successful cutover — runtime: `2026-07-19`
- [x] Full dry gates and final tracker reconciliation — commit: `b4ed849`

## Confirmed contracts

- Target version is `0.3.0`, owned by `.codex-plugin/plugin.json`.
- The standalone plugin is canonical and dual-harness; maintained copies are forbidden.
- Repo-local Codex marketplace name is `lightbridge-tools`.
- Static roots remain authoritative in direct mode.
- Plugin roots prefer MCP client roots, then explicit user config, then fail closed.
- Public Plugin Directory submission, apps, hooks, and visual assets are deferred.
- Codex desktop `0.144.4` does not provide usable MCP client roots for this local plugin;
  the explicit fallback contains only `/Users/kittipos/my_config`.
- A disabled direct MCP entry with the same `notebook-tools` name still shadows the plugin
  server. The direct entry must be removed—not merely disabled—after cutover.

## Acceptance evidence

- Python 3.11 focused suite: 18 notebook/root tests and 4 packaging tests pass.
- Repository validator and the official plugin validator accept the bundle.
- Ruff check, Ruff format check, and `git diff --check` pass for the implementation milestone.
- Repo marketplace `lightbridge-tools` installed `notebook-tools` version `0.3.0`; a fresh
  task discovered the packaged skill and all four MCP tools.
- Client-root resolution failed closed with `ROOT_CONFIGURATION_REQUIRED`; the packaged
  roots CLI then configured exactly `/Users/kittipos/my_config` with mode `0600`.
- Live workflow passed through `root_source=config`, `root_count=1`: create, read, guarded
  dry-run/commit, reread, in-memory execution, guarded write-back, and final reread.
- Final notebook revision: `ed70be3cb3e4c1a89ba3870375298a5f8802e6831ef3cea45aa0978b9cb0f383`;
  standard validation reports nbformat 4.5, four cells, execution counts `[1, 2, 3]`,
  and persisted stdout `FINAL_RESULT=41`.
- `/Users/kittipos/_notebook_tools_plugin_outside.ipynb` returned
  `OUTSIDE_ALLOWED_ROOT`, listed only `/Users/kittipos/my_config`, and was removed.
- Reads were prompt-free. Write annotations remain correct in discovery tests, but the
  delegated runtime displayed no approval UI for either direct or plugin calls, so the
  interactive prompt itself remains unobserved rather than proven failed.
- Final `just test` passes 193 tests; Python 3.11 focused tests, both validators, Ruff,
  format, whitespace, and standard nbformat validation also pass.

## Deferred

- Public directory submission and workspace publication review.
- Bundled runtime dependencies or kernel installation.
- Stateful kernels, rendering, rich image return, and conversion workflows.

## Open questions attached to scheduled work

- Do write-tool annotations surface the expected approval UI in a normal interactive task
  whose runtime approval policy permits prompting?
