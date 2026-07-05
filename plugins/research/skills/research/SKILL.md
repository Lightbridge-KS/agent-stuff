---
name: research
description: Stateful deep-research sessions — conversational scoping into an editable plan.md, then autonomous multi-wave searcher fan-out producing a cited, adversarially verified report, with resumable file state under docs/research/. Use when the user says /research, "start a research session", asks to resume or check on a research session, or needs pluggable backends (PubMed MCP) or research state that survives interrupts. NOT for quick one-shot fact-checked answers — use the built-in deep-research skill for those.
metadata:
  version: "2026-07-06"
---

# Research — stateful deep-research sessions

Five phases; the **filesystem is the only shared state**. Every invocation re-reads state
from disk — never trust conversation memory over the files. Design rationale:
`docs/research-skill-design/design.md` in agent-stuff.

Session directory layout:

```
<research-parent>/YYYY-MM-DD_<slug>/
├── plan.md            # SSOT: phase + config (frontmatter) and the plan (body)
├── notes/NN-<slug>.md # one searcher note per sub-question
├── sources/NN.yaml    # per-searcher ledger fragments (write-isolated)
├── sources.yaml       # merged ledger (script-generated — never hand-assemble)
├── verification.md    # verdicts on load-bearing / uncertain claims
├── report.md          # final cited report (output: markdown)
└── report.qmd + references.bib   # output: quarto (.bib script-generated)
```

## Session directory resolution

Precedence for `<research-parent>`:
1. `.lightbridge/config.toml` `[research] dir` (skip if `enabled = false`)
2. repo has `docs/` → `docs/research/`
3. otherwise ask once; default `./research/`

New topic → new session dir `YYYY-MM-DD_<slug>`. Bare `/research` with no topic → glob
`<research-parent>/*/plan.md`; exactly one non-done session → resume it; several → ask
which; none → ask for a topic.

## Phase router — first act on EVERY invocation

Read the session's `plan.md` frontmatter. Route on `phase`:

| `phase` | Action |
|---|---|
| no `plan.md` | New session: create dir, begin **SCOPING** |
| `scoping` | Re-read plan body; ask the still-open scoping questions; continue |
| `planned` | Run `status`; give a one-line plan digest; await the approval trigger |
| `executing` | Run `status`; resume the wave loop at the `progress` cursor |
| `verifying` | Re-read `verification.md`; verify only claims lacking verdicts |
| `reporting` | (Re)write the report; run the citation gate |
| `done` | Print `status` digest; offer a follow-up session — never mutate a done one |

The frontmatter `phase` field is the **only** phase authority. Update it (and `progress`)
immediately after each transition or completed wave, *before* narrating to the user.

## Phase: SCOPING

Conversational, not machinery. Before any searching:

1. Ask the 2–4 questions that most change what you'd research: audience/purpose, time
   range, depth, output language. Open questions in prose; enumerable choices may use
   AskUserQuestion. Skip questions `.lightbridge` or the conversation already answers.
2. **Capability probe** — determine the research fuel:
   - Built-ins: are WebSearch / WebFetch available (load via ToolSearch if deferred)?
   - MCP: ToolSearch for search/retrieval tools (e.g. `pubmed search articles`).
   - `.lightbridge/config.toml` `[research]`: `backends` preference order;
     `searcher_model` seeds `execution.searcher_model` in the plan (`corpus` is reserved
     for a future local-corpus module — acknowledge but don't use).
   - Map backends → modules: web search/fetch → [`modules/general-web.md`](modules/general-web.md);
     PubMed MCP → [`modules/academic-papers.md`](modules/academic-papers.md).
   - A missing capability degrades **visibly**: record what's absent in the plan body so
     the user can object before execution.
3. Write `plan.md` with `phase: scoping` as soon as topic + dir are known (crash-safe from
   minute one). When scope + probe + sub-questions are settled, draft the full plan body,
   set `phase: planned`, and present the plan in chat for iteration.

## Phase: PLANNED

`plan.md` schema (frontmatter fields exactly these; quote sub-question ids as strings):

```markdown
---
phase: planned              # scoping | planned | executing | verifying | reporting | done
shape: narrative            # v1: always narrative
topic: "<topic>"
created: YYYY-MM-DD
language: en                # report language (en | th)
output: markdown            # markdown | quarto (asked at scoping; see references/quarto-output.md)
backends: [websearch, webfetch, pubmed-mcp]   # probed + confirmed
modules: [general-web, academic-papers]
execution:
  wave_size: 4              # searchers per wave (rate-limit guard)
  max_waves: 3              # reflection-loop budget
  searcher_model: sonnet    # searcher tier; "inherit" to match the session model
progress:
  waves_done: 0
  sub_questions_done: []    # e.g. ["01", "02"]
---

# Research plan: <topic>

## Scope (from conversation)
- <digested answers: audience, time range, depth, language, capability gaps>

## Sub-questions
1. <sub-question — its number, zero-padded, is the note id NN>
2. ...
```

The user iterates by talking; edit `plan.md` in place, phase unchanged.

**Trigger rule (hard constraint):** approval phrases ("plan is OK", "conduct deep
research", "go ahead", "looks good") flip `phase` to `executing` **only while
`phase: planned`**. On flip, confirm in exactly one line — *"Starting autonomous execution
— N sub-questions, ~M waves."* — then proceed with **zero further user gates**.

## Phase: EXECUTING — the wave loop

1. Read `plan.md`. Undone = sub-questions not in `progress.sub_questions_done` **and**
   without an existing `notes/NN-*.md` (never re-research an existing note).
2. Take up to `execution.wave_size` undone sub-questions. Spawn one **searcher subagent
   per sub-question, in parallel**, with the frozen template below. Pass
   `execution.searcher_model` as the subagent's model (`inherit` → omit, matching the
   session model).
3. Collect receipts. A searcher whose two files don't exist on disk → mark failed, retry
   once in the next wave (then record the gap in the plan body and move on).
4. Run `uv run <skill_dir>/scripts/research_kit.py merge-sources <session_dir>`
   (`<skill_dir>` = the directory this SKILL.md was read from — see Invocation below).
5. Update `progress` in `plan.md` (waves_done, sub_questions_done). Narrate one line:
   *"wave 2/3 — 4 searchers done, 47 sources."*
6. **Reflect:** read the receipts' `gaps[]`. If a gap blocks answering the topic and
   `progress.waves_done < execution.max_waves`, append derived sub-questions to the plan
   body (continue the numbering) and loop to 1. Otherwise set `phase: verifying`.

### Frozen searcher prompt (Hard Constraint)

Reproduce exactly; substitute only the `{variables}`. Do not reword or restructure.
Variables: `{nn}` zero-padded sub-question id · `{sub_question}` · `{scope_digest}` 3–5
lines from the plan's Scope section · `{module_paths}` absolute paths of the assigned
module files · `{note_path}` `<session>/notes/{nn}-<slug>.md` · `{sources_fragment_path}`
`<session>/sources/{nn}.yaml` · `{date}` today.

```
## Task
Research the sub-question below. Today is {date}.

Sub-question {nn}: {sub_question}

Scope:
{scope_digest}

## Method (mandatory, in order)
1. Read these strategy module files BEFORE any search: {module_paths}
2. Search and fetch per the modules. Extract findings.
3. Write {note_path} with sections:
   ## Findings — the evidence, every non-obvious claim cited inline as [S{nn}-1],
   [S{nn}-2], ... numbered in first-use order. Mark any claim you could not confirm
   inline as [uncertain U{nn}-1], [uncertain U{nn}-2], ...
   ## Gaps — questions this note could not answer (drives the next wave)
   ## Uncertainties — one line per U-id restating the uncertain claim
4. Write {sources_fragment_path}: a YAML list, one entry per cited source:
   - id: S{nn}-<k>
     url: <url>
     title: <title>
     type: <paper|docs|repo|article|dataset>
     accessed: {date}
     doi: <doi, omit if none>
     pmid: <pmid, omit if none>

## Rules
- Write ONLY those two files. Everything else is read-only.
- Every [S{nn}-k] you cite must have a fragment entry; every entry must be cited.
- Do not return your findings as text. Return ONLY this receipt:
  {"note_path": "...", "source_count": N, "gaps": ["..."], "uncertain_count": N}
```

## Phase: VERIFYING

Claims to verify: every `U`-id across `notes/`, plus 3–8 load-bearing claims you select
(claims the report's conclusions would rest on), ids `C-1`, `C-2`, ...

Spawn verifier subagents (≤ `wave_size` in parallel) with the frozen template below. The
**orchestrator** writes `verification.md` from the receipts — one row per claim:

```
- [U03-1] contradicted — source claims X for v2 only; note asserted it generally
```

(Verdicts are one-liners, so they return up-channel — the one deliberate exception to
results-through-disk; it avoids parallel appends to a single file.) Then `phase: reporting`.

### Frozen verifier prompt (Hard Constraint)

Variables: `{claim_id}` · `{claim}` verbatim claim text · `{cited_source_entries}` the
claim's ledger entries as YAML · `{date}`.

```
## Task
Adversarially verify one claim. Today is {date}. Try to REFUTE it: re-fetch the cited
source(s), check each actually supports the claim, and search for contradicting evidence.
Default to refuted when uncertain.

Claim {claim_id}: {claim}

Cited sources:
{cited_source_entries}

## Rules
- Read-only + search/fetch tools. Write no files.
- Return ONLY this receipt:
  {"claim_id": "{claim_id}", "verdict": "confirmed|unsupported|contradicted",
   "justification": "<one line>"}
```

## Phase: REPORTING

1. Read `notes/`, `sources.yaml`, `verification.md`, and
   [`references/report-style.md`](references/report-style.md); for `output: quarto` also
   read [`references/quarto-output.md`](references/quarto-output.md).
2. Apply verdicts: `confirmed` → assert with cite · `unsupported` → hedge or drop ·
   `contradicted` → drop, or surface the contradiction explicitly. Never copy
   `[uncertain]` markers or U-ids into the report. Translate each note's `[S{nn}-k]` to
   **global** ledger ids via `fragment_ids`.
3. Prune ledger entries the report will not cite (delete from `sources.yaml`).
4. Write the report:
   - `output: markdown` → `report.md`, citing `[S1]`/`[S1, S4]`.
   - `output: quarto` → run
     `uv run <skill_dir>/scripts/research_kit.py to-bibtex <session_dir>`, then write
     `report.qmd` citing `[@S1]`/`[@S1; @S4]` with `bibliography: references.bib`
     (HTML format by default; docx/pdf opt-in — see quarto-output.md), then
     `quarto render report.qmd`.
5. **Gate (hard constraint):** run
   `uv run <skill_dir>/scripts/research_kit.py check-citations <session_dir>`.
   `phase: done` may be written **only after it exits 0**. On exit 1, fix the listed
   offenders and re-run.

## research_kit.py invocation

`<skill_dir>` = the directory containing this SKILL.md *as you read it* (works for
symlinked, copied, or in-repo installs). Always pass absolute paths; never assume an
install location.

| Subcommand | Purpose | Exit |
|---|---|---|
| `merge-sources <session>` | fragments → `sources.yaml`, dedup by DOI/PMID/URL, stable ids | 0 ok / 1 malformed fragment |
| `check-citations <session>` | report(s) ↔ ledger ↔ notes ↔ verification (+ `.bib` for qmd) gate | 0 pass / 1 fail (offenders listed) |
| `to-bibtex <session>` | `sources.yaml` → `references.bib` (quarto output; ids as keys) | 0 / 1 no ledger |
| `status <session>` | 5-line phase/progress digest — run on every resume | 0 / 1 no plan |

## Hard constraints (recap)

- Always re-read state from disk; never trust conversation memory over files.
- Never write outside the session directory (searchers: only their two assigned files).
- Never re-research a sub-question whose note file exists.
- Frozen prompts: substitute `{variables}` only — never reword.
- The approval trigger only fires while `phase: planned`; after it, zero user gates.
- `phase` in `plan.md` is the only phase authority; update it before narrating.
- `phase: done` only after `check-citations` exits 0.
- Findings travel via files; subagents return only receipts.
