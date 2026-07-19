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

Extract the proven v0.2 server and skill into a canonical dual-harness plugin and implement
portable fail-closed roots for plugin mode.

## Next

Install from the repo-local Codex marketplace, run live acceptance in a new task, and only
then remove direct MCP registration.

## Milestones

- [x] Phase-3 design, ADR, and successor tracker landed before implementation — commit: pending
- [ ] Canonical `plugins/notebook-tools` bundle and source migration — commit: pending
- [ ] Codex and Claude manifests plus repo marketplace entries — commit: pending
- [ ] Static/client/config root resolver and user roots CLI — commit: pending
- [ ] Repository plugin validation and focused tests — commit: pending
- [ ] Installed-plugin discovery, root denial, and notebook live acceptance — commit: pending
- [ ] Direct MCP registration removed after successful cutover — commit: pending
- [ ] Full dry gates and final tracker reconciliation — commit: pending

## Confirmed contracts

- Target version is `0.3.0`, owned by `.codex-plugin/plugin.json`.
- The standalone plugin is canonical and dual-harness; maintained copies are forbidden.
- Repo-local Codex marketplace name is `lightbridge-tools`.
- Static roots remain authoritative in direct mode.
- Plugin roots prefer MCP client roots, then explicit user config, then fail closed.
- Public Plugin Directory submission, apps, hooks, and visual assets are deferred.

## Deferred

- Public directory submission and workspace publication review.
- Bundled runtime dependencies or kernel installation.
- Stateful kernels, rendering, rich image return, and conversion workflows.

## Open questions attached to scheduled work

- Does the current Codex desktop plugin runtime expose usable MCP roots for the active
  workspace?
- Does the installed plugin runtime resolve `uv` from its inherited `PATH`?
- Do write-tool annotations preserve the proven `writes` approval behavior without a
  direct `config.toml` server block?
