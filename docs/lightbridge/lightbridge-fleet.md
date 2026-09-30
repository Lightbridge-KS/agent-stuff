---
summary: >-
  Settled design for lb fleet: the fleet.toml schema (hub root, repos with apply/verify/
  requires, nodes with ssh/root/repos), the streamed node program and its one-line JSON
  report, the sync gate and phases, hub-side distance, the receipt shape, the verb
  surface with exit codes, the state vocabulary status prints, the fleet-inject hook's
  semantics, and the test seams.
read_when:
  - changing fleet.toml's keys, the node program, the gate, the phases, or the receipt
  - changing any lb fleet verb's surface (flags, output, exit codes, refusals)
  - reasoning about what fleet-inject will say for a given receipt and origin/main
  - writing a test for lb fleet (the runner seam, the ssh shim, the git worlds)
---

# lightbridge fleet — settled design

Decision record: [`adr/0004-fleet-hub-and-spoke.md`](adr/0004-fleet-hub-and-spoke.md).
Build tracker: [`progress/fleet.md`](progress/fleet.md). Agent-facing usage: the
`fleet-sync` skill (canonical how-to; this doc is the why-and-what).

```
            ┌────────────── GitHub · origin/main (source of truth) ──────────────┐
            │            ▲                                          │            │
            │   push     │ PR, merged                    fetch + merge --ff-only │
            │            │                                          ▼            │
   ┌────────┴───────┐    │       ssh <alias> python3 -   ┌──────────────────────┐ │
   │ HUB (this Mac) │    │  ─────────────────────────►   │ NODE (pull-only)     │ │
   │ fleet.toml     │    │       one JSON report line    │ no fleet.toml        │ │
   │ fleet/<n>.json │    │  ◄─────────────────────────   │ no path to the hub   │ │
   └────────────────┘    │                               └──────────┬───────────┘ │
                         │       node-side edit → branch → push → PR │            │
                         └────────────────────────────────────────────┘            │
```

## Schema (`~/.lightbridge/fleet.toml`, hub only)

```toml
[hub]
root = "~/my_config"          # the hub's own clones: <root>/<repo>; distance is computed here

[repos.agent-instruction]     # one per mirrored repo, at <root>/<name> on every machine
requires = [".device"]        # gitignored per-box files; absent ⇒ refused with a teaching line
apply    = "make install"     # the repo's OWN idempotent install; runs only when it moved
verify   = "make check"       # after a successful apply; optional

[nodes.beelink-ubuntu]        # one per device
ssh   = "beelink-ubuntu"      # alias in ~/.ssh/config (BatchMode, ConnectTimeout=8 are added)
root  = "~/my_config"         # expanded ON THE NODE; defaults to [hub] root
repos = ["agent-instruction", "agent-stuff", "agent-stuff-private"]   # = apply ORDER
```

`load_fleet` (in `lb_resolve`) normalizes and validates: a repo without `apply`, a node
without `ssh`, or a node naming an undeclared repo makes the whole file *unusable* (exit 1
with the reason) — never a silently thinner fleet. Absent file = not a hub, silent.
Receipts live beside it: `fleet_receipts_dir(fleet) = <parent>/fleet/`, so one `--fleet`
flag pins both in tests.

## The node program

Rendered by `lb_fleet.render_node_script(mode, root, repos, reinstall, timeout,
registries)`: the `NODE_SCRIPT` template (3.8+ stdlib Python, so any node's `python3`
runs it) with `CONFIG = json.loads(<repr of the JSON>)` substituted. Streamed on stdin;
nothing from the node's own agent-stuff clone is executed by the hub.

Every command runs with `GIT_TERMINAL_PROMPT=0`, `stdin=DEVNULL`, `start_new_session=True`
so a timeout kills the whole group (`make → quarto`); output is decoded with `replace`
and tailed (20 lines / 2000 chars) into the report. The program prints exactly one line:
`LB_FLEET_REPORT {json}` — `parse_report` scans for the marker, so motd or rc noise is
harmless.

```
mode=status   per repo: branch · HEAD · dirty files · missing `requires`          NO fetch, no writes
mode=sync     gate      refuse: not-cloned | not-on-main | dirty | missing-requires
              fetch     git fetch origin main; ahead/behind = rev-list --left-right --count
              gate      refuse: ahead (unpushed commits)
              pull      behind>0 → git merge --ff-only origin/main   (else in-sync)
              apply     sh -c <apply>, cwd=repo, timeout — repos that moved, or --reinstall; inventory order
              verify    sh -c <verify> after a successful apply
              prune     dangling symlinks in ~/.claude/skills, ~/.codex/skills (sync only)
              report    {host, mode, root, repos:{name: entry}, checks:{broken_symlinks, pruned_symlinks}}
```

Entry: `{status, reason, branch, before, after, dirty[], missing_requires[], ahead,
behind, pull{exit,tail}, apply{exit,tail}, verify{exit,tail}}` with
`status ∈ {observed | applied | in-sync | refused | failed}`. A refused repo keeps
`before == after` (nothing was pulled). Two-phase across repos: every eligible repo pulls
before any apply runs, because the private repo's apply calls agent-stuff's installer.

## Hub-side distance (`status`)

`status` never makes a node reach GitHub. For each repo: `hub_fetch` (`git fetch --quiet
origin main` in `<hub.root>/<repo>`, skipped with `--no-fetch`), then `distance(repo_dir,
nodeHEAD)`: `origin_main = rev-parse origin/main`; a HEAD the hub clone lacks ⇒ `ahead`
(unknown commit); else `merge-base --is-ancestor` decides `ahead` and
`rev-list --count HEAD..origin/main` gives `behind`.

State per repo, printed as one word plus flags:

| state | meaning | `sync` would |
|---|---|---|
| `in-sync` | on `main`, clean, HEAD == origin/main | do nothing (`--reinstall` re-applies) |
| `behind N` | clean replica, N commits to pull | pull + apply + verify |
| `diverged` (flags: `not on main (x)` · `DIRTY n` · `AHEAD` · `missing .device`) | needs a human on the node | refuse and name the fix |
| `not cloned` | `<root>/<name>/.git` absent | refuse |

Exit: `status` 0 only when every addressed node answered and every repo is `in-sync`.

## Receipt (`~/.lightbridge/fleet/<node>.json`, written by `sync` only, atomically)

```json
{"node": "beelink-ubuntu", "host": "beelink-ser9-ubuntu", "timestamp": "2026-09-30T12:00:00Z",
 "mode": "sync", "reinstall": false, "ok": true,
 "repos": {"agent-stuff": {"status": "applied", "before": "39b7244…", "after": "d4baebe…",
           "behind": 71, "ahead": 0, "reason": null, "dirty": [], "missing_requires": [],
           "pull": {"exit": 0, "tail": "…"}, "apply": {"exit": 0, "tail": "…"}, "verify": {"exit": 0, "tail": "…"}}},
 "checks": {"broken_symlinks": [], "pruned_symlinks": ["/home/…/.claude/skills/old-skill"]}}
```

`ok` = every repo `applied | in-sync` and no broken links left. A receipt is written even
when repos were refused (it records what happened); the hook reads `repos.<r>.after`.

## Verb surface

```
lb fleet init  [--dry-run]                           seed; never clobbers (exit 1)
lb fleet status [NODE] [--no-fetch] [--json]         live; 0 all in-sync · 1 lag/diverged/offline
lb fleet sync NODE [--repo R]… [--dry-run] [--reinstall] [--json]
                                                     0 all applied/in-sync + clean registries · 1 any refused/failed/offline
                                                     2 --repo names a repo the node does not carry
```
All take `--fleet FILE`. Offline = ssh exit 255 → stderr line, exit 1, **no receipt**.
`--dry-run` prints the plan and contacts nothing. Progress (`asking …`, `reconciling …`)
goes to stderr; the report to stdout. Human rows use the CLI's `row()` labels: `node`,
`repo`, `checks`, `next` (status); `applied`, `in-sync`, `REFUSED`, `FAILED`, `pruned`,
`checks`, `receipt` (sync). Refusal text is worded for the node, where the fix happens
(`REFUSALS` in `lb_commands.py`). `lb status` shows one bounded row: inventory path,
node count, receipt count — no ssh.

## `fleet-inject` (SessionStart, hub only, network-free)

Gate: `[fleet]` section present and not disabled; `fleet.toml` loads; the repo (config
`repo` key, else the folder name) is a `[repos.<name>]`; at least one node carries it;
`origin/main` resolves locally. Then per node: no receipt → "never synced"; receipt
`after == origin/main` → silent (or "last sync reported problems" when `ok` is false);
else `rev-list --count after..origin/main` → "last synced at X; origin/main is Y as of
the last local fetch (N commits ahead)". Ends with the offer line naming
`lb fleet sync <node>` and that it needs the user's go-ahead. Whole `main()` in a bare
`try/except → 0`.

## Test seams

- `run_node(alias, script, runner=subprocess.run)` — injectable transport.
- The node program runs locally: `python3 -` over a **world** of real repos (bare origin,
  hub clone, node clone, a work clone to push upstream changes).
- The CLI runs as a subprocess with an `ssh` shim on `PATH` that logs argv, honours
  `LB_TEST_SSH_EXIT=255` (offline), else `exec $LB_TEST_PYTHON -`.
- The hook runs with `HOME`/`USERPROFILE` at a temp home (`fleet.toml`, receipts, project
  config) and a repo whose `refs/remotes/origin/main` is set with `git update-ref`.
