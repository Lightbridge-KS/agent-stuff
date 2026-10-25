# Visual patterns

The visual direction is **Neutral Canvas**: near-black canvas, off-white text,
quiet gray borders, rounded figures, blue structural accents, selective teal and
orange. Light mode is a neutral interpretation of the same hierarchy. Tokens
live in `runtime/theme.css`; this is inspired by the supplied Intelligent UI
screenshots, not a claim to reproduce official ChatGPT CSS or behavior.

Compose an explanation: introduce the question, make its relationships visible,
then explain the consequence nearby. Keep persistent viewer chrome compact.

- **Diagrams:** use [Flow, Node, Connector and Boundary](diagrams.md) for named relationships, containment and container-based reflow. Use their maintained recipes for the six reference diagrams.
- **Cards and normal flow:** use `.grid`, `.node`, `Figure`, and `ExplorePanel` for
  concept grids, architecture layers, responsibility cards, comparisons, ordered
  spectra, and steps. A border is useful grouping, not a reason to box every paragraph.
- **Charts:** use [ChartFrame with LinePlot or SegmentedBar](charts.md) for bounded trends and part-to-whole counts. Supply truthful summaries/units; use the generated inspector and exact table.
- **Custom SVG:** label nodes and connectors, distinguish boundaries/annotations,
  include a title and equivalent explanatory text. The MDX queue template supplies
  a flow with a dashed shared-assumption boundary and coordinated prose.
- **Narrow screens:** reflow cards and spatial flows where possible. The queue has
  explicit horizontal/vertical SVG compositions so labels remain legible. Use a
  bounded scroll region plus equivalent text only for irreducible spatial layouts.
- **Semantic color:** define meaning in labels/legends. Selection also needs a
  label, outline, or `aria-pressed`; color alone does not encode state.
- **Controls:** prefer labeled native inputs and real buttons. Keep assumptions and
  affected outputs close. Reset, empty selection, overload, and errors are visible
  states. Every presented action must work and be tested.

Theme arrives through the bridge and CSS variables, without remounting the document.
Do not persist unsent form state or infer submission from navigation/closing a tab.
Use reduced-motion styles for authored animation; the kit itself has no animation.
Inspect 390px/1280px, dark/light, keyboard focus, and contrast. Automated scans are
supplementary; inspect labels and arrow connections directly at both widths.
