# repo-links

Resolve a repo's declared **cross-repo links** to verified local paths — so an agent
working in one repo knows where its neighbors (upstream counterpart, live test service,
OSS reference clone) live on *this* machine, without anyone committing personal paths.

Replaces the hand-maintained path list in a `CLAUDE.local.md`: names are declared once
per project, resolved per machine, and **verified on every run** — a dead name or stale
path surfaces as a WARNING line instead of rotting silently.

## The two-layer model

Both layers are user-level — nothing ever lives inside the repo:

```
~/.lightbridge/projects/<key>/config.toml  [repo-links]  PER PROJECT — logical names only, never paths
        │  resolved through                              (located via scripts/lightbridge)
        ▼
~/.lightbridge/repos.toml                  [repos]       PER MACHINE — name → path
        │  tilde-expand + verify the path exists
        ▼
one line per link, or a WARNING line when resolution fails
```

On a machine with no `~/.lightbridge/repos.toml`, the declared links simply don't
resolve (and the companion hook stays completely silent).

## Declaring links (per project, user-level)

`lightbridge path` prints where the project's config lives:

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

## The personal registry (per machine, never committed)

```toml
# ~/.lightbridge/repos.toml
[repos]
example-service = "~/work/example-service"   # ~-relative or absolute
```

One central file per machine: when a repo moves, one edit fixes every project that
links to it.

## Usage

```sh
repo_links.py                       # human map for the repo at CWD
repo_links.py --start path/to/repo  # resolve another repo's links
repo_links.py --json                # machine-readable (for hooks/tooling)
repo_links.py --check               # audit mode: exit 1 if anything is unresolved
repo_links.py --registry alt.toml   # nonstandard registry location
```

Human output:

```
Linked repos (.lightbridge [repo-links]):
- example-service → /Users/x/work/example-service (upstream) — Why this repo matters
- old-name: WARNING — not registered in ~/.lightbridge/repos.toml (add it there, or fix the name in the project's lightbridge config)
- gone-repo: WARNING — registered path /Users/x/work/gone does not exist (stale registry entry?)

When a task involves a linked repo, work with it at the absolute path above.
```

`--json` schema:

```json
{
  "config": "/abs/state/dir/<project-key>/config.toml",
  "registry": "/abs/expanded/repos.toml",
  "registry_found": true,
  "registry_error": null,
  "links": [
    {"name": "example-service", "role": "upstream", "note": "…",
     "path": "/abs/path", "status": "ok", "detail": null}
  ],
  "warnings": []
}
```

`status` per link: `ok` | `unregistered` | `relative-path` | `missing` | `not-a-dir`.

## Exit codes

- `0` — ran and rendered (warnings included; warnings are payload, not errors)
- `1` — `--check` only: at least one link unresolved
- `2` — nothing to read: no lightbridge config for the project, no `[repo-links]`
  section, or `enabled = false` (stderr names the next move)

## Notes

- Paths are tilde-expanded but **not** `resolve()`d — a symlinked path renders as you
  wrote it; existence checks follow symlinks, so a symlinked repo counts as resolved.
- Duplicate link names: first wins, with a warning. Entries missing `name` are skipped
  with a warning; other links still resolve.
- Pairs with [`hooks/repo-links-inject`](../../hooks/repo-links-inject) — a SessionStart
  hook that injects this map into agent context automatically. The hook imports this
  module as its single source of truth.
- Registered in the `.lightbridge` catalog: the `lightbridge-config` skill
  (`plugins/lightbridge/skills/lightbridge-config/references/catalog.md`).
