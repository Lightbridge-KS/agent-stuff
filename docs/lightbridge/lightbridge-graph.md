---
summary: >-
  Settled design for the cross-repo graph: the graph.toml schema (typed edges over
  registry names, [types] with inverses and 3-mode backlink defaults), the projection
  semantics every consumer shares, the lb graph verb surface, and the seeded 13-type
  vocabulary with its rationale.
read_when:
  - changing the graph.toml schema, a projection rule, or the ego-view rendering
  - adding or renaming an edge type, or changing a backlink default
  - changing any lb graph verb's surface (flags, output, exit codes, refusals)
  - reasoning about what the repo-links hook will inject for a given edge
---

# lightbridge graph — settled design

Decision record: [`adr/0002-central-repo-graph.md`](adr/0002-central-repo-graph.md).
Build tracker: [`progress/repo-graph.md`](progress/repo-graph.md). Agent-facing usage:
the `repo-graph` skill (canonical how-to; this doc is the why-and-what).

## Schema (`~/.lightbridge/graph.toml`)

```toml
[types.tooling]               # edge A -> B: the type names what B is to A
inverse = "tool-user"         # what A is to B — the label B's sessions see
backlink = "full"             # how the reverse renders in B: full | compact | off

[[edge]]
from = "ramaai-commertial-rmos"
to = "ramaai-devkit"
type = "tooling"
from_note = "manages the gateway API keys this app consumes"   # optional; A's viewpoint
to_note = "consumes RAMAAI_GDCC_API_KEY via CloudProviders"    # optional; B's viewpoint
backlink = "off"              # optional per-edge override of the type's mode
```

- Node identity = `~/.lightbridge/repos.toml` names. The graph carries **no paths**.
- One edge per relationship. The reverse direction is *projected*, never declared;
  `lb graph link` refuses a reversed duplicate outright.
- The `[types]` table is user-owned and self-describing — the tool validates
  (`lb graph doctor`), it never defines. Vocabulary grows by hand-editing the file.

## Projection (the one rule, `lb_resolve.project_node`)

For a node N, every consumer renders three tiers from the same selection:

1. **Outgoing** (N is `from`): full line — `- <to> → <path> (<type>) — <from_note>`.
2. **Backlinks** (N is `to`, effective mode `full`): full line labeled with the
   type's `inverse`, carrying `to_note`, under a `Backlinks:` heading.
3. **Mentions** (mode `compact`): one names-only line —
   `Also referenced by: a (<inverse>), b (<inverse>)`. Mode `off`: invisible.

Effective mode = the edge's own `backlink` if valid, else the type's, else `full`.
Rot projects visibly, never vanishes: an undeclared type still renders (flagged),
dead names/paths become WARNING lines, malformed edge blocks are counted and reported.

Consumers: `scripts/repo-links/repo_links.py` (CLI + the SessionStart hook's injected
map — paths verified via the registry) and `lb graph show NAME` (same view, for
inspection after a write). Formatting lives with each consumer; selection semantics
live once in `lb_resolve.py`.

## Verb surface

`lb graph init · show [NAME] · types · link · unlink · set · doctor · mermaid · html`
— all with `--json` and a `--graph FILE` seam; writers follow the house temperament
(surgical line edits, never clobber, idempotent no-ops, refusals that name the next
verb, no prompts). `link` echoes the direction-confirming sentence — the designed
catch for a reversed edge. `lb status` shows a one-line graph row.

## The seeded vocabulary (13 types)

| type | inverse | backlink | meaning (B is …) |
|---|---|---|---|
| `upstream` | `downstream` | full | the codebase A derives from — **code lineage only** |
| `component` | `solution-tracker` | full | a component repo of solution tracker A |
| `sub-repo` | `parent-workspace` | full | a sub-repo committed inside workspace A |
| `spec-source` | `spec-mirror` | full | the repo authoring specs A aggregates |
| `contracts` | `contract-consumer` | compact | the contracts A conforms to |
| `live-test-service` | `consumer` | full | the live service A tests against |
| `service-backend` | `service-client` | full | a runtime service A calls |
| `deploy-tooling` | `deploy-target` | full | the tooling that deploys A |
| `ops-manual` | `documented-app` | full | the operations manual documenting A |
| `tooling` | `tool-user` | full | dev tooling A uses |
| `sibling-reference` | *(self)* | full | a peer artifact to keep reconciled |
| `subject` | `studied-by` | compact | the system A studies or documents |
| `oss-reference` | `referenced-by` | off | an OSS reference clone A consults |

Backlink rationale (grilled 2026-08-16): `contracts` and `subject` default **compact**
so hub repos keep whole-neighborhood awareness at one line instead of unbounded
backlink lines (a spec repo's consumers, everything that studies RMOS); `upstream` was
deliberately narrowed to code lineage — analysis/docs repos point at their subject with
`subject`, so "downstream" backlinks stay meaningful (a fork tracks you; a notebook
does not).
