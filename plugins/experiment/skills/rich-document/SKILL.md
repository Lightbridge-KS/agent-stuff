---
name: rich-document
description: >-
  Present a rich browser document when a coding explanation needs Mermaid diagrams,
  tabs, collapsible detail, or side-by-side comparisons. Write constrained Quarto
  Markdown; the bundled CLI renders, saves, and opens it with light/dark themes.
metadata:
  version: "2026-09-21"
---

# Rich document

A Contract skill: the agent writes content; the deterministic CLI owns rendering,
themes, persistence, and the local viewer. Use for explanations that benefit from
navigation and diagrams. Plain answers stay in chat; questions belong to ask-form.

`<skill_dir>` is the directory containing this file. Requires `uv`, Quarto 1.9.38,
and the Lightbridge CLI (`lb` or `lightbridge`) for persistent artifacts. No extra
JavaScript runtime is needed. A copied skill needs these prerequisites on PATH.

```bash
uv run <skill_dir>/scripts/rich_document.py example
uv run <skill_dir>/scripts/rich_document.py schema
uv run <skill_dir>/scripts/rich_document.py validate explanation.qmd --json
uv run <skill_dir>/scripts/rich_document.py present explanation.qmd --json
```

1. Start from `example` or [the source contract](references/source.md). Write a
   title and supported Markdown blocks; do not author HTML, CSS, JS, or Quarto
   configuration. Ordinary code is displayed, never executed.
2. Run `present`. It validates before rendering and returns after viewer readiness,
   without waiting for the reader. Fix errors using the reported location and hint.
3. Link the returned URL and saved HTML. Report warnings; `ready` describes the
   server and validated artifact, not proof that the reader has seen it.

`--no-open` returns a URL without launching a browser; use the harness's browser
tool or a separately permitted OS open action for that exact URL. A browser launch
failure also returns the URL. `--no-save` explicitly creates a temporary artifact
instead of saving. Never silently substitute it for a failed persistent save.

```bash
uv run <skill_dir>/scripts/rich_document.py list --limit 10 --json
uv run <skill_dir>/scripts/rich_document.py open ARTIFACT_ID --json
uv run <skill_dir>/scripts/rich_document.py stop ARTIFACT_ID --json
```

Project scope is the invocation directory (Git root, or that directory outside Git).
Source paths do not change project scope. Persistent records live in the project's
Lightbridge `artifacts/` subtree. `open` does not recompile or require the original
source. `stop` stops the server and preserves saved files; temporary output is
removed on normal stop. There are no viewer timers. Closing a tab does not reliably
stop a server. Do not stop the user's viewer merely because the agent turn ends.

If a harness reaps detached children, run `serve ARTIFACT_ID` using its supported
background process mechanism, then open the emitted URL. This foreground fallback
also has no timeout; stop it explicitly when requested. macOS detachment is tested;
other harness/process-lifecycle combinations require verification.

JSON mode emits one object on stdout; diagnostics go to stderr. Exits: `0` success,
`2` invalid source/usage, `3` dependency/render failure, `4` persistence failure,
`5` viewer startup failure. Saved paths are included when viewing fails after save.

No PHI or secrets in the personal artifact store. MCP Apps, feedback collection,
custom widgets, remote images, and SVG inputs are not part of this version.
