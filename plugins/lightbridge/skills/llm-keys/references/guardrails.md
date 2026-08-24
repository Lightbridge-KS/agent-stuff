# Guardrails — one-time harness setup (by the human)

`secrets.toml` is deny-listed in the agent harness so even a direct read is refused.
In `~/.claude/settings.json`, two entries do the work — a permission deny for the Read
tool, and a sandbox read-deny next to the `.env*` ones:

```json
{
  "permissions": {
    "deny": ["Read(//Users/USER/.lightbridge/secrets.toml)"]
  },
  "sandbox": {
    "filesystem": {
      "denyRead": ["~/.lightbridge/secrets.toml"]
    }
  }
}
```

(Adapt to the settings file's existing shape; substitute the real home path in the
`Read(...)` rule — permission rules don't expand `~`.)

## What the deny changes at runtime

The sandbox blocks even `stat()` on the file, and the `lb` verbs are built to degrade
rather than traceback (applied 2026-08-24, verified live):

- `lb key ls` / `lb key doctor` — still work from the catalog; a stderr note says value
  presence is unknown ("the guardrail working"), and doctor does **not** report the
  denial as a problem (exit stays 0 on a clean catalog).
- `lb key run` — refused with exit 1: the run itself needs to read the values file, so
  an agent's sandboxed shell cannot perform it. That is the intended shape — the agent
  asks the user to approve a sandbox-disabled invocation, so **every use of a key is a
  human-approved act**.
- `lb status` — unaffected (the dashboard never opens secrets.toml).

## File mode

`secrets.toml` is created `0600` by `lb key add` (and repaired on every rewrite);
`lb key doctor` flags a loosened mode with the `bad-mode` finding.
