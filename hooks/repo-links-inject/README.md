# repo-links-inject

A **`SessionStart`** hook for **Claude Code and Codex** that injects the session repo's
ego view from the **central cross-repo graph** — so the agent knows where the upstream
counterpart, the live test service, or the OSS reference clone lives on *this* machine,
before touching any code. One typed edge per relationship, declared once; both repos'
views (including backlinks) are **projected and path-verified on every session start**.

The hook logic is agent-neutral: it reads `cwd` on stdin and emits the shared
`hookSpecificOutput.additionalContext` envelope that both agents consume. Only the
*registration* differs per agent (see below); `bin/install.py --hooks` renders both.

Opt-in is **the graph file itself**, which makes one global registration safe everywhere
— both layers are user-level; nothing lives inside the repo:

1. **The graph** — `~/.lightbridge/graph.toml` declares typed edges between logical repo
   names, plus the `[types]` vocabulary (each type's `inverse` and default `backlink`
   mode). Managed with `lb graph`; spec: the **repo-graph** skill.
   **No graph file → completely silent.**
2. **The registry** — `~/.lightbridge/repos.toml` maps those names to local paths.
   A repo participates when it is a registered node with incident edges.

It pairs with [`scripts/repo-links`](../../scripts/repo-links): the script is the
deterministic projection core (the agent can also run it by hand — `--check` audits a
repo's view on demand), the hook is the thin wiring.

## Behavior

```
SessionStart → cwd
  repo root = git toplevel of cwd (cwd itself if not a git repo)
  read ~/.lightbridge/graph.toml         file absent?           → exit 0, silent
    graph unreadable?                    → inject ONE warning line (rot must show)
  read ~/.lightbridge/repos.toml         absent / unreadable?   → inject ONE warning line
  repo root → registry name              not registered?        → exit 0, silent
  select the node's incident edges       none?                  → exit 0, silent
  → emit additionalContext:
      - <to> → /abs/path (<type>) — <from_note>          outgoing edges, verified
      Backlinks:
      - <from> → /abs/path (<inverse>) — <to_note>       incoming, backlink mode "full"
      Also referenced by: a (<inverse>), b (<inverse>)   incoming, mode "compact"
      - name: WARNING — …                                dead names / stale paths /
                                                         undeclared types
  deprecation nudges appended to whatever is emitted (or emitted alone):
      a leftover [repo-links] section in the project's lightbridge config, and
      a stray pre-migration <repo>/.lightbridge/config.toml
```

Warnings are payload, not errors — the hook always exits 0 and never blocks a session.
Paths are tilde-expanded but not `resolve()`d (symlinks render as written). Incoming
edges with backlink mode `off` are invisible; a per-edge `backlink` key overrides the
type's default.

## 1. Enable once (per machine)

The hook is a self-contained `uv` script — no install step beyond `uv` itself. The canonical,
agent-neutral descriptor is [`hook.toml`](hook.toml); the installer renders it into each
agent's native registration form with the path resolved for your checkout:

```sh
uv run bin/install.py --hooks
```

> The installer only **prints** these blocks; it never edits your settings. Wiring a hook
> stays a deliberate, one-time choice.

### Claude Code

Merge the printed `SessionStart` block into user-level `~/.claude/settings.json` (if
`docs-index-inject` is already registered, append this hook's command object to the same
group's `hooks` array):

```jsonc
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "/abs/path/to/agent-stuff/hooks/repo-links-inject/hook.py" }
        ]
      }
    ]
  }
}
```

### Codex

Merge the printed block into `~/.codex/hooks.json` (or the inline `config.toml` form),
then trust it via `/hooks`.

## 2. Declare edges (per machine, never committed)

```sh
lb repos add example-service ~/work/example-service   # names live in the registry
lb graph init                                         # once: seed the [types] vocabulary
lb graph link my-app example-service --type upstream \
    --from-note "Commercial counterpart" \
    --to-note "Derived variant tracks this repo"
```

One edge serves both repos: `my-app` sessions show
`example-service → … (upstream) — Commercial counterpart`; `example-service` sessions
show `my-app → … (downstream) — Derived variant tracks this repo` under `Backlinks:`.
See the **repo-graph** skill for the full verb surface and the direction rule.

## Verify

```sh
echo '{"cwd":"/path/to/linked/repo","hook_event_name":"SessionStart"}' \
  | uv run hooks/repo-links-inject/hook.py
```

Expected: a JSON envelope whose `additionalContext` contains the `Linked repos` map.
A repo with no graph presence prints nothing. To audit a repo's view without a session:
`uv run scripts/repo-links/repo_links.py --start /path/to/repo --check`; the whole
graph: `lb graph doctor`.
