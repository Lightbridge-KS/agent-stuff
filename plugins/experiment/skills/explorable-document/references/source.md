# Source contract

`artifact.json` owns title/summary, entry, layout (`article` default or `workspace`),
assets, provenance, interactions, and optional handoff. `schema` prints the actual
versioned descriptor schema; do not maintain a parallel schema in prose.

Use `init PATH --format mdx|tsx|dataset` for working examples with behavioral checks.
MDX imports TSX components and supports GFM. TSX exports a default component. The
runtime wraps either entry in an article. `@explorable/kit` exports `Document`,
`Section`, `Figure`, `ExplorePanel`, `Range`, `useSnapshot`, and the [diagram primitives](diagrams.md) (`Flow`, `Node`, `Connector`, `Boundary`). Use `Document` only
for a deliberate nested article; the normal entry does not need another wrapper.
The [chart family](charts.md) exports `ChartFrame`, `LinePlot`, `SegmentedBar` and their public data/prop types.
The [form/code family](forms-code.md) exports `RadioGroup`, `SelectField`, `CheckboxField`,
`NumberField`, `readNumber`, enhanced `Range`, `CodePanel` and their public types.
Native semantic HTML, custom SVG, CSS, and React state/context are available.

Imports: local TS/TSX/MDX/CSS, declared JSON/images, React and its JSX runtime,
`react-dom/client`, and `@explorable/kit`. No remote imports, Node built-ins, import
queries, computed dynamic imports, `import.meta`, or source traversal. Keep source
as a small dedicated directory: no symlinks, `.env`, package/config files,
`node_modules`, or reserved `_toolchain` folder. Declared asset paths use ordinary
relative filename characters. CSS URLs/imports/escapes are unsupported; import an
image as a declared asset in TSX. Fonts use the system stack. Data URLs in JSX
stay subject to the frame's CSP.

Limits: descriptor 64 KiB; 200-character title; 4000-character summary; 100 primary
interactions; source text 10 MiB; declared assets 50 MiB; rendered output 100 MiB.
Each interaction declares ID, trigger, input schema, output IDs, expected effect.
Declarations are claims, not automatic behavior. Keep IDs stable and implement
handlers, edge cases, and verification together. State defaults live in code.

Snapshot/input schemas use a bounded subset of JSON Schema draft-07: explicit
`type`, `properties`, `required`, `additionalProperties: false`, `items`,
`minItems`/`maxItems`, `minLength`/`maxLength`, `minimum`/`maximum`, `enum`, `const`,
and `description`. Every object is closed, every string/array has a finite maximum,
and every number has minimum/maximum. No refs, regexes, or combinators. Nullable
values use a type array such as `["number", "null"]`. Nesting ≤12; properties ≤100;
maxItems ≤10000; maxLength ≤100000. The CLI and compiled browser validator reject
unsupported schemas. Derive values remain author-produced, not authoritative facts.

## Optional handoff

Add `"handoff": {"schema": "snapshot.schema.json"}` to the descriptor. Register one
provider inside a component:

```tsx
import { useSnapshot } from '@explorable/kit';
useSnapshot(() => ({ arrival, service, jobs: result.jobs }));
```

The provider returns current JSON values only when the reader requests a snapshot.
Changing inputs never submits data. Missing provider, invalid values, timeout, and
oversized payloads produce visible errors while exploration remains available.
The shell freezes a reviewed copy and owns the comment, confirmation, credentials,
and receipt. Refresh explicitly replaces the review. After a failed save, retry
sends the same copy; refresh to change it. A new review permits another submission.
Provider JSON must fit 900000 UTF-8 bytes; the full request limit is 1 MiB, with a
4000-character comment. Static/temporary viewers download instead of saving.

## Fixed toolchain

Runtime package version owns compatibility; skill metadata uses a separate date.
Tested build prerequisites: Node **26.7.0**, pnpm **10.18.2**, Python ≥3.11 and uv.
The maintained package.json and pnpm-lock.yaml own exact dependencies. Installs
use a disposable directory with frozen lockfile and ignored package scripts.
No build configuration, dotenv files, or plugins come from the calling project.
MDX is compiled but never rendered/evaluated on the host. `tsc` checks TS/TSX;
MDX expression correctness additionally needs compilation and browser evidence.
New dependencies require a runtime/catalog update, not an artifact-local install.
