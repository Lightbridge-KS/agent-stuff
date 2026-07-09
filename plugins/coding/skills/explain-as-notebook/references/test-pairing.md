# Pairing unit tests as interactive examples

Opt-in branch of `explain-as-notebook` — read only when the user asked for it. Fold tests
in *in addition to* the normal mock define→run→show cells — never as a replacement.

1. **Locate the tests.** Look for `tests/test_<module>.py`, `test_<name>.py`, or a
   `Test<ClassName>` class. Match a test function to a decomposed symbol by the symbol name
   appearing in the test body. Cite the test file and function name in the markdown. If no
   tests are found, say so in one line and skip — don't invent them.
2. **Placement.** After a function's full decomposition, add a markdown subsection
   `#### Tested behavior (from <test_path>)`, then one `#####` sub-section (or one code cell)
   per test function. Test cells trail the decomposition; they don't interleave with it.
3. **assert → show.** Convert each `assert` into *visible* output:
   - Predicate asserts (`assert p.search(x)` / `assert not p.search(y)`) → one dict/table of
     `input → bool(actual)` so matches and non-matches appear side by side. The `bool()`
     wrapper is load-bearing — a raw match object or `None` prints ugly.
   - Value asserts (`assert f(x) == v`) → an `input | actual | expected | ok` table with
     `ok = actual == expected` computed live.
4. **Keep expected visible.** Put the test's expected outcome in an inline comment
   (`# expect: match` / `# expect: ""`) beside each case, so the reader compares expected
   vs. live actual without rerunning anything.
5. **Exceptions stay live, never abort.** For `pytest.raises(E)` tests, use
   `try/except E as e: print(e)` with an `# expect: E` comment — AND print an explicit
   `UNEXPECTED` marker in the no-raise path, so a regression (the call silently stops
   raising) shows up instead of looking like success. For environment-dependent raises (a
   missing optional dependency/backend), show *this machine's* real behavior — never fake
   the dependency; optionally walk the branch to show *why* it raised.

Granularity: one cell per test function, sub-grouped by the distinct fixtures inside it
(a test that builds two unrelated patterns → two labelled dicts in the one cell).
