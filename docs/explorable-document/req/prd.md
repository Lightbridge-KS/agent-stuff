---
summary: Requirements for explorable-document v1 — MDX and TSX explanations with local interactions, optional snapshot handoff, and durable project-scoped artifacts.
read_when:
  - deciding the scope or routing of explorable-document
  - evaluating whether an implementation satisfies the explorable-document v1 requirements
status: implemented-v1
date: 2026-10-24
---

# Explorable document — requirements

V1 implemented against the agreed [design](../design/overview.md). Acceptance evidence and
environment limits are recorded in [progress](../progress/v1.md).

## Problem and users

A reader sometimes needs to manipulate an explanation: change assumptions, step
through a mechanism, select graph elements, or inspect a filtered dataset. Static
prose and fixed diagram controls cannot express every such experience. A coding
agent can generate the web code, but repeated ad hoc applications lack consistent
delivery, source preservation, interaction contracts, and verification evidence.

The primary users are readers exploring an explanation and coding agents authoring,
revising, presenting, and reopening it. The reader may explore independently; returning
an answer to the agent is optional.

The existing `rich-document` serves constrained Quarto explanations; `ask-form`
serves structured questions. This skill fills the space where custom visuals,
calculations, or shared interactive state are central to understanding.

## Desired experience

An agent presents a browser link to a saved explanation. Narrative and interactive
elements belong to one coherent document. Controls immediately update relevant
views. The reader can stop at understanding, without completing a form. If handoff
is enabled, a deliberate action reviews and submits a snapshot for the agent to
read. The document remains usable afterward.

The source and compiled output survive the session. Reopening requires neither
the original working files nor a rebuild. An explicit export makes the artifact
portable outside the personal archive.

## Requirements and priority

| ID | Priority | Capability and success criterion |
|---|---|---|
| R-01 | P0 | Accept MDX and TSX entries through one maintained toolchain. A prose-first and a visual-first fixture both render and share reusable components. |
| R-02 | P0 | Support custom HTML elements through JSX, SVG, CSS, controls, and coordinated views. Every declared primary interaction has a working effect and verification evidence. |
| R-03 | P0 | Make exploration independent of handoff. With handoff absent, there are no submission controls or answer requirements; local interactions make no agent calls. |
| R-04 | P0 | Offer optional, explicit snapshot handoff with a declared schema, trusted review UI, durable receipt, and explicit agent retrieval. Static exports offer snapshot download instead. |
| R-05 | P0 | Save complete source, rebuild tooling, compiled output, manifest, and verification evidence under the project’s Lightbridge state. New revisions preserve previous artifacts and submissions. |
| R-06 | P0 | Isolate generated runtime code from the trusted viewer and receiver. Supply no host credentials, arbitrary tool access, or PHI; reject invalid paths, payloads, and undeclared dependencies. |
| R-07 | P0 | Verify meaningful calculations and interactions, keyboard use, responsive layout, runtime requests, and failure behavior. Distinguish passed, failed, and not-run checks. |
| R-08 | P0 | Export a multi-file static distribution and rebuildable source independent of the installed skill. Document prerequisites and distinguish offline viewing from dependency installation. |
| R-09 | P0 | Provide an agent-facing CLI with schema/example discovery, bounded JSON output, actionable errors, stable exit categories, reopening, and explicit viewer shutdown. |
| R-10 | P1 | Provide a small reusable presentation kit, two layout presets, light/dark themes, and text fallback, using the supplied ChatGPT Intelligent UI references for visual direction. Prose-integrated concept grids, layered figures, and annotated node flows remain legible and custom visual composition remains possible. |

P0 and P1 above are in v1; priority determines delivery order. No minimum count of
controls applies to every artifact. Multiple controls and coordinated outputs are
requirements of the evaluation fixtures, not a reason to overbuild a simple document.

## Constraints and routing

- Skill name: `explorable-document`; classification: **Contract × Authored**;
  initial home: the `experiment` domain.
- Prefer MDX when prose carries the explanation; TSX when visual composition does.
- Use chat for simple answers, `rich-document` for supported read/explore blocks,
  and `ask-form` when collecting structured answers is the main task.
- The default target is a local browser, initially validated on macOS. Browser
  support and agent process-lifecycle support are separate acceptance claims.
- Persistent storage is private project state, resolved through Lightbridge.
  Shared project documentation is an explicit export, not an automatic repository write.
- Local runtime behavior has no required remote services, fonts, scripts, or model
  calls. Building may require installation of pinned dependencies.
- The artifact explains or explores; it does not become an authenticated business
  application or a clinical decision surface.
- The dependency catalog is fixed in v1; new packages require a maintained toolchain
  update rather than per-document installation.
- Visual direction follows the supplied Intelligent UI screenshots, independently of
  the `rich-document` theme. The references establish dark-mode appearance; light mode
  is a neutral counterpart requiring visual review. Screenshots alone do not establish
  interaction behavior, rendering technology, or exact design-token values.

## Outside v1

Single-file HTML and `file://` guarantees; a separate raw-HTML authoring pipeline;
automatic restoration of unsent exploration state; agent wake-up or live conversation;
MCP Apps, A2UI, and AG-UI adapters; remote data refresh; external writes; authentication;
collaboration; arbitrary per-document package installation; general application
scaffolding; PDF publication; automatic cleanup of durable artifacts.

## Acceptance

The [acceptance matrix](../design/overview.md#10-verification-and-acceptance) maps these requirements
to checks. A mixed MDX explanation, TSX walkthrough, and dataset explorer must pass;
a plain-article request must route to a simpler surface. An attractive screenshot
alone is insufficient. Human visual review remains distinct from automated checks.
