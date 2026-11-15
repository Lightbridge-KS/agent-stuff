---
name: change-review
description: "Review a candidate change — staged work, a branch, or a pull request — with fresh-context reviewer subagents across four lenses (correctness, reproducibility, spec, standards). Findings return to the main agent, which owns every decision. Use before committing durable work (the `pr` skill calls this) or when asked for a change review of a branch, a PR, or 'since X'. Claude Code and Codex."
metadata:
  version: "2026-11-15"
---

# Change review

An independent read of an immutable candidate. Reviewers inspect and report. The main
agent decides, fixes, verifies, and delivers. A review authorizes nothing: not a
commit, not a push.

Scope: maintained code and durable repository documentation. Scratch spikes, toys,
and playground work are out unless the caller asks.

## 1. Candidate

Reduce the request to two git objects. Reviewers read those objects, never the
working tree or the index.

| Request | Base | Candidate |
|---|---|---|
| Staged work (a commit about to be made) | `HEAD`; an empty tree for an initial commit; for an amend, the parent of the commit being replaced | `git write-tree` |
| Branch, or "since X" | `git merge-base <X> HEAD` | `HEAD^{tree}` |
| Pull request N | merge-base of the PR base and the fetched PR head | `<head>^{tree}` |

- Run modifying checks (formatters, lint fixes) before the snapshot.
- Staged work: stage only the intended files or hunks, new files included. Keep
  unrelated staged and unstaged work; isolate the candidate without discarding it.
- An empty tree: `git hash-object -w -t tree --stdin` with empty stdin.
- Stop here, before any dispatch, on a ref that does not resolve or an empty diff.
- Record both IDs. The packet and the findings stay in the session; no review report
  is committed.

## 2. Plan the review

**Lenses.** Assign every lens that applies. Report the others as skipped with a reason.

| Lens | Applies when | File |
|---|---|---|
| correctness | the change is not documentation-only | [correctness](references/lenses/correctness.md) |
| reproducibility | always, within the scope above | [reproducibility](references/lenses/reproducibility.md) |
| spec | a spec source resolves | [spec](references/lenses/spec.md) |
| standards | the repository documents how code or docs are written | [standards](references/lenses/standards.md) |

**Documentation-only** means no changed file is executed, parsed by a machine, or
loaded as agent instructions. Skill files, agent definitions, `AGENTS.md`,
configuration, and CI files are not documentation-only.

**Spec source**, first match: issue or ticket references in the branch name or commit
messages; a path or text the caller passes; a requirements document or tracker
milestone that names this work; an approved plan the caller holds. Fetch remote text
yourself and put it in the packet — a reviewer has no network authority. No source:
skip the lens as `no spec available`; ask the human only on a standalone review.

**Reviewers.** Split lenses between reviewers, never files: a reviewer that sees part
of a diff misses defects that cross files.

| Reviewers | Lens split |
|---|---|
| 1 — default | all assigned lenses |
| 2 | correctness / the rest |
| one per lens | at most four, never more than the assigned lenses |

You choose the count. Anchors, from `git diff --shortstat <base> <candidate>`: up to
about 400 changed lines → 1; up to about 1500 → 2; above → one per lens. A one-way-door
change (migration, deletion, published contract) moves up one row. State the count
and the reason in the report. The author tends to under-review its own change; when
in doubt, move up.

## 3. Dispatch

Spawn the installed reviewer agent with no conversation history. More than one
reviewer: dispatch them together and wait for all. The agent definitions are native
and not converted, so each harness has its own names. The agent files hold the exact
model and effort pins.

| Harness | Default tier | Documentation-only tier | Fresh context |
|---|---|---|---|
| Claude Code | `change-reviewer`, as its definition pins it | the same agent, with `model: sonnet` and `effort: high` passed at dispatch | Agent tool `subagent_type`; never a fork |
| Codex | role `change-reviewer-codex` | role `change-reviewer-codex-docs` | the selected role with `fork_turns = "none"` |

On Claude Code the agent registers as `change-reviewer` when this repository's
installer placed it, and as `coding:change-reviewer` when it came from the plugin
marketplace. Use whichever is registered; it is the same agent, not a substitute.

Codex role pins take precedence over spawn model/effort arguments, which can be
silently ignored. Select the role for the required tier; do not try to override it.
Fresh context excludes parent conversation history, but retains standing harness
and repository instructions.

The packet, and nothing else:

- Repository location; base and candidate object IDs.
- Intended outcome, approved constraints, relevant design references.
- Assigned lenses, each with the absolute path to its lens file, and the absolute
  path to [the reviewer contract](references/reviewer-contract.md). Resolve them from
  this skill's installed directory.
- Reproducibility lens: the absolute paths to the `reproducible-codebase` and
  `write-for-the-clone` skill files.
- Spec lens: the spec text, or its path.
- On a re-review: the previous candidate ID, and the prior findings with their
  dispositions.
- On a full review after a partial one: the prior findings with their dispositions,
  and no previous candidate ID.

Never supply your conclusions about why the change is correct. Never substitute a
full-history fork, a different agent, or your own review.

- **The agent is not registered or fails to dispatch:** report the gap and pause.
- **Only the documentation-only tier is unavailable:** use the default tier and say so.
- **The harness has no fresh-context subagent:** no review. Report `not reviewed`.

## 4. Collect

A return is complete only when its coverage says complete, its IDs match the packet,
and it has one section for each assigned lens. Otherwise the review is partial:
re-dispatch the missing lens once, then report the gap.

Keep findings under their lens. Do not merge or rerank across lenses — a change can
pass one and fail another, and the separation keeps one from masking the other.

## 5. Disposition

Check each finding against evidence, then record one disposition in the session:

- **fixed** — routine fixes need no approval;
- **dismissed** — with the evidence that refutes it;
- **deferred** — with the reason and where it is tracked;
- **human decision needed** — the choice needs judgment the human owns.

A finding is input, not an order. If a disagreement repeats without new evidence,
surface the specific unresolved decision.

On a standalone review, report findings with proposed dispositions and change
nothing unless asked.

## 6. Re-review

A fix or a modifying check changes the candidate, and a result never covers a
different base or tree. Capture the new candidate, then take the first case that
fits:

- **The last pass was partial.** Run a full review of the new candidate against the
  base, steps 2 to 5. Send no previous candidate ID; the prior findings and their
  dispositions go in the packet as context.
- **Close without a dispatch.** The last pass was complete, every finding was low,
  and every fix changes only wording: how something is said, not what a reader, an
  agent, or a machine is told to do. Close; the captured candidate is the closing tree.
- **Otherwise, re-review.** Dispatch again with every assigned lens, planned as in
  step 2 from the difference between the two candidates. Add the previous candidate
  ID and the prior findings with their dispositions to the packet. The reviewer
  confirms the fixes and applies every lens to what changed; together with the
  earlier complete review, that covers the new candidate in full.

The model tier follows the whole candidate, not the difference.

A review closes on a tree: the last reviewed candidate, or that candidate with the
wording fixes of the second case applied. Callers commit the closing tree.

## Report

State: base and candidate IDs; when the closing tree is not the last reviewed tree,
both IDs and that they differ by wording fixes only; coverage (complete, partial, or not reviewed);
reviewer count with the reason; lenses run and skipped; each finding with its
disposition; what remains unresolved. Keep tests and review apart. Complete describes
coverage, not the absence of defects.
