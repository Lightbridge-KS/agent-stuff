---
name: research-bg
description: Quick one-shot research delegated to a background agent — investigates a question against primary sources and writes a single cited Markdown note into the repo. Use on /research-bg or when the user wants reading legwork delegated while they keep working. NOT for multi-session stateful research — use `research-deep` for that.
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
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save it where the repo already keeps such notes; match the existing convention
   (e.g. an active `_playground/` session, or `docs/`). If there is none, put it
   somewhere sensible and say where.

<!-- Adapted from mattpocock/skills (skills/engineering/research), 2026-08-15 -->
