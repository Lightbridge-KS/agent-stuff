---
summary: Widen ask-form's one-column default to 1040 px and let the reader adjust and remember width independently for each layout.
read_when:
  - changing form width defaults, slider limits, or reader preference persistence
---

# 0001 — Reader-controlled form width

Date: 2026-10-12. Status: accepted.

## Context

The fixed 720 px One column layout constrains diagrams and code on desktop screens. Split
already uses a wider 1280 px maximum. Readers need to adjust the available space without changing
the form spec or losing their preferred width when switching layouts.

## Decision

Raise One column's default to 1040 px. Add a Form width slider to Settings, with immediate
resizing, a pixel readout, and Reset to default. One column allows 720–1600 px; Split allows
960–1800 px and retains its 1280 px default. Both use 40 px steps.

Remember each layout's width in its own host-only preference cookie, using the existing one-year
lifetime. Validate integer syntax, bounds, and step alignment on both read and write. Malformed
cookies use defaults. Apply widths before first paint to a shared page/footer CSS variable.

Width remains a responsive maximum. The existing 1100 px Split breakpoint and smaller-window
stacking behavior remain; below the breakpoint, use One column's width. Layout, width and theme
belong to the reader and are excluded from the spec and submitted answers.

## Alternatives

- A wider fixed default alone would not accommodate individual readers or different diagrams.
- One remembered width for both layouts would make a compact One column choice constrain Split.
- Percentage widths would make the slider's result vary with the window and could create
  excessively long lines on very large displays.

## Consequences

The form and footer expand together. Numeric cookies extend the preference validation beyond
enum choices. Split keeps its existing default, and the slider reports the selected layout's
maximum even when a smaller window limits the visible page.
