---
summary: Implemented Flow, Node, Connector and Boundary API — six screenshot-derived recipes, explicit endpoints, responsive HTML layout, bounded SVG routing, accessibility and acceptance slices.
read_when:
  - reviewing or implementing the reusable diagram primitives
  - deciding connector semantics, diagram scope or responsive behavior
  - migrating the six screenshot diagram examples into the maintained kit
status: approved
---

# Reusable diagram primitives

**Status: approved 2026-10-25; implementation tracked in [D1–D4](../progress/diagram-primitives.md).**
Parent: [implemented design](overview.md). Evidence: [component gallery study](../tests/component-gallery.md).

## Intent and scope

Reduce repeated layout and connector work in the six diagram examples while keeping
agent-authored MDX/TSX flexible. Export four components from `@explorable/kit`:
`Flow`, `Node`, `Connector`, `Boundary`. Existing `Figure` continues to own the outer
figure and caption. Ordinary HTML, CSS and custom SVG remain available.

The strongest observed defect is semantic, not cosmetic: the prototype's workflow
stem is positioned after the entire row. On mobile it appears attached to Release
result, although the original connects Check QC to shared workflow knowledge.
Named endpoints must preserve that relationship through reflow.

No new dependencies, graph serialization format, editor, automatic node placement,
pan/zoom, icons package, execution engine, or agent integration are proposed.

**Approved routing choice:** use named endpoints and a small measured connector layer, rather than decorative arrows placed between siblings. This costs some runtime geometry code but preserves relationships across branches and responsive reflow.

## Responsibilities

| Primitive | Owns | Does not own |
|---|---|---|
| `Flow` | Row/column/grid composition; responsive stacking; root diagram scope; endpoint registry and connector layer | Domain state, arbitrary graph layout, outer figure caption |
| `Node` | One labeled item, optional icon/detail, visual surface, measurable endpoint | Workflow execution, implicit click handlers, arbitrary positioning |
| `Connector` | Explicit endpoint relationship, arrowheads, line style, optional label | Node placement, data transfer, event dispatch |
| `Boundary` | Labeled containment or explanatory group, nested content, group endpoint | Domain-specific annotation logic, implicit connections to children |

A Boundary is a group; a Node is an item. A service containing an internal-model
node is a Boundary. A standalone published contract is a Node. Shared workflow
knowledge is a dashed Boundary containing explanatory prose. The distinction is
structural rather than a special `service` or `annotation` component type.

Keep layout measurement, endpoint registration and routing inside one diagram module.
They change together when labels, card dimensions or breakpoints change. Authors
supply stable names and relationships, not DOM refs or pixel coordinates.

## Public API

```tsx
import { Figure, Flow, Node, Connector, Boundary } from '@explorable/kit';

type Tone = 'neutral' | 'blue' | 'teal' | 'orange' | 'red';
```

| Component | Props and defaults |
|---|---|
| `Flow` | Required `label: string`, `children`; `layout: 'row' \| 'column' \| 'grid' = 'row'`; `columns: 2 \| 3 \| 4` required only for grid; `collapseBelow: number = 600` CSS px of its own available width; `gap: 'normal' \| 'wide' = 'normal'`; optional `description`, `className` |
| `Node` | Required `title: string`; optional diagram-local `name: string`, `subtitle: string`, `icon: ReactNode`, `children`, `className`; `variant: 'outline' \| 'plain' \| 'filled' = 'outline'`; `tone: Tone = 'neutral'` |
| `Boundary` | Required `title: string`, `children`; optional diagram-local `name`, `className`; `variant: 'outline' \| 'dashed' \| 'plain' = 'outline'`; `tone: Tone = 'neutral'` |
| `Connector` | Required `from: string`, `to: string`; optional `label: string`; `arrows: 'end' \| 'both' \| 'none' = 'end'`; `line: 'solid' \| 'dashed' = 'solid'`; `tone: Tone = 'neutral'` |

`name` deliberately differs from an HTML `id`. It is an endpoint key local to the
outermost Flow. DOM IDs and SVG marker IDs are generated and namespaced internally.
Names must be nonempty and unique across both nodes and boundaries in that root.
Repeated titles are permitted; repeated endpoint names are not.

Root Flow establishes the scope. Nested Flows inherit it and provide layout only;
connectors can reach named descendants across those layouts. Two sibling root Flows
are independent and may reuse names. A connector cannot reach another root.
Use sibling roots for independent figures; use nested Flows for one connected diagram.

TypeScript props use a discriminated union for grid columns. Invalid values from MDX
or JavaScript receive a readable diagram diagnostic. Component title text does not
become a document heading automatically; document sections retain heading ownership.

`className` is an escape hatch for appearance and normal-flow composition. Geometry
transforms, CSS order reversal, absolute positioning of endpoints, or clipping the
root connector surface fall outside the supported layout contract.

## Example: workflow with shared knowledge

```tsx
<Figure caption="Business rule changes can affect both services.">
  <Flow label="Result release workflow" layout="column" gap="wide">
    <Flow label="Release steps" layout="row">
      <Node name="inference" title="Check inference" tone="blue" />
      <Node name="qc" title="Check QC" tone="blue" />
      <Node name="release" title="Release result" tone="blue" />
    </Flow>

    <Boundary
      name="knowledge"
      title="Shared workflow knowledge"
      variant="dashed"
      tone="orange"
    >
      <p>Business rule changes can affect both services.</p>
    </Boundary>

    <Connector from="inference" to="qc" />
    <Connector from="qc" to="release" />
    <Connector
      from="qc" to="knowledge"
      arrows="none" line="dashed" tone="orange"
      label="shares workflow rules"
    />
  </Flow>
</Figure>
```

Connector declarations do not occupy layout cells. On desktop the annotation link
can descend from QC. On narrow screens the router takes a side gutter around Release
result; it must not silently attach the annotation to the last visible node.

## Six recipes

| Reference | Composition | Reflow and relationship contract |
|---|---|---|
| Workflow/shared knowledge | Root column Flow, nested row of three Nodes, dashed Boundary, three Connectors | Stack steps; preserve the QC-to-boundary attachment around the intervening release node |
| Service contract/code | Row Flow: inference Boundary with Internal model Node; filled teal contract Node; report Node; two Connectors | Stack the three endpoints; retain internal-model containment. Code panel stays outside these primitives |
| Layered architecture | Column Flow with user and agent Nodes, nested two-column Flow of UI/tool Boundaries, rendered-experience Node; explicit branch Connectors | Stack UI and tool groups in DOM order. Each group retains its own links to agent/output; no implied chain from UI to tools |
| Coupling dimensions | Three-column Flow of plain Nodes with icon, subtitle and descriptive children | Stack into three concepts. **No connectors**: adjacency is not a claimed relationship |
| Short/long distance | Two named Boundaries in a column Flow, each containing a row Flow and a bidirectional Connector between two Nodes; labeled connector between the groups | Keep each pair bidirectional and the short-to-long progression explicit; monospace content remains ordinary authored markup |
| Integration spectrum | Column Flow of four filled Nodes using red/orange/blue/teal; numbered titles, icon and description | Preserve authored order and descriptive text. **No connectors**; endpoint labels remain ordinary prose |

The architecture reference has an ambiguous shared synchronization label under its
two branches. The recipe makes both branch-to-output links explicit and repeats the
meaning in the figure caption; it does not imply a previously invisible runtime API.

Boundary nesting does not create edges. If a connector targets the service Boundary,
it terminates at that outer border, not at its Internal model child. Authors target
the child name explicitly when that is the intended relationship.

## Layout and routing contract

### HTML determines placement

- Row gives its ordinary direct children equal-width cells; column stacks them;
  grid uses the explicit column count. Connector components render no layout item.
- Row and grid switch to a single column below their own `collapseBelow` threshold.
  Column stays vertical. DOM order remains reading and visual order.
- Labels wrap; card heights grow with content. No fit-to-width font shrinking or
  whole-diagram SVG scaling. The root reserves outer routing gutters; gaps provide
  space between adjacent cards. Token values are tuned against the fixtures.
- Each nested Flow responds to its actual available width, including narrow panels
  inside a wide page. A viewport-only media query is insufficient.
- Normal-flow author wrappers are permitted. A direct wrapper consumes one layout
  cell; registered descendants remain measurable. Common rows/branches should use
  nested Flow so the responsive behavior remains predictable.

### SVG draws the relationships

The root owns one noninteractive SVG overlay. Nodes and boundaries register element
refs and names through context. The root measures border boxes relative to its canvas
and draws border-to-border paths with a small arrowhead clearance. Labels are HTML
so they wrap and inherit the document font.

Measurement is coalesced after React layout commits. Observe the canvas, registered endpoints and
nested layout containers; recalculate after content/size changes, registration,
viewport/container resizing, and font readiness. React lifecycle cleanup removes
observers and stale registrations. No perpetual animation loop or global DOM query.

The v1 router is deliberately bounded:

1. Try an unobstructed straight path between facing edges.
2. Try an orthogonal path through an inter-item gap.
3. Try a dogleg through a reserved outer gutter, assigning distinct lanes in connector
   declaration order when multiple relationships share a gutter.
4. If none fits, expose a diagram diagnostic and retain the textual relationship;
   do not draw a plausible-looking line through an unrelated node.

Endpoints and their ancestor groups are distinguished from unrelated obstacles.
A containing group cannot block access to its own child endpoint. Route labels avoid
node boxes and previously placed labels; an unplaceable visual label falls back to
the relationship list with a visible diagnostic. Labels do not expand the canvas
in a measurement feedback loop.

This is not a general obstacle-avoiding graph router. Arbitrary cycles, self-loops,
large dense graphs and optimal crossing reduction are outside this tranche.
Self-loops, duplicate names and unresolved endpoints receive specific diagnostics.
A target in another root is unresolved in the current scope; no global lookup is performed. The supported six fixtures must produce no unintended node
crossings or ambiguous connector crossings at the acceptance widths.

If content is temporarily hidden or has zero-size bounds, defer its paths until it
becomes measurable. Removing an endpoint must not leave its old arrow on screen.
Persistent unresolved references become visible diagnostics after registration has
settled, not transient errors during ordinary mounting.

## Accessibility and interaction

- Flow is a labeled HTML group, not one `role="img"` that hides interactive descendants.
  SVG strokes and decorative icons are hidden from assistive technology.
- Node and Boundary titles label their groups. HTML prose and controls remain
  selectable, readable and in normal tab order. Static cards are not focus stops.
- Root Flow provides a keyboard-accessible **Diagram relationships** disclosure when
  connectors exist. It lists source title, direction/association, destination title
  and connector label from the same endpoint records that drive the drawing.
  Arrowless associations and bidirectional links receive different text.
- Figure caption supplies the explanation; the relationship list supplies exact links.
  No relationship meaning depends only on color, dashing or spatial arrangement.
- Existing Neutral Canvas variables own surfaces. Filled variants require dedicated
  foreground/fill pairs that pass contrast checks in both themes; matching a screenshot
  color never overrides readable text or focus indicators.
- No animation by default. Layout changes preserve authored input state and focus.

**Approved interaction choice:** keep these four primitives presentational in the first tranche. Authors can put native buttons/links/controls inside Node content; a whole-node selection/navigation API is deferred until a real interaction example defines its semantics.

This avoids shipping a generic clickable `div`, nested buttons, or a selection state
that has no implemented effect. If interactive content is authored, its state and
snapshot provider remain in the document; the diagram kit never submits anything.

## Internal ownership and compatibility

Runtime ownership:

```text
runtime/diagram/
  index.tsx          four components and responsive layouts
  scope.tsx          root registry, measurement and endpoint lifecycle
  geometry.ts        pure rectangle/anchor/path calculations
  diagram.css        namespaced styles and responsive layout tokens
```

`kit.tsx` re-exports the four components. The fixed runtime imports the CSS; no
artifact-owned package or build configuration is required. Keep geometry pure enough
for deterministic tests, while integration tests cover real browser measurement.
Do not create independent node/edge stores, a generic layout service or a diagram
plugin architecture at this scale.

Use an `ed-diagram-*` CSS namespace; leave existing `.node`, `.grid`, Figure and
hand-authored SVG behavior intact. Existing archived artifacts retain their frozen
toolchain. New artifacts opt into these exports explicitly. Update the runtime
manifest version when the public API is added; the manifest remains version SSOT.
No bridge, receiver, persistence or descriptor-schema change is required.

## Acceptance and implementation slices

Both review decisions are approved. Implement the slices below in order as checks pass.

1. **D1 — layout and surfaces:** Flow, Node and Boundary; namespace/containment;
   concept-grid and spectrum fixtures; both themes and narrow containers.
2. **D2 — explicit relationships:** Connector, root scope, simple and bidirectional
   routing, generated relationship list; contract and distance fixtures.
3. **D3 — branches and responsive routing:** nested scopes/layouts, boundary endpoints,
   outer-gutter routing; workflow and layered architecture. The mobile QC attachment
   is a blocking acceptance case.
4. **D4 — integration:** migrate the six gallery examples; document API/recipes and
   diagnostics; republish a reviewed immutable gallery revision.

Verification must establish behavior, not merely pixel similarity:

- Pure geometry tests: border intersection, arrow clearance, obstacle rejection,
  gutter route and label bounds using independent coordinate expectations.
- Browser fixtures: all six examples at **390, 768 and 1280 px**, dark and light;
  plus a narrow diagram container inside a wide page. Separate fixture entries make
  every example the initial view, avoiding the gallery runner's state-coverage gap.
- Inspect endpoint proximity and path intersections against independently measured
  boxes. Include long labels, a multiline detail, nested boundaries, two diagrams
  reusing endpoint names, and dynamic content expansion after initial render.
- Failure fixtures: duplicate/missing endpoint, removed target, self-loop and
  temporarily hidden content. Require useful diagnostics, no stale arrows and no
  crash or unbounded remeasurement.
- Keyboard and accessibility: relationship disclosure, native controls inside a node,
  stable focus/state through resize/theme changes, text/graphic contrast and no page
  overflow. Document native Safari smoke separately from Chromium automation.
- Reproducible build/package and existing runtime/CLI tests remain green. Human
  review judges spacing, visual hierarchy, branch legibility and screenshot resemblance.

The four primitives are implemented in runtime 0.2.0 without new dependencies.
Broader routing or selection APIs require a demonstrated use case beyond these recipes.
