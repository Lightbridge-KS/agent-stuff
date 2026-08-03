# liteparse (`lit`) reference

Local, model-free document parser. Verified against liteparse **2.0.0**
(`npm i -g @llamaindex/liteparse`). PDFs work out of the box; Office files need
LibreOffice, images need ImageMagick (auto-converted to PDF).

## `lit is-complex` — the router probe

```bash
lit is-complex "<file>" --compact -q     # exit 0 = simple, 1 = complex
```

Emits a JSON array, one object per page. Fields that matter for routing:

- `needsOcr` + `reasons` (e.g. `vector-text` — text drawn as graphics; OCR required even
  on born-digital PDFs)
- `layout.isComplex` + `layout.reasons` (`multi-column`, `table-likely`, `dense-graphics`)
- `isGarbled` — broken text layer

Options: `--target-pages "1-5,10"` · `--max-pages <n>` · `--password <pw>`.
Any page complex → treat the document as complex.

## `lit parse` — local markdown extraction

```bash
lit parse "<file>" --format markdown -o out.md
```

Key flags:

| Flag | Effect |
|---|---|
| `--format json\|text\|markdown` | default `text` — always pass `markdown` explicitly |
| `--no-ocr` | skip OCR — only when the probe didn't flag `needsOcr`; much faster |
| `--ocr-language <lang>` | Tesseract language, default `eng` |
| `--image-mode off\|placeholder\|embed` | raster images in markdown; default `placeholder` |
| `--image-output-dir <dir>` | where embedded images land with `--image-mode embed` |
| `--keep-headers-footers` | keep running headers/footers (stripped by default) |
| `--no-links` | plain anchor text instead of hyperlinks |
| `--target-pages "1-5,10"` / `--max-pages <n>` | partial parse |
| `--password <pw>` | encrypted documents |
| `-q, --quiet` | suppress progress |

`--format json` adds layout/bounding boxes (`--complexity`, `--extract-content-bounds`,
form fields, annotations) — much larger output; only when structure is needed.

## `lit screenshot` — visual fallback

When a page's content genuinely can't be captured as text (dense charts, figures):

```bash
lit screenshot "<file>" --target-pages "13" --dpi 150 -o outdir/
```

One page at a time, modest DPI (150–200). The flag is `--target-pages`, not `--pages`.

## `lit batch-parse`

```bash
lit batch-parse <input-dir> <output-dir>    # same per-file flags apply
```

## OCR model cache (first-run gotcha)

The first OCR run downloads `eng.traineddata` from GitHub
(`tesseract-ocr/tessdata_best`) and caches it locally. Sandboxed shells may block the
cache write — symptom: `[ocr] failed for page N: error sending request` while the URL
itself is reachable. Fix: one unsandboxed run; the cache persists.
