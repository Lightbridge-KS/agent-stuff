---
name: yolo-ship
description: "Autonomous git workflow for low-risk work: commit → push → PR → watch CI → fix if red → merge when green → switch-pull-prune. OPT-IN ONLY: invoke only when the user explicitly says 'yolo ship' or /yolo-ship in the current turn — never self-select, never chain from another task."
metadata:
  version: "2026-07-19"
---

# YOLO Ship

Land the working tree on the base branch autonomously: wrap `commit-push-pr` and
`switch-pull-prune` around a ready → watch-CI → merge core. Every phase is observable
from `git`/`gh` state, so re-invoking resumes where it left off — never restarts.

## Opt-in gate

Human-triggered only. The explicit trigger in the current turn is the standing
authorization to merge without further confirmation — do not re-ask at merge time.
Absent that trigger, this skill must never run, even as a "helpful" continuation of
`commit-push-pr`.

## Phases

0. **Preflight** — verify the autonomous path is safe; on any failure **downgrade**:
   run `commit-push-pr` only and report why the YOLO path stopped.
   - Never against protected branches (`release/*`, or a base with required-review
     branch protection — the merge would be blocked anyway; check via `gh`).
1. **Ship** — invoke the `commit-push-pr` skill. It owns branch policy, dry gates,
   and the draft-PR contract; a dry-gate failure stops the whole flow there.
2. **Ready** — `gh pr ready` (drafts can't merge, and some CI skips them).
3. **Watch** — `gh pr checks --watch` (re-run on command timeout; state is
   re-entrant).
   - **No checks at all:** proceed to merge, but flag in the report that local dry
     gates were the only gate — "green" was vacuous.
   - **Red:** enter the fix loop.
4. **Fix loop** (red CI only) — diagnose from `gh run view --log-failed`, then:
   - Fix only what is **low-risk**: lint/format, type errors, missing imports, small
     test or fixture updates, manifest/config sync. Anything touching logic or design
     intent → stop and report instead — that needs the human.
   - Each attempt: fix → commit → push → re-watch. **Max 3 attempts.**
   - The same check failing with the same error twice → treat as flaky or
     environmental: stop, don't spin.
5. **Merge** — `gh pr merge --merge` (merge commit). No `--delete-branch` — pruning
   belongs to `switch-pull-prune`, which verifies the merge landed first. A blocked
   merge → stop and report.
6. **Close the loop** — invoke the `switch-pull-prune` skill.

## Report

End with: PR URL, CI outcome (including fix attempts and what each changed), merge
commit, new base HEAD, and what was pruned. On any stop or downgrade: the phase
reached and exactly what blocked, so the human can resume with one command.
