# repo-links

Project a repo's **ego view from the central cross-repo graph** — so an agent working
in one repo knows where its neighbors (upstream counterpart, live test service, OSS
reference clone) live on *this* machine, without anyone committing personal paths.

Every relationship is one typed edge in `~/.lightbridge/graph.toml`, declared once;
this tool projects the view for whichever repo you point it at — outgoing edges,
backlinks labeled with each type's inverse, one compact mentions line — with every
path **verified on every run**: a dead name, stale path, or undeclared type surfaces
as a WARNING line instead of rotting silently.

## The two-layer model

Both layers are user-level — nothing ever lives inside the repo:

```
~/.lightbridge/graph.toml   [types] + [[edge]]   PER MACHINE — one typed edge per
        │                                        relationship between logical names
        │  repo at --start → registry name → incident edges
        ▼                                        (managed by `lb graph`; spec: the
~/.lightbridge/repos.toml   [repos]              repo-graph skill)
        │  name → path; tilde-expand + verify    PER MACHINE — the node namespace
        ▼
outgoing lines · Backlinks: · Also referenced by: · WARNING lines
```

On a machine with no `~/.lightbridge/graph.toml`, there is nothing to project (and the
companion hook stays completely silent).

## Declaring edges

Never hand-write the graph — `lb graph` owns it (see the **repo-graph** skill):

```sh
lb repos add example-service ~/work/example-service
lb graph link my-app example-service --type upstream \
    --from-note "Commercial counterpart" --to-note "Derived variant tracks this repo"
```

The edge direction rule, the `[types]` vocabulary (inverse labels, `full | compact |
off` backlink defaults, per-edge override), and the editing verbs are documented there.

## Usage

```sh
repo_links.py                       # human map for the repo at CWD
repo_links.py --start path/to/repo  # another repo's view
repo_links.py --json                # machine-readable (for hooks/tooling)
repo_links.py --check               # audit mode: exit 1 if anything is rotten
repo_links.py --graph alt.toml --registry alt-repos.toml   # nonstandard locations
```

Human output:

```
Linked repos (.lightbridge graph):
- example-service → /Users/x/work/example-service (upstream) — Commercial counterpart
- gone-repo: WARNING — registered path /Users/x/work/gone does not exist (stale registry entry?)
Backlinks:
- solution-tracker-repo → /Users/x/work/tracker (solution-tracker) — Epics live there
Also referenced by: analytics (studied-by), qms-docs (studied-by)

When a task involves a linked repo, work with it at the absolute path above.
```

`--json` schema:

```json
{
  "graph": "/abs/expanded/graph.toml",
  "registry": "/abs/expanded/repos.toml",
  "registry_error": null,
  "root": "/abs/repo/root",
  "node": "my-app",
  "out":       [{"other": "example-service", "type": "upstream", "label": "upstream",
                 "note": "…", "path": "/abs/path", "status": "ok", "detail": null}],
  "backlinks": [],
  "mentions":  [],
  "warnings":  []
}
```

`status` per entry: `ok` | `unregistered` | `relative-path` | `missing` | `not-a-dir`.

## Exit codes

- `0` — ran and rendered (warnings included; warnings are payload, not errors)
- `1` — `--check` only: something in this repo's view is unresolved or warned
- `2` — nothing to read: no graph on this machine, unreadable graph, no registry, the
  repo is not a registered node, or its node has no edges (stderr names the next move)

## Notes

- Paths are tilde-expanded but **not** `resolve()`d — a symlinked path renders as you
  wrote it; existence checks follow symlinks, so a symlinked repo counts as resolved.
- Compact mentions are names-only by design (low salience, no path verification);
  `full` tiers are verified line by line.
- A leftover pre-graph `[repo-links]` section in the project's lightbridge config earns
  a one-line deprecation warning (stderr for the CLI, appended context for the hook).
- Pairs with [`hooks/repo-links-inject`](../../hooks/repo-links-inject) — a SessionStart
  hook that injects this map into agent context automatically. The hook imports this
  module as its single source of truth.
- Graph state is registered in the `.lightbridge` catalog's user-level section
  (`plugins/lightbridge/skills/lightbridge-config/references/catalog.md`); the
  agent-facing spec is the `repo-graph` skill.
