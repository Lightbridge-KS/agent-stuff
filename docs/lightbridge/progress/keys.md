---
summary: >-
  Progress tracker for the lb key build: personal LLM API key management as a two-layer
  split — agent-readable catalog (~/.lightbridge/keys.toml) + 0600 deny-listed values
  (~/.lightbridge/secrets.toml) — with injection-at-exec (`lb key run`) and deliberately
  no read verb. Milestones with commit SHAs; confirmed contracts; deferred items.
read_when:
  - resuming or continuing the lb key build (feat/lb-keys)
  - checking what the key-management effort shipped vs deferred
  - touching lb_keys.py, the key verbs, keys.toml/secrets.toml, or the status keys line
---

# lb key — progress

Authorized by the approved plan (2026-08-24, three consult rounds: injection model,
store backend, per-scope naming). ADR:
`docs/lightbridge/adr/0003-personal-key-management.md` (M5). Branch: `feat/lb-keys`.

The unlock: an AI coding agent can *use* a user-level LLM API key without ever
being able to *read* it accidentally — the agent's only verb is
`lb key run NAME -- CMD`, which injects the value into the child process env and
execs. There is no `lb key get`; the absence is the contract. The catalog
(keys.toml) stays agent-readable so the agent can discover *what* inference
capabilities exist without touching a single value.

## Milestones

- [ ] M0 — this tracker (plan contracts recorded)
- [ ] M1 — document model: `lb_keys.py` (constants, headers, KEY_NAME/ENV_NAME,
      tri-state readers, line surgery, `write_secrets` 0600, `secrets_mode_problem`,
      `audit`) + unit-test classes of `tests/test_lb_keys.py` + justfile entry
- [ ] M2 — catalog verbs: `lb key ls|add|rm` (wiring + `cmd_key_*` handlers) +
      CLI tests incl. 0600 and no-secret-on-output asserts
- [ ] M3 — `lb key run`: `--` guard, comma multi-name, env-collision refusal,
      POSIX execvpe / Windows subprocess fallback, exit-code passthrough, 127 on
      exec failure + tests
- [ ] M4 — `lb key doctor` + `lb status` keys line (+ `--keys` isolation flag) + tests
- [ ] M5 — docs & skill: ADR 0003, `llm-keys` skill (usage + deny-rule snippet),
      lightbridge-config SKILL.md + catalog.md amendments ("no secrets *except*
      secrets.toml"), scripts README, docstring/epilog, `__version__` → 0.7.0
- [ ] Gates: `bin/validate.py` + full `just test` green

## Confirmed contracts

- **No read verb** — no `lb key get`; no verb ever prints a value; `--json` shapes
  carry `has_value` booleans, never values. `load_secrets` (values) is called only
  by `cmd_key_run`.
- **Two-layer split** — keys.toml (metadata: `provider`, `env`, `scope` per
  `[keys.<name>]`) is agent-readable; secrets.toml (`[secrets]` flat name → value)
  is 0600 and deny-listed in the agent harness (Claude Code permission deny +
  sandbox read-deny — applied by the user, snippet ships in the llm-keys skill).
- **Per-scope naming** — `openai-personal`, `openai-image-gen`, `llama-cloud`;
  many keys per provider legal; two entries sharing one `env` is NOT a doctor
  finding (only a same-`run` selection collides).
- **Rotation is `rm` + `add`** — values are write-once per name; no update verb.
- **Nothing enters the frozen importer API** (ADR 0001 §3) — no hook reads keys;
  `DEFAULT_KEYS`/`DEFAULT_SECRETS` and every reader live CLI-side in `lb_keys.py`.
- **Exit 127 on exec failure** in `key run` — the `env(1)` convention, a
  documented step outside the 0/1/2 taxonomy; the child's own exit code passes
  through untranslated.

## Deferred (out of this effort)

- macOS Keychain (or other encrypted) backend — plain 0600 file chosen for the
  accidental-exposure threat model; revisit if the model tightens.
- Multi-machine sync of keys/secrets — per-machine like the rest of
  `~/.lightbridge` (see `docs/lightbridge/multi-machine-sync.md`).
- `getpass` confirmation re-prompt on `key add` — a typo'd paste surfaces at
  first use; acceptable for v1.
- Windows mode-bit enforcement — `write_secrets` chmod and the `bad-mode` check
  are POSIX-only.
