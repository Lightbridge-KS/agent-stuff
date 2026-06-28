# Error codes & exit codes

`error.code` strings are **public API** — they will not be renamed or
repurposed once shipped. Branch on `code`, not on `message`. Show the
`message` to the user; apply the `hint`.

## Code → exit code map

| Code | Exit | Category | Agent action |
|---|---|---|---|
| (none — success) | 0 | success | proceed |
| `E_BAD_INPUT` | 1 | user error | re-read your own command, fix, retry |
| `E_HTTP_4XX` | 2 | Slicer-side | inspect `endpoint` + `message`; usually a bad arg |
| `E_HTTP_5XX` | 2 | Slicer-side | check `doctor`; often `/exec` disabled or volume invalid |
| `E_BAD_RESPONSE` | 2 | Slicer-side | Slicer returned malformed/empty data; see `hint` |
| `E_NOT_RUNNING` | 3 | network | **stop** — Slicer not reachable; surface to user |
| `E_NETWORK` | 3 | network | TCP/HTTP error other than refused; check `--url` |
| `E_TIMEOUT` | 3 | network | exceeded `--timeout`; consider raising it |
| `E_CONFIG` | 4 | config | bad TOML or env var; inspect `slicer-cli config show` |
| `E_EXEC_DISABLED` | 5 | gating | **hard stop** — do not auto-pass `--i-understand-the-risk` |
| `E_DESTRUCTIVE` | 6 | safety | **hard stop** — user did not authorize destruction |
| `E_EMPTY_SELECTOR` | 6 | safety | **hard stop** — empty `<id>` was passed; ask the user |
| `E_NOT_IMPLEMENTED` | 7 | phase | **hard stop** — `hint` names the phase that ships it |

## Hard-stop codes (do NOT retry)

When you see one of these, surface the failure verbatim to the user and
ask before doing anything else:

- `E_DESTRUCTIVE` — adding `--confirm` is the user's call, not yours.
- `E_EMPTY_SELECTOR` — substituting an id you guessed is dangerous.
- `E_NOT_IMPLEMENTED` — emulating via `api raw` or `exec` is the user's call.
- `E_EXEC_DISABLED` — auto-flipping `--i-understand-the-risk` defeats the gate.

## Retry-safe codes

These can be retried after a fix:

- `E_BAD_INPUT` — fix the argument and retry.
- `E_TIMEOUT` — retry once with a higher `--timeout`.
- `E_NETWORK` — sometimes transient; one retry is fine, then surface.

## Codes that need a diagnosis step

- `E_HTTP_5XX` from `scene save`, `dicom pull`, `markup line`, or `exec` →
  almost always means `/slicer/exec` is disabled. Run `doctor`; the
  `power-tool-endpoint` probe will confirm. If disabled, the user must
  enable `/exec` in Slicer's WebServer module settings — you cannot fix
  this from the CLI side.
- `E_BAD_RESPONSE` on `render slice` / `render threed` with a hint
  containing `GALLIUM_DRIVER=llvmpipe` → headless Linux without GPU. The
  user must `export GALLIUM_DRIVER=llvmpipe` *before* launching Slicer.
- `E_NOT_RUNNING` → the WebServer module isn't started. Tell the user to
  open Slicer → *Welcome* module → search "Web Server" → click **Start
  server**.

## How errors look on the wire

```json
{
  "ok": false,
  "error": {
    "code": "E_EXEC_DISABLED",
    "message": "exec is disabled by configuration",
    "hint": "pass --i-understand-the-risk or run: slicer-cli config set exec.enabled true",
    "endpoint": "/slicer/exec",
    "http_status": null
  }
}
```

`hint` is human-readable guidance — quote it back to the user when
surfacing the failure. `endpoint` is the underlying Slicer route the call
was about to hit (or did hit).
