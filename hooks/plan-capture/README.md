# plan-capture

`PostToolUse(ExitPlanMode)` → files the **approved** plan into
`~/.lightbridge/projects/<project-key>/plans/`.

Claude Code writes every plan it drafts to `~/.claude/plans/<codename>.md` — flat across all
repos, randomly named, no frontmatter, no project, no outcome. This hook keeps the ones you
actually approved, files them under the right project, and stamps them with a lifecycle.

The artifact contract, the CLI (`list` / `show` / `status`), and the design rationale live
with the tool: [`scripts/plan-store/README.md`](../../scripts/plan-store/README.md). This
hook is just the wire.

## Why `PostToolUse` and not `PreToolUse`

`PostToolUse` fires **iff the tool executed**, and `ExitPlanMode` only executes when the plan
is approved. Rejecting a plan ("keep planning with feedback") never runs it, so nothing gets
filed. That makes this hook the approval signal — the one fact `~/.claude/plans/` cannot
give you.

`PreToolUse` fires *before* the decision, so it would happily file plans nobody said yes to.
(That event is used by the sibling [`plan-gate`](../plan-gate/) hook, whose job is the
decision itself.)

## Opt-in

```bash
lb add plans        # adds [plans] to this project's lightbridge config
```

No `[plans]` section, `enabled = false`, or a malformed config → the hook emits nothing and
exits 0. Fail open, always.

## Install

```bash
uv run bin/install.py --hooks --claude     # prints the settings.json block to paste
```

## Verify

```bash
lb add plans                                  # opt this repo in
# …enter plan mode, write a plan, approve it…
uv run scripts/plan-store/plan_store.py list  # the plan is filed
```
