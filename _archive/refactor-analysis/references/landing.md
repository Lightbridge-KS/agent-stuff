# Landing

The executor's contract. The analysis ends in cards; when the user says *apply*, the same
session usually lands them. The card is the plan: its **Preserve** field is the input, its
**Proof** field names the rungs, [verification.md](verification.md) holds the techniques.
Nothing below starts before the pick.

## Before the first move

1. **Sync.** The checkout is clean and at the remote head — another session may have
   landed work since the analysis. Re-read every file a card touches; a card written
   against stale code is re-proposed, not forced.
2. **Baseline.** Record what *same* will be measured against: the full list of test names
   (per platform when there are several), the counts, and any seeded-run tallies (fuzz,
   differential). Save them outside the tree.
3. **Tracker** (broad mode). Write it as its own commit, staged by path, before the first
   move — nothing else rides in it.

## Per card

1. **Preserve → Pin.** For each Preserve item, name the test that would fail if it broke.
   Unsure → break it on purpose and run the suite. Nothing red → write the pinning test
   first and run it against the *old* code: a pinning test passes on both sides; a test
   that passes only after the move documents a change, not a preservation. Restore the
   mutation byte for byte.
2. **Move.** A module extraction lands as two commits: the logic diff inside the file, then
   the pure move behind the facade ([moves.md](moves.md), *Extract Module behind a Facade*).
3. **Prove.** Run the card's rungs with the techniques that fit. Every new test and every
   new fitness test gets a mutation check of its own: plant the violation, watch exactly
   that test go red, restore.
4. **Gates.** The repo's dry gate on every card; its live and long gates when the card
   touches what they cover (network code → live; a parser → fuzz and corpus).
5. **Docs in the same commit.** The structure doc's tree and its "where a change lands"
   rows, marked *(amended)*; a new fitness test gets its invariant row.
6. **One commit per card** (`refactor:` or `test:`), staged by path. Tick the tracker box
   with the SHA and the evidence as each lands — never "(this commit)".

## Behaviour found mid-move

A bug, a delta on malformed input, a validation that drifted: never inside a `refactor:`
commit. It lands as a separate `fix:` before or after, with the test that failed before the
fix — or, when someone else owns that behaviour, it stops and asks. The commit body names
the delta; the pass summary lists behaviour changes first.

## After the last card

- **Replay.** Each commit on its own (`git archive` into a scratch dir) analyses clean and
  passes with the expected count.
- **Push only when asked.** Then set the tracker `status: complete` and ask whether to
  prune it — the verdicts survive the prune (SKILL.md, *Handoff*).
- **Summarise** for whoever was not in the session: behaviour changes, then moves, then
  tests added, then docs; name who must hear of an API that can now throw.

## Pitfalls seen

- `git commit` takes everything staged: renames staged with `git mv` rode along in the
  tracker commit. Stage by path.
- `git stash` leaves untracked files behind; to run a new test on old code, stash only the
  paths the move touched, not the tree.
- A gate ten times slower than before was the machine sleeping, not the code. Check the
  power log before chasing a regression.
