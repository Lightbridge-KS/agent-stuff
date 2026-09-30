# fleet-inject

A **`SessionStart`** hook for **Claude Code and Codex** that tells the agent which fleet
nodes lag *this* repo's `origin/main`, so it can **offer** `lb fleet sync <node>` at the
right moment — the first session after `main` moved — instead of the node drifting for
weeks. Hub only: it is silent on any machine without `~/.lightbridge/fleet.toml`.

It pairs with `lb fleet` ([`scripts/lightbridge`](../../scripts/lightbridge), ADR 0004):
the CLI does the sync and writes a receipt per node; this hook only reads the receipts.
The hook logic is agent-neutral (stdin `cwd`, `hookSpecificOutput.additionalContext`
envelope); only the registration differs per agent — `bin/install.py --hooks` renders both.

**Network-free by contract.** The injected line compares the receipt's synced sha with
the *local* `origin/main` ref — two or three local git calls, no fetch, no ssh — so a
session start never waits on a node. The receipt is the hub's memory, not the node's
truth; `lb fleet status` verifies live before anything acts.

## Behavior

```
SessionStart → cwd
  repo root = git toplevel of cwd
  read ~/.lightbridge/projects/<key>/config.toml   none / no [fleet] / enabled=false → exit 0, silent
  read ~/.lightbridge/fleet.toml                   absent (not a hub) or unusable      → exit 0, silent
  repo = [fleet].repo, else the folder name        not a [repos.<name>] in fleet.toml → exit 0, silent
  origin/main = git rev-parse origin/main          no such ref                        → exit 0, silent
  for each node carrying this repo:
    receipt fleet/<node>.json missing              → "never synced from this hub"
    receipt.repos.<repo>.after == origin/main      → nothing (or "last sync reported problems")
    else                                           → "last synced at X; origin/main is Y (N commits ahead)"
  nothing to say → exit 0, silent
  else → additionalContext: the lines + "offer `lb fleet sync <node>` — needs the user's go-ahead"
```

Any exception anywhere → exit 0, silent. A hook that cries wolf gets ignored.

## 1. Enable once (per machine — the hub)

```sh
uv run bin/install.py --hooks
```

The installer prints the registration blocks with the path resolved for your checkout;
it never edits settings. Merge the `SessionStart` block into `~/.claude/settings.json`
(Claude Code) and into `~/.codex/hooks.json` **or** the `[hooks]` table of
`~/.codex/config.toml` (Codex — exactly one of the two; then `/hooks` to trust it).

## 2. Opt in (per repo — the three fleet repos)

```sh
cd ~/my_config/agent-stuff && lb add fleet        # likewise agent-instruction, agent-stuff-private
```

```toml
# ~/.lightbridge/projects/<project-key>/config.toml
[fleet]                  # presence = opt in
enabled = true           # optional; default true
# repo = "agent-stuff"   # optional; defaults to the repo folder's name
```

## Verify

```sh
# in an opted-in repo on the hub, after main has moved past a node's last sync:
echo '{"cwd":"'"$PWD"'","hook_event_name":"SessionStart"}' | uv run hooks/fleet-inject/hook.py
```

A JSON object with `hookSpecificOutput.additionalContext` naming the lagging node(s); an
in-sync fleet, a non-hub machine, or a repo without `[fleet]` prints nothing and exits 0.
