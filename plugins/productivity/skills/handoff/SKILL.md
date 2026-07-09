---
name: handoff
description: Compact the current conversation into a durable handoff document another agent (any harness) picks up later — or resume from the latest handoff.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
metadata:
  version: "2026-07-09"
---

# Handoff

Write a handoff document summarising the current conversation so a fresh agent — on any
harness — can continue the work. Also handles pickup. Two halves, one artifact contract.

## Artifact contract

Location — the user-level lightbridge state dir (spec: `lightbridge-config` skill):

```
~/.lightbridge/projects/<project-key>/handoffs/<YYYY-MM-DD_HHMM>_<slug>.md
```

- `<project-key>` — absolute cwd with path separators replaced by `-` (same encoding as
  `~/.claude/projects`), e.g. `-Users-kittipos-my_config-agent-stuff`. Windows: drop the
  drive colon.
- Timestamp — local time; lexicographic order = chronological, so the latest handoff is
  always the last file. (Filename `_HHMM` and frontmatter `THH:MM` intentionally differ:
  filesystem-safe vs ISO-like.)
- `<slug>` — kebab-cased from the argument's first few significant words (≤ 6): drop filler
  words and all punctuation, keep it readable. `session` if no argument given.
- Create missing parent directories.

Required frontmatter:

```yaml
---
project: /Users/kittipos/my_config/agent-stuff   # absolute cwd
created: 2026-07-09T14:30                        # local time
harness: claude-code                             # or codex, pi, …
focus: <the argument verbatim; else your one-line summary of the next session's purpose>
git: main @ 8a84de3                              # <branch> @ <short-sha>; append " (dirty)"
                                                 # if uncommitted changes; `none` if not a repo
---
```

Required sections — the spine is fixed, the prose inside is free:

- `## State` — where the work stands: what's done, what's in flight, what's decided.
- `## Next steps` — concrete, ordered; the receiving agent starts here.
- `## Suggested skills` — skills the next agent should invoke, and when.
- `## Pointers` — artifacts referenced by path or URL, never duplicated (PRDs, plans, ADRs,
  trackers, tickets, commits, diffs). Anything already captured elsewhere goes here as a
  reference, not restated.

Rules:

- Redact secrets, API keys, passwords, and PII — this file outlives the session.
- Tailor content to the argument: it describes what the next session is *for*.
- After writing, report the absolute path to the user.

## Pickup

When asked to pick up / resume a handoff:

1. Derive `<project-key>` from cwd; take the **last** file in `handoffs/` (or the one the
   user names).
2. **Staleness guard** — before acting, surface it and confirm if any of: the handoff is
   older than 7 days; its `git` sha is not an ancestor of current `HEAD`; the repo state
   visibly contradicts `## State`. A stale handoff silently resumed is worse than none.
3. Follow `## Pointers` for full context; continue from `## Next steps`.

---

_Adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)._
