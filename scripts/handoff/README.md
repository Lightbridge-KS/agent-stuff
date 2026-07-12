# handoff

Handoff storage for a repo: a **pulled journal**, and a **pushed inbox**.

```
~/.lightbridge/projects/<project-key>/handoffs/
├── 2026-07-09_2233_foundation.md        journal — PULLED. "resume" reads the tail.
├── 2026-07-11_0313_tracer-m2.md
└── inbox/
    ├── .acked
    └── 2026-07-11_1739_dataset-landed.md   inbox — PUSHED. announced, needs ack.
```

```bash
handoff.py                 # unread inbox items for this repo
handoff.py --all           # ...including acknowledged ones
handoff.py --journal       # latest journal handoff — what `resume` picks up
handoff.py --ack <file>    # mark one inbox item read
handoff.py --ack-all
handoff.py --json          # machine-readable, for an agent
```

[`hooks/handoff-inject`](../../hooks/handoff-inject) is the thin SessionStart wiring that
surfaces unread inbox items automatically.

## Why they are two directories

They are two data structures. The **journal** is a log: the newest supersedes the older, pickup
reads the tail, nothing is acknowledged. The **inbox** is a queue: every item is independently
live, two messages from two repos do not supersede each other, and each needs an explicit ack.

Flat, they poisoned each other — `resume` took the last file and could hand you an unrelated
cross-repo notification instead of your own work. Split, that is unrepresentable, and every
consumer stops filtering.

## Delivery is not origin

The split is on **delivery** (*did anyone ask for this?*), not on which repo wrote it:

- A **sibling repo** that just changed something you depend on → inbox. The common case.
- A **scheduled or background session in your own repo**, leaving a note for the next human →
  also the inbox. Unsolicited is unsolicited; there is no `from:` block, and it is still
  announced.

Origin lives in the `from:` frontmatter block — **provenance, never routing**. Impact lives in
top-level `breaking`, because it is a fact about the destination, not about who sent it.

## Acknowledgement is durable

State is `<handoffs>/inbox/.acked` — one filename per line. An agent merely *seeing* a notice is
not an acknowledgement; a notice that re-fires forever is one that gets tuned out, which is the
exact failure this exists to prevent.

`<project-key>` derives from the repo root — the git toplevel of cwd (cwd itself for
non-git dirs) — via the `scripts/lightbridge` resolver, so a session launched in a subdir
lands on the same key. `$LIGHTBRIDGE_STATE_DIR` overrides the default
`~/.lightbridge/projects` (used by the tests).

Exit codes: `0` ok · `1` nothing to acknowledge · `2` usage.
