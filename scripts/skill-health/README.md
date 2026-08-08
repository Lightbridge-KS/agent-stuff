# skill-health

One scheduled sweep over the agent-surface health checks. **Report-only** — it never
repairs anything. Settled design:
[`docs/skill-health/design.md`](../../docs/skill-health/design.md).

The skill surface spans symlink registries, content trees, and vendored binaries that
drift independently. Each already has a deterministic checker; none of them ran on a
schedule. This is the scheduler's single entrypoint.

## Checks

| Name | Command | Covers |
|---|---|---|
| `skill-vendor` | `skill-vendor doctor` | vendored skew + the registry invariant |
| `lightbridge` | `lb doctor` | the `~/.lightbridge` project tree |
| `agent-stuff` | `bin/validate.py` | this repo's content contract |
| `agent-stuff-private` | `bin/validate.py --root ../agent-stuff-private` | private castle |
| `skills-island` | `bin/validate.py --root ../skills-island` | island skills |

The last two are **skipped, not failed**, when the sibling tree is absent — a clone of
this public repo on another machine has neither.

A check whose command is missing from PATH is **red**, not skipped: it was meant to run
and did not, so the surface it covers is unverified.

## Usage

```bash
skill-health                                  # human summary
skill-health --json                           # machine report (what an agent repairs from)
skill-health --notify-command ~/bin/notify    # exec on RED only, alert JSON on stdin
```

Exit codes: **0** all green · **1** at least one check red · **2** usage/internal error.
Per-checker nuance (skew vs broken) survives in the JSON; the process code collapses to
did-anything-fail, the only question a scheduler or notifier asks.

Latest run is always written to `~/.lightbridge/health/skill-health.json`, green or red.

## Notifier contract

`--notify-command PATH` runs **only when something is red**, with the alert JSON on
stdin. Core field names mirror `mac-cpu-watchdog`'s `Alert` struct
(`internal/notify/notify.go`), so one notifier script can serve both tools:

```json
{
  "severity": "warning",
  "type": "skill_health",
  "timestamp": "2026-08-09T03:07:00Z",
  "host": "example.local",
  "message": "skill-health: 1 of 5 checks red — skill-vendor",
  "metadata": {
    "checks_total": "5",
    "checks_red": "1",
    "red": "skill-vendor",
    "report_path": "/Users/you/.lightbridge/health/skill-health.json"
  },
  "checks": [
    {"name": "skill-vendor", "what": "vendored skew + registry invariant",
     "status": "red", "exit_code": 1, "detail": "registry SKEW dangling symlink: …"}
  ]
}
```

`severity` is always `warning` on red (`info` otherwise) — this tool is report-only, so
nothing it finds needs action within the hour. `metadata` values are strings, matching
the watchdog's `map[string]string`.

A notifier that fails does not change the health verdict: the checks already ran and
their answer stands. The failure goes to stderr.

## Scheduling (launchd)

From the repo root:

```bash
mkdir -p ~/Library/Logs/skill-health
sed -e "s|__HOME__|$HOME|g" \
    -e "s|__SCRIPT__|$PWD/scripts/skill-health/skill_health.py|g" \
  scripts/skill-health/launchd/com.kittipos.skill-health.plist.template \
  > ~/Library/LaunchAgents/com.kittipos.skill-health.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.kittipos.skill-health.plist
launchctl kickstart -k gui/$UID/com.kittipos.skill-health   # force one run now
```

Use `bootstrap`, not the legacy `launchctl load` — `load` fails with `Input/output error`
on current macOS. To remove: `launchctl bootout gui/$UID/com.kittipos.skill-health`.

Saturdays at 10:07 (off the `:00`/`:30` mark). `RunAtLoad` is false — a weekly audit
should not fire on every login. `StartCalendarInterval` runs a missed fire on next wake,
so the Mac being asleep only delays it.

launchd hands jobs a minimal PATH, which bites twice. The plist therefore invokes `uv` by
absolute path rather than relying on the script's `env`-based shebang (otherwise the job
never starts — silently, weekly), and the tool itself prepends `~/.local/bin`,
`/opt/homebrew/bin`, and `/usr/local/bin` before resolving any checker. Both are
deliberate: a health checker that silently fails to find its own checkers is worse than
no checker at all.

To wire notifications, append `--notify-command /path/to/notifier` to the plist's
`ProgramArguments`.

Logs: `~/Library/Logs/skill-health/`.

## PATH shim (recommended)

```bash
ln -s "$PWD/scripts/skill-health/skill_health.py" ~/.local/bin/skill-health
```

The `#!/usr/bin/env -S uv run --script` shebang carries through the symlink. Use a real
PATH executable, not a shell alias — an alias is invisible to an agent's non-interactive
shell.

## Testing

```bash
uv run tests/test_skill_health.py
```

Env override for isolation: `SKILL_HEALTH_HOME` replaces `~/.lightbridge` (or pass
`--home DIR`); `--root DIR` replaces the agent-stuff root used to locate `bin/validate.py`
and the sibling trees.
