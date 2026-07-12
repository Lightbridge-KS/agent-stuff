---
summary: Deferred design for syncing ~/.lightbridge across machines via a private GitHub
  repo — what gets committed vs stays local, the identical-paths assumption that makes
  project-keys transfer, bootstrap flow for a new machine, and the doctor nuance it needs.
read_when:
  - setting up ~/.lightbridge on a second machine, or asked to sync lightbridge config
  - changing the project-key encoding or the root staleness contract (this design depends on both)
  - extending `lightbridge doctor` (the not-on-this-machine vs stale distinction lives here)
---

# ~/.lightbridge multi-machine sync (deferred design)

*Status: designed 2026-07-12, **deferred** — KS currently runs one machine. Pick this up
when a second machine arrives. Context: the local-scope migration
([`../archive/lightbridge-local-scope.md`](../archive/lightbridge-local-scope.md)) moved all
per-project config into `~/.lightbridge/projects/<key>/config.toml`, which means config no
longer travels with a repo clone — this design is the recovery for that accepted trade-off.*

## Design

`git init ~/.lightbridge` itself, private GitHub remote (suggested: `lightbridge-state`,
personal account, not the orgs). Commit **config only**; state and the machine registry
stay local via `.gitignore`:

```
~/.lightbridge/                    ← git repo, private remote
├── .gitignore
├── README.md                      ← committed
├── repos.toml                     ← IGNORED — machine-specific by design
└── projects/<project-key>/
    ├── config.toml                ← COMMITTED — the payload
    └── handoffs/                  ← IGNORED — conversation-derived, stays local
```

```gitignore
# machine-specific: its PRESENCE is the per-machine opt-in for repo-links
repos.toml
# conversation-derived state — private to each machine
projects/*/handoffs/
```

Why those two stay local:

- **`repos.toml`** — its *presence* is the per-machine opt-in for `[repo-links]`
  resolution. Synced, a fresh machine would opt in with paths that don't exist yet and
  spray WARNING lines into every session. Authoring it per machine keeps opt-in deliberate.
- **`handoffs/`** — conversation-derived; "private GitHub is probably fine" is the wrong
  bar for chat-derived text. Excluding is the safe default; flipping later is one gitignore
  line.

## The load-bearing assumption

Project-keys encode **absolute paths**. Synced config only lights up on machine B if the
repos live at the **same paths** — same `/Users/kittipos` home, same workspace layout.
All-Mac, same-username, mirrored layout → keys transfer verbatim, zero re-setup. If a
machine ever diverges (Linux home, different username), build `lightbridge relocate`:
re-key an entry by consulting its `root`. Do not build it before that machine exists.

## Flows

```
MACHINE A                                 MACHINE B (new)
─────────────────────                     ──────────────────────────────
edit config / bootstrap a repo            git clone <private> ~/.lightbridge
        │                                 author ~/.lightbridge/repos.toml
git commit && git push          ──────►   clone work repos to the SAME paths
                                          git pull; lightbridge doctor
                                          → hooks light up, zero re-setup
```

- **Sync is plain git**, manual and low-frequency. Do NOT wire it into a SessionStart
  hook — network latency in every session start for a file that changes weekly is a bad
  trade. If it becomes a chore, add a `lightbridge sync` subcommand (pull --rebase, add,
  commit, push — ~20 lines).
- **`doctor` nuance (build with this design):** on machine B, a config whose `root`
  doesn't exist is ambiguous — *moved repo* (true rot) vs *not cloned here yet* (expected).
  Readers are already safe either way (a hook only fires inside the repo, so un-cloned
  projects are inert). Downgrade doctor's `stale` to a `not-on-this-machine` note when the
  whole parent tree (e.g. `~/my_ramaai`) is absent; keep `stale` for the suspicious case.

## Why a dedicated repo, not dotfiles

Dotfiles repos drift public (one `gh repo edit --visibility` away); the sync cadence
differs (config churns with project work, dotfiles rarely); and the gitignore semantics
above are load-bearing — easiest kept correct in a repo with exactly one job.

## Caveat for the repo README

`git clean -xdf` inside `~/.lightbridge` deletes the ignored `repos.toml` and `handoffs/`.
List the ignored files explicitly in the README so this is survivable — and it is another
reason handoffs could graduate to committed if the loss ever bites.
