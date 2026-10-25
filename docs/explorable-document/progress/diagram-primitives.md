---
summary: Diagram primitives D1–D4 implementation tracker — approved explicit endpoints, presentational nodes, fixture gates and gallery migration.
read_when:
  - implementing or resuming the diagram primitives
  - checking diagram acceptance evidence and remaining work
---

# Diagram primitives

Parent: [v1 tracker](v1.md). Contract: [approved design](../design/diagram-primitives.md).
Both review decisions approved 2026-10-25. Implementation is prepared for draft-PR review.

- [x] D1: layout and surfaces; concept-grid/spectrum fixtures.
- [x] D2: explicit relationships; service-contract/distance fixtures.
- [x] D3: branches, responsive routing and failure cases; workflow/architecture fixtures.
- [x] D4: migrate the six gallery examples, document the API, publish the gallery.

## Evidence

Local evidence: `_playground/2026-10-25_diagram-primitives/`.

- **D1/D2:** layout/surface fixtures, simple and bidirectional relationships, strict
  TS builds and geometry tests passed. Contract/distance also passed the CLI browser runner.
- **D3:** 50 real-Chromium checks passed: seven fixtures (six recipes plus lifecycle)
  at 390/768/1280 px in dark/light; each in a 350 px container within a 1280 px page;
  and lifecycle/failure checks. Independent geometry assertions cover endpoint
  clearance, node/label intersections, connector crossings and overlapping lanes.
  Hidden endpoints defer paths; removal clears arrows; duplicates/missing references,
  self-loops and unplaceable labels produce diagnostics. Native input state/focus
  survives resize; keyboard disclosure and observer quiescence pass.
- **D4:** all six gallery diagrams use maintained primitives. All 37 existing gallery
  scenarios and initial-state dark/light phone/desktop checks pass. All six panels
  were inspected in the in-app browser. Final concept/contract presentation refinements
  have a separate focused matrix in `polish-evidence/`.
- **Dry gates:** runtime Biome/TypeScript pass; 12 Node tests pass (including five
  identical builds and seven geometry regressions); 22 Python CLI tests and eight
  packaging tests pass; Python format/lint/types and repository validation pass.
  Skill packaging dry-run includes the new modules/fixtures/reference.

`outputs/results.json` owns the complete diagram matrix; `gallery-check.json` owns
hash-bound gallery evidence. `sample.json` identifies the newest immutable saved
revision and its archived source. The editable gallery remains in
`_playground/2026-10-25_component-gallery/source/`; its `diagrams-sample.json` points
to the updated revision while the original `sample.json` preserves the initial study.

## Confirmed contracts and limits

- Border attachment points project into shared spans, so a wide parent can connect
  directly to separate branches. Bounded routing rejects obstructed/overlapping
  candidates instead of drawing through unrelated nodes.
- Labels copy explicit rectangle dimensions; DOMRect prototype properties cannot
  be assumed enumerable. Label bounds are tested in the actual browser.
- Only connector paint layers clip during the frame before a resize measurement;
  the canvas retains its routing gutters. This prevents transient horizontal overflow.
- No dependencies, bridge changes, persistent diagram state or graph editor were added.
- Native Safari has **not** been checked for this diagram revision. Chromium evidence
  does not establish native Safari or exact screenshot equivalence. Hosted CI was not run.
- Human taste review remains open. No skill registry installation, release or
  fleet sync was performed.
