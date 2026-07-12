# repo-links-inject

A **`SessionStart`** hook for **Claude Code and Codex** that injects a repo's resolved
cross-repo links into the agent's context automatically — so it knows where the upstream
counterpart, the live test service, or the OSS reference clone lives on *this* machine,
before touching any code. Replaces hand-maintained path lists in `CLAUDE.local.md` with
names that are **resolved and verified on every session start**.

The hook logic is agent-neutral: it reads `cwd` on stdin and emits the shared
`hookSpecificOutput.additionalContext` envelope that both agents consume. Only the
*registration* differs per agent (see below); `bin/install.py --hooks` renders both.

It is **opt-in twice**, which makes one global registration safe everywhere — both layers
are user-level; nothing lives inside the repo:

1. **Per project** — only fires for projects whose user-level lightbridge config
   (`~/.lightbridge/projects/<project-key>/config.toml`, resolved by
   [`scripts/lightbridge`](../../scripts/lightbridge)) declares a `[repo-links]` section.
   Links are logical *names*, never paths.
2. **Per machine** — names resolve through the personal `~/.lightbridge/repos.toml`
   registry. **No registry file → completely silent.**

It pairs with [`scripts/repo-links`](../../scripts/repo-links): the script is the
deterministic core (the agent can also run it by hand — `--check` audits a repo's links
on demand), the hook is the thin wiring.

## Behavior

```
SessionStart → cwd
  repo root = git toplevel of cwd (cwd itself if not a git repo)
  read ~/.lightbridge/projects/<key>/config.toml   none? / malformed? → exit 0, silent
  read [repo-links] section              no section / enabled=false → exit 0, silent
  parse [[repo-links.link]] entries      zero declared?         → exit 0, silent
  read ~/.lightbridge/repos.toml         file absent?           → exit 0, silent
    registry unreadable / no [repos]?    → inject ONE warning line (rot must show)
  resolve each name → path, verify it exists on disk
  → emit additionalContext:
      - name → /abs/path (role) — note          for each resolved link
      - name: WARNING — …                        for dead names / stale paths
  a stray pre-migration <repo>/.lightbridge/config.toml (no longer read)
      → one-line deprecation warning appended to the context
```

Warnings are payload, not errors — the hook always exits 0 and never blocks a session.
Paths are tilde-expanded but not `resolve()`d (symlinks render as written).

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

Merge the printed `SessionStart` block into user-level `~/.claude/settings.json` (if
`docs-index-inject` is already registered, append this hook's command object to the same
group's `hooks` array):

```jsonc
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "/abs/path/to/agent-stuff/hooks/repo-links-inject/hook.py" }
        ]
      }
    ]
  }
}
```

### Codex

Merge the printed block into `~/.codex/hooks.json` (or the inline `config.toml` form),
then trust it via `/hooks`.

## 2. Opt in (per project, user-level)

`lightbridge path` prints where the project's config lives (never inside the repo):

```toml
# ~/.lightbridge/projects/<project-key>/config.toml
root = "/abs/path/to/repo"  # staleness marker for `lightbridge doctor`
[repo-links]              # presence of this section = opt in
enabled = true            # optional; default true. MUST precede the first link —
                          # TOML attaches later keys to the last [[table]] otherwise.
[[repo-links.link]]
name = "example-service"  # required; logical name, resolved via the personal registry
role = "upstream"         # optional; free-form (upstream, oss-reference, live-test-service, …)
note = "Why this repo matters when working here"  # optional
```

## 3. Register names (per machine, never committed)

```toml
# ~/.lightbridge/repos.toml
[repos]
example-service = "~/work/example-service"   # ~-relative or absolute
```

One central file per machine: when a repo moves, one edit fixes every project that
links to it.

## Verify

```sh
echo '{"cwd":"/path/to/opted-in/repo","hook_event_name":"SessionStart"}' \
  | uv run hooks/repo-links-inject/hook.py
```

Expected: a JSON envelope whose `additionalContext` contains the `Linked repos` map.
An un-opted-in directory prints nothing. To audit links without a session:
`uv run scripts/repo-links/repo_links.py --start /path/to/repo --check`.
