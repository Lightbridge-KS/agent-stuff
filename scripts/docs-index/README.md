# docs-index

Print a compact, **read-before-coding** index of a repo's `docs/` — one line per doc
with a short summary and optional "read when" hints. The point is a cheap, scannable map
an agent reads at the start of a task, then opens only the docs that match the work.

Adapted from Peter Steinberger's `scripts/docs-list.ts`, rewritten in Python + `uv`
with configurable paths, a `description` fallback, and JSON output for hook consumption.

## Use

```sh
uv run docs_index.py                     # human index of ./docs
uv run docs_index.py --dir documentation # a different docs dir
uv run docs_index.py --json              # machine-readable
uv run docs_index.py --exclude archive,research,vendor
uv run docs_index.py --include CONTEXT.md,CONTEXT-MAP.md,VISION.md  # extra root-level files
```

`--include` names files **outside** `--dir` (relative to the current directory) to index
too — typically root-level charter docs like `CONTEXT.md` / `CONTEXT-MAP.md` / `VISION.md`.
They render in a separate `Charter docs (repo root)` group; missing files are skipped.

Run it from the repo root (it reads `./docs` by default). Installed onto `PATH` via
`bin/install.py` it's just `docs-index`.

Exit codes: `0` success (even if some docs lack a summary); `2` when `--dir` is missing.

## Frontmatter contract

Each doc may carry YAML frontmatter. All keys are optional, but a doc with none is
flagged in the index so gaps are visible.

```yaml
---
summary: One line on what this doc covers.
read_when:
  - touching the cache layer
  - changing database migrations
---
```

- `summary` — the one-line description shown in the index. Falls back to the standard
  `description` key when absent, so skill-style frontmatter is understood too.
- `read_when` — a list (or a single string) of task hints. Shown under the summary so the
  agent knows *when* this doc is relevant.

## Wire it into a project

Add a line to the project's `AGENTS.md` / `CLAUDE.md`:

> Before coding, run `docs-index` and read any doc whose "Read when" hint matches the task.

Or make it automatic with the companion hook in
[`hooks/docs-index-inject`](../../hooks/docs-index-inject) — a `SessionStart` hook that
injects this index into the agent's context with no manual step.
