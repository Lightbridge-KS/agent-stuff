---
name: md-to-docx
description: >-
  Render Markdown to DOCX via Quarto CLI (Pandoc fallback), Thai-friendly TH Sarabun New
  A4 template by default. Use when asked to convert or export .md to .docx. Not for
  editing existing .docx files.
metadata:
  version: "2026-08-15"
---

# Markdown to DOCX Rendering

Render any Markdown file to a Word document (.docx) — **Quarto CLI** as the primary
engine, plain **pandoc** as the fallback. Every render applies the bundled TH Sarabun
New A4 reference template unless the user explicitly asks for plain Word styling.

## Step 1 — Pick the render path

Run the detector (from this skill's base directory):

```bash
bash <skill-base-dir>/scripts/ensure_quarto.sh
```

Branch on its stdout / exit code:

- prints `quarto` (exit 0) → **Quarto path** (primary)
- prints `pandoc` (exit 1) → **Pandoc fallback** — same theme: Quarto's docx writer
  *is* pandoc, so `--reference-doc` styling is identical
- exit 2 → stop and tell the user: no docx renderer on this machine

On Linux without Quarto the script attempts a user-local install into `~/.local`
(no root); on macOS it suggests `brew install quarto`.

## Step 2 — Pick the template

Templates are `.docx` reference documents that control styling only (TH Sarabun New
font, A4 page, 1-inch margins, heading styles) — they contain no content.

Bundled in `<skill-base-dir>/assets/`:

- `th-sarabun-new-ref.docx` — color headings (dark blue) — **the default; use for
  every render**
- `th-sarabun-new-ref-bw.docx` — black headings — use when the user asks for
  print / black-and-white / grayscale output

Omit the template **only** when the user explicitly asks for plain/default Word
styling (Calibri look).

## Step 3a — Quarto path (primary)

Render to the **same directory** as the input:

```bash
INPUT="/path/to/document.md"
OUTPUT_DIR="$(cd "$(dirname "$INPUT")" && pwd)"
TEMPLATE="<skill-base-dir>/assets/th-sarabun-new-ref.docx"
quarto render "$INPUT" --to docx --output-dir "$OUTPUT_DIR" -M "reference-doc:$TEMPLATE"
```

Gotchas (each of these fails silently or breaks paths if ignored):

- **`--output-dir` requires an absolute path** — Quarto resolves it relative to the
  *input file's* directory, not the CWD. Always resolve as above; for a different
  output directory use `"$(cd /path/to/output && pwd)"`.
- **Template flag is `-M reference-doc:<abs-path>`** (Quarto metadata flag). Do NOT
  use `--reference-doc` or `-- --reference-doc` — Quarto silently ignores both.
- **Do NOT use `--output`** — it causes path handling issues with `--output-dir`.
- Output name follows the input stem: `report.md` → `report.docx`.

Batch rendering:

```bash
TEMPLATE="<skill-base-dir>/assets/th-sarabun-new-ref.docx"
for f in /path/to/docs/*.md; do
  quarto render "$f" --to docx --output-dir "$(cd "$(dirname "$f")" && pwd)" -M "reference-doc:$TEMPLATE"
done
```

## Step 3b — Pandoc fallback

Typically a web-app VM (Claude.ai / ChatGPT) with no Quarto and no way to install it.

```bash
TEMPLATE="<skill-base-dir>/assets/th-sarabun-new-ref.docx"
pandoc "$INPUT" --reference-doc="$TEMPLATE" -o "${INPUT%.md}.docx"
```

- Here `--reference-doc=` **is** the correct flag — the opposite of the Quarto path.
- Add `--toc` for a table of contents, `--number-sections` for numbered headings.
- Pandoc has no Quarto shortcodes (`{{< pagebreak >}}` etc.). For a page break,
  put a raw OpenXML block in the Markdown:

  ````markdown
  ```{=openxml}
  <w:p><w:r><w:br w:type="page"/></w:r></w:p>
  ```
  ````

## Error handling

- Exit 2 from `ensure_quarto.sh`: tell the user neither Quarto nor pandoc is
  available — install Quarto from https://quarto.org (or `brew install quarto`).
- If rendering fails: the renderer prints errors to stderr — read and relay them.
- If the input file doesn't exist: verify the path before rendering.
