# Forms and code

Runtime 0.4.0 exports native controlled fields and read-only source/JSON panels from
`@explorable/kit`. The artifact owns state, calculations, resets and optional snapshot.
These helpers do not create a form store, submit data, configure an agent or persist inputs.

## Fields

Every field requires a visible `label` and a typed change callback. Shared optional
props: `id`, `help`, `error`, `disabled`, `required`, `className` (`Range` has no
`required`, because it always has a value). IDs are generated when omitted.

| Export | Controlled props | Other props |
|---|---|---|
| `RadioGroup` | `value: string \| null`, `options`, `onChange(string)` | `layout: 'column'` (default) or `'row'`; option description |
| `SelectField` | `value: string \| null`, `options`, `onChange(string \| null)` | `placeholder` (default `Choose an option`) |
| `CheckboxField` | `checked: boolean`, `onChange(boolean)` | Native two-state checkbox |
| `NumberField` | `value: string`, `onChange(string)` | `min`, `max`, `integer`, `validation: 'blur'` (default) or `'change'` |
| `Range` | `value/min/max: number`, `onChange(number)` | `step` (default 1); existing numeric behavior |

Options are `{value: string, label: string, disabled?: boolean}`. Radio options may
add `description`. Values/labels are nonempty; values are unique. Limits: 12 radios
or 200 select options. Unknown selected IDs and malformed catalogs show a diagnostic;
empty catalogs show an unavailable state. No component silently picks another value.
Required selects disable the unselected placeholder; optional selects allow clearing
to null. Disabled values remain visible. Radio names are scoped independently.

Shared `error` is an authored business/required error. It is visible immediately,
linked with `aria-describedby`, and participates in native validity. NumberField
also computes its own validity. Its automatic errors appear after blur/invalid by
default, then update while editing. Hidden numeric error geometry is reserved so
revealing it on blur does not move a nearby button before its click completes.

Use an authored `<form onSubmit={...}>` for native submit/validity and error-summary
policy. Components create no form or network submit. Reset by assigning authored
values; native form reset alone does not reset controlled React state.

## Numeric drafts

```tsx
import { NumberField, readNumber } from '@explorable/kit';
const rules = { min: 0, max: 1_000_000, integer: true, required: true };
const [countText, setCountText] = useState('85');
const count = readNumber(countText, rules);
<NumberField label="Count" value={countText} onChange={setCountText}
  {...rules} help="Whole count from 0 to 1,000,000." />;
// Calculate/serialize only if count.status === 'valid'.
```

`readNumber(raw, rules)` returns `{status, value, error}`:

- `valid`: finite number; error null.
- `empty`: value null; error only if required.
- `incomplete`: value null and an error; preserves prefixes such as `-`, `.`, `1e-`.
- `invalid`: value null and an error; no partial parses, comma guessing or expressions.

The input is native text with numeric/decimal inputMode, retaining the original
string. Parsing trims outer whitespace and accepts ASCII signed decimal/scientific
literals. No coercion, clamping or fallback to a last valid result. Integer literals
must be whole and parse to a safe integer; fractions that round to integers are
rejected. Decimal fields retain ordinary JavaScript finite-number precision.
Bounds must be finite/ordered. No step validation or steppers; use Range for bounded
stepping. Empty/invalid inputs pause the example's calculations; a valid zero
denominator is an undefined result, not an invalid field. Domain validity remains
an authored calculation/snapshot rule.

## CodePanel

```tsx
<CodePanel title="Configuration" value={config} />
<CodePanel title="Example" code={pythonSource} language="Python" />
```

Required: nonempty title and exactly one of `value: JsonValue` or `code: string`.
Optional: `id`, `note`, `wrap=true`, `className`, `emptyMessage`. `language` is
metadata for raw code only; a value always uses JSON. `JsonValue` and component/
field/number prop types are exported from the kit.

The labeled read-only textarea shows plain monospace text. JSON is serialized with
two-space indentation and insertion order. Finite numbers, null, booleans, strings,
dense arrays and plain string-keyed objects are accepted. Undefined/nonfinite/
nonplain values, cycles, accessors, symbols, sparse arrays or extra array properties
show a diagnostic; they are never silently omitted or coerced. Accessors/toJSON are
not invoked. Limit: 100,000 displayed characters and 12 nested containers. Repeated
noncyclic object references are valid. No silent truncation.

Source line endings normalize to LF. Body height is 4–16 rows with native scrolling/
vertical resize. Wrap defaults on; `wrap={false}` permits horizontal scrolling.
Selection uses the same text that is displayed. “Select text” focuses and selects
all text locally; use the system copy shortcut or text menu to copy. It never
claims “Copied”, calls the clipboard, executes code or sends a viewer message.
Content updates clear old selection feedback without taking focus from controls.
Empty/invalid panels disable selection and clear stale text; JSON null displays
`null`. For a paused derived preview, render `code=""` with an explanatory
`emptyMessage`/note rather than serializing invalid numbers or stale JSON.

With an explicit CodePanel `id`, the panel uses that ID; the textarea, selection
button and status use `-text`, `-select`, `-status`. Native field IDs identify the
input/select; a RadioGroup ID identifies the fieldset and options use `-option-N`.
These are useful anchors for declared interactions and browser checks.

Maintained recipes: `runtime/fixtures/forms/examples.tsx` (settings/live JSON,
numeric counts and source selection). Use these components for shared field and
selection semantics; keep domain layout and computations in authored TSX.
