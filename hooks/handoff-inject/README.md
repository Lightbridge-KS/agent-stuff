# handoff-inject

A **`SessionStart`** hook for **Claude Code and Codex** that announces the handoffs **pushed at
this repo** — so an agent finds out that a sibling repo changed something it depends on (or that
last night's unattended run left the tree needing action) *before* touching any code, instead of
never.

The hook logic is agent-neutral: it reads `cwd` on stdin and emits the shared
`hookSpecificOutput.additionalContext` envelope that both agents consume. Only the
*registration* differs per agent; `bin/install.py --hooks` renders both.

## Why this exists

Handoffs split on **delivery**. The **journal** (`handoffs/*.md`) is **pulled**: the user says
"resume", and the `handoff` skill's pickup runs *because someone asked for it*.

The **inbox** (`handoffs/inbox/*.md`) is **pushed**: another repo — or a scheduled session in this
one — left something nobody asked for. **Nothing prompts anyone to look.** The artifact is correct,
durable, and completely invisible: a letter with no postman. Worse, the `breaking: true` flag (the
one field an agent can branch on) is worth exactly nothing if nothing ever reads it.

This hook is the postman.

## Behavior

```
SessionStart → cwd
  repo root = git toplevel of cwd (cwd itself if not a git repo)
  ~/.lightbridge/projects/<project-key>/handoffs/inbox/   missing?  → exit 0, silent
  each inbox/*.md  (a plain glob — delivery was decided at WRITE time,
                    so there is nothing to classify here)
  listed in inbox/.acked?                                 yes       → skip
  nothing left?                                                     → exit 0, silent
  otherwise → inject a compact, breaking-first notice
```

**The journal is never injected.** It is pulled on demand, and surfacing it every session would
fight the harness's own context management — worse, it could resurrect a plan the session has
already moved past. Push must announce itself; pull is already announced by the user asking.

Example injected context:

```
Unread handoff in this repo's inbox: 1  (1 BREAKING)
!! BREAKING from orthanc-test-pacs (main @ 72745e1) · 2026-07-11T17:39
     The dataset extension you requested has LANDED on main. …
     /Users/…/handoffs/inbox/2026-07-11_1739_orthanc-dataset-landed.md

These were PUSHED here — nobody asked for them, so read before assuming context. Start with
`## Impact here`; a BREAKING one means this repo needs a code or ops change to stay correct.
Acknowledge with `handoff.py --ack <file>` so it stops being announced. (Your own resumable
work is the journal, one level up — this is not that.)
```

## Acknowledgement is durable, on purpose

State lives in `<handoffs>/inbox/.acked` — one filename per line, written by
`scripts/handoff/handoff.py --ack`.

An agent *seeing* a notice once is not an acknowledgement. If "read" meant "appeared in context",
every fresh session would re-announce work that was already done, and the notice would be tuned
out within a week — which is precisely the failure this hook exists to prevent. So acking is an
explicit act, and the `handoff` skill's pickup protocol ends with it.

## Fails open, always

No `~/.lightbridge` state dir · no inbox for this repo · an empty inbox · everything
acknowledged · an unparseable frontmatter → **emits nothing, exit 0**. A hook that cries wolf is
a hook that gets ignored.

## Pairs with

- [`scripts/handoff`](../../scripts/handoff) — the deterministic core (journal + inbox; the agent
  or a human can drive it by hand). The hook is thin wiring around it.
- The [`handoff`](../../plugins/productivity/skills/handoff) skill — writes the artifact, and
  decides at write time which directory it lands in.
