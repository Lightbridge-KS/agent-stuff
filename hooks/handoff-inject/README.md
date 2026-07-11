# handoff-inject

A **`SessionStart`** hook for **Claude Code and Codex** that announces **cross-repo handoffs
addressed to this repo** — so an agent finds out that a sibling repo changed something it
depends on *before* touching any code, instead of never.

The hook logic is agent-neutral: it reads `cwd` on stdin and emits the shared
`hookSpecificOutput.additionalContext` envelope that both agents consume. Only the
*registration* differs per agent; `bin/install.py --hooks` renders both.

## Why this exists

A **same-repo** handoff is **pulled**: the user says "resume", and the `handoff` skill's pickup
protocol runs *because someone asked for it*.

A **cross-repo** handoff is **pushed**: repo A writes a handoff into repo B's project-key because
A changed something B depends on. **Nothing prompts B to look.** The artifact is correct, durable,
and completely invisible — a letter with no postman. Worse, the schema's `breaking: true` flag
(the one field an agent can branch on) is worth exactly nothing if nothing ever reads it.

This hook is the postman.

## Behavior

```
SessionStart → cwd
  ~/.lightbridge/projects/<project-key>/handoffs/    missing?          → exit 0, silent
  each *.md: frontmatter has a `from:` block?         no  (same-repo)   → skip
                                                      yes (cross-repo)  → candidate
  candidate listed in <handoffs>/.acked?              yes               → skip
  nothing left?                                                         → exit 0, silent
  otherwise → inject a compact, breaking-first notice
```

**Same-repo handoffs are never injected.** They are pulled on demand, and surfacing one every
session would fight the harness's own context management — worse, it could resurrect a plan the
session has already moved past. Push must announce itself; pull is already announced by the user.

Example injected context:

```
Unread cross-repo handoff addressed to this repo: 1  (1 BREAKING)
!! BREAKING from orthanc-test-pacs (main @ 72745e1) · 2026-07-11T17:39
     The dataset extension you requested has LANDED on main. …
     /Users/…/handoffs/2026-07-11_1739_orthanc-dataset-landed.md

These were PUSHED here by another repo — nobody asked for them, so read before assuming
context. Start with `## Impact here`; a BREAKING one means this repo needs a code or ops
change to stay correct. Acknowledge with `handoff.py --ack <file>` so it stops being announced.
```

## Acknowledgement is durable, on purpose

State lives in `<handoffs>/.acked` — one filename per line, written by
`scripts/handoff/handoff.py --ack`.

An agent *seeing* a notice once is not an acknowledgement. If "read" meant "appeared in context",
every fresh session would re-announce work that was already done, and the notice would be tuned
out within a week — which is precisely the failure this hook exists to prevent. So acking is an
explicit act, and the `handoff` skill's pickup protocol ends with it.

## Fails open, always

No `~/.lightbridge` state dir · no handoffs dir for this repo · no cross-repo handoffs · all
acknowledged · an unparseable frontmatter → **emits nothing, exit 0**. A hook that cries wolf is
a hook that gets ignored.

## Pairs with

- [`scripts/handoff`](../../scripts/handoff) — the deterministic core (the inbox; the agent or a
  human can drive it by hand). The hook is thin wiring around it.
- The [`handoff`](../../plugins/productivity/skills/handoff) skill — writes the artifact and
  defines the `from:` schema this hook keys on.
