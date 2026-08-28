# Entities — what deid detects, what counts as PHI, and what it cannot see

`deid.py entities` prints the live list for the installed presidio (PHI-relevant starred).
This page is the judgment layer on top of it.

## Always-on in deid (beyond presidio's defaults)

| Entity | Source | Note |
|---|---|---|
| `TH_TNIN` | presidio `ThTninRecognizer`, registered under `en` | Thai national ID, 13 digits, **checksum-validated** — an invalid checksum is not flagged |
| `ID` | `columns:`/`patterns:` in a policy, or the `--llm` recognizer | Presidio has no MRN/HN recognizer; local identifiers are yours to declare |
| policy `patterns:` | ad-hoc regex recognizers | e.g. `HN\s?\d{8}` → `ID`, score 0.6, context words boost |

## HIPAA Safe Harbor — 18 identifiers ↔ presidio entities

`safe-harbor.yaml` covers what the detector can reach. The last column is the honest part.

| # | Safe Harbor identifier | Entity type(s) | Gap / caveat |
|---|---|---|---|
| 1 | Names | `PERSON` | English NER only; Thai names need `--llm` |
| 2 | Geographic subdivisions smaller than a state | `LOCATION` | NER finds cities/countries; **street addresses, ZIP/postcodes, sub-district names are unreliable** — add `patterns:` |
| 3 | Dates directly related to an individual (except year); ages > 89 | `DATE_TIME` | Preset *shifts* dates rather than removing them (research-grade); free-text dates ("last Tuesday") become `<DATE_TIME_n>`; **ages > 89 are not detected at all** |
| 4 | Phone numbers | `PHONE_NUMBER` | Bare US/Thai numbers score 0.4 without context; CSV column names give context, prose usually does too |
| 5 | Fax numbers | `PHONE_NUMBER` | same |
| 6 | Email addresses | `EMAIL_ADDRESS` | strong |
| 7 | Social Security numbers | `US_SSN`, `TH_TNIN` (analogue) | |
| 8 | Medical record numbers | `ID` via `columns:`/`patterns:`/`--llm` | **not built in** |
| 9 | Health plan beneficiary numbers | `US_HEALTH_INSURANCE_MEMBER_ID`, `US_MBI` | US formats only |
| 10 | Account numbers | `US_BANK_NUMBER`, `IBAN_CODE`, `CREDIT_CARD` | `US_BANK_NUMBER` is loose (any 8–17 digits) |
| 11 | Certificate / license numbers | `MEDICAL_LICENSE`, `US_NPI` | US-centric |
| 12 | Vehicle identifiers, plates | `US_DRIVER_LICENSE` | plates not detected |
| 13 | Device identifiers, serial numbers | — | **not detected** — `patterns:` |
| 14 | URLs | `URL` | also fires on email domains (harmless overlap) |
| 15 | IP addresses | `IP_ADDRESS` | |
| 16 | Biometric identifiers | — | out of scope (not text) |
| 17 | Full-face photos | — | out of scope; image path redacts *burned-in text* only |
| 18 | Any other unique identifier | `UUID`, `MAC_ADDRESS`, `GENERIC_PII_ENTITY` (LLM) | |

Also flagged by default (not Safe Harbor, often wanted): `NRP` (nationality/religion/political
group — "Thai"), `ORGANIZATION` (hospital names; `pseudonym` preset keeps them), `CRYPTO`.

## Language coverage

- `en` — spaCy `en_core_web_lg` NER + all pattern recognizers. Thai script passes through
  unharmed; pattern recognizers (`TH_TNIN`, phone, email, dates in digits) work on mixed text.
- Thai names/addresses — no spaCy Thai model exists. `--llm ollama:gemma4:e4b` adds presidio's
  LangExtract recognizer over local Ollama: 5/5 names on a synthetic note, ≈25 s per 400 chars,
  occasional dropped span (`Extraction missing char_interval` on stderr means one was lost —
  rerun or add a `patterns:` entry). Not deterministic; verify the output.
- Other languages: not configured (presidio supports `de`/`es`/… with their spaCy models; out
  of scope for this skill).

## Reading a scan

- Overlaps are normal (`URL` inside an email, `DATE_TIME` on a digit run that is also `TH_TNIN`);
  the anonymizer keeps the highest-scoring/longest span.
- `recognizer` says who fired: `SpacyRecognizer` = NER (trust names/places, distrust digits),
  `*PatternRecognizer` = regex + context, `BasicLangExtractRecognizer` = the LLM.
- `--explain` adds the textual reason and the pre/post context-boost scores.
- Scores: pattern recognizers with checksums → 1.0; NER → 0.85; context-boosted patterns ≈
  0.75; bare weak patterns 0.05–0.4 (below the default 0.5). Lower `--threshold` to see them,
  raise `--allow` to silence a known-safe literal.
