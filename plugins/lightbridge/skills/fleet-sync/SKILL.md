---
name: fleet-sync
description: >-
  Keep the agent repos (agent-instruction, agent-stuff, agent-stuff-private) current on
  node devices with the `lb fleet` verbs — hub-and-spoke, GitHub is the truth, this Mac is
  the only initiator. Use when a session start says a node lags, when asked to sync or
  update a device's skills or instructions, when a node reports refused/diverged, or when
  working ON a node and about to change one of these repos. Inventory and per-project
  opt-in belong to lightbridge-config; skill↔binary drift is skill-vendor.
metadata:
  version: "2026-10-02"
---

# Fleet sync

Every device mirrors the three agent repos at `~/my_config/<repo>` and installs them
with the repo's own command (`make install`, `bin/install.py --all`). **GitHub's
`origin/main` is the truth; this Mac is the hub — the only machine that initiates;
every other device is a pull-only replica.** The hub never ships files: it sends one
command over ssh ("reconcile yourself to origin/main"), the node pulls `--ff-only`,
reinstalls itself, and reports. A node that has diverged is **refused and named, never
stashed** — its edits must travel branch → push → PR. Design: `docs/lightbridge/
lightbridge-fleet.md`, ADR 0004 (agent-stuff).

## When a session says a node lags

The `fleet-inject` hook prints a line like *"`<node>` last synced `agent-stuff`
at 39b7244; origin/main is d4baebe (71 commits ahead)"*. That is the hub's memory, not
the node's state. **Offer, don't act:**

```bash
lb fleet status                 # live: asks each node; distance computed here; exit 1 = something to do
```

Then tell the user what `status` showed and ask for the go-ahead before `sync` — it
changes the node (pull + reinstall). Never run `sync` unasked; never run it from a node.

## Sync a node

```bash
lb fleet sync NODE --dry-run      # the plan: repos, apply/verify commands — contacts nothing
lb fleet sync NODE                # gate → ff-only pull → apply → verify → prune dangling links → receipt
lb fleet sync NODE --repo agent-stuff      # one repo (repeatable)
lb fleet sync NODE --reinstall             # re-run apply even where nothing moved
```

Read the rows: `applied` (sha → sha, +N), `in-sync`, `REFUSED` (with the fix, worded for
the node), `FAILED` (fetch/pull/apply/verify; git's or the command's tail on stderr and in the receipt),
`pruned` (dangling registry links removed), `checks`, `receipt`. Exit 0 only when every
repo is applied or in-sync and the registries are clean. An unreachable node exits 1 with
no receipt, and the line names why (`unreachable` kind in `status --json`). `dns` means
*this* machine could not resolve the name — the node may be up: check `tailscale status`
here, and rerun outside an agent sandbox, which blocks Tailscale. `timeout` / `no-route`
mean the node is off — retry later; nothing queues (the truth waits on GitHub).

## What a refusal means, and where the fix is

| REFUSED … | on the node |
|---|---|
| `dirty: N file(s)` | `git switch -c <branch>`, commit, push, open a PR — or revert. The hub merges, then syncs. |
| `ahead of origin/main by N` | push that branch and open a PR; the hub pulls after merge. |
| `on branch X` | push X, then `git switch main`. |
| `missing .device` | `cp .device.example .device`, edit it to the box's name. |
| `not cloned` | clone it at `<root>/<name>` (ssh remote, on-box key). |

Refusals are never worked around from the hub: no stash, no reset, no `--force` pull.
If the user wants the node's edits kept, that is a PR from the node.

## Working ON a node (you are the agent there)

Nothing here runs from a node — `fleet.toml` does not exist there by design. If you must
change `agent-instruction` or `agent-stuff*` on a node: **never commit to `main`**.
Branch, commit, push, `gh pr create --draft`; leave the clone on a clean `main` so the
next `lb fleet sync` can fast-forward it. The hub picks the change up by an ordinary
`git pull` after the PR merges.

## Inventory and opt-in

`~/.lightbridge/fleet.toml` (hub only) — `[hub] root`, one `[repos.<name>]` (`apply`,
`verify`, `requires`), one `[nodes.<name>]` (`ssh` alias, `root`, `repos` in apply
order). `lb fleet init` seeds it once (never clobbers) with an `example-node` to rename; it is
hand-edited from there.
The hook's per-repo opt-in is the `[fleet]` section (`lb add fleet`), documented in the
lightbridge-config catalog. Windows nodes and a node-side drift timer are deferred.

## Source of truth

Verbs and flags: `lb fleet --help`. Semantics, receipt shape, exit codes:
`docs/lightbridge/lightbridge-fleet.md`. Why hub-and-spoke and what was rejected:
`docs/lightbridge/adr/0004-fleet-hub-and-spoke.md`.
