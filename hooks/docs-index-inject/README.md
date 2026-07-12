# docs-index-inject

A **`SessionStart`** hook for **Claude Code and Codex** that injects a project's docs index
into the agent's context automatically — so it knows which docs exist, and *when* to read
them, before writing any code. No manual "run docs-index first" step.

The hook logic is agent-neutral: it reads `cwd` on stdin and emits the shared
`hookSpecificOutput.additionalContext` envelope that both agents consume. Only the
*registration* differs per agent (see below); `bin/install.py --hooks` renders both.

It is **opt-in per project**: registered once in your user settings, it only fires for
projects whose user-level lightbridge config — `~/.lightbridge/projects/<project-key>/config.toml`,
resolved by [`scripts/lightbridge`](../../scripts/lightbridge); nothing lives inside the
repo — declares a `[docs-index]` section. Projects with no docs — or a `docs/` used for a
website (Docusaurus/mkdocs/Quarto) — get nothing. That makes one global registration safe
across every project.

It pairs with [`scripts/docs-index`](../../scripts/docs-index): the script is the
deterministic core (the agent can also run it by hand), the hook is the thin wiring.

## Behavior

```
SessionStart → cwd
  repo root = git toplevel of cwd (cwd itself if not a git repo)
  read ~/.lightbridge/projects/<key>/config.toml   none?      → exit 0, silent (not opted in)
  read [docs-index] section              no section / enabled=false → exit 0, silent
  build index of <repo>/<dir>            (skipped if the dir is missing)
    (explicit summary/read_when only — no description fallback)
  index the `include` files at repo root (default CONTEXT.md / CONTEXT-MAP.md; missing skipped)
  nothing annotated at all?              → exit 0, silent
  else → emit additionalContext with the docs map + a "Domain context (repo root)" group
         (docs without a summary are dropped from the listing but counted
          in a footer line, so the map never silently reads as complete)
  a stray pre-migration <repo>/.lightbridge/config.toml (no longer read)
         → one-line deprecation warning appended to the context
```

Unlike the CLI, the hook does **not** fall back to the `description` key, so website
frontmatter (which commonly has `description`) is never surfaced even in an opted-in repo.
Because the `include` files live outside `dir`, a repo with a `CONTEXT.md` but no docs dir
still gets a map. It fails open and quiet on any error (missing/malformed config, missing
source).

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

## 2. Opt in (per project)

For each project where you want the index injected, add a `[docs-index]` section to its
user-level config — `lightbridge path` prints where it lives (never inside the repo):

```toml
# ~/.lightbridge/projects/<project-key>/config.toml
root = "/abs/path/to/repo"  # staleness marker for `lightbridge doctor`
[docs-index]              # presence of this section = opt in
enabled = true            # optional; default true. Set false to disable without deleting.
dir = "docs"              # docs directory, relative to repo root
exclude = ["archive", "research"]
include = ["CONTEXT.md", "CONTEXT-MAP.md"]  # extra root-level files (this is the default)
```

`include` lists files **outside** `dir` (relative to the repo root) to index too. It
defaults to `["CONTEXT.md", "CONTEXT-MAP.md"]` — the domain-modeling glossary and context
map — so they surface with no extra config when present. Set `include = []` to suppress them.

If a repo's `docs/` is a website, point `dir` at your agent-facing docs instead
(e.g. `dir = "agent-docs"`), or simply omit the `[docs-index]` section.

`.lightbridge` is a personal, tool-agnostic config namespace (spec: the `lightbridge-config`
skill); the hook only reads its `[docs-index]` section and ignores everything else.

## Verify

```sh
# from a repo whose lightbridge config has [docs-index] + annotated docs:
echo '{"cwd":"'"$PWD"'","hook_event_name":"SessionStart"}' | uv run hook.py
```

You should see a JSON object with `hookSpecificOutput.additionalContext` containing the
index. A project without the `[docs-index]` section prints nothing and exits 0.
