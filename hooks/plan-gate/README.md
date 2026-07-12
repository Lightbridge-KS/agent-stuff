# plan-gate

`PreToolUse(ExitPlanMode)` → **opt-in** auto-approve for Claude Code's plan-approval dialog.

With `[plans].auto_approve = true`, the hook returns `permissionDecision: "allow"` and the
plan executes without the dialog ever rendering. With anything else, it stays silent and the
native gate behaves exactly as it always has.

**Default: off.** This hook exists because the capability is real, not because it is usually
a good idea.

## Read this before turning it on

Bypassing the gate deletes three things, not just a keypress:

1. **"Keep planning with feedback"** — the only way to iterate on a plan *before* it runs.
   Auto-approve makes every plan final on first draft.
2. **The post-approval mode choice** (auto / acceptEdits / review-each-edit). Bypassed, the
   session inherits your `defaultMode` — if that's `auto`, the plan goes straight to
   unsupervised execution.
3. **The last human checkpoint before writes.** Its cost is one keypress; its value is
   catching the plan that is confidently wrong.

If what you actually wanted was plan mode's *exploration* side effect — the subagent
grounding that makes plans accurate — **don't enter plan mode.** Ask for it directly:
*"ground this with Explore subagents, then implement."* You get the exploration with no gate
to bypass. That is free, and it is the right answer for most of the cases that make the
dialog feel like ceremony.

Turn this on for a repo where you have genuinely stopped reading the plans.

## Enable

```bash
lb add plans
```

then, in `~/.lightbridge/projects/<project-key>/config.toml`:

```toml
[plans]
enabled = true
auto_approve = true     # ← the switch; per-project, never global
```

## Install

```bash
uv run bin/install.py --hooks --claude     # prints the settings.json block to paste
```

Pair it with [`plan-capture`](../plan-capture/), which files every approved plan — including
the auto-approved ones, stamped `approval: auto` so you can always tell which plans nobody
read.

## Verified behavior

On Claude Code **2.1.207**, `permissionDecision: "allow"` from a `PreToolUse` hook matching
`ExitPlanMode` bypasses the approval dialog in a normal interactive session.

The official docs say this bypass requires headless (`-p`) mode. **That is wrong in both
directions** — it works interactively, and `ExitPlanMode` is not offered at all under `-p`
(a headless plan-mode session has no way to exit plan mode). Everything here comes from a
live test rig, not from the docs. Re-test after a Claude Code upgrade.
