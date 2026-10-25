# Diagram primitives

Import `Flow`, `Node`, `Connector`, `Boundary` from `@explorable/kit`. Use `Figure`
for the outer panel/caption. These are presentational HTML components with a
measured SVG connector layer, not a graph editor or execution engine.

```tsx
<Figure caption="QC shares the release rules.">
  <Flow label="Release workflow" layout="column" gap="wide">
    <Flow label="Steps">
      <Node name="check" title="Check QC" tone="blue" />
      <Node name="release" title="Release result" tone="blue" />
    </Flow>
    <Boundary name="rules" title="Shared rules" variant="dashed" tone="orange">
      <p>Changes must remain consistent across services.</p>
    </Boundary>
    <Connector from="check" to="release" />
    <Connector from="check" to="rules" arrows="none" line="dashed" />
  </Flow>
</Figure>
```

## Public API

| Component | Required | Optional (defaults) |
|---|---|---|
| Flow | `label`, `children`; `columns={2\|3\|4}` when grid | `layout="row"` (`column`, `grid`); `collapseBelow={600}` CSS px of its own width; `gap="normal"` (`wide`); `description`, `className` |
| Node | `title` | `name`, `subtitle`, `icon`, `children`, `className`; `variant="outline"` (`plain`, `filled`); `tone="neutral"` |
| Boundary | `title`, `children` | `name`, `className`; `variant="outline"` (`plain`, `dashed`); `tone="neutral"` |
| Connector | `from`, `to` | `label`; `arrows="end"` (`both`, `none`); `line="solid"` (`dashed`); `tone="neutral"` |

Tones: `neutral`, `blue`, `teal`, `orange`, `red`. Exported prop types and `Tone`
are available for authored wrappers. `className` supports appearance and normal-flow
composition; endpoint transforms, CSS order reversal and absolute placement are
outside the layout contract.

## Composition rules

- Name endpoints explicitly; names are local to the **outermost Flow**, unique across
  Nodes and Boundaries, and unrelated to HTML IDs. Nested Flows share that scope;
  sibling roots may reuse names. Declarations create no layout cells.
- Target a Boundary to connect to its outer border; target a named child to connect
  inside it. Containment and adjacency never create implicit relationships.
- Row/grid layouts stack in DOM order below their own width threshold. Column stays
  vertical. Never shrink the entire figure to fit the page or add decorative arrows
  between siblings: those can imply a different relationship after stacking.
- Put ordinary text, code, controls and custom SVG inside Nodes/Boundaries. Titles
  label groups rather than creating document headings. Static nodes are not buttons;
  native controls retain their normal focus and React state.
- An accessible **Diagram relationships** disclosure derives from the same endpoint
  records as the paths. SVG paths/icons are decorative; relationships are also text.
  Merely opening this disclosure does not need a primary interaction declaration.
- Keep state and snapshot providers in the authored document. The diagram module
  has no submission, selection, navigation or agent-communication behavior.

## Bounded routing and diagnostics

The router tries facing borders, orthogonal gaps and reserved outer gutters. It
remeasures on resize, font readiness, content changes and endpoint mount/unmount.
Labels wrap and avoid node boxes and other labels. Hidden/zero-size endpoints defer
paths; removing an endpoint removes its old path.

Duplicate/missing names, self-loops, blocked routes and labels that do not fit produce
visible diagnostics. Relationships remain readable in the disclosure. Repair names,
increase gaps or simplify the layout; do not hide diagnostics or draw a misleading
replacement arrow. Dense/cyclic graphs, automatic graph placement, pan/zoom and
whole-node selection are outside this API. Custom SVG remains an escape hatch.

## Six maintained recipes

See `runtime/fixtures/diagrams/examples.tsx` and its authored `recipes.css`:

- `Workflow`: nested row plus dashed Boundary; QC association survives stacking.
- `Contract`: service Boundary containing an internal Node, filled contract Node,
  report Node; Python code remains a display-only authored panel.
- `Architecture`: root column, branch grid, five explicit links to/from groups.
- `Concepts`: grid of three plain Nodes with icons; no connectors.
- `Distance`: two Boundaries, paired bidirectional links and a progression label.
- `Spectrum`: four filled Nodes with authored icon placement; no connectors.

Copy only the recipe and styles needed into the source directory; artifacts cannot
import files outside their source or the kit. The recipe icons/content are examples,
not additional public components. Inspect actual arrows and labels in both themes
at 390/768/1280 px and in narrow containers; browser readiness alone is insufficient.
