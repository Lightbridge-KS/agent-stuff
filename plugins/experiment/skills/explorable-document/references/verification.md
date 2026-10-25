# Verification

`check` performs descriptor/boundary validation, strict TS/TSX checking, MDX
compilation, and fixed-toolchain bundling. It does not execute arbitrary source tests
on the host. `check --browser` runs the maintained Chromium runner over `checks.json`,
checks frame isolation, themes, responsive overflow, runtime errors/requests, and an
accessibility scan. Missing browser tooling fails explicitly. Install Chromium into
the ordinary Playwright cache from a disposable copy of the pinned runtime:
`pnpm exec playwright install chromium` (Linux CI may also require system libraries).

`checks.json` version 1 has scenarios naming declared interaction IDs. Each scenario
starts with a fresh page and contains bounded steps:

```json
{"version":1,"scenarios":[{"interaction":"arrival-rate","steps":[
  {"action":"fill","selector":"input[type=range]","index":0,"value":"6"},
  {"action":"text","selector":"#scenario-summary","value":"Mean jobs in system: 3.00."}
]}]}
```

Actions: `click`, `fill`, `select` (native option value), `press`, `text` (exact textContent), `value` (exact input
value). Index defaults 0. Every scenario must include an assertion, and every primary
interaction needs a passing scenario. Cover meaningful edge cases and use independently
computed expectations. Build checks do not prove semantic correctness of arbitrary
calculations. The maintained fixtures include independent queue-model checks.

Before delivery inspect screenshots and exercise keyboard interactions. Check charts
and text agree, units/provenance are clear, empty/reset states work, and resizing
preserves relationships. Dark/light and 390px/1280px are the baseline. Record native
Safari separately; Chromium or Playwright WebKit is not native Safari evidence.
Human taste remains a review step, even when technical gates pass.

A saved artifact reports static and browser results independently. Supplied evidence
is matched by hashes, not cryptographically attested. Do not present edited evidence
or assertions that merely mirror implementation as independent verification.

## Runtime maintenance

Copy `runtime/` into a disposable working directory; install there with
`pnpm install --frozen-lockfile --ignore-scripts`. Run `pnpm lint`, `pnpm typecheck`,
and `pnpm test`. The dry tests compile both formats, test forbidden imports, compare
five fixed-source builds, check the queue model, and exercise pure diagram geometry. Python contracts live at
`tests/test_explorable_document.py`; `just test` includes them. Browser checks are
live gates and are requested explicitly, not silently folded into PR CI.

For changes to the diagram kit, also run `pnpm test:diagrams <evidence-directory>`
in the disposable runtime. This compiles each of the six maintained recipes plus
one lifecycle fixture, then checks 390/768/1280 px in dark/light, narrow containers,
real endpoint clearance, node/label collisions, connector crossings, accessibility,
resize overflow, invalid references, hidden/removed endpoints, input preservation
and observer quiescence. `DIAGRAM_CASES=Workflow,Architecture` narrows a debugging run;
a final acceptance run omits that filter. Screenshots and `results.json` are retained
in the chosen evidence directory. The gallery's own interaction suite remains separate.

The bridge uses an exact child window and a private MessageChannel, protocol/session
identity, bounded messages, and one outstanding snapshot request. The frame cannot
access parent DOM/storage/receiver credentials. CSP blocks tested direct fetches,
forms, popups, nested frames, and parent navigation; arbitrary self-navigation and
resource exhaustion are outside the guarantee. A clean trace proves only the tested
paths. Review generated source; do not use sensitive data or call this a hostile-code
sandbox.

For chart changes, run `pnpm test:charts <evidence-directory>` in the disposable runtime.
The four initial fixtures cover 390/768/1280 in dark/light, narrow containers,
independent coordinate/count expectations, mouse/touch/native keyboard inspection,
focus/state through resize/theme changes, controlled scope, null gaps, exact precision,
zero/tiny/empty/invalid data, long labels and recovery. `CHART_CASES=Trend,Parts`
limits a debugging run; omit it for final acceptance.

For form/code changes, run `pnpm test:forms <evidence-directory>` in the disposable
runtime. Fields, Numeric, Code and Examples fixtures cover 390/768/1280 in both
themes and a 350px container, native keyboard/group behavior, labels/descriptions,
required/disabled/stale/reset values, numeric draft preservation/native validity,
blur-to-button clicks, independent exact selection, live-update focus and code
error/empty/wrap behavior. `FORM_CASES=Numeric,Code` narrows debugging only; omit it
for final acceptance. Numeric parsing and strict JSON serialization also have pure
Node tests. Native Safari and manual screen-reader evidence remain separate.
