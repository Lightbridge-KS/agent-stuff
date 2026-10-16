---
summary: Replace the rich-document near-black dark palette with warm charcoal and amber.
read_when:
  - changing rich-document dark theme colors
---

# Warm dark palette

Date: 2026-10-16. Status: accepted.

The requested visual direction follows the warm dark Quarto book theme:
charcoal backgrounds, off-white text, and amber accents. Replace the former
near-black/teal palette in both Bootstrap SCSS and document CSS variables.
Diagram and enlargement colors already derive from those variables.

Keep the existing typography, layout, light theme, and fixed theme toggle.
Copying the entire book stylesheet would also introduce serif prose and a
narrower reading measure, beyond this palette change. Keeping the previous
palette would not meet the requested direction.

Bump the renderer version. Existing immutable artifacts retain their embedded
styles; new presentations receive the new palette.
