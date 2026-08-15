---
name: research-bg
description: Quick one-shot research delegated to a background agent — investigates a question against primary sources and delivers a cited Markdown note, into the repo when the findings have future readers or up-channel when they only feed the current task. Use on /research-bg or when the user wants reading legwork delegated while they keep working. NOT for multi-session stateful research — use `research-deep` for that.
metadata:
  version: "2026-08-15"
---

# Research (background)

Spin up a **background agent** to do the research, so the main thread keeps working
while it reads. (Claude Code: the Agent tool; Codex: spawn a subagent. A harness that
cannot spawn background agents runs the same steps inline.)

Its job:

1. Investigate the question against **primary sources** — official docs, source code,
   specs, first-party APIs — not a secondary write-up of them. Follow every claim back
   to the source that owns it.
2. Capture the findings with each claim's source cited, then route them by audience:
   - Feeding only the current task → return them up-channel, no repo artifact. If they
     run long, write a scratch file instead and return its path plus a short digest —
     keep the main context lean.
   - Future readers in the repo → a single Markdown file where the repo already keeps
     such notes (an active `_playground/` session, or `docs/`). If there is no
     convention, put it somewhere sensible and say where.

<!-- Adapted from mattpocock/skills (skills/engineering/research), 2026-08-15 -->
