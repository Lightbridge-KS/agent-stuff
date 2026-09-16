---
name: harness-design
description: >-
  Decide how much agent harness to own — off-the-shelf, middleware on one, a custom loop,
  or an explicit graph — from the task's distribution distance and its need for control;
  then shape what stays yours (instructions, skills, environment, evals) and the flywheel
  that improves it. Use when designing or reviewing an agent harness, choosing between a
  hand-rolled loop, a framework and a hosted harness, deciding whether something should
  be a tool or a skill, setting up evals for an agent, or when a harness has grown while
  models improved. Also on harness engineering, file-system agent, agents-as-files,
  cognitive architecture, Harbor, Eve, Antigravity, Deep Agents. For mapping the organs of
  an existing agent, use `agentic-architecture`; for the UI it emits, `generative-ui`.
metadata:
  version: "2026-09-16"
---

# Harness design

An **agent is a harness orchestrating a model and context.** The harness has one job:
get the model the right context at the right time for the task. Everything else about
a harness is a question of **how much of it you write yourself**, and that question has
an answer that does not depend on taste.

The failure this skill prevents has two faces that are one mistake. A prescriptive tool
set that passes internal evals and that the first real users call awful. A harness that
grows more complex with every model release. Both write *competence* into code that the
model already has, or will have next quarter. The cure is to own only what the model
cannot derive: your instructions, your domain knowledge, your environment, your evals.

## 1. The migration: code → files

Two teams on opposite stacks rebuilt the same agent until it shipped and climbed the
same ladder. Each rung moves something from code you own to a file the model reads.

```
 rung  Vercel (data agent)                  DeepMind (PR reviewer)              what moved to files
 ────  ──────────────────────────────────   ─────────────────────────────────   ─────────────────────────────
  0    mega prompt; human runs the SQL      —                                   nothing yet
  1    chain of scoped agents (pipeline)    hand-written Python loop            you own the loop
  2    one agent, many modes                framework abstracts the loop        loop; tools still code
  3    file-system agent in a sandbox       hosted harness + sandbox            tools → ls/read/write/bash + CLIs
  4    skills/ distilled from real queries  AGENTS.md + SKILL.md + memory/      capabilities → Markdown
  5    framework-defined agent (folders)    "agents are just files"             the folder is the agent
```

Rung 3 is where the eval score doubled: general tools the model was trained on, freedom
to explore, the semantic layer dumped in as files. Rung 4 is where a run stops starting
from nothing.

## 2. The decision rule: two axes

How much harness you own is set by two forces, not by preference.

```
 off-the-shelf         middleware / hooks        custom harness              cognitive architecture
 Claude Code · Codex   Deep Agents + hooks;      your loop, your organs,     explicit graph of steps
 Deep Agents as-is     coding-agent plugins      native primitives kept      and gates
 ◀── task in-distribution ───────────────────────────────── task out-of-distribution ──▶
 ◀── "good enough, fastest to value" ─────────────────────── "predictability and control" ──▶
```

- **Distribution distance.** The closer the task is to what the model was RL'd on, the
  better an off-the-shelf harness performs. Move right only for the components that are
  genuinely out of distribution.
- **Control need.** Where a wrong or varying run is unacceptable (regulated, financial,
  clinical, destructive), an explicit graph with gates buys predictability the loop
  cannot. Some customers look at a general agent and say "too scary"; they are not wrong
  for their slice.

**Start at the left; move right only when a force pushes.** And keep **in-distribution
primitives native** even inside a custom harness: the labs RL'd their models on
*different* edit-file and shell tool shapes, so a custom harness swaps those
implementations per model rather than inventing its own.

## 3. Three rules

1. **Generality beats prescription, inside a box you shape.** A prescriptive tool set
   scored ~30 % and users called it awful; a sandbox with bash and files doubled the
   score. A harness with only declared tools refuses anything undeclared; one with
   atomic general tools reaches for search unprompted. Teams that refactored their
   harness several times a year gained most from *removing* things.
2. **The harness commoditizes; the content is yours.** Every vendor drew the same split.

   | the harness gives | you own |
   |---|---|
   | execution loop, tool routing, dispatch | instructions, rules, behaviors (`AGENTS.md`) |
   | session state, context compaction | procedural context (`SKILL.md`), episodic and semantic context (memory, your data) |
   | sandbox, durability, delegation, steering | domain knowledge: when to query what, what links to what |
   | channels, observability plumbing | **evals** |

   Where the harness *runs* varies (a framework you deploy, a library you embed, a hosted
   service behind an API); what you *write* is identical.
3. **Constrain the environment, not the tool list.** Once the agent may run bash, safety
   cannot live in a tool schema. Sandbox isolation, a network allow-list, and a proxy
   that injects credentials on outbound requests so no secret ever enters the context
   window. When the environment cannot be constrained enough, move one rung right and
   constrain the *path* with gates.

## 4. Anatomy of a harness

Every organ is a decoration of the base loop at one of six seams. Coding-agent hooks and
plugins are the same seams under another name.

```
 request ─▶ before_agent ─▶ before_model ─▶ [model] ─▶ after_model ─▶ after_agent ─▶ result
                                  │  wrap_model_call    ▲
                                  └─▶ wrap_tool_call ───┘   (tools → observation)

 EXECUTION ENVIRONMENT   code interpreter · sandbox · filesystem
 DELEGATION              planning · subagents
 STEERING                human-in-the-loop
 CONTEXT MANAGEMENT      skills · memory · summarization · context offloading · prompt caching
```

Summarization is a `before_model` check; context offloading wraps a tool call; a
permission gate wraps a tool call or sits `before_agent`. The organ list matches the
checklist in `agentic-architecture`; this skill adds *where each organ attaches* and
*whether you should own it at all*.

## 5. Procedure

Three phases, twelve steps, each ending on a checkable criterion. The output is one
design section (template in §6) embeddable in an `agentic-architecture` doc or standing
alone as `docs/design/harness-design.md`.

### Decide

1. **Frame the three parts.** Name the model (and whether switching models is a
   requirement), the context (episodic / semantic / procedural), the harness candidates.
   *Done when* all three are written with one line each.
2. **Distribution check.** List the task's components; mark each in- or
   out-of-distribution for the chosen model. Only out-of-distribution components justify
   harness work; in-distribution primitives stay in the model's native shape. *Done when*
   every component carries a mark and a one-line reason.
3. **Control check.** Name the slices where variance is unacceptable. Those get gates or
   an explicit graph; the rest stays a loop. *Done when* every control slice names the
   harm a varying run would cause.
4. **Place on both axes.** One position on the ownership spectrum, one rung on the
   code→files ladder, one line of reason each. *Done when* the reason names the force
   (distribution or control) that pushed right, or says none did.

### Build

5. **The harness/you table** for this system. Move everything possible to the harness
   side; what remains on your side is the deliverable. *Done when* nothing on your side
   is loop, routing, state, compaction or sandbox machinery.
6. **Tool policy.** Default to general tools plus CLIs in the sandbox plus skills that
   explain them. Every remaining custom tool carries a written reason a CLI cannot
   replace it. *Done when* the tool table has no empty reason cell.
7. **Environment boundary.** Sandbox, network allow-list (state its default explicitly,
   open or empty), credential injection, no secrets in context, a human gate wherever
   the environment cannot be constrained enough. *Done when* each line names its
   mechanism, not a wish.
8. **Organ map.** For each organ in use, the seam it attaches to and whether it is
   harness-provided or yours. *Done when* every organ from §4 is present, absent, or
   n/a with a reason.

### Learn

9. **Evals before the rebuild.** A task set in Harbor shape (an environment definition,
   an `instruction.md`, a verifier script that may run code, tests, or a judge), scored on
   accuracy *and* latency *and* cost. *Done when* the set exists and a baseline number is
   recorded for the current harness.
10. **Observability.** When an agent fails, an LLM call went wrong, and it is usually the
    context, not the model. Capture the trajectory and the full assembled context per
    call. *Done when* a failed run can be replayed to the exact window the model saw.
11. **Flywheel.** Run → collect traces → curate → experiment → update the harness, the
    context (skills, memory, prompts) or the model. State what gets distilled back into
    `skills/` and `memory/`, by whom (a job, the agent, a human), gated how. *Done when*
    the feedback source is named: surface design, online evaluators, or both.
12. **Over-engineering check.** Record the lines of orchestration as a number. Re-measure
    at the next model release; for in-distribution work the curve must fall. Write the
    exception beside it: complexity retained for an out-of-distribution component or a
    control slice, by name. *Done when* the number and its exceptions are in the doc.

## 6. Output template

```markdown
## Harness design

**Model:** <name; switchable: yes/no>  **Context:** <episodic / semantic / procedural sources>

| axis | position | force | reason |
|---|---|---|---|
| ownership | <off-the-shelf · middleware · custom · graph> | <distribution / control / none> | |
| ladder | <rung 0–5> | | |

### Harness / you
| harness gives | you own |

### Tools
| tool | why a CLI cannot replace it |

### Environment boundary
<sandbox · allow-list default · credential injection · gates>

### Organ map
| organ | seam | provided by | present |

### Evals
<task-set location · baseline: accuracy / latency / cost>

### Flywheel
<traces → curation → what is updated, by whom, gated how>

### Over-engineering number
<lines of orchestration · date · exceptions by name>

### Open questions
<💡 items only a human can settle: taste, hard-to-reverse choices>
```

## 7. Pitfalls seen in production

- A pipeline of scoped agents: each hop sees only a summary, so an execution error
  cannot reach back into exploration. One agent with modes recovers; the pipeline
  cannot.
- "We thought we were cooking": evals at 30 % felt like progress until real users spoke.
  Evals define good only if they contain the questions users actually ask.
- The funded vertical agent lost to the in-house one because domain knowledge, not the
  harness, made it good. Own the knowledge; rent the harness.
- A network allow-list that defaults to open because closed was inconvenient.
- A tool per intent. Recurring queries have few shapes; distill them into skills.
- Evals owned by nobody, so the flywheel has nothing to turn on.
- Tuning the model when the failure was in the context it received.
- A harness that grew with every model release and nobody measured.

## References

- `references/landscape.md` — harnesses, runtimes and eval runners named in the sources,
  with a `verified:` date. Fetch current docs before quoting a version, API or default.
- `references/sources.md` — the three talks this skill distils, one line per lesson kept,
  and where the transcripts and slides live.
