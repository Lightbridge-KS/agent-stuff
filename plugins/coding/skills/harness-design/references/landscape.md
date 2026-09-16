# Harness landscape

`verified: 2026-07/08` (from talks given July–August 2026). This moves monthly: **fetch
current docs before quoting a version, API, default or price.** The table carries shape
and lock-in profile only.

| harness / runtime | owner | runs where | model binding | what it gives | how you extend it |
|---|---|---|---|---|---|
| Claude Code · Claude Agent SDK | Anthropic | your machine or your process | Anthropic models | file-system agent: list/read/write/bash, skills, subagents, hooks; `query()` with `allowedTools` | `AGENTS.md`/`CLAUDE.md`, `SKILL.md`, hooks, MCP, plugins |
| Codex | OpenAI | your machine or cloud | OpenAI models | coding agent; observed to write itself small scripts against data | `AGENTS.md`, skills |
| Deep Agents | LangChain | a library you embed (Python / JS) | model-agnostic; **model profiles** swap in-distribution primitives (edit-file) per model | the base loop with six middleware seams; sandbox, filesystem, subagents, planning, HITL, skills, memory, summarization, offloading, caching | middleware (`before_agent`, `before_model`, `wrap_model_call`, `wrap_tool_call`, `after_model`, `after_agent`) |
| Eve ("Next.js for agents") | Vercel | code you deploy; self-host or Vercel | any via AI SDK / AI Gateway | runtime (durable workflow, sandbox, connections, tools, subagents) + channels (Slack, Discord, Teams, API, cron, GitHub, Linear…); observability on deploy | folder conventions: `system/`, `skills/`, `tools/`, `subagents/`, `channels/` |
| Gemini Interactions API + Antigravity remote agent | Google DeepMind | **hosted**: loop, state, compaction and sandbox live behind the API | Gemini | steps data model (input · reasoning · function call · function result); `environment` with `sources` (repo, bucket, inline files) and a **network allow-list with credential injection at the proxy**; Agents API to save `instruction + environment` under an ID | `AGENTS.md`, `SKILL.md`, files in `sources`; a bootstrap script to install CLIs |
| ADK | Google | your process | Gemini-first | `Agent(model, instruction, tools=[fn])`; schemas from signatures; loop, retries, routing | Python tools |
| `bash-tool` · `skill.sh` | Vercel | npm | any via AI SDK | `createBashTool({ sandbox, files })`, `createSkillTool({ skillsDirectory })`, `ToolLoopAgent` | files and `skills/` |
| Harbor | Terminal Bench 2 makers | open-source eval runner | agent = model × harness | task = `environment/` (Dockerfile) + `instruction.md` + `solution/` + `tests/test.sh` verifier; runs in sandboxes, parallel; leaderboard across harnesses, models, reasoning efforts | task folders |
| LangSmith · Engine | LangChain | SaaS | any | traces, trajectories, experiments (accuracy · latency · tokens), Harbor integration; Engine mines traces into issues and proposes prompt / context / harness edits | online evaluators (SLMs, prompts, code) |

## Lock-in profiles

Three ways the same file contract can bind you:

- **Code you deploy** (Eve, Claude Agent SDK, ADK): the harness is in your repo; you carry upgrades, you choose the host.
- **Library you embed** (Deep Agents, LangChain): model-agnostic by design; the loop is yours to read and patch.
- **Hosted service** (Antigravity via the Interactions API): loop, state and sandbox are the vendor's; switching means re-hosting the environment and re-implementing compaction and state. The file contract (`AGENTS.md`, `SKILL.md`) ports; the runtime does not.

Pick by where your data may travel and whether switching models is a requirement, then
record the choice in the design section's axis table.
