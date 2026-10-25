# Accessible charts

Import `ChartFrame`, `LinePlot`, `SegmentedBar` from `@explorable/kit`. The frame owns
its figure surface; use it directly without another Figure wrapper. One readonly
model drives marks, units, legend, inspection and an unrounded exact-data table.
Replace the model/arrays when values change. Calculations and fetching remain authored.

```tsx
const data: XYData = {
  kind: 'xy',
  x: { label: 'Day', items: [{ id: 'mon', label: 'Monday' }, { id: 'tue', label: 'Tuesday' }] },
  y: { label: 'Requests', unit: 'requests/day' },
  series: [{ id: 'requests', label: 'Requests', values: [1100, 1450] }],
};
<ChartFrame title="Agent performance" summary="Requests increased on Tuesday." data={data}
  note="Synthetic two-day example.">
  <LinePlot />
</ChartFrame>
```

## Public API

| Component | Required | Optional/defaults |
|---|---|---|
| ChartFrame | `title`, meaningful `summary`, `data`, one plot element | `controls`, `note`, `className`; XY selection props below |
| LinePlot | XY frame | `domain="auto"`, `includeZero={true}`; or explicit `domain={[min,max]}` without includeZero |
| SegmentedBar | Parts frame | No plot-specific props |

Public types: `ChartData`, `XYData`, `PartsData`, `ChartTone`, `ChartFrameProps`,
`LinePlotProps`, `SelectionChange`. Tones: blue, teal, orange, red, neutral. Default
series/segment tones cycle blue/teal/orange/red. Styles and marker shapes also
identify line series; color is not the only distinction.

XY model: `kind: 'xy'`; `x: {label, items: [{id,label}]}`;
`y: {label,unit}`; `series: [{id,label,tone?,values: (number|null)[]}]`.
Use 1–4 same-unit series, up to 200 equally spaced ordered categories, one value
per category. IDs must be unique and strings nonempty. Preserve null for missing
observations: it creates a gap, not zero or interpolation. Numeric/time X scales
are not implied by date labels. Use separate frames for different units.

Parts model: `kind: 'parts'`; `unit`; `segments: [{id,label,value,tone?}]`.
Use up to eight finite nonnegative counts. The bar derives proportions and total;
never supply percentages independently. Zero segments stay in HTML but have no
false mark. Tiny counts use scientific notation when necessary; tiny nonzero shares
show `<0.1%`. The exact table preserves the supplied number representation.

```tsx
<ChartFrame title="Expected outcomes" summary="Illustrative counts out of 100."
  data={{ kind: 'parts', unit: 'cases', segments: [
    { id: 'positive', label: 'Positive', value: 25, tone: 'teal' },
    { id: 'negative', label: 'Negative', value: 75, tone: 'blue' },
  ] }}>
  <SegmentedBar />
</ChartFrame>
```

## Selection and controls

- XY defaults to the first category. `defaultSelectedId` supplies an initial choice;
  an unavailable uncontrolled ID falls back to the first item, or null when empty.
- Linked views use `selectedId: string|null` plus `onSelectionChange(change)` together,
  mutually exclusive with defaultSelectedId. `change` is `{id, source:'control'|'plot'}`.
  A stale controlled ID gets a diagnostic; the frame does not silently change it or
  call the parent during render. Parts charts do not accept selection props.
- Native category select and Previous/Next operate the persistent inspector. Tab
  visits ordinary controls, not hundreds of SVG points. Native select keyboard
  behavior follows the browser/platform. Boundaries disable Previous/Next.
- Mouse preview does not change pinned selection or focus. Leaving restores the
  pinned value; control actions clear preview. Click/tap selects the nearest category
  inside the plot; touch scrolling/cancellation does not commit a selection.
- Preview clears on data changes. Matching category IDs preserve selection across
  series changes; sibling frames have independent contexts and generated DOM IDs.
- Authored selectors/calculators belong in `controls` or nearby document prose.
  Declare/test their primary effects and plot selection in the artifact descriptor.
  Native Exact data disclosure is built-in reference access, not an agent handoff.

## Geometry, alternatives and diagnostics

Geometry responds to container width in CSS pixels, retaining readable text. X ticks
thin/wrap as space changes; the inspector/table retain every category and full label.
The displayed scale is explicit. Auto domains include zero unless includeZero=false.
Explicit increasing finite bounds must contain observations. One-point/constant/signed
and all-zero data have defined behavior. Empty/all-null lines show an empty state;
zero parts total has no proportions. Invalid shapes/IDs/values/scales get diagnostics.
Fix the data or domain; do not suppress those messages or silently drop observations.

The frame provides a meaningful summary, named SVG, text legend, persistent readout,
polite announcements for explicit selection and an exact table with caption/scoped
headers. Hover does not announce continuously. This foundation still needs truthful
summary/provenance and checks of the actual content. Formatting is for presentation;
calculations use source numbers and the table preserves unrounded values.

For custom SVG with the same model, control selection in authored code and pass it
both to ChartFrame and the custom plot. Implement its geometry/pointer behavior
explicitly. Other chart semantics can use Figure/custom SVG. There is no public
scale engine, automatic aggregation, animation, hidden-series control or new package.

Maintained recipes and acceptance fixtures: `runtime/fixtures/charts/`. For runtime
changes run the normal dry gates plus `pnpm test:charts <evidence-directory>` in a
disposable installed runtime; see [verification](verification.md). Chromium checks,
native Safari and manual screen-reader evidence must be reported separately.
