---
summary: Design for the `research` skill — a conversational, file-stated, pluggable deep-research
  harness for Claude Code. Covers the UX (claude.ai-style plan-then-trigger), the AX (subagent
  contracts, strategy modules, deterministic gates), the on-disk state contract, and the phase
  machine.
read_when:
  - implementing or changing the research skill (plugins/research/skills/research/)
  - adding a search strategy module or retrieval backend
  - changing the research state contract (plan.md, sources.yaml, notes/)
  - debugging resume/phase-detection behavior of a research session
---

# Design: the `research` skill

*Status: design settled 2026-07-05; v1 implemented same day (narrative shape + Markdown
output). Quarto output added 2026-07-06 after the first E2E: `to-bibtex` generates
`references.bib` from the ledger, `report.qmd` cites `[@Sn]` keys, HTML (self-contained)
is the default render with docx/pdf opt-in. Matrix mode and the remaining modules stay
deferred. Skill: `plugins/research/skills/research/`. E2E fixture:
`~/my_config/_tests/deep-research-test/`. Execution state lives in the progress tracker:
[`progress/research-skill.md`](progress/research-skill.md).*

## 1. Problem & positioning

Replicate the claude.ai Deep Research **UX** — conversational scoping, a plan you iterate on
in natural chat, a single "Plan OK, conduct deep research" trigger, then autonomous execution
into a cited report — inside **Claude Code**, with two properties the product can't give:

1. **State on the local filesystem** — every phase's output is an inspectable, hand-editable,
   resumable file (the Weizhena repo's strongest idea).
2. **Pluggable search/retrieval** — web search, PubMed/arXiv MCP tools, and local corpora are
   interchangeable fuel, probed at plan time rather than hardcoded.

### Why not the built-in `deep-research` skill?

Claude Code ships a `deep-research` skill (one-shot Workflow harness: fan-out searches →
adversarial verify → cited report). It is the right tool for a *quick* fact-checked answer.
This skill exists for the three things it lacks:

| Gap in built-in | This skill |
|---|---|
| No conversational planning — question in, report out | Scoping + plan iteration is the front half of the UX |
| No file state — nothing survives the session | `docs/research/<session>/` is the product; the report is one file in it |
| Fixed backends (web only), fixed output | Probed backends (PubMed, local corpus, …), Markdown or Quarto+BibTeX output |

### The two inspirations, and what we take from each

A real claude.ai Deep Research session showing the target UX (clarifying questions → plan
draft → "Conduct deep research" trigger → autonomous run) is kept as the inspirational
example: [`examples/example-claude-ai-deep-research-conversation.md`](examples/example-claude-ai-deep-research-conversation.md).

| | Weizhena Deep-Research-skills | claude.ai Deep Research |
|---|---|---|
| Take | Filesystem as the only shared state; deterministic completion gate; frozen subagent prompt contracts; pluggable strategy modules; per-item context isolation; `[uncertain]` as a structured signal | Conversational scoping → plan → single trigger; fully autonomous execution; narrative synthesis; progress narration |
| Leave | Five rigid slash commands; `AskUserQuestion` gate at every step; human approval between every batch; matrix-only research shape | Hidden state; no resume; no backend choice |

## 2. Decision log

Settled 2026-07-05 with the user; these are binding on the implementation.

| # | Decision | Choice | Rejected alternatives |
|---|---|---|---|
| D1 | Autonomy after plan approval | **Fully autonomous + resumable.** No human gates during execution; interrupt-safety via the state contract, not via approval prompts. | Per-wave gates (Weizhena); plan-time gating knob |
| D2 | Research shape | **Both, plan decides.** Planner classifies the question: open-ended → *narrative*; landscape/comparison → *matrix* (items × fields). One skill, two execution templates. | Narrative-only; matrix-only |
| D3 | Execution engine | **Agent-tool fan-out.** The orchestrator (main loop, driven by SKILL.md) spawns parallel research subagents. Portable in spirit; state via files. | Workflow tool (Claude-Code-only, less inspectable); hybrid |
| D4 | Skill surface | **One phase-aware skill.** `/research` is the only entrypoint; it reads on-disk state to resume at the right phase. | 2–3 skill family; Weizhena-style 5+ |
| D5 | Verification rigor | **Verify wave + citation gate.** Adversarial refutation of load-bearing claims before writing, plus a deterministic script checking report ↔ source-ledger consistency. | Citation gate only; prompt discipline only |
| D6 | Backend configuration | **Probe + strategy modules + `.lightbridge`.** Capability probe at plan time; tactics in pluggable module files; optional `[research]` section in `.lightbridge/config.toml` for per-repo defaults. | Probe+modules only; hardcoded set |
| D7 | Placement | **New `research` plugin domain**: `plugins/research/skills/research/`. Room for strategy modules and future companion skills. | `productivity` domain; `radiology` domain |

## 3. UX: the session lifecycle

One conversation, five phases, one trigger phrase. The user only ever talks naturally.

```
 /research <topic>            "plan is OK — conduct deep research"
      │                                      │
      ▼                                      ▼
 ┌─────────┐    ┌─────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
 │ SCOPING │───►│ PLANNED │───►│ EXECUTING │───►│ VERIFYING │───►│ REPORTING │──► done
 └─────────┘    └─────────┘    └───────────┘    └───────────┘    └───────────┘
  converse       plan.md         waves of         refute load-     report.md /
  2–4 clarifying  written;       searchers;       bearing claims;  report.qmd;
  questions;     user iterates   notes+sources    verdicts →       citation gate
  probe backends in chat         accumulate       verification.md  must pass
      ▲                                                               │
      └────────────── /research in a dir with existing state ─────────┘
                      resumes at the recorded phase (crash-safe)
```

**Scoping** mirrors the claude.ai behavior the user likes (see
[`examples/example-claude-ai-deep-research-conversation.md`](examples/example-claude-ai-deep-research-conversation.md)):
before searching anything, the model asks the 2–4 questions that most change what
it would research — audience, time range, depth, output format. Mechanics: open questions in
prose; enumerable choices may use `AskUserQuestion`. This phase is *conversation, not
machinery* — the skill only prescribes that it happen and what must be captured into the plan.

**Planning** ends with `plan.md` on disk. The user iterates by talking ("add a section on X",
"drop the vendor comparison") — the model edits `plan.md` in place. Any clear approval
("plan is OK", "go ahead", "conduct deep research") flips the phase. No approval ceremony
beyond the user's own words.

**Executing / Verifying / Reporting** run without gates (D1). The orchestrator narrates
progress in chat, claude.ai-timeline style ("wave 2/3 — 4 searchers running, 47 sources so
far"), but never blocks on the user. An interrupt at any point loses at most one in-flight
wave: everything landed is on disk, and re-invoking `/research` resumes.

**Working directory** (from the idea file):
- repo with `docs/` → `docs/research/YYYY-MM-DD_slug/`
- otherwise → ask once; default `./research/YYYY-MM-DD_slug/`
- `.lightbridge/config.toml` `[research] dir = "..."` overrides both (D6).

## 4. The state contract (the load-bearing design)

Skills phases rendezvous through files, never through conversation memory. Everything below
is hand-editable between phases; the orchestrator re-reads, never caches.

```
docs/research/2026-07-05_local-deep-research-stack/
├── plan.md                  # SSOT for session config + the research plan (see §4.1)
├── notes/                   # searcher output: one file per sub-question / item
│   ├── 01-orchestration-layers.md
│   ├── 02-model-serving.md
│   └── ...
├── sources/                 # per-searcher ledger fragments (write-isolated)
│   ├── 01.yaml
│   └── 02.yaml
├── sources.yaml             # merged, deduplicated source ledger (script-generated)
├── verification.md          # verify-wave verdicts on load-bearing claims
├── report.md                # narrative output (default)
└── report.qmd + references.bib   # Quarto output (opt-in; .bib derived from sources.yaml)
```

Matrix-shaped sessions add `matrix/<item-slug>.yaml` (one structured record per item,
Weizhena-style) and the report renders a comparison table from them.

### 4.1 `plan.md` — one file, two jobs

YAML frontmatter is the **machine state** (the phase pointer and execution config); the body
is the **human-readable plan** the user iterates on. Single file so approving the plan and
flipping the phase are the same edit, and so the session is self-describing to a fresh
context.

```markdown
---
phase: executing            # scoping | planned | executing | verifying | reporting | done
shape: narrative            # narrative | matrix
topic: "Local deep-research stack on a Mac"
created: 2026-07-05
language: en                # report language (en default; th on request)
output: markdown            # markdown | quarto | quarto-book
backends:                   # probed + confirmed at plan time (§6)
  - websearch
  - webfetch
  - pubmed-mcp
modules: [general-web, academic-papers]
execution:
  wave_size: 4              # searchers per wave (rate-limit guard)
  max_waves: 3              # reflection loop budget
  searcher_model: sonnet    # searcher tier; "inherit" to match the session model
progress:                   # orchestrator updates after every wave — the resume cursor
  waves_done: 1
  sub_questions_done: [01, 02, 03]
---

# Research plan: Local deep-research stack on a Mac

## Scope (from conversation)
- Model: switch freely between local models …
- Domain: medical + general/technical …

## Sub-questions
1. Orchestration layers: Claude Code vs LangGraph vs purpose-built …
2. …
```

**Resume rule:** on invocation, glob for `plan.md` under the research dir (newest session
wins; ambiguity → ask). `phase` + `progress` say exactly where to pick up; `notes/` files
that already exist are never re-researched (Weizhena's skip-done rule).

### 4.2 The source ledger

`sources.yaml` is the single source of truth for citations; `references.bib` is derived,
never hand-authored. Each entry:

```yaml
- id: S17
  url: https://arxiv.org/abs/2511.18743
  title: "RhinoInsight: …"
  type: paper           # paper | docs | repo | article | dataset | local
  accessed: 2026-07-05
  pmid: null            # or DOI/PMID when the backend provides one
  supports: [note-03]   # which notes cite it
```

Parallel searchers **never write the merged ledger** — each writes its own
`sources/<note-id>.yaml` fragment; the merge (dedup by URL/DOI/PMID, stable ID assignment)
is deterministic script work, not model work (§7).

### 4.3 Uncertainty as a structured signal

Adopted from Weizhena end-to-end: a searcher that can't confirm a fact writes it as
`[uncertain]` in the note; the verify wave targets these first; the writer must either
resolve, hedge-with-citation, or drop — never silently assert. The citation gate rejects a
report that cites an `[uncertain]`-only claim as fact.

## 5. AX: the execution engine

### 5.1 Orchestrator ⇄ searcher fan-out

The main loop is the orchestrator (D3). Per wave, it spawns one **searcher subagent per
sub-question** (narrative) or **per item** (matrix), up to `wave_size` in parallel, each in a
fresh context. Weizhena's key AX insight is kept: deep research is context-hungry, so
*one unit of research = one subagent context*, and results flow through **disk, not
up-channel tokens** — the searcher's return message is a short structured receipt, never the
findings themselves.

```
ORCHESTRATOR (main loop — context stays small)
  │  reads plan.md, picks undone sub-questions
  ├─ wave: spawn ≤ wave_size searchers in parallel ──► notes/NN.md + sources/NN.yaml
  │        each returns only: {note_path, source_count, gaps[], uncertain_count}
  ├─ merge ledger (script), update plan.md progress
  ├─ REFLECT: gaps reported? coverage thin? ──► derive new sub-questions, next wave
  │        (bounded by max_waves — the loop budget is in the plan, not vibes)
  ├─ VERIFY wave: refuter subagents attack load-bearing claims ──► verification.md
  └─ WRITER: synthesize report from notes/ + sources.yaml, honoring verdicts
             └─ citation gate script must exit 0 before phase: done
```

### 5.2 The searcher contract (frozen boundary prompt)

Weizhena's "Hard Constraint" pattern, kept verbatim in spirit: SKILL.md carries a frozen
prompt template — only `{variables}` substitute; structure and wording never drift. The
contract:

| Concern | Contract |
|---|---|
| Input | `{sub_question}`, `{scope_digest}`, `{module_paths}`, `{note_path}`, `{sources_fragment_path}`, `{date}` |
| First act | Read the assigned strategy module(s) before any search |
| Output | Write `notes/NN.md` (findings, inline `[S-local-n]` cites, `[uncertain]` marks) + `sources/NN.yaml`; return only the receipt |
| Tools | Read-only + search/fetch; never edits repo files outside the session dir |
| Done | Both files exist and the receipt is returned — the orchestrator, not the searcher, judges coverage |

The **verifier contract** mirrors it with an adversarial stance: given one claim + its cited
sources, *try to refute it* (re-fetch the source, check it actually supports the claim, hunt
for contradicting evidence); return `confirmed | unsupported | contradicted` + a one-line
justification into `verification.md`. Default-to-refuted when uncertain.

### 5.3 Strategy modules (progressive disclosure)

`plugins/research/skills/research/modules/*.md` — small files, loaded by searchers on
assignment, never all at once:

| Module | Covers |
|---|---|
| `general-web.md` | WebSearch/WebFetch tactics, credibility heuristics, query reformulation |
| `academic-papers.md` | PubMed MCP first (PMID/DOI capture for BibTeX), arXiv, citation chasing |
| `technical-oss.md` | GitHub/docs/PyPI: repo vitality signals, changelog-over-blogpost rule |
| `local-corpus.md` | Grep/read a local dir of PDFs/Markdown as a source type (`type: local`) |
| `medical-clinical.md` | Guidelines/systematic-review preference, evidence-level tagging |

Adding a backend = adding a module file + a probe line — no skill-body change. Modules
declare which tools they need so the planner only offers modules whose tools probed present.

## 6. Pluggability: probe + `.lightbridge`

At plan time the orchestrator runs a **capability probe** and records the result in
`plan.md` (`backends:`): built-ins (WebSearch/WebFetch), MCP search tools discovered via
ToolSearch (PubMed, Tavily, Exa, Brave, SearXNG…), and any configured local corpus. Missing
capability degrades gracefully and *visibly* — the plan says what fuel the session will run
on, and the user can object before execution.

Optional per-repo defaults via the `lightbridge-config` mechanism (D6):

```toml
[research]
dir = "docs/research"              # session parent dir
output = "quarto"                  # default output format
backends = ["pubmed-mcp", "websearch"]   # preference order
searcher_model = "sonnet"          # searcher tier; "inherit" to match the session model
corpus = ["~/papers/rad-ai"]       # local corpora offered to the planner
```

Section presence is the opt-in, per the `.lightbridge` convention. With it, a recurring-
research repo gets near-zero-question planning; without it, the probe + conversation covers
everything.

## 7. Deterministic machinery (the shell around the intelligence)

One helper CLI, **inside the skill folder** (`scripts/research_kit.py`, PEP 723, `uv run`) so
the skill stays self-contained for packaging and avoids Weizhena's hardcoded-install-path
trap — the skill invokes it relative to its own directory.

| Subcommand | Job | Exit codes |
|---|---|---|
| `merge-sources <session>` | Fragments → `sources.yaml`; dedup by URL/DOI/PMID; stable IDs | 0 ok / 1 malformed fragment |
| `check-citations <session>` | Every `[Sn]` in report resolves to ledger; no orphan sources; no `[uncertain]`-only claim asserted as fact | 0 pass / 1 fail (lists offenders) |
| `to-bibtex <session>` | `sources.yaml` → `references.bib` (Quarto path) | 0 / 1 |
| `status <session>` | Token-economical phase+progress digest (for resume and for the user) | 0 |

"Done" is therefore not the model's self-assessment: **`phase: done` may only be written
after `check-citations` exits 0** — the Weizhena completion-gate idea, applied to citations
instead of field coverage.

## 8. Repo integration

- **Placement:** new domain — `plugins/research/.claude-plugin/plugin.json` + entry in
  `.claude-plugin/marketplace.json`; skill at `plugins/research/skills/research/` (D7).
- **Skill folder layout:**

  ```
  plugins/research/skills/research/
  ├── SKILL.md              # phase router + frozen contracts (operational, terse)
  ├── modules/*.md          # search strategy modules (§5.3)
  ├── references/           # longer guidance loaded on demand (report style, Quarto setup)
  └── scripts/research_kit.py
  ```

- **SKILL.md frontmatter:** `name: research`, model-invocable, description as router trigger
  ("conduct deep, multi-source research into a cited report; plan conversationally, then
  execute autonomously with resumable file state").
- **Naming collision note:** the built-in `deep-research` skill coexists; this one is
  `/research`. The description should distinguish them so routing doesn't coin-flip
  (built-in = one-shot quick harness; this = stateful sessions, pluggable backends,
  Quarto).
- **Validation:** normal repo contract — `uv run bin/validate.py` after edits; tests for
  `research_kit.py` under `tests/`.

## 9. Sharp edges carried forward (known, accepted)

- **Coverage ≠ correctness.** The citation gate proves report↔ledger consistency, not truth.
  Truth rests on the verify wave + module discipline — same residual risk as every deep-
  research system.
- **Trigger-phrase ambiguity.** "Looks good" mid-scoping vs plan approval — the skill treats
  only approval *while phase = planned* as the trigger, and confirms in one line ("Starting
  autonomous execution — N sub-questions, ~M waves") as it flips the phase, so a
  misread costs one sentence, not a runaway session.
- **Rate limits.** `wave_size` is the only throttle; default 4. Matrix sessions with many
  items take more waves rather than wider ones.
- **Two execution templates (D2)** is real surface area; matrix mode reuses the same
  contracts (a "field schema" section in plan.md plays the role of `fields.yaml`) to keep
  the delta small.

## 10. Implementation order (when build starts)

1. Domain scaffolding + `SKILL.md` with phase machine and narrative shape only.
2. `research_kit.py` (`merge-sources`, `check-citations`, `status`) + tests.
3. Modules: `general-web`, `academic-papers`. Probe + `.lightbridge` `[research]` section
   (register in `lightbridge-config` skill catalog).
4. Verify wave + gate wiring; then Quarto output (`to-bibtex`); then matrix shape.
5. E2E dry run on a real topic; iterate SKILL.md wording from the transcript.
