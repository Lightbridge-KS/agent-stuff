---
summary: Settled design for skill-health — a scheduled aggregator that runs the existing
  deterministic health checks (skill-vendor doctor, lb doctor, validate.py across three
  content trees), reports red/green, and hands a red result to a pluggable notifier
  command. Report-only by contract; launchd is the scheduler, not any agent harness.
read_when:
  - implementing or changing scripts/skill-health
  - adding a check to the weekly health sweep, or changing an exit-code mapping
  - wiring a notifier (Telegram/OpenClaw) to the health report
  - deciding where a periodic agent-surface check belongs, or why launchd was chosen
    over Claude's in-session cron and cloud routines
---

# skill-health — Design

## Why

The skill surface spans several symlink registries, three content trees, and four
vendored binaries that drift independently. Every one of those has a deterministic
checker already. None of them ran on a schedule.

The prompting failure (2026-08-09): `RAMAAI-WorkSpace/agent-skills` restructured from
`skills/<name>` to `plugins/<domain>/skills/<name>`, orphaning two symlinks in
`~/.codex/skills/`. They stayed broken ~10 days and were found only because the user
happened to run `skill-vendor doctor` by hand. Nothing was wrong with the checker; the
gap was that no one called it.

## The one idea

**Detection is deterministic; only repair needs a model.**

Five commands, five exit codes. No LLM is involved in noticing that something broke —
that keeps the check cheap, testable, and runnable when no agent is open. Reasoning
enters only after a human is told, at which point an agent re-runs `skill-health --json`
and works from the structured findings.

```
Sat 10:07 ── launchd  com.kittipos.skill-health
                │
                ▼
        skill-health (deterministic, no model)
        ├─ skill-vendor doctor          0 ok · 1 skew · 2 broken
        ├─ lb doctor                    0 ok
        └─ validate.py × 3 trees        agent-stuff · -private · skills-island
                │
         ┌──────┴──────┐
       green          red
         │              │
     write JSON     write JSON + exec --notify-command < alert.json
      (silent)                   │
                                 ▼
                        notifier → Telegram/OpenClaw
```

## Scheduler choice

launchd, not either Claude-native scheduler:

| Mechanism | Persists | Local FS | Verdict |
|---|---|---|---|
| `CronCreate` (in-session) | no — dies with the session; recurring auto-expires after 7 days | yes | a weekly job fires once at best |
| `/schedule` cloud routines | yes | **no** | cannot read the registries under test |
| **launchd** | yes | yes | nothing need be open; `StartCalendarInterval` fires on next wake |

## Contracts

**Aggregation, never reimplementation.** Each check stays owned by its engine, so every
invariant has exactly one definition. skill-health shells out, maps exit codes, and
aggregates. A check that needs to see more (e.g. more registries) is fixed in *its* tool,
not here.

**Report-only.** No repair action, ever. `skill-vendor sync` moves worktrees and relinks
registries; it is not something to run unattended against an unwatched machine. Severity
in the payload is informational.

**Exit codes.** `0` all green · `1` at least one check red · `2` usage/internal error.
The nuance a checker reports (skew vs broken) survives per-check in the JSON; the
process code collapses to did-anything-fail, because that is the only question the
scheduler and the notifier ask.

**Notifier seam.** `--notify-command PATH` execs on red only, with the alert JSON on
stdin. This mirrors `mac-cpu-watchdog`'s `notifier.type: "command"`, and the payload
reuses that tool's core field names — `severity`, `type`, `timestamp`, `host`,
`message`, `metadata` (`internal/notify/notify.go:54`) — so one notifier script can
serve both tools. Cost of the coupling: this tool tracks that struct's naming.

**State.** Latest run lands at `~/.lightbridge/health/skill-health.json` — durable,
harness-neutral, alongside `handoffs/`. `SKILL_HEALTH_HOME` overrides for tests.

## Known coverage gap

`skill-vendor doctor` enforces the registry invariant over the registries in its
manifest's `[defaults]` — `~/.claude/skills` and `~/.codex/skills`. Four symlink
registries on this machine are unscanned: `~/.claude/agents/`, `my_book/.claude/skills`,
`my_book/.agents/skills`, `my_config/.claude/skills`. The 2026-08-09 breakage happened to
land in a covered registry.

Deliberately **not** patched here: the invariant belongs to `doctor` (see
`docs/skill-vendor/design.md`), and a second copy of it in this tool would drift. The fix
is a follow-up that extends `doctor`'s registry list — noting that `~/.claude/agents/`
holds files (`mech.md`), not skill directories, so it likely needs code, not just a
manifest line.
