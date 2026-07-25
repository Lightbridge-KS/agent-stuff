# Output Validation

Do not stop at “the code ran.” Validate the result.

## 1. Reproducibility validation

Confirm the workflow can run end-to-end:

- execute the notebook or script without errors
- confirm paths resolve from the project structure used in the analysis
- confirm required dependencies are declared through the local `uv`-managed environment
- confirm the main notebook/script does not depend on hidden manual steps

## 2. Artifact validation

Confirm the expected deliverables actually exist:

- expected plot files exist in `plots/`
- expected derived tables exist in `outputs/` when promised
- files are non-empty
- filenames are stable, readable, and correspond to what the analysis claims to produce

## 3. Analytical validation

Confirm the analysis logic makes sense:

- totals, rates, and denominators are not mixed carelessly
- labels, units, and date ranges are correct
- the chart type matches the underlying relationship in the data
- summaries do not overclaim beyond what the dataset actually encodes
- caveats are stated when semantics are ambiguous

## 4. Visual validation

If the goal includes visualization, inspect the final exported image files directly.

Do not rely only on notebook inline output.

When image inspection is available, look at the exported plots and check for:
- cropped plot area, title, subtitle, labels, or legend
- overlapping annotations or tick labels
- unreadable text size
- bad aspect ratio or excessive whitespace
- color choices that reduce readability
- scales that visually mislead
- extreme outliers that flatten everything else and justify a second view

## 5. Completion standard

Consider the task ready only when:

- the analysis is rerunnable
- the artifacts exist where a human would expect them
- the exported visuals are legible
- the interpretation is aligned with the data and its limits
