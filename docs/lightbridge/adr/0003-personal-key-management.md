---
summary: >-
  Decision to manage personal LLM API keys as a two-layer split — an agent-readable
  catalog (~/.lightbridge/keys.toml) and a 0600, deny-listed values file
  (~/.lightbridge/secrets.toml) — consumed only through injection-at-exec
  (`lb key run`). Adds the CLI-side lb_keys.py module and the `lb key` verb family;
  deliberately amends nothing in the frozen importer API and ships no read verb.
read_when:
  - changing keys.toml/secrets.toml's schema, the run injection semantics, or a doctor check
  - touching lb_keys.py, the lb key verbs, or the status keys line
  - tempted to add a `key get`/read verb, or to move keys constants into lb_resolve.py
  - wondering why key values live in a plain 0600 file rather than a keychain
---

# ADR 0003 — Personal LLM key management: catalog + injected-only values

Accepted 2026-08-24 (KS), after three consult rounds (injection model, store backend,
per-scope naming). Build: [`../progress/keys.md`](../progress/keys.md).

## Context

KS holds user-level LLM API keys (Anthropic, OpenAI, Gemini, llama-cloud) that belong
to no repository, scoped per purpose (general inference, image gen, document parsing).
AI coding agents should be able to *run* inference with these keys, but the keys must
never *transit the agent's context* — the threat model is accidental exposure (a
`cat`, an `env` dump, a value pasted into code), not an adversarial local user.
`~/.zshrc` exports fail this: every child process inherits them, so one innocent
`env` lands the value in a transcript.

## Decision

1. **Injection at exec, never read.** The agent's only path to a value is
   `lb key run NAME[,NAME...] -- CMD`: the value is fetched, placed in the *child*
   process's environment, and the process is exec'd (`execvpe` on POSIX; a
   `subprocess.run` fallback on Windows). The child's exit code passes through
   untranslated; a failed exec is **127** (the `env(1)` convention — a documented
   step outside the CLI's 0/1/2 taxonomy). There is **no `lb key get`** and no verb
   ever prints a value; `--json` shapes carry `has_value` booleans only. The absence
   of a read verb is the contract.
2. **Two-layer split.** `keys.toml` is the agent-readable catalog — one
   `[keys.<name>]` per key with `provider`, `env` (the variable `run` injects), and
   `scope` (what the key is FOR) — so an agent can discover *what inference
   capabilities exist* without touching a value. `secrets.toml` holds the values in a
   flat `[secrets]` table: written only through `write_secrets` (0600 open + `fchmod`
   repair), read only by `cmd_key_run`, and deny-listed in the agent harness
   (Claude Code permission deny + sandbox read-deny; snippet in the `llm-keys` skill).
3. **Per-scope naming.** Keys are named by purpose (`openai-personal`,
   `openai-image-gen`), not per provider; many keys per provider is the normal shape.
   Two catalog entries sharing one `env` is legal and not a doctor finding — only
   selecting both in a single `run` collides (refused there). Rotation is `rm` +
   `add`: values are write-once per name, so there is no update verb to leak through.
4. **Nothing joins the frozen importer API** (ADR 0001 §3). No hook reads keys, so
   `DEFAULT_KEYS`/`DEFAULT_SECRETS` and every reader live in the CLI-side
   `lb_keys.py` — the amendment rule ("a path-loading consumer genuinely needs it")
   is deliberately not met, and secrets access stays out of the path-loaded surface.
5. **Plain 0600 file over a keychain.** Chosen for the stated threat model: the
   guardrail's job is to turn an accident into a deliberate act, and a deny-listed
   0600 file does that with zero dependencies and full cross-platform portability of
   the *format* (mode enforcement is POSIX-only; `write_secrets` and the `bad-mode`
   doctor check are no-ops on Windows).

## Rejected alternatives

- **Shell-profile exports (`~/.zshrc`).** Every process inherits the value; the
  accidental-exposure case this ADR exists to close.
- **macOS Keychain backend.** Encrypted at rest, but macOS-only (the `.lightbridge`
  tree is otherwise portable), and `security find-generic-password -w` is itself one
  agent command away — the deny-rule guardrail does the equivalent work either way.
  Revisit if the threat model tightens.
- **1Password `op run`.** The industry shape this design mirrors, but a paid
  dependency + daemon for a problem a 40-line module closes.
- **A `key get`/`key set` read-write surface.** Symmetric CRUD is the habit that
  leaks: any read verb makes "show me the key" a one-liner an agent can be socially
  engineered into. Write-only values keep the failure mode deliberate.

## Consequences

- `lb key run NAME -- env` still prints the injected value — by design out of scope:
  that is a deliberate act, not an accident, and the policy is safe-enough, not
  zero-trust.
- The catalog's `env` field means scripts stay ignorant of the scheme — they read
  standard variables (`OPENAI_API_KEY`, `LLAMA_CLOUD_API_KEY`); which stored key
  fills the variable is the caller's choice of NAME.
- `secrets.toml` is the one exception to the "no secrets in the `.lightbridge`
  tree" hygiene rule; the lightbridge-config catalog records the amendment.
- keys/secrets are per-machine like the rest of `~/.lightbridge` (multi-machine sync
  deferred; see `../multi-machine-sync.md`).
