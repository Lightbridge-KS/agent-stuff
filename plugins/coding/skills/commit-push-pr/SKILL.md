---
name: commit-push-pr
description: "Git workflow: commit, push, and create/update a draft PR. If a PR exists for the current branch, update its body. Trigger: 'commit push pr', 'ship it', 'send a PR', or /commit-push-pr."
metadata:
  version: "2026-06-12"
---

# Commit → Push → PR

## Step 1: Gather Context

Run in parallel:

- `git status`, `git diff`, `git diff --staged`, `git log --oneline -10`
- `git branch --show-current`, `git rev-parse --abbrev-ref @{upstream} 2>/dev/null`
- `gh auth status`
- `gh pr list --head $(git branch --show-current) --json number,title,isDraft,url --limit 1`

**Hard stops:**

- Stop if `gh auth status` fails. Report a clear fix (e.g., run `gh auth login`).
- Stop if branch is `main` or `master`.

Skip steps that aren't needed (e.g., nothing to commit → skip to push).

## Step 2: Commit

- Stage files by name (never `git add -A` or `git add .`)
- Never commit files that likely contain secrets (`.env`, credentials, tokens)
- Follow project's commit conventions; default to Conventional Commits
- Use HEREDOC for multi-line messages
- Co-author trailer should be runtime-appropriate and configurable (do not hardcode Claude-specific identity)

## Step 3: Push

- If no upstream exists: `git push -u origin HEAD`; otherwise `git push`.
- If branch is high-risk or protected (e.g., `release/*`, protected remote branches), ask for explicit confirmation before pushing.

## Step 4: Create or Update PR

- Get diff/log against base branch: `git log --oneline BASE..HEAD` and `git diff BASE...HEAD --stat`
- Draft PR body in a temp markdown file and use `--body-file` (avoid inline multi-line shell quoting)
- **No existing PR →** `gh pr create --draft` with title (<70 chars) and body summarizing all commits since base
- **Existing PR →** Update body via `gh pr edit --body-file` incorporating new changes; keep title unless outdated
- PR body: `## Summary` + bullet points + `## Test plan` checklist. Scale detail to change size.

## Step 5: Optional Quality Checks (recommended)

Before push/PR, run project checks when available (e.g., test/lint/typecheck). If checks fail, report and ask whether to proceed.

## Step 6: Report

Show: commit hash/message (if any), clickable PR URL, whether PR was created or updated, and whether checks passed/skipped.