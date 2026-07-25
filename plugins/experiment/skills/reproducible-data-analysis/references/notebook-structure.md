# Notebook Structure

Use this as a default outline for reproducible notebook-based analysis.

## Recommended section order

1. **Title / scope**
   - State what dataset is being analyzed and what the notebook aims to produce.

2. **Setup**
   - Imports
   - Project-relative paths
   - Plot style defaults

3. **Load inputs**
   - Read source files
   - Enumerate sheets/tables when needed

4. **Profile inputs**
   - Shapes
   - Column names
   - Sample rows
   - Missingness or type issues worth noting

5. **Clean / reshape**
   - Standardize column names
   - Tidy wide data when needed
   - Create derived metrics deliberately

6. **Analyze / visualize**
   - Build tables and plots that answer the actual question
   - Save final figures to `plots/`

7. **Export outputs**
   - Save cleaned tables or summaries to `outputs/` when useful

8. **Interpretation / caveats**
   - Summarize the key findings
   - State what the data does and does not support

## Default preference

Prefer a notebook when the user is likely to:
- inspect intermediate steps
- rerun cells manually
- validate charts visually
- modify the analysis later
