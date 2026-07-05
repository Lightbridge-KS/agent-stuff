# example-claude-ai-deep-research-conversation

**Human**

```
I'd like to know a modern way to do "deep research" locally in my Mac with the model that I can choose. It should somehow achieve what deep research feature have done here in Claude.ai
My initial thought were:
Using AI Coding Agent: e.g., Claude Code.
LangChain / LangGraph / LangSmith stack.
I'd like you to do deep research to find out. But first, do you have any question you'd like to ask?
```

**Claude**

```
Good instinct to scope this before I dive in — "local deep research with a model of your choice" branches into pretty different research directions depending on a few things, and getting these right up front will save us both a lot of noise.
A quick map of why I'm asking:

"Deep research" here on Claude.ai is really an agentic loop: a planner decomposes your question, runs many searches, reads/synthesizes sources, and writes a cited report. Replicating that locally means picking (a) an orchestration layer (Claude Code as an agent, LangGraph, or a purpose-built deep-research tool), (b) a model, and (c) a search/retrieval backend. Your two initial thoughts sit at different points on that spectrum, so I want to know which trade-offs matter to you.

Three questions that would most change what I go research:
```

**Human**

```
Q: For the model powering it, what matters most to you?
A: Both — I want to switch freely
Q: What's the primary use for this deep-research setup?
A: Medical Field and General + Technical / Academic topics
Q: What kind of end result do you want from my research?
A: Full Landscape Overview with ready-to-run tool (aim at OSS) with the framework/stack they likely used so that I could build my own

---
Now, please draft your deep research plan.
```

**Claude**

```
Here's my proposed plan. I've organized it around the *anatomy* of what "deep research" actually is, because that gives us a stable skeleton to map every OSS tool and framework onto — rather than just listing projects.

## The reference architecture I'll research against

Claude.ai's deep research is an **agentic loop**, not a single prompt. Everything I find will be mapped onto this spine:

```
              ┌──────────────────────────────────────────────┐
              │              DEEP RESEARCH LOOP               │
              └──────────────────────────────────────────────┘
  User Question
       │
       ▼
  ┌──────────┐   decompose into sub-questions
  │ PLANNER  │◄─────────────────────────────────┐
  └────┬─────┘                                   │
       │ sub-queries                             │ reflect: gaps?
       ▼                                         │
  ┌──────────┐   search → read → extract         │
  │ SEARCHER │──► web / PubMed / local RAG        │
  └────┬─────┘                                   │
       │ evidence + notes                        │
       ▼                                         │
  ┌──────────┐                                   │
  │SYNTHESIZE│───────────────────────────────────┘
  └────┬─────┘
       │ coverage sufficient
       ▼
  ┌──────────┐
  │  WRITER  │  cited report (Markdown → Quarto)
  └──────────┘
```

Underneath that loop sit four swappable layers, which are exactly the four research workstreams:

```
  ┌─ LAYER ────────────┬─ WHAT I'LL INVESTIGATE ──────────────┐
  │ 1 Orchestration    │ LangGraph, LlamaIndex, smolagents,   │
  │   (the agent loop) │ Claude Agent SDK, CrewAI, PydanticAI │
  ├────────────────────┼──────────────────────────────────────┤
  │ 2 Model            │ local (Ollama / LM Studio / MLX) +   │
  │   (swap freely)    │ API (Claude/GPT/Gemini) via LiteLLM  │
  ├────────────────────┼──────────────────────────────────────┤
  │ 3 Search/Retrieval │ SearXNG, Tavily, Brave, Exa +        │
  │   (research fuel)  │ PubMed / arXiv + local RAG           │
  ├────────────────────┼──────────────────────────────────────┤
  │ 4 Output           │ cited Markdown, report generators    │
  └────────────────────┴──────────────────────────────────────┘
```

## Research workstreams

**WS-0 · Baseline — what "deep research" really does.** Pin down the actual agentic pattern (plan → iterate → reflect → cite) from how Anthropic/OpenAI/Google describe their own features, so the OSS comparison is grounded rather than hand-wavy.

**WS-1 · Ready-to-run OSS deep-research tools.** The core of your "install today" ask. Candidates I'll evaluate and compare: GPT Researcher, LangChain's Open Deep Research + Local Deep Researcher (Ollama), HuggingFace's Open Deep Research (smolagents), Stanford STORM, `local-deep-research`, Khoj, and Perplexity-style adjacents (Perplexica, Morphic, Farfalle). For each: what loop it implements, which framework it's built on, local-model support, search backend, maturity/activity, and license.

**WS-2 · Orchestration frameworks (build-your-own).** The stacks *behind* those tools, so you can build your own with clean architecture: LangGraph vs LlamaIndex Workflows vs smolagents vs Claude Agent SDK vs CrewAI/AutoGen/PydanticAI — their agent-loop model, state/memory handling, and which the WS-1 tools actually use.

**WS-3 · Model layer for your M3 Pro (36 GB) + API switching.** Which local open-weight models are actually reliable at *tool-use + long-context research* and fit in 36 GB unified memory (Qwen3, Llama 3.3, Gemma 3, gpt-oss, DeepSeek-class — current state), the best Mac runtimes (Ollama / LM Studio / MLX), and the abstraction layer that lets you flip between local and API cleanly (LiteLLM, OpenRouter).

**WS-4 · Search + medical retrieval.** The "fuel." Self-hostable OSS search (SearXNG) vs API search (Tavily/Brave/Exa), plus the medical-literature angle that matters for your unit: PubMed/NCBI E-utilities, Europe PMC, Semantic Scholar, arXiv, ClinicalTrials.gov — and how to wire them in as tools/MCP. Note: I have a PubMed connector available, so I can also validate this live.

**WS-5 · Synthesis for *your* context.** A comparison matrix, one recommended "switch-freely" reference stack for your setup, an ASCII architecture diagram of the build-your-own version, and a short learning path (since this is a learn-and-Q&A project).

## What you'll get

A landscape overview → shortlist of ready-to-run OSS tools → the frameworks they're built on → a recommended stack + architecture diagram you could implement yourself, with the local↔API switch as a first-class design goal.

Two notes before I run it:

- This is a substantial multi-source effort (roughly 20–30 searches across the workstreams). I'll do it here rather than punting to a separate feature, and lead with the most current sources since this space moves monthly.
- Given your "both models" answer, I'll treat **local↔API switchability** as a hard design requirement throughout, not an afterthought.

Anything you want to add, drop, or reprioritize — or shall I run it as-is?

```

**Human**

```
Your plan looks good. Conduct deep research.
```


**Claude**

- Research plan created
- Gathered 321 sources
- Research Report is Ready

