# Policies, operators, sidecar

## Policy YAML schema

```yaml
language: en                 # analyzer language (only `en` is provisioned)
threshold: 0.5               # min score; --threshold overrides
entities: []                 # restrict to these types (empty = all); --entities overrides
allow: []                    # literals never flagged (exact); --allow appends
columns: {hn: ID, mrn: ID}   # csv/json: force column or key → entity (matches full dotted path or last segment)
patterns:                    # ad-hoc regex recognizers (added to the engine)
  - {name: hn, entity: ID, regex: "\\bHN\\s?\\d{6,10}\\b", score: 0.7, context: [hn, hospital, number]}
llm: ollama:gemma4:e4b       # optional; or {model: ..., entities: [...], generic: false}; --llm overrides
operators:                   # entity type → operator; DEFAULT applies to everything else
  DEFAULT:  {op: replace}
  PERSON:   {op: pseudonym}
```

Unknown keys, unknown ops, missing required params, an `encrypt` key in the file, or a bad
regex all exit 2 before any model loads.

## Operators

| op | params | Effect | Reversible |
|---|---|---|---|
| `replace` | `new_value` (default `<ENTITY_TYPE>`) | substitute a literal | no |
| `redact` | — | delete the span | no |
| `mask` | `chars_to_mask` (int, required), `masking_char` (`*`), `from_end` (false) | partial mask | no |
| `hash` | `hash_type` sha256\|sha512, `salt` | one-way digest | no |
| `keep` | — | leave as is (verify treats the type as expected residual) | — |
| `encrypt` | key from **`$DEID_KEY`** (16/24/32 bytes) | AES; `restore` decrypts with the same env var | yes |
| `pseudonym` | `format` (default `<{entity}_{n}>`) | consistent per-run surrogate: same value → same `<PERSON_3>` across the whole file | yes (sidecar) |
| `date_shift` | `days` int or `random` (default), `range` (365) | one offset per run; keeps the input format; unparseable dates fall back to a `<DATE_TIME_n>` counter | yes (sidecar; verify expects `DATE_TIME` residuals) |

`pseudonym` and `date_shift` are deid's own operators (presidio has neither); presidio's
`custom` lambda operator is deliberately not exposed.

Date formats recognised by `date_shift`: ISO (`2024-06-12`, with `T`/space time), `12/06/2024`,
`06/12/2024`, `12-06-2024`, `2024/06/12`, `12.06.2024`, `12 June 2024`, `June 12, 2024`, 3-letter
months, two-digit years. Ambiguous `dd/mm` vs `mm/dd` follow the first matching format in that
order (`%d/%m/%Y` first) — an interval between two dates in the same document stays exact either
way, which is what shifting is for.

## Structured files (CSV, JSON)

Every string cell is span-scanned in a batch, with the column name / key path as context words
(so a bare `212-555-5555` under `phone` scores high enough). A column or key is then treated as
**bare entities** — whole-cell operator on every non-empty cell, catching what NER missed — when
it is forced by `columns:` or when ≥ 60 % of its cells have a finding that covers ≥ 80 % of the
cell. Everything else keeps its span findings (free-text `report` columns stay readable with
only the spans replaced). Cells already holding a placeholder (`<ID_1>`) are never re-flagged.

## Sidecar (`--sidecar map.json`)

Written by `anonymize` for text/csv/json; required when the policy uses `pseudonym` or `encrypt`
(restore is impossible without it), optional for `date_shift` alone (then the offset is simply
lost — the safe-harbor default).

```json
{
  "version": 1, "kind": "csv", "source": "patients.csv", "policy": "pseudonym",
  "created": "2026-08-28T14:02:11+00:00",
  "date_offset_days": -37,
  "entity_mapping": {"PERSON": {"Jane Doe": "<PERSON_1>"}, "ID": {"12345678": "<ID_1>"}},
  "typed": {"hn": "ID", "name": "PERSON"},
  "cells": [{"column": "name", "row": 0, "items": [{"start": 0, "end": 10, "entity_type": "PERSON", "text": "<PERSON_1>", "operator": "pseudonym"}]}]
}
```

Text sidecars carry `items` at the top level; csv/json carry `cells` addressed by
`{column,row}` or `{path}`. `items` offsets index the **anonymized** text. The file contains the
original values — treat it like the original document.

## Images and DICOM

Irreversible by construction (pixels are painted). `--fill black|white|R,G,B` for images;
`contrast|background` for DICOM (presidio picks a fill that contrasts with the box's
surroundings). DICOM output is a directory (`<name>.dcm` + `<name>.json` bounding boxes).
Header PHI (PatientName, PatientID, dates…) is untouched — run `dcmodify` from the `dcmtk`
skill afterwards. `verify` on an image re-OCRs the output: boxes that hid text pass; text the
OCR never read (rotated, tiny, handwritten) was never scanned either — Read the image yourself.
