---
name: design-md
description: >-
  Author, extract, lint and export a repo's root DESIGN.md — the visual identity spec
  (Google design.md format: YAML design tokens + prose rationale) that any coding agent
  follows when building UI. Use when a repo needs a design system agents can follow across
  harnesses, when asked for design tokens, brand tokens, a theme file or "a DESIGN.md",
  before building or restyling UI in a repo that has one, or when a brand skill's identity
  must land in a codebase. Not for system design docs (`docs/design/`).
metadata:
  version: "2026-09-26"
---

# DESIGN.md — visual identity as a lintable file

`DESIGN.md` at the repo root is the **single source of truth for how a product looks**:
machine-readable design tokens in YAML front matter, human-readable rationale in ordered
`##` sections. Any agent, in any harness, reads it before touching UI; the CLI lints it,
diffs it and exports it to Tailwind or DTCG. Spec: <https://github.com/google-labs-code/design.md>.

> **Freshness:** verified against `@google/design.md` **0.4.0**, spec version **`alpha`**
> (2026-09). The format is young — on a newer CLI, run `design.md spec` and re-check the
> section order and rules table before authoring.

## Tool

```bash
command -v design.md >/dev/null || npm install -g @google/design.md   # once; Node ≥18
design.md spec              # the full format — load this instead of guessing the schema
design.md spec --rules-only # the 11 lint rules
```

`designmd` is the same binary (use it on Windows / in `package.json` scripts). If a global
install is unwelcome, `npx -y @google/design.md <cmd>` works but can be slow or blocked
in sandboxes.

## Verbs

**Read** — before building or restyling any UI in a repo: read `DESIGN.md` first. Its prose
wins over generic design guidance (including the `frontend-design` skill's defaults):
where the two disagree, the repo's own words rule. Missing? Offer to author one; don't
invent a look silently.

**Author** — from a brand skill or a brief.
1. A brand skill that ships a `DESIGN.md` (e.g. an org design-system skill) → copy it to
   the repo root and specialise in place; note the lineage in the Overview.
2. From a brief → ask for one **specific reference** ("a 1970s university lecture
   handout"), not adjectives ("clean, modern"); adjectives describe a region, a reference
   describes a point. Draft tokens *from* the prose, never the reverse.
3. Lint, then hand over for review — taste is the human's call; the linter only proves
   structure and contrast.

**Extract** — from an existing codebase, without building it: read `package.json` for the
stack, then the token sources (`tailwind.config.*`, `globals.css`/`:root` custom
properties, `theme.*`/`tokens.*`, component-library theme files), then representative
components for shape, spacing and states. Record **exact values** found in code; describe
intent in the prose; put unknowns under *Open questions* at the end, never as guesses.

**Gate** — `design.md lint DESIGN.md` (JSON; exit 1 on errors). Errors block; warnings are
triaged, not silenced — `orphaned-tokens` and `contrast-ratio` usually mean a real gap.
Add it to the repo's dry gates once a DESIGN.md exists. `design.md diff OLD NEW` (exit 1
on regression) reviews a redesign PR.

**Export** — `design.md export --format css-tailwind|json-tailwind|dtcg DESIGN.md`
(exit 0 export ok · 1 bad format/emitter · 2 unreadable input). The export is a
*projection*: DESIGN.md stays canonical, generated files are rebuilt, never hand-edited.
Tailwind output uses Tailwind's namespaces (`--color-*`), not the token names verbatim.

## File contract

- Path: `DESIGN.md`, uppercase, repo root — alongside `AGENTS.md`, `CONTEXT.md`, `VISION.md`.
  It is a **charter doc** (visual identity), not a `docs/design/` system-design doc.
- Front matter: `version: alpha`, `name`, then token groups `colors` (a `primary` is
  expected), `typography`, `spacing`, `rounded`, `components`. Reference other tokens as
  `"{colors.primary}"`. Custom groups (`motion`, `elevation`) are allowed and pass lint.
- Sections, in this order, any omissible: Overview · Colors · Typography · Layout ·
  Elevation & Depth · Shapes · Components · Do's and Don'ts. Declare deliberate gaps with
  `omitted:` (e.g. `- section: components` with a `reason`) so lint stays quiet on purpose.
- To surface it in the docs-index hook, add `summary:` / `read_when:` to the front matter
  (the linter ignores unknown scalar keys) and list `DESIGN.md` in the repo's docs-index
  `include`.

## Writing rules

- **Prose is the design; tokens are context.** A token's meaning lives in the sentence that
  names it: `**Vermilion** {colors.vermilion} — the single accent; diagrams only, never type.`
- **Do's and Don'ts carry the character.** A short, intentional list beats a long one; a
  long list means the Overview's reference was too vague.
- Never invent values, metrics or brand assets. A hex not found in code or brief is a
  proposal, marked as such.
- Keep it one screen per section. It is read by a forgetful, text-only reasoner every
  session — token economy is a feature.

## Neighbours

- `frontend-design` (harness) — general taste for *new* UI; DESIGN.md overrides it per repo.
- Org brand skills — the upstream identity; a repo's DESIGN.md is their specialised, lintable projection.
- Claude "Design System" artifact — a claude.ai projection for the design canvas with its
  own list-shaped `tokens.json`; derive it *from* DESIGN.md, never the other way.
- `surface-architecture` — the UX/DX doc of *what the surface does*; DESIGN.md is *how it looks*.
