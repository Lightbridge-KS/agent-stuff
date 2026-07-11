# handoff

The **cross-repo handoff inbox**: list what other repos have sent to this one, and acknowledge it.

A **same-repo** handoff is *pulled* — the user says "resume" and the `handoff` skill's pickup runs
because someone asked. A **cross-repo** handoff is *pushed*: repo A writes it into repo B's
project-key because A changed something B depends on. **Nothing prompts B to look.** This is the
inbox that fixes that; [`hooks/handoff-inject`](../../hooks/handoff-inject) is the thin SessionStart
wiring that surfaces the unread ones automatically.

```bash
handoff.py                 # unread cross-repo handoffs for this repo
handoff.py --all           # ...including acknowledged ones
handoff.py --ack <file>    # mark one read, so it stops being announced
handoff.py --ack-all
handoff.py --json          # machine-readable, for an agent
```

- **Cross-repo is detected by the `from:` block** in the handoff frontmatter — its presence *is* the
  signal (handoff skill, v2026-07-11). Same-repo handoffs are ignored here on purpose: they are
  pulled on demand, and announcing one every session would fight the harness's own context
  management, and could resurrect a plan the session already moved past.
- **Acknowledgement is durable**, in `<handoffs>/.acked`. An agent merely *seeing* a notice is not
  an acknowledgement; a notice that re-fires forever is one that gets tuned out.
- `$LIGHTBRIDGE_STATE_DIR` overrides the default `~/.lightbridge/projects` (used by the tests).

Exit codes: `0` ok · `1` nothing to acknowledge · `2` usage.
