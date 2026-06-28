# docs-index-inject

A Claude Code **`SessionStart`** hook that injects a project's docs index into the agent's
context automatically — so it knows which docs exist, and *when* to read them, before
writing any code. No manual "run docs-index first" step.

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

The hook is a self-contained `uv` script — no install step beyond `uv` itself. Register it
**once** in user-level `~/.claude/settings.json`. Print the ready-to-paste snippet (paths
already resolved for your checkout):

```sh
uv run bin/install.py --hooks
```

It prints a block like this — merge it into `~/.claude/settings.json`:

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

> The installer **prints** the snippet; it never edits your settings. Wiring a hook stays a
> deliberate, one-time choice.

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
