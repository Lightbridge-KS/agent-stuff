---
name: md-to-docx
description: "Render Markdown files to DOCX (Word) format using Quarto CLI. Use when the user asks to convert, render, or export Markdown (.md) files to .docx format. Supports custom DOCX reference templates for consistent styling (fonts, margins, headings). This skill is for Markdown-to-DOCX conversion only — not for editing existing .docx files."
metadata:
  version: "2026-07-26"
---

# Markdown to DOCX Rendering

Render any Markdown file to a Word document (.docx) using **Quarto CLI** as the rendering engine.

## Prerequisites

Quarto CLI must be installed and in PATH. Verify with:

```bash
quarto --version
```

If not installed, direct the user to https://quarto.org/docs/get-started/

## Basic Rendering

To render a Markdown file to DOCX, placing the output in the **same directory** as the input:

```bash
quarto render /path/to/document.md --to docx --output-dir "$(cd "$(dirname /path/to/document.md)" && pwd)"
```

### Critical: --output-dir requires an absolute path

Quarto interprets `--output-dir` relative to the **input file's directory**, not the current working directory. Always resolve to an absolute path. If you want the output in the same folder as the input:

```bash
INPUT="/path/to/document.md"
OUTPUT_DIR="$(cd "$(dirname "$INPUT")" && pwd)"
quarto render "$INPUT" --to docx --output-dir "$OUTPUT_DIR"
```

If the user specifies a different output directory, resolve it to an absolute path:

```bash
quarto render "$INPUT" --to docx --output-dir "$(cd /path/to/output && pwd)"
```

### Output naming

Quarto automatically names the output with the same stem as the input:
- `report.md` → `report.docx`
- `meeting-notes.md` → `meeting-notes.docx`

Do NOT use the `--output` flag — it causes path handling issues with `--output-dir`.

## Using Templates

Templates are `.docx` reference documents that control styling (fonts, margins, heading styles, page layout). They do NOT contain content — only style definitions.

### Available templates

Check the skill's `assets/` folder for bundled templates:

```bash
ls ~/.agents/skills/md-to-docx/assets/*.docx
```

Currently bundled:
- `th-sarabun-new-ref-bw.docx` — Thai Sarabun New font, black & white style

### Applying a template

Use the `-M reference-doc:` flag with the **absolute path** to the template:

```bash
TEMPLATE="$HOME/.agents/skills/md-to-docx/assets/th-sarabun-new-ref-bw.docx"
quarto render "$INPUT" --to docx --output-dir "$OUTPUT_DIR" -M "reference-doc:$TEMPLATE"
```

### Important: correct template flag syntax

Use `-M reference-doc:<path>` (Quarto metadata flag). Do NOT use:
- `--reference-doc` — Quarto silently ignores this Pandoc passthrough
- `-- --reference-doc` — Also silently ignored

### When to use a template

- If the user asks for specific fonts, margins, or styling → use a template
- If the user mentions "Thai" or "Sarabun" → use `th-sarabun-new-ref-bw.docx`
- If the user just wants a basic conversion → no template needed, omit the flag

## Batch Rendering

To render multiple Markdown files:

```bash
for f in /path/to/docs/*.md; do
  quarto render "$f" --to docx --output-dir "$(cd "$(dirname "$f")" && pwd)"
done
```

## Error Handling

- If `quarto` is not found: tell the user to install Quarto from https://quarto.org
- If rendering fails: Quarto prints errors to stderr — read and relay the error message to the user
- If the input file doesn't exist: verify the path before running quarto
