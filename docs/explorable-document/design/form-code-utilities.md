---
summary: Implemented form and code utilities — controlled native fields, explicit numeric drafts, selectable JSON/source panels, three review examples and acceptance slices.
read_when:
  - reviewing or implementing reusable form and code utilities
  - deciding number-input, field error, JSON preview or selection semantics
  - migrating the settings, calculator and code examples into maintained components
status: implemented
date: 2026-10-25
---

# Form and code utilities

**Status: implemented in runtime 0.4.0; acceptance in [F1–F4](../progress/form-code-utilities.md).**
Parent: [implemented design](overview.md). References: the settings/JSON, calculator
and Python-code screenshots in the [component gallery](../tests/component-gallery.md).
Design mockups/evidence live in `_playground/2026-10-25_form-code-design/`.

## Scope and ownership

The kit exports five components from `@explorable/kit`: `RadioGroup`, `SelectField`,
`NumberField`, `CheckboxField`, `CodePanel`; one pure `readNumber` helper; and
compatible help/error/disabled/ID styling additions to the existing `Range`.

The first four share an internal field shell for labels, instructions, errors and
IDs. Keep numeric parsing beside NumberField: the component and calculations must
agree on validity. Keep CodePanel serialization/selection in a separate module;
its source can be a form, query result or static explanation.

The document owns values, domain rules, derived results, layout and optional snapshot.
Components emit local typed React callbacks. They provide no form schema engine,
central form store, implicit submit, automatic agent call, persistence or validation
of domain-specific calculations. Reuse Figure/Section/ordinary HTML for composition.
No dependencies or bridge changes were added.

## Three examples

### A. Agent settings → live JSON

Recreate the reference's provider/behavior choices, temperature, output-token select
and two boolean options. Keep the settings in one authored object. Each change
updates CodePanel from that object; it does not apply settings to a real agent.

```text
Agent settings
Model provider
(●) OpenAI    ( ) Anthropic    ( ) Google

Agent behavior
( ) Chat assistant    (●) Tool-calling agent    ( ) Workflow

Temperature   0.3        ─────●────────────────
Max output tokens                       [4,096 ▾]
[✓] Enable tool calling
[✓] Enable streaming output

Live configuration                  JSON · Read only
                                        [Select text]
{ "provider": "OpenAI", ... }
```

```tsx
<RadioGroup label="Model provider" value={config.provider}
  options={providerOptions} layout="row"
  onChange={provider => setConfig({ ...config, provider })} />
<SelectField label="Max output tokens" value={String(config.max_tokens)}
  options={tokenOptions} required
  onChange={id => { if (id !== null) setConfig({ ...config, max_tokens: Number(id) }); }} />
<CheckboxField label="Enable streaming output" checked={config.streaming}
  onChange={streaming => setConfig({ ...config, streaming })} />
<CodePanel title="Live configuration" value={config} />
```

Select option IDs are strings; converting an ID to a domain number belongs to the
artifact. The option catalog guarantees which IDs are meaningful. Provider choices
and reset values remain explicit; no component chooses a provider automatically.

### B. Numeric editing → guarded calculation

Use two illustrative counts: true positives 85 and false negatives 15. The initial
ratio is 85%. The controls retain raw text. A complete zero is distinct from an
empty or unfinished input; two zero counts produce an undefined ratio.

```text
True positive · Required             False negative · Required
[85                         ]         [15                        ]
Whole count from 0 to 1,000,000.       Whole count from 0 to 1,000,000.

Sensitivity   85.0%
```

Clearing a field pauses the result/derived JSON rather than treating blank as zero.
Typing `-` or `1e` preserves the draft. A decimal count such as `2.5` reports an
integer constraint error. Inline validation appears on blur by default; calculation
validity is available immediately. A separate disabled-field specimen demonstrates
retained values and explanatory help without silently changing the calculation.

**Approved numeric contract:** keep NumberField's controlled value as raw text and expose `readNumber` for the parsed result; never clamp, coerce blank to zero, or replace unfinished drafts with the last valid number.

```tsx
const countRules = { min: 0, max: 1_000_000, integer: true, required: true };
const [tpText, setTpText] = useState('85');
const tp = readNumber(tpText, countRules);

<NumberField label="True positive" value={tpText} onChange={setTpText}
  {...countRules} help="Whole count from 0 to 1,000,000." />

// Calculate/serialize only when every required reading has status === 'valid'.
// If the valid denominator is zero, report an undefined result, not an input error.
```

### C. Code/text panels → deliberate selection

Use the same panel for a live JSON object and a display-only Python example. A
read-only, labeled textarea is the first body implementation: complete text, native
selection/scrolling, quiet monospace styling and a visible focus indicator.

```text
Report service sample               Python · Read only
                                        [Select text]
class ReportService:
    def generate(self, result):
        return {"conclusion": result.conclusion}
```

```tsx
<CodePanel title="Report service sample" code={pythonSource} language="Python" />
<CodePanel title="Live configuration" value={config} />
```

**Approved code-panel contract:** start with plain selectable source and deterministic JSON, using “Select text” plus the system copy shortcut. Clipboard bridging, syntax highlighting and execution require separate extensions.

This intentionally changes the Python example's current manually colored spans to
plain text. The screenshot's Run/Copy icons do not imply corresponding capabilities.
Do not present an enabled Run action or label selection as successful copying.
The current viewer explicitly denies `clipboard-write` to the opaque child and has
no clipboard bridge; this tranche preserves that boundary.

## Form catalog contract

All controls require a nonempty visible label. Shared optional props are `id`,
`help`, `error`, `disabled=false`, `required=false`, `className`, except Range has no
required prop because it always has a numeric value.

| Component | Required value/action | Other props/defaults | Representative intent |
|---|---|---|---|
| RadioGroup | `value: string|null`, `options`, `onChange(value: string)` | `layout='column'` or `row`; option description/disabled | Choose one provider; choose an agent mode |
| SelectField | `value: string|null`, `options`, `onChange(value: string|null)` | `placeholder='Choose an option'`; option disabled | Choose an output limit; choose a dataset column |
| NumberField | `value: string`, `onChange(raw: string)` | `min`, `max`, `integer=false`, `validation='blur'` or `change` | Enter whole counts; edit a decimal assumption |
| CheckboxField | `checked: boolean`, `onChange(checked: boolean)` | Shared field props | Enable a feature; choose streaming output |
| Range | Existing `label/value/min/max/onChange` contract | Existing step; additive `id/help/error/disabled/className` | Explore a probability; adjust temperature |

Options use `{value: string, label: string, disabled?: boolean}`; RadioGroup may add
`description?: string`. IDs/labels are nonempty; values unique within a group. Up to
12 radio options or 200 select options keep these native controls bounded. Empty
catalogs have an explicit unavailable state. Unknown selected IDs, duplicates,
invalid constraints or prop types receive diagnostics; no silent first-option fallback.

- `id` identifies a single input/select, or a RadioGroup fieldset. Internal IDs for
  radio options/help/errors are generated and scoped. Native radio names are also
  generated, so separate groups can reuse values without becoming one browser group.
- RadioGroup uses fieldset/legend and native radio inputs. It emits only a newly
  chosen string; clearing an optional group is an authored reset to null. It does
  not implement a second custom keyboard model.
- SelectField renders native select/options. Null is a real unselected state.
  The optional placeholder can be chosen to clear; required mode disables that
  placeholder after a choice. Disabled options cannot be newly chosen. A previously
  chosen now-disabled option remains visible without silently changing its value.
- CheckboxField is a native two-state checkbox. There is no indeterminate-state API.
- Disabled controls retain authored values; whether those values contribute to a
  derived configuration is an explicit artifact rule. Hiding a conditional control
  also does not implicitly erase state. Reset is authored state assignment.
- Standalone controls create no form element. An authored HTML form owns its submit
  handler, native validity checks, domain validity and focus/error-summary policy.
  Components never perform a network submit.

## Numeric parsing and error contract

```ts
type NumberRules = { min?: number; max?: number; integer?: boolean; required?: boolean };
type NumberReading =
  | { status: 'valid'; value: number; error: null }
  | { status: 'empty'; value: null; error: string|null }
  | { status: 'incomplete'|'invalid'; value: null; error: string };
function readNumber(raw: string, rules?: NumberRules): NumberReading;
```

Use a native text input with `inputMode='numeric'` for integer fields or `decimal`
otherwise. No spinbutton role or custom increment keyboard behavior is implied.
This preserves drafts consistently rather than relying on number-input sanitization.

- Trim outside whitespace for parsing while preserving displayed text. Empty stays
  empty; required emptiness has an error, optional emptiness has no field error.
- Accept a complete signed decimal/scientific literal using ASCII digits and a dot.
  Examples: `85`, `-2.5`, `.5`, `1.`, `1e3`. Incomplete signs/decimal prefixes or
  exponents (`-`, `.`, `1e`, `1e-`) have no numeric value yet.
- Reject nonfinite results, partial parses (`12x`), expressions, comma grouping,
  fractions, and values violating bounds or integer rules. A complete `0` is valid
  when allowed. No snapping, clamping, rounding or locale guessing.
- Min/max must be finite and ordered. Integer literals must be whole and parse to a safe integer; fractions that round to integers are rejected; a decimal may
  still have the normal finite IEEE-754 precision of JavaScript. Step validation
  and numeric steppers are outside this initial NumberField contract; use Range
  when bounded stepping is the intended interaction.
- NumberField and readNumber use the same parser/rules. The input's native custom
  validity reflects required/parse/constraint errors; optional emptiness remains
  natively valid. Custom domain `error` also marks the field invalid.
- Lay out the current numeric error before revealing it, so blur does not move a
  nearby button between pointer-down and click. Hidden error text is not exposed
  as an accessible description until shown.
- Automatic numeric errors appear after blur by default, then update as the draft
  is corrected. `validation='change'` requests immediate display. Native invalid
  events also reveal the error. Explicit `error` is displayed immediately and
  takes precedence over automatic copy; it does not make an invalid parse valid.
- For other controls, authored `error` supplies business/required error copy. Displayed
  errors are linked by aria-describedby and aria-invalid; required native semantics
  remain available even before an inline error is requested. Avoid per-keystroke
  alert/live-region chatter.

Derived output must explicitly handle empty/incomplete/invalid states. If previewing
an older valid result is useful, label it as an older result. The default examples
pause output and disable text selection for an empty preview; they do not show stale
JSON as current or serialize invalid numeric values as null without explanation.

## Code panel catalog contract

| Required | Optional/defaults |
|---|---|
| `title` plus exactly one of `code: string` or `value: JsonValue` | `id`, `language='Text'` for code; `note`, `wrap=true`, `className`, `emptyMessage='No text to display'` |

`value` implies JSON and a fixed JSON label. It does not also accept code/language.
`JsonValue` contains strings, booleans, null, finite numbers, dense arrays and plain
string-keyed objects. Serialize with two-space indentation and insertion order.
Reject undefined/functions/symbols/bigints, cycles, sparse arrays, nonfinite numbers
and nonplain objects rather than silently dropping/coercing them. Rendering/copy
selection uses one derived string. Limit source/rendered text to 100,000 characters
and JSON nesting to 12; overflow is a readable diagnostic, never silent truncation.

- Title labels the read-only textarea. The header identifies format and read-only
  state; language is metadata, not a syntax-highlighting promise.
- Wrap on small screens by default; wrap=false uses native horizontal textarea
  scrolling. The body grows with line count up to 16 rows, then scrolls natively.
  Native resize remains available. Source line endings normalize to LF for display
  and selection; the original authored source remains canonical.
- Select text focuses/selects the complete textarea value using a local ref. It does
  not read/write the clipboard or message the viewer. Status says "Text selected;
  use the system copy shortcut", never "Copied". Browser text menus also work.
- Empty text disables selection; JSON null is the valid text `null`, not empty.
  Invalid JSON input shows a diagnostic and disables selection, without a stale body.
- Content updates do not focus or select automatically. Clear old selection-status
  copy when content changes; retain ordinary editing focus in the source controls.
- Two panels have independent refs/IDs. Strings containing HTML remain literal text.
  There is no editor, search, line gutter, diff engine, code execution or clipboard
  message added to the bridge.

## Accessibility and visual contract

Use the Neutral Canvas palette, visible labels, native focus/disabled states, and
help/error text adjacent to the relevant input. Native check/radio affordances stay
visible. Radio rows wrap; number-field grids stack in narrow containers. Select
carets have a comfortable inset. No placeholder-only labels, custom combobox menu,
color-only errors, whole-card input selection or automatic focus on rerender.

These choices follow WAI [labels](https://www.w3.org/WAI/tutorials/forms/labels/),
[grouping](https://www.w3.org/WAI/tutorials/forms/grouping/) and
[error notification](https://www.w3.org/WAI/tutorials/forms/notifications/) guidance.
The [HTML number-state rules](https://html.spec.whatwg.org/multipage/input.html#number-state-(type=number))
explain why a raw numeric-draft contract is explicit. These references guide the
proposal; they do not constitute browser or screen-reader acceptance evidence.

## Implementation slices

1. **F1 — field foundation:** native radio/select/checkbox controls; shared labels,
   help/error/disabled/required semantics, unique IDs/group names; compatible Range
   additions. Verify existing slider examples and independent sibling groups.
2. **F2 — numeric drafts:** pure parser, NumberField, native validity, error timing,
   guarded calculation/JSON recipe and incomplete/boundary fixtures.
3. **F3 — code panel:** deterministic strict JSON/source text, independent selection
   refs, empty/error/update behavior, wrapping/scrolling and literal-text fixtures.
4. **F4 — integration:** migrate settings, calculator and Python code panel; keep
   calculations/snapshot policy authored; document recipes and save new example/gallery
   revisions. Historical saved artifacts retain their frozen runtimes.

Ownership: `runtime/form/` (field shell/controls/parser) and `runtime/code/`
(text derivation/panel), re-exported from kit.tsx. Range may delegate to the field
shell but must preserve its current value/callback behavior and existing checks.
No generic form store or cross-module preview controller is needed.

Acceptance: all examples as initial fixtures at 390/768/1280 in dark/light, plus a
narrow container on a wide page. Verify actual label/help/error relationships;
native keyboard/pointer behavior; no radio-group collisions; required/optional/null
and disabled/reset behavior; numeric preservation and finite/boundary cases;
blur-to-button behavior without layout-shift lost clicks; no invalid calculations; code serialization and exact selection ranges; no focus theft
on live updates; wrapping/scroll access; no execution/clipboard/bridge side effects;
existing chart/diagram/range and runtime/CLI/package checks. Report Chromium, native
Safari and manual screen-reader evidence separately; human taste remains a review step.
