# Report style — how to write the report

Read at REPORTING time. The report is the session's product: a standalone document for a
reader who never saw the notes. Everything here applies to both output formats; for
`output: quarto`, the Quarto-specific mechanics (`.bib` bibliography, `[@S1]` citation
syntax, YAML header, rendering) are in [`quarto-output.md`](quarto-output.md) and
override the citation-syntax and Sources-section rules below.

## Skeleton

```markdown
# <Topic as an answerable title>

*Research session: <session dir> · <created date> · <n> sources*

## Executive summary
<3–6 sentences: the answer, the strongest evidence, the biggest caveat>

## <One section per sub-question, merged/reordered for narrative flow>
...

## Open questions & limitations
<unanswered gaps from the notes; unsupported claims that were dropped; scope cuts>

## Sources
<the ledger, rendered: - [S1] Title — url (accessed date)>
```

Sections need not map 1:1 to sub-questions — merge and reorder for the reader; the notes
are organized for the writer, not the reader.

## Citations

- Syntax: `[S1]` single, `[S1, S4]` multiple. Global ledger ids only — never fragment ids
  (`S03-1`) and never U-ids.
- Density: every non-obvious factual claim carries a citation. A paragraph of synthesis
  may cite once at the end if all claims trace to the same sources; a number, date, or
  quote always cites inline.
- Every ledger entry must be cited at least once (the gate enforces both directions —
  prune uncited entries from `sources.yaml`).

## Applying verdicts from `verification.md`

- `confirmed` — assert plainly, with cite.
- `unsupported` — either drop, or hedge explicitly: "X *reportedly* ... though this could
  not be independently verified [S7]." Never present as established fact.
- `contradicted` — drop, or surface the conflict when it matters to the reader:
  "Source A claims X [S3]; B contradicts this [S9]. The safer reading is ..."

Never copy `[uncertain ...]` markers or `U`-ids into the report — they are note-layer
machinery; the gate rejects leaks.

## Language

- `language: en` — English throughout.
- `language: th` — Thai prose; keep technical terms, tool names, and citations in English
  (no transliteration of established technical vocabulary). Section headings in Thai.
