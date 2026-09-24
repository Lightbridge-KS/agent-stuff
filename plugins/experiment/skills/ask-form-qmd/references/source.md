# Source and result contract — v1

Only `title` is required in frontmatter. Optional: `subtitle`, `form: {version: 1,
layout: article}`, and `assets: {diagram: images/local.png}`. Titles are plain text.
Question YAML and frontmatter reject duplicate keys and aliases. Quote YAML words
such as `"yes"` and `"no"` when intended as string identifiers.

```yaml
---
title: Review the proposal
form:
  version: 1
assets:
  screenshot: images/screenshot.png
---
```

The body supports ordinary Markdown, literal code fences, `{mermaid}` diagrams,
Quarto `.panel-tabset` with 2–6 same-level headings, two equal `.column` divs inside
`.columns`, and `.callout-note`/`.callout-tip`/`.callout-warning` with optional
`collapse="true"`. Tabs/columns are main-flow layouts and cannot nest. Callouts can
appear in the main flow or a tab/column; their bodies exclude diagrams/layouts.
Images use `![Alt text](asset:screenshot)` and declared PNG/JPEG/WebP files within
the source directory. No raw HTML, remote images, custom CSS/JS, author filters,
includes/shortcodes, or executable Python/R/OJS cells. Code examples stay literal.
Heading/block IDs beginning `aq-` or `rd-` are reserved for the viewer.

## Questions

Interleave `{ask}` fences in the main document. Each carries one YAML mapping.
Do not put questions in tabs, columns, callouts, lists, or quotes. Duplicate IDs
and unknown keys are errors. `schema` emits the exact question JSON Schema.

````markdown
```{ask}
id: direction
type: single_select
label: Which direction should proceed?
required: true
options:
  - value: native
    label: Native controls
    recommended: true
  - value: current
    label: Current form
recommendation: Native controls fit a document-led review.
```
````

Common fields: `id` (lowercase letters/digits/underscore/hyphen), `type`, `label`,
optional `required`, `help`, and `recommendation`. IDs must be unique. Recommendations
badge choices/values; they never choose for the reader.

| Type | Fields | Answer |
|---|---|---|
| `single_select` | `options[{value,label,description?,detail?,recommended?}]`, `allow_other` default true | string |
| `multi_select` | same options, `min`/`max` selection counts, `allow_other` | string array |
| `scale` | required `min`/`max`, `step` default 1, `labels`, `recommended` | number, omitted until touched |
| `number` | optional `min`/`max`/`step`/`unit`/`recommended` | number |
| `ranking` | `options[{value,label}]` | complete order, omitted until moved/confirmed |
| `short_text` | `placeholder`, `max_length` | nonblank text |
| `long_text` | `placeholder` | nonblank text |
| `matrix` | `rows` and `columns` as `{value,label}` lists | row → column |
| `review` | `items[{id,label,description?,detail?,recommended?}]`, `decisions` default approve/revise/reject, `comment` default true | item → {decision,comment} |

Option/row/item identifiers are unique in their list. Identifiers and decisions
must be nonblank and have no surrounding whitespace. `__other__` is reserved.
A single-select question permits at most one recommended option; multi-select
bounds must be satisfiable with its options plus at most one Other answer.
Numbers must be finite and satisfy range/step (step starts at `min`, or zero).
Required matrices/reviews need every row/item; optional ones may be partial.
No duplicate multi-select entries or missing/duplicate ranking entries.

`help` and `detail` are constrained rich Markdown: prose, code, images, diagrams;
put headings and Quarto layouts in the surrounding main context. Details expand
beneath the question. Notes are available on every question; overall comments end
the form. Limits: 1 MB source, 20 diagrams at 30 KB each, 20 images at 10 MB each /
20 MB total, 40 MB rendered HTML, 1 MB submission body.

## Collection

`ask` waits for one terminal outcome; no default timeout. Browser validation gives
immediate feedback and the receiver validates again. Ctrl/Cmd+Enter submits.
Invalid answers preserve input and focus the first invalid question. A successful
submission disables collection; duplicate POSTs cannot create another record.
The browser can recover an accepted result through authenticated `/state` during
the five-second acknowledgement window. That is delivery grace, not a user timeout.

`status: submitted` includes `answers` and `meta`: `ask_id`, `duration_s`, `skipped`,
`other`, `notes`, `comments`, `diverged`, and on archive success `saved` and `bundle`.
`other` names IDs carrying free text rather than only catalog values. A save failure
adds `save_error`; submitted answers still return with exit 0. Cancellation/timeout
returns only its status with exit 1. Closing the tab does not cancel the process.

## Persistence

Resolve state with `lb path --json` from the invocation project. Submitted records
are `asks/<ask-id>.md`; complete companion bundles are `asks/_bundles/<ask-id>/`.
No config opt-in, parallel database, or implicit archive reading. Use `list` to find
this producer's records, or search `asks/*.md` alongside existing ask-form records.
`open` verifies file hashes and uses the frozen HTML/result read-only. `serve` is its
foreground fallback. `stop` stops the viewer without deleting the record.

The bundle contains normalized `source.qmd` (asset paths point to bundled copies),
`form.json`, `result.json`, `assets/`, `rendered/index.html`, and `manifest.json`.
The top-level Markdown file is the completion marker and readable projection.
Relative links survive state moves. The manifest records source/render/schema/theme
versions and integrity hashes; session tokens and addresses are runtime-only.
Unreferenced bundles after an interrupted publication are retained for diagnosis.
`list` skips incomplete/modified records; explicitly opening one reports the failure.

`--stage-save` is available where a harness requires separately authorized host
writes. It stages the entire package in private system temp and emits one stderr
line prefixed `ASK_QMD_SAVE_REQUEST`, then waits up to 120 seconds:

1. Validate `source_bundle` and `source_record` are within this process's system-temp
   session, are regular files/directories without symlinks, and match the advertised
   manifest and record SHA-256. Verify the manifest's file hashes. Resolve the
   destination independently through `lb path --json`; require the matching ask ID
   under its `asks/_bundles/` and `asks/`.
2. Perform only the exact permitted directory creation and no-clobber copies: the
   bundle to `destination_bundle`, then the record to `destination_record`. The
   Markdown record must be last. Never escalate the collecting Python server or
   copy arbitrary directory contents supplied by a form.
3. The original process verifies the copied manifest, record, and every bundled file
   before returning `meta.saved`. If permission is denied or the copy fails, create
   only the emitted `abort` marker so answers can return with `save_error`.

The staged package is temporary and is removed after the result returns. No-save
runs never request a copy. Do not describe an unverified or partial copy as saved.
