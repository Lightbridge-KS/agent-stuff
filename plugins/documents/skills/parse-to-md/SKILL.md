---
name: parse-to-md
description: "Convert a document — PDF, DOCX, PPTX, XLSX, HTML — to Markdown. Routes between markitdown (simple, local), lit/liteparse (complex, local), and LlamaParse cloud (complex, highest quality). Use when the user asks to parse, convert, or extract a document into Markdown."
metadata:
  version: "2026-08-03"
---

# Parse to Markdown

Facade over three parsers. Pick by **complexity** (probe, don't guess) and **sensitivity**
(cloud uploads the document — gate it).

| Tool | Runs | Speed | Strength |
|---|---|---|---|
| `markitdown` | local | ~1s | Simple docs; many formats; zero setup |
| `lit` (liteparse) | local | ~1–5s | Complex layout, tables, OCR — best local option |
| LlamaParse (`scripts/llamaparse.cjs`) | **cloud** | ~1–2 min | Best quality on complex layout; **uploads the file** |

## Router

```
input file
 │
 ├─ obviously simple (plain DOCX/PPTX/XLSX/HTML) ──► markitdown
 │
 └─ PDF or unsure ──► lit is-complex "<file>" --compact -q
        │              (exit 0 = simple, 1 = complex; JSON reasons explain)
        │
        ├─ simple ──► markitdown  (inspect output; broken tables → treat as complex)
        │
        └─ complex ──► sensitivity gate:
              ├─ clearly public/non-sensitive (published paper, brochure)
              │     └──► llamaparse.cjs parse   (cloud, agentic tier)
              ├─ PHI / sensitive
              │     └──► lit parse --format markdown   (local only)
              └─ unsure whether it contains PHI/sensitive data
                    └──► ASK the user before any cloud upload
```

Rules:

- **Never silently upload.** Cloud (LlamaParse) only when the document is clearly
  non-sensitive or the user has approved it. PHI, patient data, or internal documents
  stay local (`lit`).
- **Trust the probe, not the born-digital heuristic.** `is-complex` may demand OCR on a
  born-digital PDF (vector-drawn text). Pass `--no-ocr` to `lit parse` only when the
  probe did NOT flag `needsOcr`.
- Parse **once** per document; write output to a file (`-o`), never dump to stdout.

## Quickstarts

```bash
# markitdown — simple docs
markitdown "in.pdf" -o out.md

# lit — complexity probe (exit code is the verdict), then local parse
lit is-complex "in.pdf" --compact -q
lit parse "in.pdf" --format markdown -o out.md          # OCR on by default
lit parse "in.pdf" --format markdown --no-ocr -o out.md # only if probe didn't flag OCR

# LlamaParse — cloud, via the bundled deterministic CLI (paths relative to this skill's base dir)
node scripts/llamaparse.cjs health                       # checks key + package
node scripts/llamaparse.cjs parse "in.pdf" --output out.md
```

Depth: [references/liteparse.md](references/liteparse.md) (full `lit` flags, probe JSON,
screenshots, batch) · [references/llamaparse.md](references/llamaparse.md) (tiers, cjs
flags, custom prompts, TypeScript escape hatch).

## Setup notes

- **`lit` first OCR run** downloads the Tesseract model (`eng.traineddata`) from GitHub
  and caches it. In a sandboxed shell this download can fail (`[ocr] failed for page N`)
  — run once outside the sandbox (or allow the cache path); subsequent runs work sandboxed.
- **LlamaParse** needs `LLAMA_CLOUD_API_KEY` in the environment and network access to
  `api.cloud.llamaindex.ai` (a sandboxed shell without that host allowed fails with
  `Connection error`). `node scripts/llamaparse.cjs health` verifies both prerequisites
  except the network.
- Installs, if missing: `pip install markitdown` (or `uv tool install markitdown`) ·
  `npm i -g @llamaindex/liteparse` (`lit`) · `npm i -g @llamaindex/llama-cloud`
  (LlamaParse SDK). `lit` needs LibreOffice for Office files, ImageMagick for images.
