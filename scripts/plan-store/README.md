# plan-store

Durable, project-keyed, status-bearing plans — the filing system Claude Code's plan mode
never had.

## Why

Claude Code already persists every plan it drafts to `~/.claude/plans/<codename>.md`. That
store is a **drafting scratchpad**: flat across every repo, randomly named
(`immutable-herding-noodle.md`), no frontmatter, no project key, no outcome. It cannot
answer *"what did I approve in this repo, and did it land?"* — so in practice the plans are
invisible, and users experience them as ephemeral even though they are on disk.

`plan-store` keeps only the plans a human said **yes** to, files them under the project
they belong to, and gives each one a lifecycle.

**This is not `docs/progress/`.** A tracker is shared, committed, zoomed-out checkbox state
that collaborators audit — it belongs in the repo. A plan is private, zoomed-in, one-off
execution detail, which is why Claude Code itself writes it to a *user-level* path. This is
the ephemeral layer given a filing system; it links *up* to the tracker, never replaces it.

## Artifact contract

```
~/.lightbridge/projects/<project-key>/plans/<YYYY-MM-DD_HHMM>_<slug>.md
```

```yaml
---
project: /Users/kittipos/my_config/agent-stuff
created: 2026-07-13T00:40
harness: claude-code
git: main @ 2826723
status: approved          # approved | executing | landed | abandoned | superseded
approval: auto            # auto (gate bypassed by config) | human (dialog)
source: /Users/kittipos/.claude/plans/add-a-subtract-a-b-robust-shore.md
session: ade31e11-50f5-47eb-98ce-bb7d1ae1cbc4
---

<the approved plan, verbatim>
```

Timestamp-prefixed, so lexicographic order is chronological and `latest` is the last file.
The slug comes from the plan's own H1, falling back to the harness codename.

## Usage

```bash
plan_store.py list                    # this project's plans, newest last
plan_store.py list --status executing # filter
plan_store.py list --json             # machine-readable
plan_store.py show                    # the latest plan, in full
plan_store.py show 2026-07-13_0040    # stem, or any unique prefix
plan_store.py status latest landed    # move it through the lifecycle
plan_store.py capture < payload.json  # file a plan from a hook payload (hooks call this)
```

`<id>` is a filename stem, any unique prefix of one, or `latest`.

Exit codes: `0` ok · `1` refused (no such plan, ambiguous id, bad state) · `2` usage.

## Opt-in

A project stores plans iff its lightbridge config has a `[plans]` section:

```bash
lb add plans
```

```toml
[plans]
enabled = true         # optional; default true
auto_approve = false   # default false — see hooks/plan-gate before turning this on
```

No section → `capture` is a silent no-op. (Spec: the `lightbridge-config` skill.)

## How capture knows a plan was approved

`hooks/plan-capture` runs on **`PostToolUse(ExitPlanMode)`**, which fires *iff* the tool
actually executed — and `ExitPlanMode` only executes when the plan is approved. Rejecting a
plan ("keep planning with feedback") never runs the tool, so nothing is filed. That is the
whole approval signal, and it is the one fact `~/.claude/plans/` cannot tell you.

`PreToolUse` would be the wrong hook: it fires *before* the decision, so it would file plans
that were never approved.

**The approved text comes from the file at `planFilePath`, not from `tool_input.plan`.** The
user can edit the plan inside the approval dialog; the edited version is what lands on disk,
while `tool_input.plan` still holds the pre-edit draft. The draft is only a fallback.

## Design notes

- **No cross-hook state.** `approval: auto|human` is *derived*: when `auto_approve` is on,
  the gate hook always bypasses the dialog, so an approval under that config is by
  definition automatic. No marker files to leak or garbage-collect.
- **Fails open.** Missing config, missing section, malformed payload, unreadable plan file →
  do nothing, exit 0. A hook must never break a session.
- **One resolver.** Root/key/config resolution comes from `scripts/lightbridge` via
  `importlib` — never reimplemented, and no third-party imports (several dep-free readers
  exec this module into their own interpreter).

## Readers

- `hooks/plan-capture` — `PostToolUse(ExitPlanMode)`; files the approved plan.
- `hooks/plan-gate` — `PreToolUse(ExitPlanMode)`; opt-in auto-approve.
