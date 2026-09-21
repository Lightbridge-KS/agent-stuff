# Source contract — profile 1

Use `example` for a complete source and `schema` for machine-readable metadata
and block constraints. Quarto 1.9.38 is the verified engine; the CLI rejects other
versions rather than silently relying on a different parser/runtime.

```yaml
---
title: Explanation title
subtitle: Optional plain-text subtitle
artifact:
  version: 1
  layout: article
assets:
  screenshot: images/screenshot.png
---
```

Only `title` is required. Metadata is literal, with no YAML aliases, duplicate
keys, or Quarto options. The engine owns theme, execution, filters, and includes.

| Content | Syntax / limits |
|---|---|
| Prose | Standard Markdown headings, emphasis, lists, quotes, tables, links |
| Code | Ordinary fenced language blocks; examples never execute |
| Diagram | A `{mermaid}` fence; syntax checked before rendering |
| Tabs | `::: {.panel-tabset}` with 2–6 same-level headings; first panel selected |
| Callout | `::: {.callout-note}` / `.callout-tip` / `.callout-warning`; optional `collapse="true"` |
| Columns | Outer `:::: {.columns}`, two inner `::: {.column width="50%"}` blocks |
| Image | `![Descriptive alt text](asset:screenshot)`; declared PNG/JPEG/WebP only |

Blank lines separate headings and code fences. Use more colons for an outer div
than its nested divs. Tabs and columns belong in the main article; they cannot
nest. Their bodies accept ordinary content, diagrams, images, and callouts.
Callouts cannot contain nested layouts or diagrams. Widths are equal; columns
stack on narrow screens. Div classes/attributes outside this catalog are errors.

Links are `#heading` anchors or HTTP(S) URLs without embedded credentials. Images
must be within the source's directory, including after resolving symlinks. Remote
images and SVG are unsupported. Assets are copied; reopening never reads originals.

No raw HTML, scripts, CSS, executable `{python}`/`{r}` cells, shortcodes, author
filters/includes, or Mermaid directives/click handlers/custom styling. These
strings can still appear literally in ordinary code examples.

Limits: source 1 MB; 20 images, 10 MB each/20 MB combined; 20 diagrams, 30 KB each;
rendered HTML 40 MB. Diagram layout also has engine resource limits. Diagnostic
locations are line numbers where available, otherwise Pandoc block paths.

`present` saves a new immutable artifact. The archived source rewrites asset
declarations to its copied assets; the manifest retains the original source hash.
The artifact HTML embeds its dependencies. No external publication takes place.

Viewer choices are local browser state, not source metadata. The toggle selects
light/dark; diagrams have an enlargement dialog with zoom, drag/scroll pan, Reset,
and Escape/Close. No countdown or automatic shutdown applies to the viewer.
