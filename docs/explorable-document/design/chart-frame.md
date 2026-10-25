---
summary: Implemented accessible chart frame — shared data, exact-value tables, persistent inspection, line and segmented-bar examples, and acceptance slices.
read_when:
  - reviewing or implementing the accessible chart frame
  - choosing chart data, inspection, responsive or accessibility contracts
  - migrating the dashboard and simulator charts into maintained components
status: implemented
date: 2026-10-25
---

# Accessible chart frame

**Status: implemented in runtime 0.3.0; acceptance in [C1–C4](../progress/chart-frame.md).**
Parent: [implemented design](overview.md). Starting evidence:
[component gallery](../tests/component-gallery.md), especially the dashboard and
simulator references. Design mockups live in the ignored
`_playground/2026-10-25_chart-frame-design/` session.

## Aim and boundary

Make a small chart easy to understand, inspect and verify in an explorable document.
The plot, units, legend, readout and exact-value table must agree after every update.
Preserve the Neutral Canvas theme and ordinary MDX/TSX composition.

**Approved scope:** implement `ChartFrame`, `LinePlot` and `SegmentedBar` first, using the fixed React/SVG catalog. Add other chart types when a concrete example requires them.

`ChartFrame` owns the figure surface; it is used directly rather than nested inside
`Figure`. It owns one dataset, accessible title/summary, legend, inspection, exact-data
disclosure and optional note. `LinePlot` and `SegmentedBar` consume the frame's model;
they do not accept independent arrays. Keep their shared data and interaction
knowledge together in one chart module. Business calculations and data fetching stay
in the authored document.

This is a maintained component family inside the existing open-ended document body.
The agent selects a plot and supplies typed data/copy. The runtime controls the
frame composition and built-in behavior. Existing sandbox and optional snapshot
boundaries apply; chart actions remain local React callbacks.

## Three review examples

### A. Agent performance — one series at a time

Reference: `dashboard-metrics-and-line-chart.png`.

```text
Agent performance                        [Requests] [Errors]
Requests increase from 1,100 on Monday to 2,750 on Sunday.

Requests / day       ───── line with observed-point markers ─────
                      Mon   Tue   Wed   Thu   Fri   Sat   Sun
Legend: — ● Requests

Inspect day  [Sunday ▾]       [Previous] [Next (disabled)]
Sunday · Requests: 2,750 requests/day
▸ Exact data
Synthetic 7-day data. Errors values are illustrative.
```

- The Requests/Errors selector is authored native HTML in the frame's controls slot.
  It supplies a different model and summary; the frame does not invent series filters.
- Requests and Errors have different ranges. Each view declares its unit and uses
  its own visible axis scale. There is no dual axis or claim of a shared scale.
- Selection is the category ID (`sun`), so switching series keeps the same day.
  The visible readout, point highlight and table all reflect the current model.
- Metric cards above the chart remain authored composition; this tranche does not
  add a metric-card component.

```tsx
<ChartFrame
  title="Agent performance"
  summary={summaryFor(activeMetric)}
  data={models[activeMetric]}
  controls={<MetricChoice value={activeMetric} onChange={setActiveMetric} />}
  note="Synthetic 7-day data. Errors values are illustrative."
>
  <LinePlot />
</ChartFrame>
```

`MetricChoice`, models and summaryFor above are authored code, not new kit exports.

### B. Expected outcomes — one part-to-whole bar

Reference: `simulator-diagnostic-inputs-and-outcomes.png`.

```text
Expected outcomes
Illustrative expected counts for a population of 100.

[ True positive 17% ][ FP 8% ][       Test negative 75%       ]

TP · True positive       17       17%
FP · False positive       8        8%
N  · Test negative       75       75%
Total                  100
▸ Exact data
Test negative combines true negatives and false negatives.
```

- Existing simulator controls/calculations supply 17, 8 and 75. The chart computes
  only the total and display proportions. The frame accepts counts, not a second
  independently supplied list of percentages.
- The legend lists every segment's label, count and share; tiny segments are never
  forced to a minimum visual width. Zero segments stay in the legend/table.
- At total zero show "Total: 0 — no proportions to display", with zero counts and
  shares marked unavailable. Do not divide by zero or turn missing data into zero.
- This chart needs no point-selection control: all of its values are already listed.
  Calculated metrics such as PPV remain outside the chart module.

```tsx
<ChartFrame
  title="Expected outcomes"
  summary={`Illustrative expected counts for a population of ${population}.`}
  data={{
    kind: 'parts', unit: 'expected cases',
    segments: [
      { id: 'tp', label: 'True positive', value: result.tp, tone: 'teal' },
      { id: 'fp', label: 'False positive', value: result.fp, tone: 'red' },
      { id: 'negative', label: 'Test negative', value: result.negative, tone: 'blue' },
    ],
  }}
  note="Synthetic arithmetic. Test negative combines true and false negatives."
>
  <SegmentedBar />
</ChartFrame>
```

### C. Comparison with a missing observation

An additional fixture exercises a reusable capability absent from the screenshot.

```text
Response time: baseline and candidate
The candidate is lower on Sunday. Baseline has no Wednesday observation.

ms          — ● Baseline       - - □ Candidate
            Two lines on the same 0–200 ms scale; baseline breaks at Wed.

Inspect day  [Wednesday ▾]      [Previous] [Next]
Baseline: No observation       Candidate: 130 ms
▸ Exact data
```

Use category IDs for one ordered week. Baseline values are
`[120,150,null,180,190,160,170]`; candidate values are
`[110,135,130,170,165,155,150]` milliseconds.

- `null` breaks the line and is "No observation" in the readout/table, never zero.
- Line style and marker shape supplement color. The inspector shows every series
  for the same category; readers need not select lines one at a time.
- A read-only legend identifies series. Hidden-series toggles are not implicit.
  Compare different units in separate frames.

```tsx
<ChartFrame title="Response time" summary={comparisonSummary} data={comparisonData}>
  <LinePlot />
</ChartFrame>
```

## Dataset and API contract

```ts
type ChartTone = 'blue' | 'teal' | 'orange' | 'red' | 'neutral';
type XYData = {
  kind: 'xy';
  x: { label: string; items: readonly { id: string; label: string }[] };
  y: { label: string; unit: string };
  series: readonly {
    id: string; label: string; tone?: ChartTone;
    values: readonly (number | null)[];
  }[];
};
type PartsData = {
  kind: 'parts'; unit: string;
  segments: readonly {
    id: string; label: string; value: number; tone?: ChartTone;
  }[];
};
```

| Component | Required | Optional/defaults |
|---|---|---|
| ChartFrame | `title`, `summary`, `data`, one plot child | `controls`, `note`, `className`; XY selection contract below |
| LinePlot | Matching XY frame | `domain="auto"` or `[min,max]`; `includeZero={true}` |
| SegmentedBar | Matching parts frame | No additional props in the first tranche |

`title`, `summary`, unit and label strings must be nonempty. Summary is authored
meaning/context, not generated analysis; it must update when controls change its
truth. Controls contain ordinary HTML/TSX, declared and tested as primary interactions
when they change chart data. Fixed kit copy includes "Inspect", "Previous", "Next",
"Exact data", "No observation" and diagnostics.

- XY supports 1–4 same-unit series and at most 200 ordered categories. Values align
  by category position; lengths must match. Category and series IDs are unique in
  their respective lists. Category spacing is equal: date labels do not imply a
  continuous or irregular time scale. Values may be finite signed numbers or null.
- Parts supports at most eight segments; unique IDs, finite nonnegative counts.
  Empty arrays are valid empty states. Negative/malformed/nonfinite values, duplicate
  IDs, incompatible plot/model and a domain excluding observations are diagnostics.
  Do not silently discard values, sort categories, aggregate, sample or impute data.
- XY defaults to the first category. Optional `defaultSelectedId` configures that
  initial choice. For linked views, supply both `selectedId: string | null` and
  `onSelectionChange({id, source: 'control' | 'plot'})`; they form a controlled pair,
  mutually exclusive with defaultSelectedId. Parts has no selection props.
- Each frame has its own context and generated DOM IDs; sibling charts can reuse
  category/series IDs without sharing selection accidentally.
- Dataset updates preserve a selected ID if it exists. An uncontrolled selection
  removed by an update falls back to the first remaining item, or null when empty.
  A stale controlled selection gets a diagnostic; the frame never calls the parent
  during render or silently changes the parent's value. Transient pointer preview
  is cleared on model change. Mounted controls retain DOM identity and focus.
- Exact-data table cells use unrounded supplied number representations and explicit
  units; null is "No observation". Tick labels and readouts may format for legibility;
  rounded values never feed calculations. Segment shares are derived and identified
  as rounded percentages. UI copy does not claim more measurement precision than
  the source provides.

Custom SVG remains possible inside a ChartFrame using the same model and a controlled
selection passed from authored code. Such a plot must implement its own geometry
and pointer behavior; the frame still owns the HTML inspector/table. No public scale
engine, renderer plug-in registry or context hook is proposed. For visuals that do
not fit XY or parts semantics, use the existing Figure/custom SVG path.

## Interaction and accessibility

**Approved interaction:** use a persistent inspector with a native category select and Previous/Next controls; add pointer preview and click/tap selection to LinePlot, with no floating tooltip in this tranche.

- Tab reaches normal controls, not hundreds of SVG points. The native select handles
  keyboard choice; Previous/Next have real disabled boundaries. No page-level key
  interception or application role. Clicking/tapping the plot selects its nearest
  category within the plot bounds; it never infers an agent handoff.
- Hover preview updates a readout in reserved normal-flow space. It does not steal
  focus or change the pinned selection. Pointer leave restores that selection.
  Touch tap and select/button choice persist. Keyboard/control selection ends hover
  preview so a parked mouse cannot override keyboard exploration.
- The inspector always labels category, series and unit. Its HTML display serves
  mouse, keyboard and touch. A separate polite announcement follows explicit
  selection actions; pointer movement and every intermediate simulator update do
  not create live-region chatter.
- The frame is an HTML figure containing normal controls. Only the plot SVG is an
  atomic graphic, with a short accessible name/description pointing to the summary
  and exact-data disclosure. Controls and table are outside that image role.
- The summary explains the relevant meaning; the table provides values and row/column
  relationships from the same model. A table alone does not replace a useful summary.
  The disclosure has a native summary; the table has a caption and scoped headers.
- Line styles/markers, text labels and selection outlines supplement color. A parts
  legend identifies every segment in order even when its mark is too small to label.
  Segment boundaries and marks need contrast review in both themes; zero-width and
  tiny marks rely on the complete HTML value list as well as the visual bar.

This design follows WAI guidance on short descriptions plus structured long
alternatives for [complex images](https://www.w3.org/WAI/tutorials/images/complex/)
and [table captions](https://www.w3.org/WAI/tutorials/tables/caption-summary/).
The persistent readout also avoids an overlay that obscures the chart. Any future
floating tooltip needs the dismissible/hoverable/persistent behavior described in
[WCAG hover/focus guidance](https://www.w3.org/WAI/WCAG22/Understanding/content-on-hover-or-focus.html).
These are design inputs; Chromium acceptance and remaining manual/browser evidence are recorded separately in the implementation tracker.

## Responsive rendering and edge states

Use measured container width and SVG coordinates in CSS pixels. Keep text/controls
at readable sizes; resize geometry rather than scaling the whole graphic. Reduce
visible X tick density while retaining endpoints and every item in inspection/table.
Reserve space for axes and never clip labels to make a chart fit. A long categorical
label may wrap or be omitted as an intermediate tick; its full text remains in HTML.
Controls wrap above the plot. Legends wrap below it. No horizontal page overflow.
The exact-data table can have a named keyboard-usable horizontal scroll region when
needed; narrow table layout must not hide columns or values.

Auto Y domains include all supplied series and zero by default, with explicit ticks.
An explicit `[min,max]` domain is mutually exclusive with `includeZero`; it must
contain every observation, have finite increasing bounds, and show those bounds.
Signed lines can span zero. One point renders as a marker; constants/all-zero series
get a finite nondegenerate domain. All-null or empty XY data shows a clear empty
state while preserving the available categories/table. Parts total zero is distinct
from an empty dataset. No drawing animation by default, crosshair-following popup,
nonzero baseline without an explicit domain or includeZero=false, or connected null gaps.

## Implementation slices

1. **C1 — frame/data:** model validation, figure slots, generated legend/table,
   empty/invalid states and standalone fixtures for each model.
2. **C2 — line/inspection:** measured axes, single-series plot, native inspection,
   pointer parity, controlled selection, comparison/null-gap fixture.
3. **C3 — parts/responsiveness:** segmented bar, derived totals/shares, tiny/zero
   segments, long labels, both themes and narrow containers.
4. **C4 — gallery/docs:** migrate dashboard and simulator charts, retain their
   calculation owners, document recipes and save a reviewed gallery revision.

Acceptance: 390/768/1280 px and a narrow container on a wide page; dark/light;
independent scale/coordinate/total expectations; every category reachable by native
controls; pointer/keyboard/touch parity; reduced motion; focus and selection through
resize/theme/data changes; missing/zero/negative/constant/one-point datasets;
empty and invalid data; exact table agreement; runtime/CLI/package checks and
reproducible builds. Exercise each fixture as an initial state. Chromium automation,
native Safari and manual screen-reader evidence must be reported separately.

`runtime/chart/` owns model, geometry, frame/plots and namespaced CSS;
`kit.tsx` re-exports the three components and public types. The runtime manifest is the version source of truth (0.3.0). No bridge or artifact schema
change is required.
