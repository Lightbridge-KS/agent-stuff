---
name: notebook-literate-python
description: >
  Notebook-native literate workflow for Python — author, execute, and iterate on
  Jupyter `.ipynb` files directly with NotebookEdit → nbconvert → NotebookRead, keeping
  code, results, and narration in one artifact. Use when building or running a Python
  notebook for analysis, EDA, a data report, or model-prototyping; when the
  edit→execute→verify loop on an .ipynb needs structure; when notebook outputs (tables,
  plots, tracebacks) must be read back and verified; or when deciding between a notebook,
  a plain .py script, and Quarto. Python only (uv-managed projects).
metadata:
  version: "2026-07-25"
---

# Notebook-Literate Python

Author `.ipynb` directly so a reader sees **narration + code + results** as one literate
report, and so a fresh kernel reproduces it top-to-bottom. This skill is the *procedure*;
the always-on principle lives in `~/.claude/CLAUDE.md` → **Literate & Notebook Workflow**.

## When to use / when not

| Use a notebook for | Use something else for |
|---|---|
| Exploratory analysis / EDA | **Smoke scripts, CI checks** → plain `.py` (clean exit code, no kernel) |
| A literate data report (prose + tables + plots) | **Heavy / long training loops** → `.py` script you can run + checkpoint; thin notebook only for the writeup |
| Model *prototyping* and result inspection | **Polished publication / any R work** → Quarto (`.qmd`) |

If the deliverable is "a script that does X," it's not a notebook. If it's "a report that
shows and explains X," it is.

## The core loop

```
NotebookEdit  ──►  author / insert / edit / delete cells (never hand-edit .ipynb JSON)
     │
     ▼
Bash          ──►  uv run jupyter nbconvert --to notebook --execute --inplace \
     │               --ExecutePreprocessor.timeout=120 notebooks/<name>.ipynb
     ▼
NotebookRead  ──►  read code + outputs back (tables/text/tracebacks read well; plots don't)
     │
     ▼
evaluate ──► zero errors & every claim backed? ──no──► loop ──yes──► done
```

`NotebookEdit` only changes cell *source* — it never executes anything. Outputs appear
only after the `nbconvert` step.

## The lever: `src/`-first (do this BEFORE touching the notebook)

The single biggest factor in keeping the slow execute loop short: **put reusable/heavy
logic in `src/` and verify it off-kernel first.**

```bash
# Smoke-test the logic with plain uv run BEFORE it ever enters a cell
uv run python -c "from mypkg.data import load_clean; df = load_clean(); print(df.shape)"
# or: uv run pytest -q
```

By the time logic reaches the notebook it's already correct, so the notebook loop only
validates *presentation*, not *correctness*. The notebook **orchestrates and narrates** —
it imports from `src/`; it does not hide meaningful logic inside long cells.

## Authoring conventions

- **One idea per cell.** Interleave **markdown** (the *what* and *why*) with **code** (the
  *how*). The notebook should read like a short report.
- **Every analytical claim is backed by the output cell directly below/above it.** Don't
  write a number in prose that no output shows. (If you cite per-group means, print a
  per-group means table.)
- **Imports + setup in one early cell**; reusable logic imported from `src/`.
- **Section structure that works:** Title/question → Load & clean → Describe + interpret
  → Visualize + read the plots → Model + metrics → Findings + caveats.

## Gotchas (hard-won)

### 1. Plots are opaque to the read tool — save them to files
Embedded image outputs come back as `"Outputs are too large to include…"` (base64 PNG
blobs). You **cannot see the chart** through `NotebookRead`. For any figure whose
*appearance* matters, also write it to a file and `Read` that file — standalone PNGs
render visually:

```python
fig, ax = plt.subplots()
# ... draw ...
fig.savefig("outputs/bill_shape.png", dpi=90, bbox_inches="tight")  # then Read this file
```

Verify the *data* behind a chart via printed tables even when you can't see the chart.

### 2. The kernel needs local sockets — disable the command sandbox for execution
A Jupyter kernel binds loopback TCP/ZMQ ports. Under a command sandbox `nbconvert
--execute` fails with `PermissionError: [Errno 1] Operation not permitted`
(`...find_available_port → tmp_sock.bind`). Run the execute step with the sandbox
disabled (or allowlist loopback). Also allowlist `~/.cache/uv` if `uv` itself is blocked.
This is environment-specific, not a code error.

### 3. `NotebookEdit insert` inserts at the TOP when given no `cell_id`
To build a notebook top-to-bottom, either **insert cells in reverse order** (last section
first, title last), or **chain on the `cell_id`** each insert returns (insert after the
previous cell). Read the notebook back once to confirm ordering.

### 4. Whole-notebook re-execution every time
`nbconvert --execute` reruns *all* cells on a fresh kernel — there is no partial run.
Cheap for light notebooks; for anything heavy, keep the expensive work in `src/`
(testable without the kernel) and the notebook thin, or cache/checkpoint deliberately.

## Verification gate (definition of done)

Done = runs top-to-bottom on a fresh kernel with **zero errors**, every claim backed by
an output. Machine-checkable after the execute step:

```bash
# 0 = no error outputs anywhere
jq '[.cells[]|select(.cell_type=="code")|.outputs[]?|select(.output_type=="error")]|length' notebooks/<name>.ipynb
# 0 = no unexecuted code cells (all ran this pass)
jq '[.cells[]|select(.cell_type=="code")|select(.execution_count==null)]|length' notebooks/<name>.ipynb
```

Tracebacks *are* text, so a failing cell reads fine via `NotebookRead` — localize and fix
the cell, then re-execute from clean.

## Commit policy & location

- **Commit executed notebooks** (outputs embedded) — they are the literate artifact.
  Accept the noisier diffs; the trade for a self-contained report is worth it.
- **Exploratory** notebook → `_playground/<YYYY-MM-DD_slug>/` (gitignored). **Kept /
  shareable** report → `notebooks/` at repo root (committed). The notebook's markdown
  doubles as the session `NOTES.md`.
- Keep figures in `outputs/` next to the notebook (both for the file-based visual check
  and as shareable artifacts).

## Decision matrix

| Use case | Recommendation | Why |
|---|---|---|
| Data analysis / EDA / literate report | **Notebook-native** | Deliverable *is* narration + outputs; tables read perfectly; fresh-kernel reproducibility built in. Pair with figures→files. |
| Model training / heavy compute | **`.py` script for the loop + thin notebook for the writeup** | Whole-notebook re-execution and kernel fragility make heavy notebooks painful to iterate. |
| Smoke script / CI check | **Plain `.py`** | Clean exit code, no kernel startup, trivial to assert; narration buys nothing. |
| Polished publication / any R | **Quarto (`.qmd`)** | Better rendering target; the canonical choice for R. |

## Quick reference

```bash
# Execute on a fresh kernel, outputs embedded in place (run with sandbox disabled)
uv run jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=120 notebooks/<name>.ipynb

# Pre-flight: verify src/ logic off-kernel
uv run python -c "import mypkg; ..."   # or: uv run pytest -q

# Post-flight gate: zero errors, all cells executed
jq '[.cells[]|select(.cell_type=="code")|.outputs[]?|select(.output_type=="error")]|length' notebooks/<name>.ipynb
```
