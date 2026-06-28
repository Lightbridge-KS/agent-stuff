# Safety guardrails

Read this before doing anything destructive or before invoking `exec`.

The CLI is built so an agent acting in good faith **cannot** wipe the
user's scene without being explicit. The contract:

1. **Empty selectors are refused at the client layer.** `node delete ""`
   never reaches Slicer — it returns `E_EMPTY_SELECTOR`. This defends
   against `DELETE /slicer/mrml`'s default semantics, where an empty `id`
   means "clear the whole scene".
2. **Destructive ops require `--confirm`.** Without it → `E_DESTRUCTIVE`.
3. **Binary commands require `--out`.** No accidental binary on stdout.
4. **`exec` is gated** by `config.exec.enabled` (see below).

## Destructive endpoints

| Endpoint | CLI command | Guard |
|---|---|---|
| `DELETE /slicer/mrml` (no selectors) | `scene clear` | `--confirm` mandatory |
| `DELETE /slicer/mrml?id=…` | `node delete <id>` | empty `<id>` refused |
| `DELETE /slicer/system` | `system shutdown` | `--confirm` mandatory |
| `POST /slicer/exec` | `exec` | gating below |
| `api raw` matches in `client.routes.DESTRUCTIVE_RAW` | `api raw …` | `--confirm` mandatory |

**Never run `scene clear --confirm`, `system shutdown --confirm`, or
`exec` without explicit user instruction.** The `--confirm` flag is a
safety check, not a checkbox to fill in automatically.

## `exec` gating flow

`/slicer/exec` runs **arbitrary Python with the privileges of the user
running Slicer**. Treat it as a last resort.

```
exec call → check config.exec.enabled
           │
           ├── enabled = true (the YOLO default)
           │     └── run + write audit-log line
           │
           └── enabled = false
                 └── is --i-understand-the-risk set?
                       │
                       ├── yes → run + write audit-log line
                       └── no  → E_EXEC_DISABLED, exit 5
```

When `exec.enabled = false` (project-locked posture), every `exec` call
needs `--i-understand-the-risk`. The flag is intentionally long and
friction-y so it doesn't become muscle memory. **Do not auto-pass it;
ask the user.**

## Audit log

Every successful `exec` call (whether direct or via `scene save`,
`dicom pull`, `markup line`) writes one line to:

```
~/.local/state/slicer-cli/exec.log    # override via config.exec.audit_log
```

Line shape (one per call, append-only):

```
2026-05-04T19:42:11Z  rev=ef05a7c  url=http://127.0.0.1:2016  hash=sha256:1a2b…  preview="<first 200 chars>"  op=cli.exec
```

The hash lets the user verify exactly what ran without flooding the log
with code.

## `--no-audit-log`

This flag exists for narrow operational situations (CI sandbox,
`ENOSPC` on the audit-log volume). It emits a stderr warning and skips
the audit write but still proceeds.

**Do not use `--no-audit-log` to hide an action.** If the user asks you
to "skip the audit", push back — the right answer is almost always to
make the audit log writable.

## Why the empty-selector defence matters

Slicer's `DELETE /slicer/mrml` accepts query parameters `id`, `class`,
`name`. With **none** present, the handler interprets the call as
"clear the entire scene" — same as `slicer.mrmlScene.Clear()`. This is
positionally fragile: a typo or a templating bug that produces an empty
id string would wipe the user's work.

The CLI refuses empty selectors at the client layer (before any HTTP
call). If you see `E_EMPTY_SELECTOR`, **do not** try to "help" by adding
`--all` or guessing an id — surface the failure and ask which node the
user meant.

## Rule of thumb

> Never re-run a command "just to retry" if it returned `E_DESTRUCTIVE`,
> `E_EMPTY_SELECTOR`, or `E_EXEC_DISABLED`. The user did not authorize
> the action; surface it instead.
