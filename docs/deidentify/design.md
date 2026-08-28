---
summary: Settled design for the `deidentify` skill (plugins/privacy) — PHI/PII scan,
  anonymize, pseudonymize and restore over text, JSON, CSV, images and DICOM, driven by a
  bundled deterministic CLI (scripts/deid.py) over Microsoft Presidio's Python SDK. The
  verb contract, findings JSON, policy YAML, sidecar (re-identification key material),
  exit codes, and the local-only rule.
read_when:
  - implementing or changing plugins/privacy/skills/deidentify (SKILL.md, deid.py, policies)
  - deciding whether a de-identification need belongs in this skill or in dcmtk / parse-to-md
  - adding an entity, operator, input type, language, or LLM recognizer to deid.py
  - wondering why the skill bundles its own CLI instead of using presidio-cli or REST
---

# `deidentify` — design

Approved 2026-08-28 (KS). Tracker: [`progress/v1.md`](progress/v1.md).

## Problem

An agent should be able to act on *"scan this file for PHI, flag it, then anonymize it"*
deterministically, locally, and reviewably — on text, JSON, CSV, images and DICOM pixels.
[Presidio](https://github.com/data-privacy-stack/presidio) has the detection and
transformation core (105+ recognizers, spaCy/transformers NLP, operators for replace / mask /
hash / encrypt), but none of its three surfaces fits an agent driving files:

| Upstream surface | Why not the skill's surface |
|---|---|
| `presidio-cli` | Scan only — no anonymize. Analyzes per line (splits multi-line entities). Exit code is always 0 (`show_problems()` returns a never-assigned `max_level = 0`). No `--list-entities`. |
| REST (Docker) | Deployment concern; no auth; refuses `custom` operators — pseudonymization and date shifting are SDK-only. |
| Python SDK | The real surface — but "use the SDK" means the agent hand-writes a fresh script on every request: non-reproducible, unreviewable, on PHI. |

## Decision

**Bundle a deterministic CLI** (`scripts/deid.py`, PEP 723 `uv run --script`) that wraps the
SDK behind a stable contract; SKILL.md stays a thin router + workflow. The agent supplies the
judgment — which entities, which policy, review of findings, verification — the tool never
does. Same shape as `image-gen` and `parse-to-md`.

Skill taxonomy: **Contract** (verbs, findings JSON, policy, sidecar, exit codes) over
**Reference** (entity catalog, operator params, Safe Harbor mapping). Vendor: **Authored**.
Domain: new `privacy` plugin.

**Local-only invariant.** Every recognizer and operator runs on this machine. Azure / OpenAI
recognizers are never enabled. Ollama is allowed only for local model tags — `*:cloud` tags
are refused. No PHI leaves the device through this skill.

## CLI contract

```
deid.py entities  [--lang en] [--json]
deid.py scan      <in> [--policy] [--threshold 0.5] [--entities A,B] [--allow x,y] [--columns hn=ID] [--llm ollama:<model>] [--explain] [--json]
deid.py anonymize <in> -o <out> --policy <preset|file> [--sidecar map.json] [--fill ...] [--json]
deid.py verify    <out> --policy <same>          # re-scan; keep/date_shift types are expected residuals, the rest are leaks
deid.py restore   <out> -o <orig> --sidecar map.json
deid.py doctor
```

**Exit codes:** `0` clean / done · `1` findings (scan) or leaks (verify) · `2` request invalid —
params or policy, validated *before* any engine loads · `3` environment — spaCy model,
tesseract, Ollama, or `DEID_KEY` missing; the message names the fix.

**Input routing** (by extension; the tool refuses what it can't route with exit 2):

```
.txt .md          → text        AnalyzerEngine + AnonymizerEngine
.csv .tsv / .json → structured  one cell model: every string cell span-scanned in a batch with the
                                column name / key path as presidio `context`; a group is typed as
                                bare entities (whole-cell operator) when forced by `columns:` or when
                                ≥60 % of cells hit with ≥80 % coverage — free text keeps its spans
.png .jpg .tif    → image       ImageRedactorEngine (Tesseract OCR → boxes), irreversible
.dcm / --dicom d  → dicom       DicomImageRedactorEngine (pixels ONLY — header scrub is dcmtk `dcmodify`)
.pdf .docx        → refused     route through parse-to-md (local `lit`) first
```

presidio-structured is **not** used: its column classifier typed free-text columns as a single
entity and replaced whole cells; the heuristic above plus `columns:` replaced it (spike record).

**Findings JSON** (`scan --json`):

- text: `[{entity_type, start, end, score, text}]` (+ `analysis_explanation` with `--explain`)
- structured: `[{column | key, entity_type, score}]`
- image / dicom: `[{entity_type, score, left, top, width, height, text}]`

Human default: compact table + one-line count. Bytes of anonymized output go only to `-o`.

## Policy YAML

```yaml
language: en
threshold: 0.5
entities: []            # optional restriction to these entity types
allow: []               # literals never flagged (exact match)
columns: {hn: ID}       # csv/json: force column / key (full dotted path or last segment) → entity
patterns:               # ad-hoc regex recognizers for local identifiers presidio lacks (HN, MRN)
  - {name: hn, entity: ID, regex: "\\bHN\\s?\\d{6,10}\\b", score: 0.7, context: [hn]}
operators:
  DEFAULT:         {op: replace}                    # → <ENTITY_TYPE>
  PERSON:          {op: pseudonym}                  # <PERSON_1>; consistent per run; reversible via sidecar
  PHONE_NUMBER:    {op: mask, chars_to_mask: 6, from_end: true}
  DATE_TIME:       {op: date_shift, days: random}   # one offset per run, stored in sidecar; unparseable → replace
  MEDICAL_LICENSE: {op: hash}
  US_SSN:          {op: encrypt}                    # AES key from $DEID_KEY only — never a flag
```

Operators: presidio's `replace`, `redact`, `mask`, `hash`, `encrypt`, `keep`, plus two
custom operators the tool registers: `pseudonym` (instance counter per entity type, from
upstream's pseudonymization sample) and `date_shift`. Both are reversible.

Shipped presets (`references/policies/`): `redact`, `safe-harbor` (HIPAA 18 identifiers
mapped to entities; see `references/entities.md` for the gaps), `pseudonym`, `mask`.

## Sidecar — re-identification key material

`--sidecar map.json` is **required** when the policy uses `pseudonym` or `encrypt` (restore is
impossible without it) and optional for `date_shift` alone — then the offset is simply lost,
which is what `safe-harbor` wants. Text sidecars carry `items`; csv/json carry `cells` addressed
by `{column,row}` / `{path}`:

```json
{"source": "...", "policy": "...", "created": "...",
 "entity_mapping": {"PERSON": {"Jane Doe": "<PERSON_1>"}},
 "date_offset_days": -37,
 "items": [{"start": 0, "end": 10, "entity_type": "PERSON", "operator": "pseudonym", "text": "<PERSON_1>"}]}
```

`restore` needs it (plus `$DEID_KEY` for `encrypt`). It is key material: playground / temp
only, never committed, never sent anywhere.

## Languages

- `en` — spaCy `en_core_web_lg`, pinned as a wheel URL in the script's PEP 723 header so
  one `uv run` installs everything (first run downloads ~600 MB; outside the sandbox once).
- Thai — presidio has no Thai NLP model. `TH_TNIN` (Thai national ID, checksum) is a pattern
  recognizer; it is registered under `en` always, so Thai IDs in mixed Thai/English documents
  are caught without a `th` language mode. Thai *names* need an LLM: `--llm ollama:<model>`
  adds presidio's `LMRecognizer` (LangExtract over local Ollama) — shipped only if the spike
  meets the usability gate recorded in the tracker.

## Out of scope (upstream docs cover these)

REST deployment (Docker/K8s), writing custom recognizers or NLP configs, evaluation
harnesses, DICOM *metadata* scrubbing (→ `dcmtk` skill), document parsing (→ `parse-to-md`).
