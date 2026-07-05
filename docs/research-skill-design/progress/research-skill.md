---
summary: Canonical progress tracker for the `research` skill build — milestones with commit
  SHAs, Now/Next, deferred scope, and the contracts confirmed by E2E testing that now bind
  the implementation.
read_when:
  - resuming or continuing work on the research skill (plugins/research/skills/research/)
  - deciding what to build next for the research skill (deferred scope, open items)
  - checking whether a research-skill behavior is a confirmed contract before changing it
---

# Progress: the `research` skill

Design (the *what & why*, decisions D1–D7): [`../design.md`](../design.md).
Implementation plan executed 2026-07-05/06. This tracker is the single source of truth for
execution state; update it when work lands (with the commit SHA).

## Milestones

- [x] **v1 core** — domain scaffolding, phase-aware SKILL.md, `research_kit.py`
  (merge-sources / check-citations / status), `general-web` + `academic-papers` modules,
  `report-style.md`, 17 tests, justfile + CI wiring, lightbridge `[research]`
  registration, E2E fixture repo — `d81f6f2`
- [x] **searcher_model default → sonnet** (+ SKILL.md now explicitly passes it when
  spawning searchers) — `8f1aa27`; surfaced as a `.lightbridge [research]` key — `7e82141`
- [x] **Manual E2E, happy path** — full lifecycle run in
  `~/my_config/_tests/deep-research-test/` (topic: uv vs pipx; 33 sources, 11 verdicts,
  Markdown report then Quarto report) — 2026-07-05/06, done by Kittipos
- [x] **Quarto output** — `to-bibtex` subcommand, qmd-aware citation gate
  (`references.bib` required + synced), `quarto-output.md` reference (`[@Sn]` cites,
  self-contained HTML default, docx/pdf opt-in), 8 more tests (25 total) — `8e57fc7`
- [x] **verifier_model knob** — explicit `execution.verifier_model` (default `sonnet`,
  `"inherit"` to match the session model); verifiers previously inherited the session
  model by accident — `b6ed3a7`

## Now / Next

- [ ] Fixture README: add a Quarto step to the try-it walkthrough
  (`~/my_config/_tests/deep-research-test/README.md` still describes Markdown only).
- [ ] `agent-instruction/AGENTS.qmd` (external repo): sync the one-line `[research]`
  section brief per `lightbridge-config/references/extending.md` step 4.
- [ ] Manual E2E, resilience paths (not yet exercised): **interrupt + resume** (Esc
  mid-wave → new session → `/research` resumes without redoing notes) and **negative
  gate** (hand-add `[S99]` → `check-citations` exits 1 naming it).
- [ ] Optional cleanup: run `to-bibtex` on the legacy uv-vs-pipx session so its
  `report.qmd` passes the (newer, stricter) gate.

## Deferred (by design — see design.md §10 and D2)

- **Matrix shape** (items × fields, Weizhena-style) — plan.md `shape:` field already
  exists; v1 always writes `narrative`.
- **Quarto book** variant (multi-chapter output).
- **Modules:** `technical-oss`, `local-corpus` (+ the `[research] corpus` key it unlocks),
  `medical-clinical`.
- **CI py_compile glob** — `validate.yml` names `research_kit.py` explicitly; generalize
  to a `plugins/**` glob if more in-skill scripts appear.

## Confirmed contracts (learnings that now bind the implementation)

- **`plan.md` frontmatter `phase` is the only phase authority**; sessions keep their
  recorded values (e.g. `searcher_model`) even when skill defaults change later —
  `.lightbridge`/defaults apply only at plan time.
- **Citation IDs:** searchers write per-note fragment ids `[S<NN>-<k>]`; notes are never
  rewritten; only reports use global `[Sn]` (md) / `[@Sn]` (qmd), translated via the
  ledger's `fragment_ids`.
- **`report.qmd` requires a script-generated `references.bib`** whose keys equal the
  ledger ids exactly; the gate fails on a stale bib ("re-run to-bibtex"). Legacy
  bracket-style `[Sn]` citations in a qmd still count as citations (gate reads both).
- **Orphan rule with two reports:** a ledger entry is an orphan only if cited in
  *neither* report (union).
- **`phase: done` only after `check-citations` exits 0** — verified against the real E2E
  session, not just fixtures.
- **Note filenames:** `NN.md` or `NN-<slug>.md` both resolve to sub-question NN
  (`status`/resume matching).
- **Quarto render in a sandbox** may fail on the Sass cache write; re-run outside the
  sandbox (documented in `quarto-output.md`).
- **Skill self-location:** `research_kit.py` is always invoked via `<skill_dir>` = the
  directory SKILL.md was read from — never a hardcoded install path (symlink install
  makes repo edits live immediately).

## Open questions

- ~~Per-wave `searcher_model` overrides?~~ Resolved 2026-07-06: one tier per session for
  each role — `searcher_model` + `verifier_model` (both default `sonnet`), orchestrator
  work (scoping, reflect, verification.md, report writing) stays on the session model.
  Revisit per-wave overrides only if a real session shows sonnet searchers missing
  things; `verifier_model: inherit` is the per-session escape hatch for judgment-heavy
  verification.
- Should `verifier_model` (like `searcher_model`) also be a `.lightbridge [research]`
  key? Deferred until a repo actually wants a per-project verifier tier.
