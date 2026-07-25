---
summary: Settled design for `lb mv OLD NEW` (CLI v0.4) — the repo move/rename repair verb.
  One command performs the filesystem move (when OLD exists) and repairs every path-keyed
  artifact in ~/.lightbridge — project-key dirs, `root` markers, repos.toml entries — with
  uniform prefix semantics for parent-dir moves, a TTY confirmation + `--yes` guard, and a
  verifiable idempotent re-run contract. Resolved 2026-07-25 by grilling.
read_when:
  - implementing or changing `lb mv` (mode detection, guard, prefix rewrite, collisions)
  - a repo tracked by ~/.lightbridge is being moved or renamed
  - changing the project-key encoding, the `root` staleness contract, or doctor's stale repair
---

# lightbridge CLI — `lb mv` (v0.4 design)

> Source: grilling session (KS + Claude) · Date: 2026-07-25 · Mode: Design · Surface: CLI
> See also: [CLI surface design](./lightbridge-cli-design.md) · [multi-machine sync (deferred)](./multi-machine-sync.md) · canonical spec: `plugins/lightbridge/skills/lightbridge-config/references/catalog.md`

Everything in `~/.lightbridge` is keyed by absolute repo path: `projects/<key>/` (config +
handoffs + plans), the `root =` staleness marker inside each config, and `repos.toml`
entry paths. Moving or renaming a repo breaks all three — and the first breaks *silently*
(new sessions compute the new key, find nothing, hooks quietly stop injecting).
`[repo-links]` consumers survive by design (logical-name indirection); only the pointers
need repair. `lb mv` is that repair, plus the move itself, in one deterministic verb.

## Cheat Sheet

```bash
lb mv OLD NEW             # move/rename a repo (or parent dir) and repair all bookkeeping
lb mv OLD NEW --dry-run   # print the blast-radius plan, change nothing, exit 0
lb mv OLD NEW --yes       # skip the TTY prompt — agents: only under explicit human instruction
lb mv OLD NEW --json      # machine-readable plan + result
```

Explicit path args; cwd is ignored (unlike the cwd-resolving verbs). Exit codes follow
the CLI taxonomy: `0` ok (incl. verified idempotent no-op) · `1` refused · `2` usage.

## Mode detection

| OLD | NEW | Behavior |
|---|---|---|
| exists | absent | **Move mode:** validate → `mv` → bookkeeping |
| absent | exists | **Repair mode:** bookkeeping only (after a manual move) |
| both exist (distinct) | | Hard error — print what's at each path; no heuristics |
| neither exists | | Hard error |
| samefile (case-only rename on APFS) | | Valid — treated as move mode |

If move-mode `mv` succeeds but bookkeeping then fails, the filesystem is exactly the
repair-mode state — re-running the same command converges. The command is its own
recovery.

## The guard

- **TTY:** print the blast-radius plan, then `proceed? [y/N]`.
- **Non-TTY without `--yes`:** refuse, exit 1, message teaches the flag.
- **`--yes`:** proceed non-interactively. Its help text and the pre-flight banner both
  state: *agents pass this only when the human explicitly instructed this move.*

This is the CLI's first exception to the "nothing that needs a TTY" non-goal — granted
because `mv` is the CLI's first destructive verb (it touches the filesystem outside
`~/.lightbridge`). The non-interactive path remains fully functional, so the two-audience
rule holds: the agent's experience is unchanged refusal-teaches-the-flag.

## Uniform prefix semantics

No repo-vs-parent distinction — the operation is prefix-based over normalized paths:

```
for every projects/<key>/config.toml:
    root == OLD  or  root under OLD/   →  re-key dir + rewrite root
for every repos.toml entry:
    path == OLD  or  path under OLD/   →  rewrite path
plus the filesystem mv of OLD itself (move mode)
```

A single-repo move is the one-match case. A parent-dir move (`lb mv ~/my_ramaai/X ~/Y`)
re-keys every project beneath it in one shot. The confirmation prompt and `--dry-run`
list every affected project key and registry entry — the blast radius is always shown
before anything changes.

## Destination collisions in `projects/`

State is path-keyed too, so `projects/<new-key>/` may already exist (e.g. a handoff
written at the new path before the repair ran):

- **New-key dir holds state only (no `config.toml`):** merge — move the config in, union
  the state files. A true filename collision hard-errors rather than overwrite either
  side (state filenames are timestamped, so this should not occur).
- **New-key dir holds its own `config.toml`:** hard error. Two configs claiming one
  project is a human judgment; the message names both paths and suggests the next move
  (diff, delete one, re-run).

## Rewrite policy — match normalized, rewrite surgically

- **Matching** normalizes both sides via `expanduser().resolve()` — consistent with
  `project_key`, and it makes `~`-style and absolute spellings of the same repo match.
  (This pins down a pre-existing asymmetry: doctor compared with `expanduser()` only.)
- **Rewriting** is a targeted line edit preserving each entry's hand-authored style:
  a `~`-style path stays `~`-style when the new path is still under home; quoting,
  comments, and ordering survive. Same temperament as `enable`/`disable` ("a line edit —
  comments survive"). The `root =` line gets the same treatment (machine-written,
  always absolute — trivial case).

## Other harnesses' path-keyed state

`~/.claude/projects/<old-key>` (session history, auto-memory) strands on a move exactly
like lightbridge config. `lb mv` **detects and reports** it — an informational line with
the old and new key names — but **never touches** another tool's namespace. Migration
stays a deliberate human/agent step. Escape-valve flag only if this ever bites.

## Re-run contract

Idempotent success (exit 0, "already consistent") **only when the completed target state
is verifiable**: no lightbridge reference to OLD remains, **and** at least one correctly
keyed config — or a registry entry — sits **at or under NEW**. OLD entirely unknown to
lightbridge, with nothing settled under NEW, is a hard error (typo protection, consistent
with the no-heuristics rule).

"At or under" rather than "at", because Decision 4's uniform prefix semantics demand it: a
parent directory has no config of its own — its repos' configs live one level down — so
checking NEW's own key verified repo-root moves only, and made a *completed* prefix move
re-run as a typo error ([#17](https://github.com/Lightbridge-KS/agent-stuff/issues/17)).
The correctly-keyed requirement is what proves the re-keying ran, rather than merely that
repos happen to live under NEW.

**The limit, accepted deliberately.** In repair mode OLD is gone from both the filesystem
and lightbridge, so a completed move and a typo'd OLD against a populated NEW are
*indistinguishable from the final state alone* — the information needed to tell them apart
no longer exists. Widening the evidence therefore widens false no-ops. The trade is bounded
and was taken knowingly: it applies to repair mode only (every other refusal — OLD present
but untracked, neither path exists, both exist and differ — is unaffected), and a false
no-op **mutates nothing**; the cost is a wrong exit 0. The message names how many
references were found, so a typo is visible in the output rather than silent.

## Decisions (resolved 2026-07-25, KS — grilling session)

1. **`mv` performs the filesystem move when OLD exists** — the partial-failure objection
   dissolves because a re-run converges (see Mode detection); bookkeeping-only repair
   mode still exists automatically. One command, no "prepare the move" phase.
2. **Interactive guard: TTY prompt + `--yes`** — KS wants a human speed bump on the
   CLI's first destructive verb; the agent path stays non-interactive with an explicit
   only-under-human-instruction warning. First (documented) exception to the
   interactive-prompts non-goal.
3. **Ambiguous states hard-error, no heuristics** — both-exist and neither-exist refuse
   with facts, except the samefile case-only rename (a real need on case-insensitive
   APFS; `repos.toml` has had both `~/oss` and `~/OSS` spellings).
4. **Uniform prefix semantics** — one code path for repo and parent-dir moves; the
   confirmation list is the mitigation for a broad-prefix typo.
5. **Collision split: merge state, error on config** — punishing the *normal* late-repair
   flow with manual state shuffling would be worse; two configs is a genuine fork.
6. **Surgical line edits over canonicalization** — `repos.toml` is hand-authored;
   `lb repos add` is the styled write path, `mv` must not flatten the file.
7. **Note-only for `~/.claude/projects`** — another tool's contract-less namespace;
   one `if exists` check, zero write risk.
8. **Verified idempotence** — exit 0 only on provable completion, so agent retry loops
   terminate and typos still surface as errors. *Amended (#17):* proof is prefix-aware —
   anything correctly keyed at or under NEW, not NEW's own key — because the original
   wording silently excluded the parent-dir moves Decision 4 requires. Perfect
   discrimination is impossible once OLD is gone; see the Re-run contract for the bounded
   trade that buys.

## Non-goals

- Guessing where a repo went (filesystem scanning, basename/remote matching) — the
  human or agent supplies both paths; the tool stays deterministic.
- Writing to `~/.claude/`, `~/.codex/`, or any other harness's namespace.
- `lb relocate` / multi-machine re-keying — still owned by the
  [sync design](./multi-machine-sync.md); when built, `relocate` becomes sugar over
  `mv`'s internals.
- `doctor --fix` — doctor now *teaches* `lb mv` in its `stale`/`key-mismatch` messages
  instead of fixing anything itself.
