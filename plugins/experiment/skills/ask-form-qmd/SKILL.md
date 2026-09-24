---
name: ask-form-qmd
description: >-
  Collect human decisions through a rich Quarto document with diagrams, comparisons,
  and native form controls. Use for document-led reviews or an explicit Quarto form;
  compact forms remain ask-form and simple questions stay in chat. Returns validated
  answers as JSON and archives submitted forms in Lightbridge asks.
metadata:
  version: "2026-09-25"
---

# Ask form QMD

An experimental Authored / Contract skill. Author constrained `.qmd` and declarative
`{ask}` blocks; the bundled CLI owns controls, rendering, collection, and records.
Requires `uv`, Quarto **1.9.38**, and `lb`/`lightbridge` for persistent records.
The skill carries independent copies of its theme and viewer; no sibling skill is required.

`<skill_dir>` is the directory containing this file.

```sh
uv run <skill_dir>/scripts/ask_form_qmd.py example
uv run <skill_dir>/scripts/ask_form_qmd.py schema
uv run <skill_dir>/scripts/ask_form_qmd.py validate review.qmd --json
uv run <skill_dir>/scripts/ask_form_qmd.py ask review.qmd --no-open
```

1. Use [the source contract](references/source.md) or `example`. Put rich reading
   context before the questions it informs; one decision per question. Mark a
   recommendation when there is a reason for one; recommendations never preselect.
2. Validate, repair source-located errors, then run `ask` as an ongoing process.
   Open its exact loopback URL from stderr using the harness browser capability.
   By default the process waits without a timeout until Send or Cancel.
3. Read the single terminal JSON document on stdout. `answers` is keyed by question
   ID; also read `meta.notes`, `comments`, `other`, `skipped`, and `diverged`.
   Quote the meaningful answers back; clarify divergence before acting on it.
4. Cite `meta.saved` when present. A save failure preserves answers and carries a
   `meta.save_error`; report that failure rather than claiming a durable record.

`--no-save` is explicit scratch mode. `--timeout SECONDS` is opt-in; no default timer.
`--stage-save` stages the complete bundle and transcript for a separately authorized
copy where required by a harness: follow the CLI's `ASK_QMD_SAVE_REQUEST` and
[storage contract](references/source.md#persistence). Never broaden permissions
for the whole server to perform that copy. Browser launch failure leaves the URL usable.

Submitted decisions go to the invocation project's `asks/*.md`, with source,
rendering, assets, and result in `asks/_bundles/<ask-id>/`. Cancel/timeout saves nothing.
No PHI or secrets in this personal archive.

```sh
uv run <skill_dir>/scripts/ask_form_qmd.py list --limit 10 --json
uv run <skill_dir>/scripts/ask_form_qmd.py open ASK_ID --no-open
uv run <skill_dir>/scripts/ask_form_qmd.py stop ASK_ID
```

`open` shows archived context and answers read-only; it never asks again. The viewer
has no idle timer; use `stop` explicitly. `serve ASK_ID` is a foreground fallback
when a harness reaps detached viewers. Do not stop a reader's viewer at turn end.

Exits: 0 submitted/command succeeded, 1 cancelled/timeout, 2 invalid input,
3 collection bind failure, 4 dependency/render/archive operation failure,
5 read-only viewer failure. An accepted submission whose save fails still exits 0.
Source code fences are displayed, never executed. Arbitrary HTML/CSS/JS, OJS,
Shiny, split layout, quote-to-note, and durable drafts are outside v1.
