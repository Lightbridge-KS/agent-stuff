---
summary: >-
  Decision to keep the agent repos (agent-instruction, agent-stuff, agent-stuff-private)
  current on every device with a hub-and-spoke control plane: GitHub is the source of
  truth, the primary machine is the only initiator, nodes are pull-only replicas that
  reconcile themselves over one streamed ssh session and are refused — never stashed —
  when they have diverged. Adds fleet.toml + receipts, the lb fleet verb family, the
  fleet-inject hook, and amends the frozen importer API with the fleet readers.
read_when:
  - changing fleet.toml's schema, the node program, the sync gate, or the receipt shape
  - touching lb_fleet.py, load_fleet/load_receipt, the lb fleet verbs, or hooks/fleet-inject
  - wondering why a node cannot push to the hub, or why a dirty node is refused
  - considering rsync, a node-side auto-pull timer, or Windows nodes
---

# ADR 0004 — Hub-and-spoke sync of the agent repos to node devices

Accepted 2026-09-30 (KS, "LB-Fleet" session). Design:
[`../lightbridge-fleet.md`](../lightbridge-fleet.md). Build:
[`../progress/fleet.md`](../progress/fleet.md). Toy example of the pattern:
`~/my_learning/Explore_Architecture_Patterns/hub-and-spoke/` (not in this repo).

## Context

The three agent repos are cloned at `~/my_config/<repo>` on every device and installed
into each box's harness dirs by their own idempotent commands (`make install`,
`bin/install.py --all`). Only the primary machine moved as work landed. Measured on
2026-09-30 for the hospital-office edge box: **16 / 71 / 7 commits behind**, 41 of 66
skills installed, one dangling registry link — and **three node-side edits from
2026-09-09 sat uncommitted for three weeks**, unknown to the hub, until a manual ssh
found them. The failure was not the missing pull; it was that nothing ever *looked*.

## Decision

1. **Roles.** GitHub (`origin/main`) is the source of truth. The primary machine is the
   **hub**: the only initiator, holder of the inventory. Every other device is a **node**:
   a pull-only replica that never addresses another machine. Node → hub is structurally
   impossible: the hub runs no sshd, and `~/.lightbridge/fleet.toml` exists only on the
   hub, so a node has no address book.
2. **Transport = one command, not bytes.** The hub streams a self-contained Python program
   over `ssh <alias> python3 -` with the node's spec embedded as JSON. The node inspects
   its clones, fetches, fast-forwards, runs each repo's own `apply`, and prints **one JSON
   report line**. Nothing on the node's (possibly stale) agent-stuff clone is executed by
   the hub; nothing is copied.
3. **Refuse, never stash.** The gate refuses a repo that is not on `main`, dirty, ahead of
   `origin/main`, or missing a required per-box file (`requires`, e.g. `.device`), and
   names the fix. Node-side edits therefore travel branch → push → PR; the hub picks them
   up with an ordinary `git pull`. The gate is what makes that rule enforceable.
4. **Distance is computed on the hub.** `status` never makes a node contact GitHub: the
   node reports HEAD/branch/dirty, the hub fetches its own clone and runs
   `rev-list --count <nodeHEAD>..origin/main`. A node HEAD the hub does not know is
   `ahead` by definition.
5. **Receipts + a network-free hook.** `sync` writes `~/.lightbridge/fleet/<node>.json`
   atomically; the `fleet-inject` SessionStart hook (gated on a `[fleet]` section, hub
   only) compares receipts with the *local* `origin/main` ref and injects one line per
   lagging node so the agent can *offer* a sync. Receipts are memory, not truth — `status`
   verifies live; the hook never fetches or sshes (the standing rule from
   `multi-machine-sync.md`).
6. **Frozen importer API amendment.** `DEFAULT_FLEET`, `load_fleet`, `load_receipt`,
   `fleet_receipts_dir` join `lb_resolve.py` (the `load_graph` precedent): the hook
   path-loads them, so the inventory is read one way everywhere. Writers and the node
   program stay CLI-side in `lb_fleet.py`.
7. **Registries are reconciled too.** A skill archived upstream leaves its symlink in
   `~/.claude/skills` / `~/.codex/skills` pointing nowhere after the pull, so `sync`
   prunes dangling links in those two dirs (only symlinks, only there); `status` reports
   them. Without this every sync after an archive would stay red.
8. **`lb fleet` is the home.** `init | status [NODE] | sync NODE`, inventory beside the
   other user-level files; `lb status` gains a bounded `fleet` row (counts, no ssh). This
   amends the CLI design's `lb sync` non-goal: *device* sync of the agent repos is in scope
   here; sync of `~/.lightbridge` itself stays deferred.

## Rejected alternatives

- **rsync the working trees hub → node.** Ships uncommitted hub state, clobbers node edits
  like the three above, and skips the per-device render (`.device`, `dist/` differ per
  box). Git history is the audit trail; bytes are not.
- **Node-side auto-pull (cron / systemd timer).** No authorization moment (the user wants
  to be offered, then say yes), failures invisible, and the node would still need the
  same gate. A *report-only* drift timer remains a possible later addition.
- **Nodes push their state to the hub / mesh.** Requires an inbound path to the primary
  machine (policy: none) and gives N² relationships; the whole point of the star is one
  address book, on the hub.
- **`tailscale status` liveness probe.** The ssh attempt already yields liveness (exit
  255) and one fewer external tool means one fewer test double.
- **Per-repo config committed in the repos.** Device names and ssh aliases are the
  operator's environment; they stay user-level, like `repos.toml`.

## Consequences

- Every node's profile gains a rule: *this box is a fleet replica — never commit to
  `main` here; branch + PR; `lb fleet sync` refuses a dirty tree.*
- `requires = [".device"]` makes a fresh clone refuse `agent-instruction` with a teaching
  line instead of a `make` error.
- Windows nodes are out of scope for v1 (the program is Python, so the port is the
  arrival shell, not the logic). A node-side drift timer is deferred.
- `docs/lightbridge/lightbridge-cli-design.md` non-goals: the `lb sync` line is amended;
  `multi-machine-sync.md` gains a pointer and keeps its own (deferred) scope.
