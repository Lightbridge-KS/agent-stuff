---
name: ask-form
description: >-
  Ask the user through a local glass form when a chat question or AskUserQuestion cannot carry
  it: sliders, rankings, matrices, long text, a diagram or image to react to, per-item
  approve/reject with comments, or more than four questions at once. Bundled CLI serves the
  form on 127.0.0.1, opens the browser, and returns the answers as JSON. Also on request
  ("use the form", "ask me with a form"). Needs a machine with a browser.
metadata:
  version: "2026-09-03"
---

# ask-form

The agent supplies the judgment: what to ask, in what order, with what context. The tool is
deterministic: a fixed catalog of ten element types rendered as one scrolling glass page, answers
back as one JSON document on stdout. It is the Declarative tier of `generative-ui`: you compose from
the catalog, you never write HTML.

`<skill_dir>` = the directory this SKILL.md was read from. Every call:

```bash
uv run <skill_dir>/scripts/ask_form.py [SPEC] [--no-open] [--timeout S]
```

## When to use it, and when not

```
Can AskUserQuestion / request_user_input carry it?   ≤ 4 questions, 2–4 options each, no scales
  yes → use that. It is faster and works on the phone.
  no  → ask-form:  scale · ranking · matrix · long text · number · a diagram/image to react to ·
                   per-item approve/revise/reject · more than four questions in one pass
User asked for the form ("use the form") → ask-form regardless.
User is not at a machine with a browser (mobile, SSH) → chat.
```

## Flags and exit codes

| call | does | exit |
|---|---|---|
| `ask_form.py [SPEC]` | validate, serve, open the browser, wait until submit or cancel, print answers | 0 submitted · 1 cancelled (or timeout, only with `--timeout`) · 2 invalid spec · 3 could not bind |
| `--example` | print a spec exercising every element type; start from it | 0 |
| `--schema` | print the JSON Schema of a spec (the single source of truth for fields) | 0 |
| `--validate [SPEC]` | check the spec only; prints answerable and required ids | 0 valid · 2 invalid |
| `--timeout S` | give up after S seconds; by default the form waits until the user acts | |
| `--no-open` | print the URL, do not launch a browser | |

`SPEC` is a path, `-`, or omitted for stdin. stdout is exactly one JSON document; the URL and
notes go to stderr. Exit 2 errors name the JSON path to fix, e.g. `$.questions[2].options`.

## Workflow contract

1. **Decide the surface** with the router above. State in one line why chat is not enough.
2. **Draft the spec** (run `--example` if unsure of the shape). Compose well:
   - ≤ 8 elements; one decision per question; `required` only where an unanswered question blocks you.
   - Put a `context` pane (markdown, mermaid, image) directly before the question it informs.
   - Use `review` for a list of 💡 decisions the user must approve, revise, or reject one by one.
   - Option descriptions say what happens if chosen. Labels in sentence case, no filler.
3. **Run it** via stdin, **in the background** so the harness's shell timeout cannot cut the wait
   (Claude Code: `run_in_background: true`; stdout lands in the task's output file). The form has
   no timeout of its own; it waits until the user submits or cancels.
   ```bash
   uv run <skill_dir>/scripts/ask_form.py - <<'EOF'
   { "spec_version": 1, "title": "…", "questions": [ … ] }
   EOF
   ```
   Tell the user a tab is opening. If stderr says the browser could not be launched (Codex's
   sandbox blocks it), hand the user the URL from stderr and keep waiting. If the user moves on
   in chat without answering, stop the background process instead of leaving it listening.
4. **Read the answers** from stdout and branch on the exit code:
   - `0` → `answers` keyed by id; `meta.skipped` lists optional ids left blank; `meta.other` lists
     ids answered with free text through "Other". Quote the user's answers back briefly, then act.
   - `1` `cancelled` → the user declined this channel. Ask in chat why; do not re-open.
   - `1` `timeout` → only when you passed `--timeout`; ask in chat, do not re-open unasked.
   - `2` → fix the field named in `errors[].path` and rerun.
   - `3` → loopback could not bind; fall back to chat.
5. **Verify** before moving on: every `required` id you relied on is present in `answers`, and any
   id in `meta.other` is treated as free text, not as an option value.

## Element types

| type | answer |
|---|---|
| `section` (heading), `context` (`markdown` · `mermaid` · `image`) | none |
| `single_select` (`options`, `allow_other`) | the value, or the typed text |
| `multi_select` (`options`, `min`, `max`, `allow_other`) | list of values |
| `scale` (`min`, `max`, `step`, `labels`) · `number` (`min`, `max`, `step`, `unit`) | number |
| `ranking` (`options`) | full ordering of values |
| `short_text` (`max_length`) · `long_text` | string |
| `matrix` (`rows`, `columns`) | `{row: column}` |
| `review` (`items`, `decisions`, `comment`) | `{item: {decision, comment}}` |

Fields and constraints: `--schema`. Closing the tab ends nothing: the run waits for Cancel or Send.

## Security and limits

Loopback only, random port, token in the URL gating the page, assets and the answer routes.
`context.src` may name a local image; only files declared in the spec are served, nothing else on
disk. Agent strings render as text or sanitized markdown; no images in markdown. Mermaid loads from
cdnjs only when a diagram is present; offline it degrades to the source. Do not put PHI in a spec
you cannot justify showing in a browser tab.
