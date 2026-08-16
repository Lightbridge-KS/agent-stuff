---
name: repo-graph
description: >-
  Manage the personal cross-repo knowledge graph (~/.lightbridge/graph.toml) with the
  `lb graph` verbs. Use when linking two repos ("link repo A to B"), asking how repos
  relate, editing or removing a repo link, choosing an edge type or backlink mode,
  auditing the graph, or rendering it (Mermaid / interactive HTML). Session injection
  internals live with the repo-links hook; per-project config belongs to
  lightbridge-config.
metadata:
  version: "2026-08-16"
---

# Repo graph

Repos are nodes (named in `~/.lightbridge/repos.toml`); relationships are typed edges
in `~/.lightbridge/graph.toml` — **one edge per relationship, declared once**. Both
repos' session context project from that single edge, so the reverse direction can
never drift out of sync; it can only be curated.

**The direction rule.** An edge `A -[type]-> B` reads: *the type names what B is to A.*
`rmos -[tooling]-> devkit` = "devkit is rmos's tooling". The graph's `[types]` table
declares each type's `inverse` (what A is to B — devkit sessions show rmos as
`tool-user`) and its default `backlink` mode.

**Backlink modes** — how the reverse direction renders in B's sessions:
- `full` — a normal linked-repo line with path and note.
- `compact` — one names-only "Also referenced by: …" line (low salience).
- `off` — invisible in B's sessions.
A per-edge `backlink` key overrides the type's default.

The vocabulary is **owned by the file, not the tool** — always read the live table
(`lb graph types`), never assume which types exist.

## Link two repos ("link A to B")

```bash
lb repos list                # 1. resolve both repos to registered names
lb graph types               # 2. pick the type — each line shows the direction reading
lb graph link FROM TO --type TYPE \
    --from-note "why TO matters when working in FROM" \
    --to-note   "why FROM matters when working in TO"     # notes optional but valuable
```

3. **Read the echo.** `link` prints the sentence both ways ("B is A's TYPE; B sessions
   will show A as (INVERSE)"). If it reads backwards, the edge is reversed —
   `lb graph unlink` and swap the arguments. Never declare the same relationship twice
   in both directions; the CLI refuses a reversed duplicate.

Unregistered repo? `lb repos add NAME PATH` first (refusals name this move).
Verify anytime: `lb graph show NAME` renders the node's projected ego view — exactly
what its sessions will be injected with.

## Edit or remove an edge

```bash
lb graph set FROM TO --from-note "..."      # replace a note ('' clears)
lb graph set FROM TO --backlink off         # per-edge override (default clears it)
lb graph unlink FROM TO                     # --type TYPE when parallel edges exist
```

Parallel edges (same pair, different types) are legitimate — e.g. a repo can be both
`contracts` and `live-test-service` to the same consumer.

## Inspect and audit

```bash
lb graph show                # whole-graph summary (nodes, edges by type)
lb graph show NAME           # one node's ego view: outgoing + backlinks + mentions
lb graph doctor              # rot audit; exit 1 on problems — run after hand-edits
lb status                    # includes a one-line graph row
uv run <agent-stuff>/scripts/repo-links/repo_links.py --check   # this repo's view only
```

## Visualize

```bash
lb graph mermaid                  # flowchart to stdout (backlink-off edges dashed)
lb graph html --out graph.html    # self-contained interactive page (never clobbers);
                                  # open in a browser — zoom, pan, drag, hover notes
```

## Grow the vocabulary

Add a `[types.<name>]` block (with `inverse` and `backlink`) to `graph.toml` by hand —
the CLI validates but never invents types — then `lb graph doctor`. Prefer reusing an
existing type over coining a near-synonym.

## Source of truth

Session injection (the SessionStart hook, its fail-open ladder, warning lines):
`hooks/repo-links-inject/README.md` in agent-stuff. Per-project `.lightbridge` config
and the registry: the `lightbridge-config` skill. The retired per-project
`[repo-links]` section is no longer read — a leftover earns a deprecation warning;
its links belong in the graph.
