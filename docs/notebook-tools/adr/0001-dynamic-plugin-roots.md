---
summary: Decision to add MCP client-root discovery with an explicit user-config fallback while preserving static direct-registration roots.
read_when:
  - changing notebook-tools filesystem authorization or plugin startup
  - handling MCP roots/list behavior or root configuration failures
---

# ADR 0001 — Dynamic Roots for Native Plugin Installation

## Status

Accepted 2026-07-19.

## Context

Version 0.2 requires repeated absolute `--root` arguments at process startup. That is safe
and works for direct Codex registration, but a portable marketplace manifest cannot embed
machine-specific paths. Defaulting an installed plugin to the home directory or `/` would
silently expand prompt-free notebook read access.

## Decision

Preserve static roots for direct registration and add an explicit plugin mode that requests
standard MCP client roots for every tool call. Valid client roots are authoritative for
that call. When the client cannot provide usable roots, read an explicit platform-native
user roots config. With neither source, fail with `ROOT_CONFIGURATION_REQUIRED`.

Root sources never union across precedence levels. All sources reuse the existing strict
absolute-path, symlink-resolution, and containment policy. Successful results report only
the source and root count, not a new unbounded path dump.

## Consequences

- Marketplace manifests stay portable and least-privilege workspaces work without manual
  per-plugin arguments.
- Hosts without MCP roots need one explicit config step.
- Tool adapters become request-context aware, while the notebook domain stays transport
  independent.
- Direct registration remains backward compatible.
- Plugin rollout is blocked, rather than weakened, if current Codex cannot preserve roots
  and write approvals.

## Rejected alternatives

- **Implicit home root:** zero setup, but grants broad prompt-free notebook reads.
- **Filesystem root:** maximally convenient and unacceptably broad.
- **Hard-coded personal path:** safe for one machine but invalid marketplace packaging.
- **Per-tool caller-supplied root:** lets an agent choose its own authorization boundary.
