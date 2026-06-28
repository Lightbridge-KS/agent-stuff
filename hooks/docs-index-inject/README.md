# docs-index-inject

A **`SessionStart`** hook for **Claude Code and Codex** that injects a project's docs index
into the agent's context automatically — so it knows which docs exist, and *when* to read
them, before writing any code. No manual "run docs-index first" step.

The hook logic is agent-neutral: it reads `cwd` on stdin and emits the shared
`hookSpecificOutput.additionalContext` envelope that both agents consume. Only the
*registration* differs per agent (see below); `bin/install.py --hooks` renders both.

It is **opt-in per repository**: registered once in your user settings, it only fires in
repos whose `.lightbridge/config.toml` declares a `[docs-index]` section. Repos with no
docs — or a `docs/` used for a website (Docusaurus/mkdocs/Quarto) — get nothing. That makes
one global registration safe across every project.

It pairs with [`scripts/docs-index`](../../scripts/docs-index): the script is the
deterministic core (the agent can also run it by hand), the hook is the thin wiring.

## Behavior

```
SessionStart → cwd
  walk up for .lightbridge/config.toml   none?                → exit 0, silent (not opted in)
  read [docs-index] section              no section / enabled=false → exit 0, silent
  <repo>/<dir> missing?                  → exit 0, silent
  build index (explicit summary/read_when only — no description fallback)
  nothing annotated?                     → exit 0, silent
  else → emit additionalContext with the docs map
```

Unlike the CLI, the hook does **not** fall back to the `description` key, so website
frontmatter (which commonly has `description`) is never surfaced even in an opted-in repo.
It fails open and quiet on any error (missing/malformed config, missing source).

## 1. Enable once (per machine)

The hook is a self-contained `uv` script — no install step beyond `uv` itself. The canonical,
agent-neutral descriptor is [`hook.toml`](hook.toml); the installer renders it into each
agent's native registration form with the path resolved for your checkout:

```sh
uv run bin/install.py --hooks
```

> The installer only **prints** these blocks; it never edits your settings. Wiring a hook
> stays a deliberate, one-time choice.

### Claude Code

Merge the printed `SessionStart` block into user-level `~/.claude/settings.json`:

```jsonc
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command",
        "command": "/abs/path/to/agent-stuff/hooks/docs-index-inject/hook.py" } ] }
    ]
  }
}
```

### Codex

Codex reads hooks from **either** `~/.codex/hooks.json` **or** an inline `[hooks]` table in
`~/.codex/config.toml` — register in **exactly one** (Codex warns if both exist in one layer).
The `--hooks` output prints both forms; paste one:

```jsonc
// ~/.codex/hooks.json
{ "hooks": { "SessionStart": [ { "hooks": [ { "type": "command",
  "command": "/abs/path/to/agent-stuff/hooks/docs-index-inject/hook.py",
  "statusMessage": "Injecting docs index" } ] } ] } }
```

Then run **`/hooks`** in Codex to review and **trust** the hook — non-managed command hooks
don't run until trusted. Trust is recorded against the hook's *current hash*, so Codex
re-prompts for review whenever `hook.py` changes; re-trust after edits (or pass
`--dangerously-bypass-hook-trust` while iterating). The hook only consumes `cwd`, so it does
not depend on the session starting at a git root.

## 2. Opt in (per repo)

In each repo where you want the index injected, add a `[docs-index]` section to a committed
`.lightbridge/config.toml` at the repo root:

```toml
# .lightbridge/config.toml
[docs-index]              # presence of this section = opt in
enabled = true            # optional; default true. Set false to disable without deleting.
dir = "docs"              # docs directory, relative to repo root
exclude = ["archive", "research"]
```

If a repo's `docs/` is a website, point `dir` at your agent-facing docs instead
(e.g. `dir = "agent-docs"`), or simply omit the `[docs-index]` section.

`.lightbridge/` is a personal, tool-agnostic config namespace; the hook only reads its
`[docs-index]` section and ignores everything else.

## Verify

```sh
# from a repo whose .lightbridge/config.toml has [docs-index] + annotated docs:
echo '{"cwd":"'"$PWD"'","hook_event_name":"SessionStart"}' | uv run hook.py
```

You should see a JSON object with `hookSpecificOutput.additionalContext` containing the
index. A repo without the `[docs-index]` section prints nothing and exits 0.
