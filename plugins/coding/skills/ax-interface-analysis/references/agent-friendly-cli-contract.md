# Agent-Friendly CLI Contract (reference)

Concrete mechanics the analysis cites when prescribing CLI/SDK fixes. These are the *evidence*
behind the rubric principles — point recommendations here for a ready-made target shape.

> The principle: make the **shipped command surface** drivable by agents, scripts, and CI
> *without* embedding an LLM. Intelligence lives in whatever calls the tool; the tool stays
> deterministic and testable.

## Deterministic configuration resolution

One documented winner per input:

```
1. command-line flags         (highest)
2. environment variables
3. user config file
4. built-in defaults          (lowest)
```

Credentials are **scope-bound** — a token is sent only when explicitly provided for that
host, so re-pointing the tool can't leak the wrong secret. Agents can set everything via env
vars and never touch interactive state.

## Output discipline

| Need | Mechanism |
|------|-----------|
| Data a program consumes | **stdout** |
| Diagnostics / progress | **stderr** |
| Structured single result | `--json` → one JSON object |
| Structured stream | `--json` → newline-delimited JSON (one event/line) |
| Stable single field | `--plain` |
| Non-interactive safety | `--no-input` (auto when stdin isn't a TTY) |

Rule: `--json` for anything parsed, `--plain` only for stable single-field output. The
stdout/stderr split is what lets `… --json | jq` work while progress still reaches the terminal.

## Composable input precedence

Fixed order so the tool pipes naturally: `positional → --body → --file → --stdin`.

```sh
agent-summarize incident.log | tool reply msg_01k... --stdin
```

## Stable exit-code taxonomy

Highest-leverage idea: agents branch on *categories of failure* without scraping English.

| Code | Meaning | Code | Meaning |
|------|---------|------|---------|
| 0 | Success | 4 | Not found |
| 1 | Generic failure | 5 | Permission denied |
| 2 | Invalid usage | 10 | Network unavailable |
| 3 | Auth required/failed | 11 | Unexpected server response |

> "Scripts should branch on exit codes, not error text."

## Durable streaming with cursor recovery

For long-lived `tail`-style streams, persist a cursor per scope. On start, replay missed
events `after_cursor`, open the stream, re-persist after each delivery, refetch on a
`resync_required` signal. An agent can crash, restart, and resume without gaps or duplicates.

## The takeaway

Agent-friendliness is a property of the public surface, not an added assistant. Exit codes
and stdout/stderr hygiene are the cheapest, highest-impact wins.
