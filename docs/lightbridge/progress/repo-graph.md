---
summary: >-
  Progress tracker for the repo-graph build: per-project [repo-links] adjacency lists
  become one central typed-edge SSOT (~/.lightbridge/graph.toml) that projects every
  repo's injected ego view plus curated backlinks. Milestones with commit SHAs;
  confirmed contracts; deferred items.
read_when:
  - resuming or continuing the repo-graph build (feat/repo-graph)
  - checking what the repo-graph effort shipped vs deferred
  - touching lb_graph.py, load_graph, the graph verbs, or the repo_links projection
---

# repo-graph — progress

Authorized by the approved build plan (2026-08-16) following the spike at
`_playground/2026-08-16_repo-graph-spike/` (graph assembled from 72 live
declarations; 25 drifted one-ways measured) and a grilled decision session — all
nine taste decisions recorded in the spike's NOTES.md. ADR:
`docs/lightbridge/adr/0002-central-repo-graph.md` (M6). Design doc:
`docs/lightbridge/lightbridge-graph.md` (M6). Branch: `feat/repo-graph`.

The unlock: a bidirectional relationship authored twice with no shared identity
*must* drift; one typed edge with declared inverses regenerates both repos'
views, so the reverse direction can never be forgotten — only curated.

## Milestones

- [x] M1 — reader + bootstrap + read verbs: `load_graph`/`project_node`/`DEFAULT_GRAPH`
      in `lb_resolve.py` (frozen-API amendment), new `lb_graph.py`, verbs
      `lb graph init|show|types`, `tests/test_lb_graph.py`, justfile entry — 6fef2a2
- [ ] M2 — projection rewrite: `repo_links.py` reads graph.toml (full/compact/off
      backlinks, per-edge override, legacy `[repo-links]` deprecation warning),
      hook flow updated, `tests/test_repo_links.py` rewritten
- [ ] M3 — write verbs: `lb graph link|unlink|set` with teaching refusals,
      direction-echo sentence, byte-preservation tests
- [ ] M4 — graph-wide reads: `lb graph doctor|mermaid|html`, `lb status` graph line
- [ ] M5 — migration (throwaway, in the spike session): backups, graph.toml written,
      9 registry names added, `[repo-links]` sections stripped, ego-regression
      report reviewed, doctor clean
- [ ] M6 — skill + docs: `repo-graph` skill, lightbridge-config catalog update
      (remove `[repo-links]` from catalog + `SECTIONS` in lockstep), ADR 0002,
      design doc, READMEs, epilog, `__version__` bump, agent-instruction sync
- [ ] Gates: `bin/validate.py` + full `just test` green

## Confirmed contracts

- **One edge, two projections** — an edge A -[type]-> B renders in A's session as
  `(type)` + from_note and in B's as `(inverse)` + to_note; proven by the spike's
  ego-check round trip for RMOS and orthanc-test-pacs.
- **Backlink is 3-mode** (`full | compact | off`), per-type default with per-edge
  override; `subject` and `contracts` default compact, `oss-reference` off.
- **`[types]` lives in graph.toml** — the SSOT is self-describing; the tool
  validates, never defines.
- **Hook registration is untouched** — `repo_links.py` stays the projection engine
  the hook imports; `hook.toml` and settings registration unchanged.

## Deferred (out of this effort)

- Multi-machine graph sync — graph.toml is per-machine like the rest of
  `~/.lightbridge`; see `docs/lightbridge/multi-machine-sync.md` (deferred design).
- `lb graph add-type` verb — the vocabulary is hand-edited in graph.toml;
  doctor validates. Revisit if type churn proves real.
