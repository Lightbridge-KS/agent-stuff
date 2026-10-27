---
summary: Codex reproducibility reviewer v1 — native agent delivery, commit review protocol, and verification status.
read_when:
  - changing reproducibility-reviewer or its commit workflow
  - checking native Codex agent delivery and reviewer validation
---

# Reproducibility reviewer v1

Parent: [Reproducibility skills v1](v1.md).
Classification: Contract × Authored, using the two accepted Concept skills.

## Accepted scope

One Codex agent reviews an immutable commit candidate with GPT-6.1 Sol and high
reasoning. The main agent dispatches with fresh context, evaluates findings, and
owns fixes and delivery. Review-only behavior is an instruction; permissions
remain inherited from the parent session.

The instruction spine carries only the Codex-specific delegation trigger. The
`pr` skill carries the main agent's snapshot, dispatch, disposition, and commit
verification procedure. Native TOML agents extend the existing installer and
validator while preserving Claude Markdown delivery and unrelated work.

## State

- [x] Draft and concise instruction router accepted (2026-10-27).
- [x] Native agent discovery, target selection, validation, and regression tests.
- [x] Reviewer definition and `pr` protocol.
- [x] Install reviewer and its two skills to Codex; verify native dispatch.
- [x] Behavioral fixture: candidate content, planted failures, valid exceptions,
  missing inputs, review-only behavior, and fresh-context dispatch.
- [x] Enable the Codex router and verify generated instructions.

## Evidence (2026-10-27)

- Repository validation passed: 54 skills and 2 subagents.
- Installer (29), validator (14), hooks (19), packager (8), and Codex plugin (4)
  tests passed. Ruff lint and formatting checks passed on the changed Python files.
- Native CLI 0.163.0 rejected a symlinked role file with ELOOP. Copying the same
  definition enabled native dispatch. The target now uses `agent_mode = "copy"`;
  regression tests cover the default, skill-mode preservation, and stale-copy audit.
- A fresh reviewer found the saved candidate's hardcoded input path and unsupported
  documented environment variable despite a different fixed index and working tree.
  The scoped toy and historical evidence did not produce findings.
- A corrected candidate produced no findings. A separate incomplete packet returned
  partial coverage and named the missing base, candidate, and constraints.
- Native dispatch requested the installed role with `fork_turns = "none"` and no
  model overrides. The installed file pins GPT-6.1 Sol / high; spawn results did not
  expose separate per-child runtime model or reasoning telemetry.
- Fixture file hashes and index checks confirmed no review mutations. Candidate
  code was not executed. These are static review observations, not test execution
  evidence for the fixture application.
- `agent-instruction` build and render checks passed. The commit-review trigger is
  confined to the Codex render; the shared reproducibility guidance remains shared.

Canonical implementation: [agent](../../../plugins/coding/agents/reproducibility-reviewer.toml),
[commit protocol](../../../plugins/coding/skills/pr/references/reproducibility-review.md),
and [delivery decision](../../installer/adr/0001-native-agent-formats.md).

## Verification boundary

Local checks and fixture reviews do not establish hosted CI, other harnesses,
or reliability across all future commit workflows.
