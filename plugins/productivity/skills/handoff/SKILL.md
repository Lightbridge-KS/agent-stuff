---
name: handoff
description: Compact the current conversation into a durable handoff document another agent (any harness, any repo) picks up later — or resume from the latest handoff.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
metadata:
  version: "2026-07-12"
---

# Handoff

Write a handoff document so a fresh agent — any harness, any repo — can continue the work.
Also handles pickup. Two halves, one artifact contract.

Two independent properties; don't conflate them:

- **Delivery** — *pulled* (written for your own next session; the user will say "resume") or
  *pushed* (written at a repo that didn't ask — you changed something it depends on, or a
  scheduled/background run is leaving a note). **Delivery decides the directory.**
- **Origin** — which repo it was written *from*. When it differs from the destination, record
  it, or the pickup guard misfires. **Origin is frontmatter (`from:`), never routing.**

Cross-repo is the common pushed case, not the only one — never use origin as a proxy for
delivery.

## Artifact contract

Location — user-level lightbridge state dir (spec: `lightbridge-config` skill), **always keyed
on the destination** (that's where the next agent will be):

```
~/.lightbridge/projects/<project-key>/handoffs/
├── <YYYY-MM-DD_HHMM>_<slug>.md         ← JOURNAL: pulled. `resume` reads the tail.
└── inbox/
    ├── .acked
    └── <YYYY-MM-DD_HHMM>_<slug>.md     ← INBOX: pushed. announced at SessionStart; needs ack.
```

**Which directory?** *Did anyone ask for this?* 

- Own next session in this repo → **journal**
(the `handoffs/` root). 
- A repo that didn't ask → **`inbox/`**. 

They are different data structures: the journal is a log (newest supersedes, pickup reads the tail, no ack); the inbox
is a queue (every item independently live, each needs an explicit ack). Mixed together, a
"resume" would hand the user an unrelated notification instead of their own work.

- `<project-key>` — **destination** repo's absolute path, separators → `-` (same encoding as
  `~/.claude/projects`), e.g. `-Users-kittipos-my_config-agent-stuff`. Windows: drop the drive
  colon.
- Timestamp — local time; lexicographic = chronological, so the latest is the last file.
  (Filename `_HHMM` vs frontmatter `THH:MM` is intentional: filesystem-safe vs ISO-like.)
- `<slug>` — kebab-case from the argument's first ≤ 6 significant words; `session` if no
  argument.
- Create missing parent directories.

### Frontmatter

Each `git` binds to the `project` directly above it — never report one repo's sha under
another repo's path.

```yaml
---
project: /Users/kittipos/my_config/agent-stuff   # DESTINATION — whose project-key this lands under
created: 2026-07-09T14:30                        # local time
harness: claude-code                             # or codex, pi, …
focus: <the argument verbatim; else a one-line summary of the next session's purpose>
git: main @ 8a84de3                              # DESTINATION: <branch> @ <short-sha>; append
                                                 # " (dirty)" if uncommitted; `none` if not a
                                                 # repo; `unknown` if unreadable (written from
                                                 # another repo)
breaking: true                                   # INBOX only, required there: does the
                                                 # destination need a code/ops change to stay
                                                 # correct? true | false
---
```

`breaking` is the one branchable field, and it's **top-level** because it's a fact about the
**destination** — a same-repo scheduled run that leaves the tree needing action is breaking
too. `true` ⇒ the receiving agent surfaces `## Impact here` before anything else.

**Different origin repo only** — add `from:`; omit entirely when writing from the repo you are
addressing (including a background session writing into its own `inbox/`):

```yaml
from:
  repo: orthanc-test-pacs                        # logical name from ~/.lightbridge/repos.toml
  project: /Users/kittipos/…/orthanc-test-pacs   # ORIGIN — absolute path; the reader can cd here
  git: main @ 72745e1                            # ORIGIN: what the described work landed as
```

The origin's `[repo-links]` usually already declares the relationship, so the reader can
answer "why is this repo talking to me?" without prose.

### Sections

Required — fixed spine, free prose:

- `## State` — what's done, in flight, decided.
- `## Impact here` — **inbox only; omit in journal.** In the *destination's* terms: what
  breaks, what must change, what's newly possible. **Lead with anything `breaking`.** This is
  the payload of a pushed handoff.
- `## Next steps` — concrete, ordered; the receiving agent starts here. Advisory in an inbox
  handoff — the destination's maintainer decides.
- `## Pointers` — artifacts by path/URL, never duplicated (PRDs, plans, ADRs, trackers,
  tickets, commits, diffs). Cross-repo: prefix origin paths with the repo name — the reader
  isn't standing in your repo.

Optional: `## Suggested skills` — only when it carries its weight; an empty ritual section is
worse than none.

Rules:

- Redact secrets, keys, PII — this file outlives the session.
- Tailor to the argument: it describes what the next session is *for*.
- Report what you got *wrong*, not just what you did. If you overrode the receiving agent's
  stated requirements, say which and show the evidence.
- After writing, report the absolute path to the user.

## Pickup

The journal is pulled (user asks). The inbox is pushed — the `handoff-inject` SessionStart
hook (`hooks/handoff-inject`) announces unread items; `scripts/handoff/handoff.py` is the
inbox behind it:

```bash
handoff.py                 # unread inbox items for this repo
handoff.py --journal       # latest journal handoff — what `resume` picks up
handoff.py --ack <file>    # mark one inbox item read
```

**Resuming (journal).**

1. Derive `<project-key>` from cwd; take the **last file in `handoffs/`** — the root, *not*
   `inbox/` (or the one the user names). An inbox item is never what "resume" means.
2. **Staleness guard** — flag and confirm before acting if: older than 7 days; `git`'s sha is
   not an ancestor of current `HEAD`; or the repo state visibly contradicts `## State`.

   ```bash
   git merge-base --is-ancestor <git sha> HEAD
   ```

3. Follow `## Pointers`; continue from `## Next steps`.

**Reading the inbox (pushed).** Same as above, plus:

1. If `breaking: true`, surface `## Impact here` **first**, before any other work.
2. **Staleness guard, when `from:` is present** — two repos, two checks, not interchangeable:

   ```bash
   # origin: is the described work still on the origin's main line?
   git -C <from.project> merge-base --is-ancestor <from.git sha> HEAD

   # destination: has my repo moved since the writer looked? if so their
   # impact analysis may be stale.
   git merge-base --is-ancestor <git sha> HEAD
   ```

   **Never run `from.git`'s sha against your own repo** — the object doesn't exist there, the
   check hard-errors, and every fresh cross-repo handoff reads as stale. A guard that always
   fires gets ignored.

3. Inbox `## Next steps` are **advisory** — the user owns the call.
4. **Ack once acted on (or consciously declined):** `handoff.py --ack <file>`. The ack is part
   of the task's definition of done — work on an inbox item is not complete until it has run.
   An unacked item is re-announced every session; a notice that never stops firing gets tuned
   out. Do not ack an item you have merely read.

---

_Adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)._
