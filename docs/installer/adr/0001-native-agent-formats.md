---
summary: Extend agent delivery with native Codex TOML while preserving Claude Markdown and existing registry behavior.
read_when:
  - changing agent format selection, discovery, validation, or installation
---

# Native subagent formats

Status: accepted, 2026-10-27.

## Change

The installer previously discovered Claude Markdown agents only. A Codex reviewer
needs a native TOML definition with model, reasoning, and developer instructions.
Keep both formats under `plugins/<domain>/agents/`, authored in their native schemas.

`agents` still opts a target into delivery. `agent_format` selects `claude` (`.md`,
the backward-compatible default) or `codex` (`.toml`). Targets without `agents`
receive no subagents. Installation, audit, and pruning use the same selection.
Copy-mode ownership reads each file's native `name`; foreign files are preserved.
Existing collision rules extend across formats, so one install key never silently
chooses between two definitions.

## Why

A native file exposes the actual harness contract. Converting a Claude definition
would require semantics for unsupported fields and could falsely promise matching
permissions or behavior. Codex inherits the parent's permissions; custom-agent
settings cannot establish an independent read-only sandbox. Validation rejects
those ineffective settings rather than presenting them as enforcement.

Rejected alternatives: sending Markdown to Codex; a general schema and renderer
before a second authored representation is needed; installation outside the
canonical content tree. `--target` remains a flat content export, while named
targets enforce format selection.

## Runtime adjustment

CLI 0.163.0 rejected a symlinked agent definition with an ELOOP error; the same
definition loaded and dispatched when copied. The Codex target sets
`agent_mode = "copy"`. This applies only when the caller uses auto mode and only
to agent files; explicit `--mode` retains precedence. Skills remain symlinked on
platforms that normally use symlinks. Native copy drift is reported by `--check`
and repaired by reinstalling with `--force`.

## Verification

Tests cover native required fields, identity, reasoning levels, copy and symlink
delivery, target filtering, audit, pruning, foreign-file preservation, duplicate
identities, copy defaults, and stale copies. Native dispatch and model availability
have separate runtime evidence in the [reviewer tracker](../../reproducibility/progress/reviewer-v1.md).

Reference: [Codex custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
