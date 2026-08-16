---
summary: >-
  Decision to replace per-project [repo-links] adjacency lists with one central typed-edge
  graph (~/.lightbridge/graph.toml) whose [types] table declares inverses and 3-mode
  backlink defaults. Amends the frozen importer API with the graph trio (DEFAULT_GRAPH,
  load_graph, project_node), adds the lb_graph.py module and the `lb graph` verb family,
  and retires the repo-links catalog section.
read_when:
  - changing graph.toml's schema, the projection semantics, or a backlink mode's meaning
  - touching lb_graph.py, load_graph/project_node, or the lb graph verbs
  - wondering why cross-repo links are not declared per project anymore
  - considering re-adding a [repo-links]-style per-project section
---

# ADR 0002 — Central repo graph replaces per-project `[repo-links]`

Accepted 2026-08-16 (KS). Spike: `_playground/2026-08-16_repo-graph-spike/` in the
working tree of that date; decisions grilled and recorded in its NOTES.md. Design:
[`../lightbridge-graph.md`](../lightbridge-graph.md). Build:
[`../progress/repo-graph.md`](../progress/repo-graph.md).

## Context

`[repo-links]` stored each repo's outgoing links in its own user-level config — per-node
adjacency lists. A bidirectional relationship had to be authored twice with no shared
identity, and measurement showed the cost: of 72 live declarations, only 15 reciprocal
pairs existed while **25 bidirectional-looking edges had never been given their reverse**,
and free-form `role` strings meant the same relationship carried different names from
each side (`client-app` meant two different things in two configs).

## Decision

1. **One SSOT**: `~/.lightbridge/graph.toml` holds typed edges between the registry's
   names. An edge `A -> B` carries `type` (what B is to A), optional per-side notes,
   and an optional `backlink` override. Declared once; both repos' views project from it.
2. **The vocabulary lives in the file**: `[types.<name>]` declares `inverse` and a
   default `backlink` mode (`full | compact | off`). The tool validates types, never
   defines them — a tool upgrade can never reinterpret stored edges.
3. **Frozen importer API amendment**: `DEFAULT_GRAPH`, `load_graph` (the registry-style
   tri-state reader), and `project_node` (the one projection rule — out/backlinks/
   mentions with inverse labels and mode resolution) join `lb_resolve.py`.
   `project_node` is data selection, not rendering: both consumers (`repo_links.py` +
   hook; `lb graph show`) need identical semantics, while formatting stays per-consumer.
4. **Write path**: new CLI-side `lb_graph.py` (document model + edge-block surgery on
   the `lb_tomledit` invariant) behind the `lb graph` verb family
   (`init·show·types·link·unlink·set·doctor·mermaid·html`) — resolver-domain, the same
   argument that admitted `lb repos` (design doc Decision 1).
5. **Retirement**: the `repo-links` section leaves the catalog (`SECTIONS`,
   `SectionName`, catalog.md — lockstep-tested); a leftover section earns a one-line
   deprecation warning from every reader, mirroring the legacy per-repo-config pattern.

## Rejected alternatives

- **Lint-only (keep per-project authoring, add a reciprocity doctor).** Keeps the
  double-authoring cost forever and makes the curated-backlink policy unexpressible —
  a reverse edge would still need hand-writing to exist at all.
- **Per-project sections as the write surface, graph as a derived cache.** Two sources
  of truth; the drift this effort exists to kill would reappear between them.
- **Vocabulary as code defaults with file overrides.** A tool upgrade could silently
  change what stored edges mean; the file would not be self-describing.

## Consequences

- The graph file's *presence* is the machine's opt-in for link injection (previously the
  registry's presence); the registry remains the node namespace and path resolver.
- Backlinks are curated, not automatic: `full`/`compact`/`off` per type, per-edge
  override — hub repos keep whole-neighborhood awareness at ~1 line of context
  (`Also referenced by: …`) instead of unbounded backlink lines.
- One-shot migration (2026-08-16) folded 72 declarations into 55 edges, registered 9
  missing names, stripped 27 configs; backups under
  `~/.lightbridge/backups/repo-graph-migration-*/`, regression report in the spike
  session, zero lost links.
