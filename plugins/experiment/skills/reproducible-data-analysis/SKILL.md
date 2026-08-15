---
name: reproducible-data-analysis
description: >-
  Build reproducible, reviewable data-analysis projects for tabular data (CSV, Excel,
  Parquet, …). Use for exploratory or reporting analysis that a human or future agent
  should rerun and validate — Jupyter notebooks, exported plots/tables, clean structured
  project layout.
metadata:
  version: "2026-08-15"
---

# Reproducible Data Analysis

## Overview

Use this skill to turn one-off dataset work into a clean, inspectable analysis project.

Prefer this skill when the user wants more than a quick answer: a notebook they can open, scripts they can rerun, plots saved to disk, or derived outputs that should remain understandable later.

## Workflow

### 1. Establish the project layout

Use or create a project-local structure like:

- `data/` for raw inputs
- `scripts/` for notebooks and helper scripts
- `plots/` for exported figures
- `outputs/` for cleaned tables, derived CSV/Parquet, and intermediate results
- `reports/` for markdown, Quarto, or polished narrative outputs

Keep raw inputs untouched. Do not overwrite source data files unless the user explicitly asks.

Read `references/project-layout.md` when you need the folder conventions or naming guidance.

### 2. Use a project-local Python environment managed by `uv`

Treat `uv` as the default package and environment manager for this workflow.

Prefer this pattern:

```bash
uv venv .venv
uv add pandas matplotlib seaborn jupyter openpyxl
uv run jupyter lab
```

Adjust dependencies to the task. Add only what is needed.

Guidelines:
- Prefer a local `.venv` inside the project.
- Prefer `uv add` / `uv sync` / `uv run` over raw `pip` when `uv` is available.
- Avoid polluting the global Python environment unless the user explicitly asks.
- If reproducibility matters across runs, keep `pyproject.toml` accurate.

### 3. Prefer notebook-first analysis when human validation matters

Default to a Jupyter notebook in `scripts/` for exploratory analysis, data cleaning, and visualization work that the user may want to inspect cell-by-cell.

Use a notebook structure like:
- setup and paths
- data loading
- input profiling / sanity checks
- cleaning / reshaping
- derived metrics
- visualization
- export
- interpretation and caveats

Execute the notebook in-place when practical so outputs are embedded and immediately reviewable.

Use plain Python scripts in `scripts/` only when the task is strongly batch-oriented or deterministic reuse matters more than interactive inspection.

### 4. Delegate chart craft to `data-visualization`

If the analysis includes charts, read and use the `data-visualization` skill for chart selection, labeling, accessibility, design quality, and plotting conventions.

Use this skill for the reproducible workflow around the analysis.
Use `data-visualization` for the craft of making the charts good.

### 5. Export durable artifacts

Do not leave the useful output trapped only inside notebook cells.

Export the final artifacts deliberately:
- save plots to `plots/`
- save cleaned or derived tables to `outputs/` when helpful
- save polished writeups to `reports/` when the task calls for them

Use stable, human-readable filenames with ordered prefixes when multiple outputs exist, for example:
- `01_volume_by_site.png`
- `02_abnormal_rate_by_disease.png`

### 6. Validate the output before calling it done

Always perform output validation. Do not assume that a successful script execution means the result is actually usable.

Read `references/output-validation.md` and follow it.

Minimum validation standard:
- rerun or execute the notebook/script end-to-end
- confirm expected files were created in the intended folders
- confirm exported artifacts are non-empty and named sensibly
- check that the interpretation matches the transformed data

If the task produces visualizations, inspect the final exported plot images directly. Do not rely only on notebook inline output.

If image inspection is available, use it to look for:
- cropped titles or labels
- overlapping text or legends
- unreadable fonts
- broken aspect ratios
- misleading axes or scales
- outlier domination that calls for an alternate view

### 7. State assumptions and caveats

Call out ambiguous semantics, especially with spreadsheet summaries.

Examples:
- totals that may be sums across categories rather than unique entities
- percentages that depend on filtered denominators
- missing units, dates, or entity definitions

A reproducible notebook is better when it explains where confidence is high and where interpretation should stay cautious.

## Reference files

- `references/project-layout.md` — folder conventions, naming, and artifact placement
- `references/output-validation.md` — reproducibility, artifact, analytical, and visual validation checklist
