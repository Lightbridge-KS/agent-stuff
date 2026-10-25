---
name: explorable-document
description: Create a source-backed local explanation with MDX/TSX, custom diagrams, and working reader interactions; optionally collect a reviewed snapshot.
metadata:
  version: "2026-10-25"
---

# Explorable document

Contract × Authored. Use for explanations whose controls, linked views, or custom
visual composition materially help the reader. Use ordinary Markdown for a short
answer, `rich-document` for prose/standard diagrams, and `ask-form` when collecting
answers is the primary task. This is a local browser artifact, not an agent host.

## Workflow

1. Define the question, data provenance, useful interactions, and expected outputs.
   Independent exploration is the default. Enable handoff only when requested or
   returning a snapshot serves the task; it never wakes the agent.
2. Resolve this skill's directory. Run `uv run <skill>/scripts/explorable_document.py
   init <new-source-directory> --format mdx` (or `tsx`). Keep substantive behavior
   in TSX and calculations in plain TS. Read [source](references/source.md) before
   authoring; [visual patterns](references/visual-patterns.md) before styling.
   For node/connector diagrams, read [diagram primitives](references/diagrams.md).
   For line or part-to-whole charts, read [accessible charts](references/charts.md).
   For controlled fields, numeric drafts or selectable source/JSON, read
   [form and code utilities](references/forms-code.md).
3. Edit source and descriptor together. Declare every primary interaction and add
   fixed-runner browser checks for its expected effects and meaningful edge cases.
   Use the fixed catalog; no artifact-owned npm packages, config, plugins, or scripts.
4. Run `check <source> --browser --json`. Inspect the rendered dark/light views at
   narrow/wide widths, exercise keyboard controls, and check derived values against
   independent expectations. Follow [verification](references/verification.md).
   Build success and browser readiness alone are not behavioral verification.
5. Run `present <source> --evidence <check-evidence.json> --json`. Return the URL,
   artifact ID, source location, and honest check status. Saved revisions are immutable.
   See [lifecycle](references/lifecycle.md) for reopen/export/stop and explicit responses.

Do not use patient data, secrets, or sensitive inputs. Generated code runs in an
opaque-origin frame; the iframe/CSP boundary isolates viewer privileges but is not
an adversarial zero-egress or resource-exhaustion sandbox. Review source before use.
The local CLI needs Python/uv; building needs the pinned Node/pnpm toolchain and
package availability. Reopening saved output needs neither Node nor original source.
Remote chat uploads do not make this machine's viewer remotely accessible.
