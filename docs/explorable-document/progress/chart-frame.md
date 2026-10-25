---
summary: Chart frame C1–C4 tracker — approved shared data, native inspection, bounded line and part-to-whole plots, and gallery migration.
read_when:
  - implementing or resuming the accessible chart frame
  - checking chart acceptance evidence and remaining work
---

# Chart frame

Parent: [v1](v1.md). Contract: [approved chart design](../design/chart-frame.md).
Both attention decisions approved 2026-10-25. Implementation is prepared for draft-PR review.

- [x] C1: validated data, frame slots, legend, exact table and empty/invalid fixtures.
- [x] C2: measured line plot, native/pointer inspection, controlled selection and gaps.
- [x] C3: part-to-whole bar, totals, small/zero segments and responsive matrix.
- [x] C4: migrate dashboard/simulator, update guidance, save and show the examples.

Evidence: `_playground/2026-10-25_chart-frame/`.

C1: model/exact-value unit tests and strict build plus Chromium 390/1280 dark/light checks passed. The frame fixture includes XY, zero segments and empty categories.

C2: 24 Chromium checks passed (three fixtures across six width/theme combinations, narrow containers and interaction/lifecycle cases). Native type-ahead, button navigation, hover restoration, click/tap, controlled callbacks, missing gaps and data replacement were checked. Headless macOS native arrow-key popup behavior was not used as a portable assertion.

C3: 32 Chromium matrix/lifecycle checks passed across four fixtures, plus seven pure model/geometry tests. Tiny counts remain nonzero in the readout, zero segments have no false marks, and unrounded values stay in the table.

## C4 evidence

- Dashboard/simulator migrated; the three approved examples use the maintained kit.
- `outputs/results.json`: 32 Chromium checks across four initial fixtures at
  390/768/1280 dark/light, narrow containers and state/interaction cases.
- `examples-check.json`: nine scenarios plus phone/desktop theme, isolation,
  request and accessibility checks. `gallery-check.json`: 38 gallery scenarios.
- Pure geometry/model tests cover finite bounds, null gaps, zero/tiny counts,
  exact precision and malformed models. Runtime Biome/TypeScript and 19 Node tests pass (including reproducible builds);
  22 Python CLI tests, eight packaging tests, Python format/lint/types, package
  dry-run and repository validation pass.
- `check-gallery-model.mjs`: 2,060,602 independent arithmetic cases; a browser
  regression covers the floating-point cancellation defect fixed in the authored model.

## Contracts and limits

The frame owns one readonly model; authored code replaces data/arrays on change.
The plot, legend, inspector and table do not accept separate numeric sources.
Counts retain zero/tiny segments in HTML; total zero and missing observations are
explicit states. Controlled selection changes only through the supplied callback.
Hover is transient, tap/click is pinned, and a touch pan cancels selection.

Native Safari and manual screen-reader review were not run for this revision;
Chromium interaction/axe evidence is separate. Hosted CI was not run. Human taste
review remains open. No registry installation, release or fleet sync occurred.

## Saved review outputs

`sample.json` identifies the immutable three-example revision; `gallery-sample.json`
identifies the updated 13-screen gallery. Both retain archived source/toolchains and
hash-bound verification metadata. The component gallery also keeps `charts-sample.json`.

The in-app browser inspection covered the migrated dashboard and simulator, native
Next inspection, the comparison's missing observation and its exact-data table.
Screenshots are in `outputs/`; `chart-proof.jpg` is the final comparison view.
Implementation is prepared for draft-PR review.
