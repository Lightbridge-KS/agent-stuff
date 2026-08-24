---
name: llm-keys
description: >-
  Run inference with the user's personal LLM API keys — and manage them — via the
  `lb key` verbs (~/.lightbridge/keys.toml + secrets.toml). Use when a task needs a
  user-level API key (OpenAI, Anthropic, Gemini, llama-cloud: image gen, OCR, document
  parsing, general inference), when an *_API_KEY env var is missing, or when asked to
  add, list, rotate, or audit personal keys. Values are injected-only: never read,
  print, or ask for a key value. Per-project config belongs to lightbridge-config.
metadata:
  version: "2026-08-24"
---

# LLM keys

Personal LLM API keys live in two user-level files: **keys.toml** — the catalog you
may read (name, provider, env var, scope) — and **secrets.toml** — the values you must
never read. There is no `lb key get`; the one path to a value is `lb key run`, which
injects it into a child process's environment and execs. That absence is the contract:
a key value must never enter your context, your output, or a file you write.

**The naming rule.** Keys are named per *scope*, not per provider — `openai-personal`,
`openai-image-gen`, `llama-cloud` — so several keys per provider is normal. Each entry
declares the env var it injects; scripts just read standard variables
(`OPENAI_API_KEY`, `LLAMA_CLOUD_API_KEY`) and stay ignorant of the scheme.

## Run something that needs a key

```bash
lb key ls                        # 1. the catalog: which key fits the task (never values)
lb key run NAME -- CMD ARG...    # 2. inject NAME's env var into CMD's env and exec
```

The `--` is required; everything after it is the child command, untouched. The child's
exit code passes through (127 = the exec itself failed). Several keys at once:
`lb key run openai-image-gen,llama-cloud -- CMD` — refused if two selected names
inject the same variable.

```bash
lb key run llama-cloud -- uv run parse.py doc.pdf   # e.g. parse-to-md's LLAMA_CLOUD_API_KEY
```

Never `lb key run NAME -- env` or otherwise echo the injected variable — the point of
`run` is that the value bypasses you entirely.

## Add or rotate a key (human at the keyboard)

```bash
lb key add NAME --provider P --env VAR_NAME --scope "what it's for"
```

On a TTY this prompts for the value hidden (the human types or pastes it — never
supply a value yourself, never accept one into the conversation); piped stdin works
for `pbpaste | lb key add ...`. Re-adding an existing name is refused: **rotation is
`lb key rm NAME` then `key add`** — values are write-only, there is no update verb.

## Inspect and audit

```bash
lb key ls            # catalog + ← NO VALUE markers; --json adds has_value booleans
lb key doctor        # valueless entries, orphan values, loose file mode; exit 1 on problems
lb status            # includes a one-line keys row
```

## Guardrails (one-time setup, by the human)

`secrets.toml` should be deny-listed in the agent harness so even a direct read is
refused, in `~/.claude/settings.json`:

```json
{
  "permissions": {
    "deny": ["Read(//Users/USER/.lightbridge/secrets.toml)"]
  },
  "sandbox": {
    "network": {},
    "filesystemReadDeny": ["~/.lightbridge/secrets.toml"]
  }
}
```

(Adapt to the settings file's existing shape — the two entries are the point: a
permission deny for the Read tool, and a sandbox read-deny next to the `.env*` ones.)
The file is created 0600 by `lb key add`; `lb key doctor` flags a loosened mode.

## Source of truth

Design + rationale (why no read verb, why a plain 0600 file, exit 127):
`docs/lightbridge/adr/0003-personal-key-management.md` in agent-stuff. The user-level
`.lightbridge` tree and its other files: the `lightbridge-config` skill.
