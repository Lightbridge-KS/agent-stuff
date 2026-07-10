---
name: switch-pull-prune
description: "Git workflow: after a PR merges, switch to the base branch, pull, and prune the merged branch. Trigger: 'I've merged the PR' or /switch-pull-prune."
metadata:
  version: "2026-07-10"
---

# Switch → Pull → Prune

Close the loop `commit-push-pr` opened. You know git — this skill pins which branch, and what to clean up.

## Policy

- **Base branch is inferred, not asked:** `git symbolic-ref refs/remotes/origin/HEAD`, falling back to `gh repo view --json defaultBranchRef`. Resolves `main` for GitHub Flow, `develop` for GitFlow. Ask only if inference fails, or the user named a different branch.
- **Dirty tree stops the flow.** Report the diff; never stash or discard unless told.
- Pull with `--ff-only`. A non-fast-forward means something diverged — stop and report, don't merge.
- **Verify the merge landed:** the branch's commits must be ancestors of the new base HEAD. If they aren't, say so rather than reporting success.
- **Prune:** delete the merged local branch with `git branch -d` (never `-D`) and `git fetch --prune`. Skip silently if already gone.

## Report

End with: base branch + new HEAD (short hash + subject), and what was pruned.
