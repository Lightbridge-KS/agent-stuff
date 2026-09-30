---
summary: >-
  Progress tracker for the lb fleet build: hub-and-spoke sync of agent-instruction /
  agent-stuff / agent-stuff-private from this Mac (the only initiator) to node devices —
  GitHub as the source of truth, nodes pull --ff-only and reinstall themselves, dirty
  nodes refused, a network-free SessionStart hook offers the sync. Milestones with commit
  SHAs; confirmed contracts; deferred items.
read_when:
  - resuming or continuing the lb fleet build (feat/lb-fleet)
  - touching lb_fleet.py, the fleet verbs, fleet.toml, receipts, or hooks/fleet-inject
  - asking why a node is refused, or how a node-side edit is supposed to travel
---

# lb fleet — progress

Authorized by the approved plan (2026-09-30, "LB-Fleet" session). ADR:
`docs/lightbridge/adr/0004-fleet-hub-and-spoke.md` (M5). Design:
`docs/lightbridge/lightbridge-fleet.md` (M5). Branch: `feat/lb-fleet`.

The unlock: the three agent repos are cloned and installed on every device, but only the
Mac ever moved. Measured 2026-09-30 on `beelink-ser9-ubuntu`: 16 / 71 / 7 commits behind,
41 of 66 skills installed, one broken symlink — and three node-side edits sat uncommitted
for three weeks. `lb fleet` makes the Mac a control plane that sends nodes one command —
"reconcile yourself to `origin/main`" — and refuses to touch a node that has diverged, so
node-side edits are forced through branch → push → PR instead of stranding.

## Milestones

- [x] M0 — this tracker (plan contracts recorded); branch `feat/lb-fleet` — 44f7879
- [x] M1 — document model: `lb_resolve` readers (`DEFAULT_FLEET`, `load_fleet`,
      `load_receipt`, `fleet_receipts_dir`) + `lb_fleet.py` (seed, node script, runner,
      distance, atomic receipt) + `lb fleet init` + tests — 44f7879
- [x] M2 — tracer bullet: node script `status` mode + hub fetch/distance + `lb fleet status`
      (`--json`, dashboard row); live read-only run against `beelink-ubuntu` (online,
      behind 18/71/7, clean, 2 dangling links) — 44f7879
- [ ] M3 — `lb fleet sync`: gate, ff-only pull, apply, verify, receipt, `--dry-run` /
      `--repo` / `--reinstall`; tests with local bare-origin repos and an `ssh` shim;
      (code 44f7879); first live sync of the Beelink (after go-ahead) — pending
- [x] M4 — `hooks/fleet-inject` + `[fleet]` section + catalog + hook tests; the three
      repos opted in on the Mac; hook registered (Claude + Codex) — 9feb8e7
- [x] M5 — docs & skill: ADR 0004 (+ cli-design non-goal amendment), design doc,
      `fleet-sync` skill, lightbridge-config amendments, READMEs, `__version__` → 0.8.0,
      `~/my_config/AGENTS.md` line, agent-instruction replica bullet
      (Lightbridge-KS/agent-instruction#23) — 86a182b
- [x] Gates: `bin/validate.py` (50 skills) + full `just test` (23 suites) green

## Confirmed contracts

- **Hub-and-spoke, GitHub is truth, the Mac is the only initiator.** The hub never ships
  bytes; it streams one self-contained Python script over `ssh <alias> python3 -`, the
  node pulls `--ff-only` from `origin/main` and runs its own idempotent install.
- **Node → hub is structurally impossible**: no sshd on the Mac; `fleet.toml` exists only
  on the hub, so a node cannot address another node.
- **Refuse, never stash.** A repo that is not on `main`, dirty, ahead of `origin/main`, or
  missing a required per-box file (`.device`) is skipped and named. Node-side edits travel
  branch → push → PR; the hub picks them up by an ordinary `git pull`.
- **Distance is computed on the hub** (`git rev-list --count <nodeHEAD>..origin/main` in
  `<hub.root>/<repo>` after a hub fetch); `status` never makes the node contact GitHub.
- **Receipts are memory, not truth** — written atomically by `sync` only, read by the
  hook and the dashboard; `status` re-verifies live.
- **Nothing network-bound in the hook**: `fleet-inject` reads receipts + local refs only.
- 💡 **`sync` prunes dangling registry links** (only symlinks, only in `~/.claude/skills`
  and `~/.codex/skills`): a skill archived upstream leaves its link pointing nowhere
  after the pull, so without this every later sync would stay red. `status` only reports.
  Found live on the Beelink (`writing-great-skills`, two links) — decided during the build.
- **Exit codes** 0 ok / nothing to do · 1 refused (offline node = ssh 255, any repo refused
  or red, unusable inventory) · 2 usage — the CLI's standing taxonomy.

## Deferred (out of this effort)

- Windows nodes (`beelink-ser9-windows`, `minisforum-windows`) — Git Bash exists there; the
  streamed script is Python so the port is mostly the ssh/PowerShell arrival.
- Node-side drift timer (report-only systemd timer → skill-health notifier).
- `~/.lightbridge` config sync across machines — still `multi-machine-sync.md`, unchanged.
