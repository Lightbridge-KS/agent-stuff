# Setup, environment, and why the skill bundles its own CLI

## Environment

`scripts/deid.py` is a PEP 723 script: `uv run` builds and caches one environment from its
header — `presidio-analyzer[langextract]`, `presidio-anonymizer`, `presidio-image-redactor`
(OpenCV, pydicom, pytesseract), pandas, and the spaCy model `en_core_web_lg` **as a wheel URL**
(GitHub release), so there is no separate `spacy download` step. Python is pinned `<3.14`
(spaCy wheels).

- Cold: ≈ 2 min, ~2 GB in the uv cache. Warm: ≈ 2 s to load the engine.
- Downloads went through the sandbox proxy on this Mac (PyPI + GitHub releases). If a first run
  is refused, run it once outside the sandbox; nothing else needs the network.
- `deid.py doctor` reports versions, the model, `tesseract`, and Ollama.

| Need | Install |
|---|---|
| image / DICOM OCR | `brew install tesseract` (macOS) · `apt install tesseract-ocr` |
| `--llm` | Ollama running at `localhost:11434`; `ollama pull gemma4:e4b` (or any **local** tag) |
| `encrypt` | `export DEID_KEY=<16/24/32-byte string>` for the run |

## Ollama LLM recognizer

`--llm ollama:<model>` adds presidio's `BasicLangExtractRecognizer` (LangExtract over the Ollama
HTTP API) with presidio's stock PII/PHI prompt and examples, `enable_generic_consolidation`
off (precision: the catch-all otherwise flags ages and clinical findings), and a generated
config in a temp file. Measured on an M3 Pro, 406-char Thai note, 5 seeded names:

| model | seconds | names |
|---|---|---|
| `gemma4:e4b` (default) | 26 | 5/5 |
| `qwen3.5:latest` | 38 | 5/5 |
| `typhoon-s-thaillm-8b` | 46 | 5/5, over-flags clinical text |
| `gemma3:12b` | 53 | 4/5 |

Tags ending in `cloud` are refused: Ollama routes them to its hosted service and PHI would leave
the machine. The LLM is additive — pattern and NER recognizers still run.

## Why not the upstream surfaces

- **`presidio-cli`** scans only (no anonymize), analyzes line by line (multi-line entities
  split), has no entity listing, and its exit code is always 0: `show_problems()` initialises
  `max_level = 0` and returns it unchanged (`presidio_cli/cli.py`), so `run()` never sets the
  failure code. An agent cannot branch on it.
- **REST (Docker)** refuses `custom` operators, so pseudonymization and date shifting are
  impossible over HTTP; it also has no auth and adds a service to run.
- **SDK in ad-hoc scripts** — what a cheatsheet would lead to — means a fresh, unreviewed
  program on every request, on PHI. deid.py is that program written once, tested, with a
  stable contract.

Presidio's own docs (`docs/` in the upstream repo) remain the reference for extending
recognizers, other languages, and deployment; none of that is this skill's job.
