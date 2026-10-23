# Proof ladder

The card's **Proof** field names a rung. This skill names it; the executor runs it. Each
rung answers one question — pick by the question, not by habit.

| Rung | Question it answers | Name it when |
|---|---|---|
| Characterization tests | what does the code do today? | a Preserve item has no test that goes red when it is broken — found by mutation, not by feel; the new test must pass on the old code too |
| Regression on edge identities | do exact values, error order, and empty inputs survive? | a function-level move touches values or control flow |
| Differential run | are old and new indistinguishable? | a module-level move re-sequences logic — seeded cases through both paths, compare every output and every error |
| Contract / snapshot fixtures | are schema order, dtypes, reserved names unchanged? | a move touches a data contract or a physical schema |
| Architecture tests | did the edge actually disappear? | any module or package move — direct-import matrix (including type-only imports), transitive contracts, cycle check, a deliberately violating fixture that proves the gate bites |
| Installed-artifact run | does the built distribution still hold everything? | a package move or a re-export change — import from the built artifact outside the source tree |

Rungs compose: a package move usually names architecture tests **and** an installed run;
a schema-touching extraction names contract fixtures **and** a differential run.

## What each rung cannot prove

- A numerical parity test cannot prove import architecture.
- A fake adapter cannot prove native correctness.
- A source-tree import cannot prove the built artifact is complete.
- A green architecture test cannot prove behavior.

When the card's preserve-list spans more than one of these, the Proof field lists more
than one rung.

## Proof techniques

Repo-agnostic ways to show a rung. Each answers one question; a card usually combines
two or three.

| Technique | Shows | How |
|---|---|---|
| Baseline | what *same* means | before touching anything: full test names per platform, counts, seeded-run tallies — saved outside the tree |
| Test-name diff | a pure move changed no test | the same names before and after; only the tests a card deliberately regroups may differ, and the card says which |
| Mutation check | a test or fitness test bites | plant the violation (a forbidden import, a loosened limit, a rule removed), watch exactly that test go red, restore byte for byte |
| Old-code check | a new test pins rather than documents | run the new test against the pre-move code; it must pass there too |
| Pure-move diff | an extraction moved code without changing it | map the renames back, diff the old file's code lines against the union of the new files; the residue should be imports, visibility and formatter wraps |
| Per-commit replay | each commit is green alone | `git archive` each commit into a scratch dir, analyze and test; counts rise monotonically |
| Seeded identity | an order or a corpus held | identical tallies at the same seed before and after — a fuzz run that picks cases by index proves the fixture order with its counts |
| Equivalence script | two helpers produce the same thing | a throwaway script feeds the old and the new helper the same inputs and compares the bytes; run once, not kept |
| Ratchet both ways | an allowlist still gates | a planted passing entry fails the gate; an emptied list fails on the case it covered |

## Incremental landing

One move → its rungs plus the repo's dry gate → one `refactor:` commit. A behavior change
discovered mid-move lands as a separate `fix:` before or after, never inside. The full
executor's contract — baseline, Preserve → Pin, docs in the same commit, replay — is
[landing.md](landing.md); the analysis orders the cards so it can be followed.
