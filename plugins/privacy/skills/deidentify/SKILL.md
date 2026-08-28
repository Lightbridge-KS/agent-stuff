---
name: deidentify
description: >-
  De-identify PHI/PII in text, Markdown, JSON, CSV, images and DICOM pixels with the bundled
  deid CLI (Microsoft Presidio, fully local) — scan and flag, anonymize/redact, pseudonymize
  with a reversible sidecar, verify, restore. Use when asked to scan a file for PHI or PII,
  de-identify, anonymize, pseudonymize, redact or scrub personal or patient data, or whenever
  presidio comes up.
metadata:
  version: "2026-08-28"
---

# De-identify (PHI/PII)

Drive the bundled deterministic CLI; you supply the judgment — which entities matter here,
which policy, whether a finding is a false positive, and reading the verify result. Never
hand-write presidio SDK code for a de-identification task.

`<skill_dir>` = the directory this SKILL.md was read from. Every verb:

```bash
uv run <skill_dir>/scripts/deid.py <verb> ...      # first run fetches ~600 MB of models (see Setup)
```

**Local-only invariant.** Everything runs on this machine. No cloud recognizer is ever enabled;
Ollama `*:cloud` tags are refused. Sidecars are re-identification key material: playground/temp
only, never committed, never sent anywhere.

## Router

```
input
 ├─ .txt .md ─────────────► text       spans → operators
 ├─ .csv .tsv ────────────► structured columns typed (bare IDs/names) or span-scanned (free text)
 ├─ .json ────────────────► structured keys, same rule; nested paths kept
 ├─ .png .jpg .tif .bmp ──► image      Tesseract OCR → boxes → black fill (irreversible)
 ├─ .dcm | --dicom <dir> ─► dicom      pixels ONLY — headers: `dcmtk` skill, dcmodify
 └─ .pdf .docx ───────────► refused    parse-to-md first (local `lit`), then the .md
Thai names ──────────────► add --llm ollama:gemma4:e4b (local LLM recognizer; ~25 s / 400 chars)
```

## Verbs

| Verb | Does | Exit |
|---|---|---|
| `scan <in> [--policy] [--threshold] [--entities A,B] [--allow x,y] [--columns hn=ID] [--llm] [--explain] [--json]` | Find and list findings | 1 found · 0 clean |
| `anonymize <in> -o <out> --policy <preset\|yaml> [--sidecar map.json] [--fill]` | Apply the policy; bytes only to `-o` | 0 |
| `verify <out> --policy <same>` | Re-scan; entities the policy keeps/date-shifts are expected, anything else is a **leak** | 1 leaks · 0 clean |
| `restore <out> -o <orig> --sidecar map.json` | Reverse pseudonym / date_shift / encrypt (text, csv, json) | 0 |
| `entities [--json]` | Supported entity types, PHI-relevant starred | 0 |
| `doctor` | spaCy model · tesseract · Ollama and local models | 3 if core missing |

Exit `2` = fix the request (bad policy/flag, validated before any model loads) · `3` =
environment (model, tesseract, Ollama, `DEID_KEY`). Messages name the next move.

## Policies (presets in `references/policies/`)

| Preset | Effect | Reversible |
|---|---|---|
| `redact` (default) | every entity → `<ENTITY_TYPE>` | no |
| `safe-harbor` | HIPAA 18 identifiers → `<TYPE>`, dates shifted by one random offset | no (dates only with sidecar) |
| `pseudonym` | `<PERSON_1>`… consistent per run, dates shifted, org/URL kept | **yes — needs `--sidecar`** |
| `mask` | partial masking (`212-55******`) | no |

A policy is small YAML — copy a preset when the case needs its own (`patterns:` for local IDs
such as `HN 12345678`, `columns:` to force a CSV/JSON column, per-entity `operators:`):
[references/operators.md](references/operators.md) has the schema and every operator's params.

## Workflow contract

1. `doctor` once per machine; `scan --json` the input. **Review the findings** — false
   positives → `--allow`; missing local identifiers → `patterns:`/`--columns`; Thai names →
   `--llm`. Findings carry `recognizer` and (with `--explain`) why.
2. Pick the policy: research reuse → `pseudonym` (+ sidecar); sharing outside → `safe-harbor`
   or `redact`. State the choice to the user when it is not obvious.
3. `anonymize` to a **new** path (the tool refuses to overwrite its input).
4. `verify` the output with the same policy — exit 0 or explain each leak. For images, also
   Read the output image back. Never report "de-identified" without this step.
5. Deliver the output; say where the sidecar is and that it must not be committed.

```bash
D="uv run <skill_dir>/scripts/deid.py"
$D scan note.md --json                                            # 1. look
$D anonymize note.md -o out/note.md --policy pseudonym --sidecar out/note.map.json   # 3
$D verify out/note.md --policy pseudonym                          # 4. prove
$D restore out/note.md -o back/note.md --sidecar out/note.map.json   # later, if needed
$D anonymize patients.csv -o out/p.csv --policy safe-harbor --columns hn=ID,mrn=ID
$D anonymize scan.png -o out/scan.png                             # image: black boxes
$D anonymize study/ --dicom -o out/study/                         # DICOM pixels; then dcmodify headers
```

Depth: [references/entities.md](references/entities.md) (entity catalog, Safe Harbor mapping
**and its gaps**, Thai coverage) · [references/operators.md](references/operators.md) (policy
schema, operators, sidecar) · [references/setup.md](references/setup.md) (models, sandbox,
Ollama, why not presidio-cli/REST).

## Setup & sandbox notes

- One `uv run` resolves everything (presidio, spaCy `en_core_web_lg` wheel, OpenCV, pydicom);
  cold start ≈ 2 min and ~2 GB cache, then ~2 s per invocation. Downloads worked inside the
  sandbox here; if refused, run once outside it.
- Image/DICOM need `tesseract` on PATH (`brew install tesseract`). `--llm` needs Ollama at
  `localhost:11434` with the model pulled; `doctor` lists what is local.
- `encrypt` takes its AES key only from `$DEID_KEY` (16/24/32 bytes) — never a flag, never in a
  policy file.
- Presidio is a detector, not a guarantee: ages > 89, small geographic units, unusual date
  formats and local identifiers need a human or a `patterns:` entry — see entities.md §gaps.
