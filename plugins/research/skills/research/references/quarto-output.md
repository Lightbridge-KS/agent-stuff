# Quarto output — how to write `report.qmd`

Applies when `plan.md` has `output: quarto`. The report is `report.qmd` +
`references.bib` (script-generated — never hand-edit the `.bib`). Content rules
(skeleton, citation density, verdict handling, language) are the same as
[`report-style.md`](report-style.md); this file covers the Quarto mechanics.

## Pipeline

1. Prune `sources.yaml` first (report-style rules), then generate the bibliography:
   `uv run <skill_dir>/scripts/research_kit.py to-bibtex <session_dir>`
2. Write `report.qmd` citing `@`-keys (below).
3. Render: `quarto render report.qmd` (HTML by default).
4. Gate: `check-citations` — it validates `.qmd` citations and that
   `references.bib` ↔ `sources.yaml` agree.

Re-run `to-bibtex` whenever `sources.yaml` changes; the gate fails on a stale `.bib`.

## YAML header template

```yaml
---
title: "<Topic as an answerable title>"
subtitle: "Deep-research report"
date: <YYYY-MM-DD>
abstract: |
  <executive summary, 3–6 sentences>
toc: true
number-sections: true
bibliography: references.bib
link-citations: true
format:
  html:
    embed-resources: true
  # docx: default        # opt-in on request
  # pdf: default         # opt-in; needs `quarto install tinytex`
---
```

HTML (self-contained) is the default format; add `docx`/`pdf` only when the user asks.

## Citations

- Inline: `[@S1]`, multiple `[@S1; @S4]`, narrative `@S1`. The ledger's global ids are
  the BibTeX keys — hyperlinked references come free via `link-citations`.
- Never bracket-style `[S1]` (that is the Markdown report's syntax) and never fragment
  ids or U-ids.
- No hand-written `## Sources` section. End the document with:

  ```markdown
  ## References {.unnumbered}

  ::: {#refs}
  :::
  ```

  Quarto renders the reference list there from `references.bib`.

## Quarto niceties (use where they genuinely help)

- Callouts: `.callout-note` for provenance/scope banners, `.callout-important` for
  corrections or contradicted-claim warnings.
- Cross-references: label sections `{#sec-...}` and tables `{#tbl-...}`; reference with
  `@sec-...` / `@tbl-...`.
- Captioned tables over bare pipe tables when the table is a finding.

## Rendering

- `quarto render report.qmd` — verify exit 0 and that the HTML landed next to the qmd.
- A sandboxed run may fail writing Quarto's Sass cache; re-run outside the sandbox.
- Quarto missing entirely → tell the user (`brew install quarto` or
  https://quarto.org/docs/get-started/), still deliver the `.qmd` + `.bib`, and run the
  gate — rendering is presentation, the gate is correctness.
