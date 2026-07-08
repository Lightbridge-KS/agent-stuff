---
name: commit-push-pr
description: "Git workflow: commit, push, and create/update a draft PR. If a PR exists for the current branch, update its body. Trigger: 'commit push pr', 'ship it', 'send a PR', or /commit-push-pr."
metadata:
  version: "2026-07-09"
---

# Commit → Push → PR

Ship the working tree as a draft PR. You already know git and `gh` — this skill pins the policy, the artifact contract, and the failure behavior. Skip any step with nothing to do.

## Policy

- **On `main`/`master`:** create a conventionally named branch (`feat/*`, `fix/*`, `chore/*`, `refactoring/*`) and continue there — never commit to the default branch, never hard-stop.
- **Dry gates before push:** if the project defines a check entrypoint (`justfile`, `package.json` scripts, `Makefile`, CI workflow), run the fast hermetic checks (lint / typecheck / unit tests). **Failure stops the flow** with the output — never push broken. No entrypoint → skip without asking.
- **Protected branches** (`release/*`, branch-protected remotes): confirm before pushing.
- Commit style: the project's conventions win; default to Conventional Commits. Stage files by name. Co-author trailer is runtime-appropriate — never hardcode one agent's identity.

## PR contract

- Always `--draft`.
- **One PR per branch:** if a PR already exists for the branch, update its body to cover all commits since base and keep the title unless outdated. Never open a second.
- Title < 70 chars. Body: `## Summary` (bullets) + `## Test plan` (checklist). Scale detail to the size of the change.

## Report

End with: commit hash + message, whether gates ran and passed, and the clickable PR URL, noting created vs updated.
