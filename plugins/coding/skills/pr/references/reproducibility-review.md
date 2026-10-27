# Reproducibility review before committing

Use for Codex commits containing maintained code or durable repository
documentation. Follow the scope and exploratory exceptions in
`reproducible-codebase` and `write-for-the-clone`. A review does not authorize
committing or pushing.

## Prepare the candidate

Run modifying checks before the review. Stage only the intended files or hunks;
preserve unrelated staged and unstaged work. If the index includes unrelated work,
isolate the authorized candidate without discarding that work before proceeding.

Record the expected parent revision and comparison base. For a normal commit,
the base is `HEAD`; for an initial commit, use an empty tree created with
`git hash-object -w -t tree --stdin` and empty stdin. An amend compares against
the parent of the commit being replaced. Capture the staged tree with
`git write-tree`; include intended new files before taking this snapshot.

The reviewer uses the resulting immutable objects, not the changing index or
working tree. Keep the packet in the session; no committed review report is needed.

## Dispatch with fresh context

Resolve the installed `reproducibility-reviewer` agent and both skill files. Spawn
the named agent without conversation history (`fork_turns = "none"` where exposed).
Use its pinned model and reasoning settings. Do not substitute a full-history fork
or silently fall back to self-review.

Supply only:

- Repository location, comparison base, and candidate tree ID.
- Intended outcome, approved constraints, and relevant design references.
- Resolved paths to both skill files.

Avoid supplying the author's conclusions about why the implementation is correct.
The reviewer inspects only and returns its findings to the main agent. Wait for
completion. Missing dependencies, unsupported fresh dispatch, or partial coverage
leave the review incomplete: report the gap and pause before committing.

## Resolve and verify

Evaluate each finding against evidence. Record a short disposition in the session:
fixed, dismissed with evidence, deferred with reason, or human decision needed.
Make routine fixes autonomously. Escalate choices that require human judgment;
findings do not automatically require human approval. If a disagreement repeats
without new evidence, surface the specific unresolved decision.

After fixes or modifying checks, capture a new candidate. Request review of the
affected changes with the previous review and dispositions, preserving coverage
of the full candidate. A prior result alone never covers a changed base or tree.

Before committing, verify the parent/base and index still match the reviewed
candidate. After committing, compare the resulting commit tree to that candidate
before pushing. If hooks changed it, review the actual committed tree and resolve
findings before delivery; do not claim it was the originally reviewed candidate.

Keep tests and review distinct in the final report. Review completeness describes
coverage, not a guarantee that no defects remain.
