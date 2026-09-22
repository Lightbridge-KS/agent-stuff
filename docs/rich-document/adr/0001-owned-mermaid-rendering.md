---
summary: Own Mermaid rendering after Quarto compilation to support hidden panels, isolate failures, and preserve diagram theme styles.
read_when:
  - changing rich-document Mermaid compilation or browser initialization
  - investigating hidden-panel geometry, diagram failure handling, or theme regressions
---

# Own the Mermaid rendering lifecycle

Accepted 2026-09-22. Amends [design](../design.md). Issues: [#60](https://github.com/Lightbridge-KS/agent-stuff/issues/60), [#62](https://github.com/Lightbridge-KS/agent-stuff/issues/62).

## Problem

Quarto 1.9.38 initializes every Mermaid diagram on window load, including diagrams
inside display:none panels. A labelled edge inside a subgraph fails during layout
there. Its sequential loop has no local catch, so the exception also prevents
later diagrams and the final sizing pass from completing. Syntax validation does
not detect browser geometry failures.

The former viewer observes SVG creation rather than completed rendering. It can
move in-progress SVGs and decorate Mermaid's error graphic. Its global rejection
filter misses exceptions without library names, and its source selector differs
from the emitted selector. The failing integration also loses generated SVG styles;
path-based shapes lack the owned theme override and fall back to unsuitable colors.

## Decision

Keep the engine pin, Mermaid library, strict sanitizer, source profile and palettes.
Own the small render lifecycle, with no patch to upstream JavaScript:

1. Canonicalization masks diagrams as inert code tokens, alongside ordinary literal
   code. The final owned Lua filter emits HTML-escaped source placeholders after
   Quarto preprocessing. Quarto never receives a Mermaid cell to initialize.
2. Copy the pinned installation's Mermaid browser bundle and embed its diagram
   theme CSS as inert JSON. Reuse Quarto's diagram-type CSS without its initializer.
   Missing dependency files are an actionable dependency error.
3. After fonts are ready, render serially in an off-screen measurable container.
   Use the nearest measurable ancestor's width, including a hidden tab's visible
   tabset. Keep source order; all panels render even if never opened. This supports
   print without asynchronously rendering in beforeprint.
4. Catch each failure, retain only that diagram's source in an inline disclosure,
   clear temporary DOM, and continue. Insert only completed SVGs with finite,
   positive viewBox dimensions. Attach enlargement after insertion; no observer
   moves in-progress SVGs. The new path retains generated SVG style elements.
5. Keep diagram colors tied to the document variables. Cover path and ellipse
   bodies and retain explicit no-fill/no-stroke paths used by composite shapes.
   Reserve space below wrapped subgraph titles so they clear the first node.
   Print rules override Quarto's more-specific inactive-panel hiding rule.

The HTML manifest records viewer_version and theme_version. Source profile remains
1: ordinary quoted prose and diagrams in tabs were already intended capabilities.
Old immutable artifacts retain their embedded renderer; present creates a new
artifact using archived source. open does not upgrade old output.

## Alternatives

- Reject diagrams in inactive tabs: contradicts the accepted composition contract.
- Render on first activation: avoids initial hidden layout, but introduces tab
  races and leaves never-visited panels unrendered for print. Measurable staging
  passes the reproduction and keeps scheduling independent of reader interaction.
- Race/replace Quarto's load handler or edit its initializer: fragile dependency
  coupling. Inert code plus the existing final filter avoids the initializer.
- Disable strict sanitization: unnecessary and outside the accepted trust boundary.
- Migrate engines or upgrade Mermaid independently: excessive scope for these bugs.

## Verification contract

Dry tests cover recursive quotation validation and missing dependency diagnostics.
Live compiler tests verify quotations, literal code, diagram placeholders and the
absence of Quarto's initializer. The self-checking browser fixture deliberately
fails one render, switches tabs during rendering, and verifies continuation,
geometry, SVG styles, theme colors and enlargement. Browser print media separately
checks all tab panels. See [progress](../progress/v1.md) for exact evidence and limits.
