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

Two things about a handoff are independent, and conflating them causes bugs:

- **Delivery** — was it *pulled* or *pushed*? A handoff you write for your own next session is
  pulled: the user says "resume", and pickup runs because someone asked. A handoff you write
  *at* a repo that did not ask for it — because you changed something it depends on, or because
  you are a scheduled/background session leaving a note — is **pushed**. Nobody is coming to
  look for it. **Delivery decides which directory it lands in.**
- **Origin** — which repo was it written *from*? Usually the same one it is addressed to. When
  it differs, that must be recorded, or the receiving agent cannot tell who is talking to it and
  the pickup guard below misfires. **Origin is frontmatter (`from:`), never routing.**

Cross-repo handoffs are the common pushed case, but not the only one — do not use origin as a
proxy for delivery.

## Artifact contract

Location — the user-level lightbridge state dir (spec: `lightbridge-config` skill). **Always
keyed on the destination**, because that is where the next agent will be:

```
~/.lightbridge/projects/<project-key>/handoffs/
├── <YYYY-MM-DD_HHMM>_<slug>.md         ← JOURNAL: pulled. `resume` reads the tail.
└── inbox/
    ├── .acked
    └── <YYYY-MM-DD_HHMM>_<slug>.md     ← INBOX: pushed. announced at SessionStart; needs ack.
```

**Which directory?** Ask one question: *did anyone ask for this?*

- Writing for your own next session in this repo, which the user will resume → **journal** (the
  `handoffs/` root).
- Writing at a repo that did not ask — a sibling repo you have just affected, or the next human
  session after an unattended run → **`inbox/`**.

They are different data structures, which is why they are different directories. The journal is
a log: the newest supersedes the older, pickup reads the tail, nothing is acknowledged. The
inbox is a queue: every item is independently live, two messages do not supersede each other,
and each needs an explicit ack. Kept in one directory they poison each other — a "resume" would
hand the user an unrelated notification instead of their own work.

- `<project-key>` — the **destination** repo's absolute path with separators replaced by `-`
  (same encoding as `~/.claude/projects`), e.g. `-Users-kittipos-my_config-agent-stuff`.
  Windows: drop the drive colon. For a handoff to your own repo this is just your cwd.
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
                                                 # not read it (wrote it from another repo)
breaking: true                                   # INBOX only, required there: does the
                                                 # destination need a code or ops change to stay
                                                 # correct? true | false
---
```

`breaking` is the one field an agent can *branch* on, and it is **top-level** because it is a
fact about the **destination**, not about who sent it — a scheduled same-repo run that leaves
the tree needing action is breaking too. A `true` means the receiving agent surfaces
`## Impact here` before doing anything else.

**Different origin repo only** — add a `from:` block. Omit it entirely when you are writing
from the repo you are addressing (including a background session writing into its own `inbox/`).

```yaml
from:
  repo: orthanc-test-pacs                        # logical name from ~/.lightbridge/repos.toml
  project: /Users/kittipos/…/orthanc-test-pacs   # ORIGIN — absolute path; the reader can cd here
  git: main @ 72745e1                            # ORIGIN repo: what the described work landed as
```

`repo` resolves via `~/.lightbridge/repos.toml`. The origin repo's `[repo-links]` section
usually already declares the relationship, so the reader can answer "why is this repo talking to
me?" without you restating it in prose.

### Sections

Required — the spine is fixed; the prose inside is free.

- `## State` — where the work stands: what's done, what's in flight, what's decided.
- `## Impact here` — **required for an `inbox/` handoff; omit for a journal one.** Written in
  the *destination's* terms, not the origin's: what breaks, what must change, what is newly
  possible. **Lead with anything `breaking`.** This is the payload of a pushed handoff — the
  receiving agent cares far more about what happens to *their* repo than about what you did in
  yours.
- `## Next steps` — concrete, ordered; the receiving agent starts here. In an `inbox/` handoff
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

The journal is **pulled** — you resume it because the user asked. The inbox is **pushed**, so
nothing prompts you to look: the `handoff-inject` SessionStart hook (`hooks/handoff-inject`)
announces unread items, and `scripts/handoff/handoff.py` is the inbox behind it:

```bash
handoff.py                 # unread inbox items for this repo
handoff.py --journal       # the latest journal handoff — what `resume` picks up
handoff.py --ack <file>    # mark one inbox item read, so it stops being announced
```

**Resuming (the journal).**

1. Derive `<project-key>` from cwd; take the **last file in `handoffs/`** — the root, *not*
   `inbox/`. (Or the one the user names.) An inbox item is never what "resume" means; keeping
   the two apart is why they are separate directories.
2. **Staleness guard** — flag and confirm before acting if: the handoff is older than 7 days;
   `git`'s sha is not an ancestor of current `HEAD`; or the repo state visibly contradicts
   `## State`.

   ```bash
   git merge-base --is-ancestor <git sha> HEAD
   ```

3. Follow `## Pointers`; continue from `## Next steps`.

**Reading the inbox (pushed).** Same as above, plus:

1. If `breaking` is `true`, surface `## Impact here` **first**, before continuing any other
   work. That is what the flag is for.
2. **Staleness guard, when `from:` is present** — two repos, two checks, and they are *not*
   interchangeable:

   ```bash
   # origin: is the work it describes still on the origin's main line?
   git -C <from.project> merge-base --is-ancestor <from.git sha> HEAD

   # destination: has my repo moved since the writer looked? if so their impact
   # analysis may be stale.
   git merge-base --is-ancestor <git sha> HEAD
   ```

   **Never run `from.git`'s sha against your own repo.** That object does not exist there — the
   check hard-errors (`fatal: Not a valid object name`) and every fresh cross-repo handoff reads
   as stale. A guard that always fires is a guard that gets ignored.

3. `## Next steps` in an inbox handoff are **advisory** — the user owns the call, not the repo
   that sent it.
4. **Acknowledge it** once acted on (or consciously declined): `handoff.py --ack <file>`.
   Acknowledgement is durable state, not "the agent saw it once" — an unacked item is
   re-announced every session, and a notice that never stops firing is a notice that gets tuned
   out. Do not ack an item you have merely read.

---

_Adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)._
