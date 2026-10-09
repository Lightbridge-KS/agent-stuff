---
summary: Progress tracker for install profiles v1 — `profiles.toml` at a content-tree root selects which skills each target registry receives; `bin/install.py` reconciles (link / `--force` relink / `--prune`) bounded by ownership and audits read-only with `--check`; validator, fleet apply, and skill-health wired. Milestones with SHAs; Deferred (skill-side veto, private-tree profile); Confirmed contracts.
read_when:
  - changing profiles.toml, its loader, or the selection / ownership / prune / check logic in bin/install.py
  - adding a target to bin/targets.toml and deciding what it should receive
  - a registry audit (`install.py --check`, skill-health) reports stray / missing / foreign entries
  - deciding whether a per-skill or per-machine profile override is in or out
---

# Install profiles v1 — progress

Design: [`../../architecture.md`](../../architecture.md) § *Profiles and reconcile*.
Approved plan 2026-10-10 (KS): profile at the content-tree root, `~/.agents/skills` for
non-coding agents, prune explicit.

## Milestones

- [x] `profiles.toml` + loader (`load_profiles`, shared by installer and validator), per-target selection, explicit-name bypass with notice, `--domain` within profile
- [x] Ownership-bounded `--prune` (symlink realpath under `<root>/plugins/`; copy mode: catalog name + frontmatter match) and read-only `--check` (missing / stray / broken / foreign; exit 0/1)
- [x] `--list` profile matrix
- [x] Validator: unknown target, mixed `like`, cycle, dead pattern — both full and `--root` content mode
- [x] Tests: `tests/test_install.py` `ProfileTest` (11), `tests/test_validate.py` profile cases (5)
- [x] Docs: architecture § Profiles, AGENTS.md tooling, README, fleet seed block, fleet-sync skill, skill-health checks
- [x] Hub machine converged 2026-10-10: `install.py --all --force --prune` pruned 4 dangling links and the coding set from the shared registry; `--check` exit 0; `skill-vendor doctor` unchanged
- [ ] Hub `~/.lightbridge/fleet.toml` apply/verify updated; nodes synced

(All of the above land in the v1 PR — SHA recorded on merge.)

## Now / Next

- Now: v1 PR open on `feat/install-profiles`.
- Next: after merge, update the hub fleet file (`apply … --prune`, `verify … && install.py --check`) and offer `lb fleet sync` per node.

## Deferred

- **Skill-side veto** (`metadata.targets` in SKILL.md frontmatter) for skills that are intrinsically harness-bound. Rejected for v1: the common decision is consumer-side and domain-wide, which is one line in `profiles.toml`.
- **Per-machine overrides** in `~/.lightbridge`. The variance observed is per harness, not per machine; `--all` presence detection already covers "which harnesses exist here".
- **Private tree profile** (`agent-stuff-private/profiles.toml`): its own repo, own PR. Known drift there: the artifact template is Codex-only today.
- **Islands**: `--target DIR` is anonymous, so profiles do not apply; `--domain <island>` is already an explicit selection.
- **Adopted shelf** (`~/.agents/skills` real dirs): out of scope; governed by the skill-taxonomy drain obligation.

## Confirmed contracts

- Absent file, or absent block, means `include = ["*"]`: a tree without a profile installs everything everywhere, as before.
- Exclude beats include; `like` copies a resolved block and cannot be mixed with include/exclude; a dead pattern is an error in installer and validator alike.
- Explicit skill tokens bypass the profile (notice on stderr); `--domain` is filtered by it (notice per excluded key).
- Ownership: symlink with realpath under `<root>/plugins/` (dangling included), or in copy mode a catalog-named real entry whose frontmatter `name` matches. Foreign entries are never pruned or reported.
- `--check` is read-only and exclusive with `--prune`, `--force`, and skill names; with no agent flag it audits every present target. Exit 0 clean, 1 diverged. Finding lines: `<target> <kind> <key-or-name>`.
- `--force` still replaces any existing entry regardless of ownership (unchanged behavior); prune is the only ownership-gated removal.
- Two trees reconcile one registry safely: each prunes only its own `plugins/`.
