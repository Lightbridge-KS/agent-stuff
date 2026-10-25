---
summary: Form/code F1–F4 tracker — controlled native fields, numeric drafts, selectable source/JSON panels and example migration.
read_when:
  - implementing or resuming reusable form and code utilities
  - checking form/code acceptance evidence and remaining work
---

# Form and code utilities

Parent: [v1](v1.md). Contract: [approved design](../design/form-code-utilities.md).
Both attention decisions approved 2026-10-25. Implementation is prepared for draft-PR review.

- [x] F1: shared field semantics; radio/select/checkbox controls; compatible Range.
- [x] F2: shared numeric parser, draft-preserving field and guarded calculation.
- [x] F3: strict JSON/source panel, exact selection and update/empty/error behavior.
- [x] F4: migrate settings/calculator/Python; references, regression checks and saved examples.

Evidence: `_playground/2026-10-25_form-code-utilities/`.

## Evidence and result

- Runtime 0.4.0 adds the approved fields/helper/panel and public TypeScript types.
  State, domain calculations, reset and snapshot policy remain artifact-owned.
- F1: strict TypeScript/Biome, native keyboard/group isolation, required/disabled/
  null/stale catalog/reset/native validity and label/help/error checks passed.
- F2: the parser preserves empty/incomplete/invalid drafts, rejects unsafe and
  rounded fractional integer literals, and pauses invalid calculations. Numeric
  native validity, blur/change error timing and blur-to-button reset passed.
- F3: strict JSON serialization, literal source, independent exact selection,
  no focus theft on updates, empty/invalid/null/wrap recovery passed.
- F4: settings/calculator/Python migrated. `outputs/final/results.json` records
  32 Chromium checks (four fixtures, six width/theme combinations, narrow
  containers and behaviors); `outputs/examples-final/` repeats the integrated
  example with additional assertions. Six example fixture screenshots inspected.
- 24 Node tests pass, including deterministic builds and existing chart/diagram
  regressions. TypeScript/Biome, 22 Python CLI tests, eight packaging tests, Python
  format/lint/types, package dry-run and repository validation pass.
- Existing chart acceptance: 32 checks; diagram acceptance: 50 checks.
- `examples-check.json`: 18 scenarios; `gallery-check.json`: 40 scenarios. Both
  include baseline theme/isolation/request/accessibility checks. The full gallery
  theme/axe baseline covers its initial panel; dedicated fixtures supply the
  form/code matrix. These are complementary scopes.
- Live CLI acceptance passes: reviewed snapshot/retry/receipt/schema boundaries,
  native dialog keyboard containment, theme/input state, isolated frame, export
  and standalone rebuild, lineage, reopen without Node/source, and stop.

## Saved examples

`examples-sample.json` and `gallery-sample.json` identify the immutable saved
revisions and archived source/toolchains. Final example ID: `4503a4e032f84f6e91498caf46d69e5e`; gallery ID: `85efda8648784fc48802a28d6a94dad2`. Evidence lives in
`_playground/2026-10-25_form-code-utilities/`. The in-app browser verified unfinished
`1e` remains visible while calculation/JSON pause, Reset restores 85%, and Select
text selects the configuration textarea. Native screenshots are in `outputs/`.

## Limits

Native Safari and manual screen-reader review were not run. Hosted CI was not run.
Human taste review remains open. No registry installation, release or fleet sync occurred. No dependencies or bridge behavior changed.
