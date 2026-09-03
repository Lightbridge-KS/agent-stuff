---
summary: Settled design for the `ask-form` skill (plugins/productivity) — an agent-driven local
  glass form for human input richer than AskUserQuestion. A stdlib CLI bundled in the skill
  validates a JSON spec (ten element types), serves one page on 127.0.0.1, opens the browser,
  blocks, and prints the answers as one JSON document. The CLI contract, spec and answer shapes,
  server routes and terminal state machine, token scope, tier placement per generative-ui, and
  the UI direction.
read_when:
  - implementing or changing plugins/productivity/skills/ask-form (ask_form.py, static/, SKILL.md)
  - adding an element type, a flag, a route, or a persistence path to ask-form
  - deciding whether a question belongs in AskUserQuestion, ask-form, or chat
  - wondering why the CLI is bundled in the skill, why stdout is one JSON document, or why closing the tab is a timeout
---

# `ask-form` — design

Approved 2026-09-03 (KS) as Claude plan `wiggly-noodling-flamingo`. Tracker: [`progress/v1.md`](progress/v1.md).

## Problem

Harness question tools (`AskUserQuestion`, `request_user_input`) cap a question at four options
with a label and a description. Real design conversations need sliders, rankings, matrices, long
text, a diagram to react to, and per-item approve/revise/reject. The harnesses cannot render any of
that; the browser can. The one thing both Claude Code and Codex can do from their shells is bind a
loopback port (spikes in `_playground/2026-09-03_ask-form-spike/`); only Claude Code can also launch
the browser.

| surface considered | why not |
|---|---|
| Artifacts (claude.ai) | cloud-published, Claude-only, asynchronous; this is local, synchronous, harness-neutral |
| Claude Design canvas | mockups, not Q&A |
| Agent-written HTML | LLM code is third-party code; and it would drift per run (see `generative-ui`) |
| MCP server | right for Codex's launch problem, but a daemon plus registration for v1; deferred |

## Decision

A **Contract** skill with a **bundled, stdlib-only CLI**. The agent composes a spec from a fixed
catalog; the tool renders it, collects the answers, and returns them. Per `generative-ui`: the
question blocks are the **Declarative** tier (UI as data against a client-owned catalog), the chrome
is **Controlled**, and Open-ended is excluded. The catalog is the contract; every element type has
one answer shape and the server validates answers against it before accepting them.

The CLI lives inside the skill (`<skill_dir>/scripts/ask_form.py`), the shape `deidentify` and
`image-gen` use, because nothing but this skill drives it and its `static/` assets must travel with
it into every registry. Skill taxonomy: **Contract** (the value is the deterministic I/O contract).
Vendor: **Authored**.

## CLI contract

```
uv run <skill_dir>/scripts/ask_form.py [SPEC] [--no-open] [--timeout S]
                                     --example | --schema | --validate [SPEC]
```

`SPEC` is a path, `-`, or absent for stdin; a TTY on stdin with no path exits 2. Validation runs
before anything binds. The URL is the first stderr line, flushed; `webbrowser.open` follows unless
`--no-open`, and a launch failure is a stderr note, not an exit (the Codex path). stdout is exactly
one JSON document per run.

| exit | meaning | stdout |
|---|---|---|
| 0 | submitted | `{"status":"submitted","answers":{…},"meta":{"duration_s","skipped":[…],"other":[…]}}` |
| 1 | no answers | `{"status":"cancelled"}`, or `{"status":"timeout"}` when `--timeout` was given |
| 2 | invalid spec or usage | `{"status":"invalid","errors":[{"path","message"}]}` |
| 3 | could not bind loopback | `{"status":"error","stage":"bind","message"}` |

**No timeout by default** (KS, 2026-09-03): the run waits until Send or Cancel; `--timeout S` is
opt-in. The skill therefore runs the CLI in the background so the harness's shell cap does not cut the
wait, and tells the agent to stop the process if the user answers in chat instead. Closing the tab
ends nothing: no `pagehide` beacon (unreliable in Safari), and a silent wait beats a false cancel.

## Spec and answers

`{spec_version: 1, title, intro?, submit_label?, questions: [element…]}`. Every element has `id`
(`[a-z0-9_-]+`, unique), `type`, `label`, `help?` (markdown), `required?`. `section` and `context`
are display-only.

| type | answer |
|---|---|
| `single_select` (`options[{value,label,description?}]`, `allow_other?` default true) | string |
| `multi_select` (+ `min?`, `max?`) | `[string]` |
| `scale` (`min`, `max`, `step?`, `labels?`) · `number` (`min?`, `max?`, `step?`, `unit?`) | number |
| `ranking` (`options`) | full ordering of values |
| `short_text` (`max_length?`) · `long_text` | string |
| `matrix` (`rows`, `columns`) | `{row: column}` |
| `review` (`items[{id,label,description?}]`, `decisions?`, `comment?`) | `{item: {decision, comment}}` |
| `context` (`format: markdown\|mermaid\|image`, `content` or `src`) · `section` | none |

Shapes are monomorphic per type. "Other" never changes a shape: the typed text is the value and the
id is listed in `meta.other`. `meta.skipped` = answerable ids minus answered ids. Two channels the
agent never declares (KS, 2026-09-03): every answerable question carries an optional **note**
(collapsed behind a toggle, `n` opens it) returned as `meta.notes {id: text}`, and the form ends
with an optional **Comments** card returned as `meta.comments`. Both live in `meta` so answer
shapes stay stable; blank notes are dropped.

**Recommendations** (KS, 2026-09-03) are a spec flag, not label text, so they render consistently,
validate (one per `single_select`, value within range, decision within `decisions`, none on
`ranking`), and can be checked against the answer: `options[].recommended: true`,
`scale`/`number` `recommended: <n>`, `review.items[].recommended: "<decision>"`, plus an element-level
`recommendation` one-liner ("Agent recommends …") rendered under the help. The tool **never
preselects**; the user still chooses. `meta.diverged` lists answered ids where the choice differs
from the recommendation (multi_select: set inequality; review: any item), so the agent knows where
to ask rather than proceed. Recommended options are not reordered. `--schema` prints
the JSON Schema and is the single source of truth for fields; `--example` prints a spec covering
every type.

## Server

`ThreadingHTTPServer` on `127.0.0.1:0`, random token in the URL.

| route | token | notes |
|---|---|---|
| `GET /` | yes | `index.html` with the spec inlined as `<script type="application/json">` (`</` escaped) |
| `GET /static/*` | no | public code, path confined to `static/` |
| `GET /asset/N` | yes | Nth local image declared by a `context`; realpath-resolved at validate time, image extensions only |
| `POST /submit` | yes | JSON only (415), ≤ 5 MB (413), answers validated against the catalog (400) |
| `POST /cancel` | yes | |

**Terminal state machine.** One lock-guarded outcome, first writer wins (later terminal POSTs get
409). A handler stores the payload, writes its response, then sets the event. The **main thread**
waits on the event with the timeout, marks `timeout` if nothing else won, sleeps 0.3 s so in-flight
responses drain, then calls `shutdown()`. Calling `shutdown()` from a handler thread deadlocks.

## Composition and UI

Fixed: header (title, intro) → one glass card per element in spec order, `section` as a heading →
Comments card → sticky footer (answered count, Cancel, Submit). The agent orders, never lays out. Submit is disabled
until every `required` element has a value; clicking it then scrolls to the first missing one.

Monochrome glass in the shadcn manner (KS, 2026-09-03): near-black or off-white base following the
system theme, one soft highlight for the blur to catch, hairline borders, pill inputs and buttons,
a white-on-black (or black-on-white) primary button. Color only where it carries meaning: blue for
the answered edge and the footer fill line, green / amber / red on a chosen approve / revise / reject.
Signature element: the footer's fill line advances with the answered count. Keyboard: Tab between cards, arrows
within a group, `⌘⏎` submits; no digit shortcuts, no wrapping `<form>`. Markdown via vendored
`marked` + `DOMPurify` (`img` forbidden); mermaid lazily from cdnjs with a code-block fallback.

## Security posture

Loopback only. Token gates the page, assets and answer routes. Only spec-declared files are served.
Agent strings render as text or sanitized markdown. CSP restricts scripts to self and cdnjs. The
server exits after one terminal outcome. The skill tells the agent not to put PHI in a spec it could
not justify showing in a browser tab.

## Out of scope for v1 (tracked as Deferred)

MCP wrapper for Codex; persistence under `~/.lightbridge/asks/`; iPad reach over the tailnet;
partial answers on timeout; drag ranking; digit shortcuts; matrix multi-choice; long-text markdown
preview; animated backdrop; background run + poll for forms longer than 9 min.
