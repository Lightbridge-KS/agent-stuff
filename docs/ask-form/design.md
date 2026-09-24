---
summary: Settled design for the `ask-form` skill (plugins/productivity) — an agent-driven local
  glass form for human input richer than AskUserQuestion. A stdlib CLI bundled in the skill
  validates a JSON spec (ten element types), serves one page on 127.0.0.1, opens the browser
  directly or through Codex's scoped launch path, blocks, and prints the answers as one JSON
  document. The CLI contract, spec and answer shapes, server routes and terminal state machine,
  token scope, tier placement per generative-ui, and the UI direction. v2 amendment: rich content
  (mermaid/diff/highlighted code in any markdown, option detail + Compare, tabs, quote-into-note,
  split layout, vendored libraries, context kept in the record).
read_when:
  - implementing or changing plugins/productivity/skills/ask-form (ask_form.py, static/, SKILL.md)
  - adding an element type, a flag, a route, or a persistence path to ask-form
  - changing how markdown, diagrams, code or context panes render in a form (static/rich.js)
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
| MCP server | unnecessary for desktop Codex once browser launch is split from the sandboxed server; retained as a possible remote-browser transport |

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

**Codex sandbox amendment (2026-09-13, #48).** Codex keeps the CLI, loopback server, declared-image
reads, and record rendering inside its normal sandbox. It passes `--no-open --stage-save`, reads the
URL from the first stderr line, and escalates only a separate macOS `open` call for that exact
`http://127.0.0.1:<port>/?t=<token>` URL. After submission the CLI stages the rendered record in a
private temp directory and emits one `ASK_FORM_SAVE_REQUEST` JSON line. Codex separately escalates
only exact `/bin/mkdir -p <asks-dir>` and `/bin/cp -n <stage> <record>` system commands, never the
repo-owned Python process; the CLI hashes the destination before reporting `meta.saved`. Denial,
mismatch, or the fixed 120-second commit timeout keeps the submitted answers and degrades to the
existing `not saved:` note. If launch approval is unavailable or denied, the printed URL remains the
manual fallback. The CLI uses `uv run --no-cache` because it has no dependencies and Codex's sandbox
may not permit writes to uv's user cache.

## CLI contract

```
uv run --no-cache <skill_dir>/scripts/ask_form.py [SPEC] [--no-open] [--timeout S]
                                                [--no-save | --stage-save]
                                                --example | --schema | --validate [SPEC]
```

`SPEC` is a path, `-`, or absent for stdin; a TTY on stdin with no path exits 2. Validation runs
before anything binds. The URL is the first stderr line, flushed; `webbrowser.open` follows unless
`--no-open`, and a launch failure is a stderr note, not an exit. Codex deliberately passes
`--no-open --stage-save`, launches the emitted URL through its separate scoped escalation path, and
commits the staged record through the exact-copy protocol above. `--stage-save` and `--no-save` are
mutually exclusive. stdout remains exactly one JSON document per run.

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
the JSON Schema and is the single source of truth for fields: it states every rule `--validate`
enforces that JSON Schema can express, names the rest in its `$comment`, and a conformance test
holds the two in agreement case by case. `--example` prints a spec covering every type.

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
`marked` + `DOMPurify` (`img` forbidden); rich rendering per *Rich content (v2)* below.

## Security posture

Loopback only. Token gates the page, assets and answer routes. Only spec-declared files are served.
Agent strings render as text or sanitized markdown. CSP restricts scripts to self (v2: every
library is vendored; no CDN). The
server exits after one terminal outcome. The skill tells the agent not to put PHI in a spec it could
not justify showing in a browser tab.

## Persistence

Every submitted form is written to `~/.lightbridge/projects/<project-key>/asks/<YYYY-MM-DD_HHMM>_<slug>.md`
(KS, 2026-09-03). Under the project, because an ask is a record of one project's decisions, the same
class as `handoffs/`; the canonical resolver (`scripts/lightbridge/lb_resolve.py`, path-loaded lazily
from the skill through the registry symlink) yields a key for every folder, and `lb mv` moves the
whole key directory so records travel. **Always-on**, `--no-save` opts out of one run, and there is
no config section: memory should not depend on remembering to opt in (the `handoffs/` precedent, not
`plans/`). A **plain archive**: `resume` does not read it; the agent greps it when relevant. Only
submitted runs are saved. Saving is best-effort: a failure (resolver missing in a copied install,
unwritable dir) is a stderr `not saved: …` note and never changes the exit code or the stdout document;
on success stdout carries `meta.saved`. In Codex, `--stage-save` holds that stdout until an exact
host copy appears at the resolver-selected destination with the advertised SHA-256; the temp source
is deleted on success, abort, mismatch, or the 120-second timeout. The record is markdown for the reader — frontmatter (title,
created, project, git, status, duration), one block per answerable question (answer per type,
recommendation, divergence, note), comments — with the raw spec and result as a JSON tail for
machines. Slug and same-minute collision suffix mirror `plan_store.write_plan`. `lb status` shows the
count; `lb doctor` and `lb mv` needed no change; the catalog lists `asks/` beside `handoffs/`.

## Rich content (v2)

Amended 2026-09-23 (KS, via an ask-form review; plan `elegant-purring-seahorse`). Tracker:
[`progress/v2.md`](progress/v2.md). Forms carry agent explanation; v2 makes that explanation render
as richly as `rich-document`, without its engine: all richness is client-side, the CLI stays
stdlib-only, `spec_version` stays 1, and **no answer shape changes**.

**Module.** `static/rich.js` is one deep module, `window.AskRich = {prose, diagram, diff, tabs}`;
`app.js` stays the catalog. Its diagram behaviour is copied from rich-document's `viewer.js` (enlarge
dialog with zoom/pan/Esc/focus restore; a serial off-screen render queue so diagrams in hidden tabs
lay out; a per-diagram error with its source) rather than shared, while rich-document is experimental.

**Rich prose** (every markdown surface: `intro`, `help`, `context.markdown`, and the new `detail`
fields) — GFM dialect so the record also renders on GitHub and Obsidian:

| source | renders as |
|---|---|
| ```` ```mermaid ```` fence | diagram, Enlarge button, re-rendered on light/dark change |
| ```` ```diff ```` fence | file / hunk headers, green/red lines |
| other code fence | language label, Copy, highlight.js colours on the glass tokens |
| `> [!NOTE]` `TIP` `IMPORTANT` `WARNING` `CAUTION` | callout |
| `<details><summary>` | collapsible block |
| GFM table | quiet full grid using theme borders; the table scrolls within its own outlined region when wide |

**Catalog additions** (all optional):

| field | effect |
|---|---|
| `single_select` / `multi_select` `options[].detail` (markdown) | Compare panel: tabs of the options (columns when exactly two carry detail); reading only, picking an option syncs the tab |
| `review.items[].detail` (markdown) | per-item "Show detail" toggle |
| `context.format: "tabs"` + `panels[{label, content}]` (2–6) | tabbed markdown panels |
| `context.format: "diff"` + `content` | same renderer as a diff fence |
| `context.collapsed: true` | the pane sits inside a `<details>` (summary = label or "Background") |
| `spec.layout: "stack" \| "split"` | a **hint** only (v2.1): `split` marks the ⚙ Settings button and labels Split "Suggested for this form"; it never applies a layout |

**Reader settings (v2.1, KS 2026-09-23).** Layout and theme are the reader's, not the agent's —
the call rich-document made for its theme. A ⚙ button at the footer's left opens a native popover:
*Layout* (One column, default · Split: each run of context panes and the questions after it become
one segment; from 1100 px the two columns sit side by side, both sticky so the shorter stays in
view, and the footer widens to match; *Explanation on* Right (default: questions left) or Left —
a visual flip only, the DOM keeps explanation first for Tab order, screen readers and Quote) and *Theme* (System · Light · Dark). `static/prefs.js` loads
in `<head>` and sets `data-theme` / `data-layout` on `<html>` before first paint. Choices persist in
host-only cookies on `127.0.0.1` (`askform_layout`, `askform_side`, `askform_theme`; SameSite=Strict, one year):
every run binds a new random port and `localStorage` is per port, while cookies ignore the port.
They carry only those enum values, never answers. Precedence: the reader's stored choice, else one
column and the system theme; the spec's `layout` hint never applies anything.

**Quote into note.** Selecting text in any rendered prose offers *Quote*; it appends `> …` to the
note of the card holding the selection, else the next question, else Comments. It reuses
`meta.notes`; nothing new crosses the wire.

**Libraries.** `mermaid@11.6.0` (MIT) and `highlight.js@11.11.1` common bundle (BSD-3) are vendored
under `static/vendor/` and loaded lazily only when a page needs them. The form works offline.

**Record.** `render_record` writes context panes in spec order (markdown verbatim; mermaid and diff
as fences; tabs as `####` panel headings; images as their reference), so the record keeps what the
user saw when answering.

**Not taken.** Glossary popovers are deferred; option ↔ diagram highlighting was rejected (it
depends on Mermaid's internal SVG ids).

## Out of scope for v1 (tracked as Deferred)

Remote-browser transport, including iPad reach over the tailnet (an MCP or resident-page design may
be appropriate there);
partial answers on timeout; drag ranking; digit shortcuts; matrix multi-choice; long-text markdown
preview; animated backdrop; background run + poll for forms longer than 9 min.
