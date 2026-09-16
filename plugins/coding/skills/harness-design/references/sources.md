# Sources

Three talks, July–August 2026. One line per lesson kept; everything else was pruned.
Transcripts, slide contact sheets and per-talk notes: `~/Movies/YouTube/Agent-Building/`
(cross-talk distillation in its `NOTES.md`).

1. **Andrew Qu (Vercel), "How We Solved Agent Building", AI Engineer World's Fair 2026-07** — https://www.youtube.com/watch?v=9dYcwOkpCE8
   - Five rebuilds of one data agent: mega prompt → pipeline of scoped agents → one agent with modes → file-system agent → skills → Eve → §1 ladder.
   - Pipeline hops pass only a summary; the mono-agent recovers from errors by re-exploring → §7 first pitfall.
   - "We thought we were cooking": 30 % on evals, users called it awful; the file-system rebuild doubled the score → §3 rule 1, §7.
   - A recurring job distils recent queries into ~100 skills; a run no longer starts from nothing → §5 step 11.
   - Off-the-shelf vertical agents lost to in-house domain knowledge → §3 rule 2, §7.
   - Eve: framework-defined agent, folders declare the agent → §1 rung 5, `landscape.md`.
2. **Philipp Schmid (Google DeepMind), "Agents Without Code", AI Engineer World's Fair 2026-07-02** — https://www.youtube.com/watch?v=fjF8EKnxKCU
   - The same PR-review agent three times, deleting code each time; the weather question answered only when tools were atomic and general → §3 rule 1.
   - What the harness solves vs what you still own → §3 rule 2 table.
   - Sandbox with network allow-list and credential injection at the proxy; the agent never sees the token → §3 rule 3, §5 step 7.
   - Extending = drop a `SKILL.md` and maybe a CLI; no code change → §5 step 6.
   - Cursor: 12k lines of TypeScript replaced by a 200-line skill; Manus, LangChain, Vercel refactor stories → §3 rule 1.
   - "If your harness gets more complex as models improve, you are over-engineering" → §5 step 12.
   - "Agents are just files": `agent.yaml`, `AGENTS.md`, `memory/learnings.md`, `skills/*/SKILL.md` → §1 rung 5.
3. **Harrison Chase (LangChain), "When to Build Your Own Agent Harness", Sequoia "Own Your Intelligence", 2026-08** — https://www.youtube.com/watch?v=HI2q3ci3Iuc
   - Agent = harness × model × context; own all three; context is episodic / semantic / procedural → opening thesis, §5 step 1.
   - The harness's job: the right context at the right time → opening thesis.
   - Off-the-shelf → middleware → custom → cognitive architecture, pushed by distribution distance and by control need → §2.
   - In-distribution primitives stay native per model; Deep Agents model profiles for edit-file → §2 caveat.
   - Anatomy: execution environment · delegation · steering · context management over six middleware seams → §4.
   - Private evals define good; Harbor task shape; score accuracy, latency and cost → §5 step 9.
   - Failures are usually the context, not the model; trajectory plus full trace → §5 step 10.
   - The flywheel (traces → curate → experiment → update harness / context / model), feedback by surface design and online evaluators, LangSmith Engine, "codex-ification" → §5 step 11.
