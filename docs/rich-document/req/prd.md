---
summary: Requirements for a one-shot rich document skill: agent-authored Markdown, deterministic browser rendering, exploratory interactions, and an optional future MCP Apps surface.
read_when:
  - designing or implementing the rich-document skill and its renderer
  - deciding whether feedback collection, custom widgets, or website publishing belongs in rich-document
---

# Rich document — requirements

Status: browser slice approved and implemented 2026-09-21. Name: `rich-document`.
Implementation: [design](../design.md).

## Problem and users

Coding agents explain architectures, alternatives, and implementations through
terminal output. Long prose, plain code, and text diagrams become difficult to
navigate and compare. The agent needs a low-friction publishing interface; the
reader needs a readable, interactive document outside the terminal.

The intended workflow is one authored document and one command. The reader opens
the result while the agent continues. Creating a website project for each
explanation defeats the purpose.

## Confirmed scope

- Markdown or a comparably deterministic text format is the agent's input.
- Proper Markdown, code blocks, Mermaid, tabs/panels, and divs are required.
- First-version interaction means reading and exploration: tabs, collapsible
  panels, diagram zoom, and code copying.
- Styling comes from a polished theme and a small catalog of layouts and
  semantic blocks. Arbitrary generated CSS or JavaScript is outside this scope.
- The preview's light style and revised near-black dark palette are accepted.
  Both modes and a built-in theme toggle are required.
- Quarto's installed dependency and saving successful artifacts by default are
  accepted decisions (2026-09-21).
- Authoring uses an accepted versioned subset of `.qmd`.
- The viewer has no countdown, idle expiry, or maximum lifetime; the reader
  closes the tab when finished. Explicit server shutdown remains available.
- Browser delivery is the baseline. MCP Apps integration should remain possible.
- Persistent personal storage is desired; `.lightbridge` is the accepted home.

## Capabilities

| Priority | Capability | Success criterion |
|---|---|---|
| P0 | One-shot authoring | One source and one invocation produce a viewable artifact; no per-artifact project scaffolding |
| P0 | Rich content | A representative explanation renders every required content type |
| P0 | Exploration | Tabs and disclosures work with keyboard and pointer; code copies; diagrams can be enlarged and zoomed |
| P0 | Deterministic presentation | The same source, engine version, and theme yield the same structure and displayed content |
| P0 | Light and dark viewing | A built-in toggle changes the complete document theme without losing reading interaction state |
| P0 | Persistence | Source and rendered output survive server and agent termination and can be reopened |
| P0 | Reader-controlled viewing | No elapsed-time or inactivity condition expires the viewer or closes its tab |
| P0 | Agent diagnostics | Invalid content produces bounded, actionable diagnostics before publishing |
| P0 | Display-only code | Code examples never start Python, R, shell, or other computation |
| P1 | MCP Apps adapter | A supporting host shows the artifact; an unsupported host receives a usable fallback |
| P1 | Export | A standalone HTML file can be moved and opened without the original server |

## Constraints and non-goals

- Harness-neutral core; no dependency on a particular chat UI or native question tool.
- Local rendering and viewing without publication to an external service.
- Clear separation between source content and renderer-owned behavior.
- No feedback collection, approvals, arbitrary widgets, live data, or document editing in v1.
- No documentation portal, collaboration service, or PDF/DOCX fidelity commitment in v1.
- No clinical data in this personal artifact store.

## Subsequent scope

The authoring engine, archive default, both light and dark visual treatments,
versioned `.qmd` subset, and no-expiry viewer lifecycle are accepted. The approved browser slice is implemented as `rich-document`; MCP host selection
and experiment graduation remain future decisions.
