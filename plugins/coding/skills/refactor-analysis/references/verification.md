# Proof ladder

The card's **Proof** field names a rung. This skill names it; the executor runs it. Each
rung answers one question — pick by the question, not by habit.

| Rung | Question it answers | Name it when |
|---|---|---|
| Characterization tests | what does the code do today? | the target is under-tested, or the move touches behavior no test pins |
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

## Incremental landing

One move → its rungs plus the repo's dry gate → one `refactor:` commit. A behavior change
discovered mid-move lands as a separate `fix:` before or after, never inside. This is the
executor's contract; the analysis orders the cards so it can be followed.
