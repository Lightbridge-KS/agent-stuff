---
name: handoff
description: Compact the current conversation into a durable handoff document another agent (any harness, any repo) picks up later — or resume from the latest handoff.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
metadata:
  version: "2026-07-11"
---

# Handoff

Write a handoff document summarising the current conversation so a fresh agent — on any
harness, in any repo — can continue the work. Also handles pickup. Two halves, one artifact
contract.

A handoff has a **destination** (the repo the next agent will be working in) and an **origin**
(the repo it was written from). Usually they are the same repo and the distinction is
invisible. When they differ — you changed something in repo A that a sibling repo B depends on
— the origin must be recorded, or the receiving agent cannot tell who is talking to it, and the
pickup guard below misfires.

## Artifact contract

Location — the user-level lightbridge state dir (spec: `lightbridge-config` skill). **Always
keyed on the destination**, because that is where the next agent will be:

```
~/.lightbridge/projects/<project-key>/handoffs/<YYYY-MM-DD_HHMM>_<slug>.md
```

- `<project-key>` — the **destination** repo's absolute path with separators replaced by `-`
  (same encoding as `~/.claude/projects`), e.g. `-Users-kittipos-my_config-agent-stuff`.
  Windows: drop the drive colon. For a same-repo handoff this is just your cwd.
- Timestamp — local time; lexicographic order = chronological, so the latest handoff is
  always the last file. (Filename `_HHMM` and frontmatter `THH:MM` intentionally differ:
  filesystem-safe vs ISO-like.)
- `<slug>` — kebab-cased from the argument's first few significant words (≤ 6): drop filler
  words and all punctuation, keep it readable. `session` if no argument given.
- Create missing parent directories.

### Frontmatter

Each `git` is bound to the `project` directly above it. That is the whole point — never report
one repo's sha under another repo's path.

```yaml
---
project: /Users/kittipos/my_config/agent-stuff   # DESTINATION — whose project-key this lands under
created: 2026-07-09T14:30                        # local time
harness: claude-code                             # or codex, pi, …
focus: <the argument verbatim; else your one-line summary of the next session's purpose>
git: main @ 8a84de3                              # DESTINATION repo: <branch> @ <short-sha>;
                                                 # append " (dirty)" if uncommitted changes;
                                                 # `none` if not a repo; `unknown` if you could
                                                 # not read it (cross-repo, no access)
---
```

**Cross-repo only** — add a `from:` block. **Its presence is the signal**; there is no separate
"kind" field. Omit it entirely for an ordinary same-repo handoff.

```yaml
from:
  repo: orthanc-test-pacs                        # logical name from ~/.lightbridge/repos.toml
  project: /Users/kittipos/…/orthanc-test-pacs   # ORIGIN — absolute path; the reader can cd here
  git: main @ 72745e1                            # ORIGIN repo: what the described work landed as
  breaking: true                                 # does the DESTINATION need a code or ops change
                                                 # to stay correct? true | false
```

- `repo` — resolve via `~/.lightbridge/repos.toml`. The origin repo's `[repo-links]` section
  usually already declares the relationship, so the reader can answer "why is this repo talking
  to me?" without you restating it in prose.
- `breaking` — the one field an agent can *branch* on. Set `true` when the destination must
  change code, drop state, or reconfigure to remain correct. A `true` here means the receiving
  agent should surface it before doing anything else.

### Sections

Required — the spine is fixed; the prose inside is free.

- `## State` — where the work stands: what's done, what's in flight, what's decided.
- `## Impact here` — **required iff `from:` is present; omit otherwise.** Written in the
  *destination's* terms, not the origin's: what breaks, what must change, what is newly
  possible. **Lead with anything `breaking`.** This is the payload of a cross-repo handoff —
  the receiving agent cares far more about what happens to *their* repo than about what you did
  in yours.
- `## Next steps` — concrete, ordered; the receiving agent starts here. In a cross-repo handoff
  these are *advisory* — the destination's maintainer decides, you don't.
- `## Pointers` — artifacts referenced by path or URL, never duplicated (PRDs, plans, ADRs,
  trackers, tickets, commits, diffs). Anything already captured elsewhere goes here as a
  reference, not restated. For a cross-repo handoff, prefix origin-repo paths with the repo
  name — the reader is not standing in your repo.

Optional — include only when it carries its weight:

- `## Suggested skills` — skills the next agent should invoke, and when. Most handoffs have
  nothing worth saying here; an empty ritual section is worse than no section.

Rules:

- Redact secrets, API keys, passwords, and PII — this file outlives the session.
- Tailor content to the argument: it describes what the next session is *for*.
- Say what you got *wrong* as well as what you did. If you overrode the receiving agent's
  stated requirements or assumptions, say which, and show the evidence — a handoff that only
  reports success teaches the next agent nothing.
- After writing, report the absolute path to the user.

## Pickup

A same-repo handoff is **pulled** — you resume it because the user asked. A cross-repo handoff
is **pushed**, so nothing prompts you to look; the `handoff-inject` SessionStart hook
(`hooks/handoff-inject`) announces unread ones, and `scripts/handoff/handoff.py` is the inbox
behind it:

```bash
handoff.py                 # unread cross-repo handoffs addressed to this repo
handoff.py --ack <file>    # mark one read, so it stops being announced
```

When asked to pick up / resume a handoff:

1. Derive `<project-key>` from cwd; take the **last** file in `handoffs/` (or the one the user
   names).
2. **Staleness guard** — surface and confirm before acting. Which check to run depends on
   whether `from:` is present:

   - **No `from:` (same-repo).** Flag if: the handoff is older than 7 days; `git`'s sha is not
     an ancestor of current `HEAD`; or the repo state visibly contradicts `## State`.

     ```bash
     git merge-base --is-ancestor <git sha> HEAD
     ```

   - **`from:` present (cross-repo).** Two repos, two checks — and they are *not*
     interchangeable:

     ```bash
     # origin: is the work it describes still on the origin's main line?
     git -C <from.project> merge-base --is-ancestor <from.git sha> HEAD

     # destination: has my repo moved since the writer looked? if so their impact
     # analysis may be stale.
     git merge-base --is-ancestor <git sha> HEAD
     ```

     **Never run `from.git`'s sha against your own repo.** That object does not exist there —
     the check hard-errors (`fatal: Not a valid object name`) and every fresh cross-repo
     handoff reads as stale. A guard that always fires is a guard that gets ignored.

3. If `from.breaking` is `true`, surface `## Impact here` **first**, before continuing any other
   work. That is what the flag is for.
4. Follow `## Pointers` for full context; continue from `## Next steps` — remembering that in a
   cross-repo handoff those are advisory, and the user owns the call.
5. **Acknowledge it** once acted on (or consciously declined): `handoff.py --ack <file>`.
   Acknowledgement is durable state, not "the agent saw it once" — an unacked handoff is
   re-announced every session, and a notice that never stops firing is a notice that gets tuned
   out. Do not ack a handoff you have merely read.

---

_Adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)._
