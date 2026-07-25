# Project Layout Reference

Use this layout as the default starting point for reproducible data analysis work.

## Core folders

- `data/`
  - Keep raw source files here.
  - Preserve original filenames when practical.
  - Avoid editing raw inputs in place.

- `scripts/`
  - Store Jupyter notebooks and helper scripts here.
  - Prefer notebooks for exploratory, inspectable analysis.
  - Prefer `.py` helpers when a transformation is deterministic and reused.

- `plots/`
  - Store exported figures here.
  - Save final visual artifacts explicitly instead of leaving them only in notebook output.

## Optional folders

- `outputs/`
  - Store cleaned tables, derived datasets, summary CSV/Parquet, or machine-readable artifacts.

- `reports/`
  - Store markdown, Quarto, HTML, or polished narrative deliverables.

## Naming guidance

Prefer stable, readable filenames.

### Plots

Use ordered prefixes when there are multiple figures:
- `01_overview.png`
- `02_rate_by_group.png`
- `03_heatmap.png`

### Notebooks

Use descriptive names such as:
- `prediction_summary_analysis.ipynb`
- `eda_customer_churn.ipynb`
- `sales_forecast_validation.ipynb`

### Outputs

Name derived data by meaning, not by vague version labels:
- `cleaned_predictions.csv`
- `disease_summary_tidy.parquet`
- `site_level_metrics.csv`

Avoid names like:
- `final.csv`
- `final_v2.csv`
- `new_final_really_final.csv`

## Working rule

Keep the project readable enough that a human can open the folder later and infer:
- what the source data was
- where the analysis lives
- where the final figures live
- where the cleaned outputs live
