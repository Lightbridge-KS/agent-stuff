---
summary: Replace the single-lens reproducibility reviewer with a generic reviewer contract, lens files, and native harness roles; Codex has a separate documentation tier.
read_when:
  - changing the change-review skill, its lenses, or the change-reviewer agent files
  - adding a review lens or a reviewer agent
  - asking why reproducibility-reviewer no longer exists
---

# Lens-based change reviewer

Status: accepted, 2026-11-15. Supersedes the scope of the
[reproducibility reviewer v1](../../archive/reproducibility/reviewer-v1.md).

## Change

Before: one Codex agent, `reproducibility-reviewer`, held the review authority, the
finding schema, and one lens. The `pr` skill held the dispatch and disposition
protocol, and applied it on Codex only.

After:

- The [`change-review`](../../../plugins/coding/skills/change-review/SKILL.md) skill
  owns the protocol: candidate, review plan, dispatch, collection, disposition,
  re-review. Any caller can run it; `pr` is one caller.
- Generic roles carry identity, model, and authority only: `change-reviewer`
  (Markdown, Claude Code), `change-reviewer-codex` and the documentation-only
  `change-reviewer-codex-docs` (TOML, Codex). The names differ because the validator
  and the installer reject one name defined in two formats
  ([native-agent decision](../../installer/adr/0001-native-agent-formats.md)).
- The reviewer contract (packet, finding schema, return format) and five lenses are files
  in the skill: correctness, reproducibility, spec, standards, and prose. The reviewer
  reads them from paths in the packet.
- The prose lens applies the rules of the `unslop` skill to human-facing prose. That
  skill defines the scope and ships in another plugin, so the main agent
  skips the lens when `unslop` is not installed.
- One reviewer covers all applicable lenses by default. The main agent scales to at
  most four reviewers for a large or one-way-door change; the prose lens
  shares a reviewer with another lens.
- The model tier follows the change: the stronger family by default, the cheaper
  family when the change is documentation only.

Unchanged: the candidate is a pair of immutable git objects; dispatch uses fresh
context; the reviewer inspects only; the main agent owns every decision; a partial
review pauses the commit.

## Why

- A lens-specific agent does not scale: five lenses on two harnesses would need
  ten near-identical files, each repeating the authority and the finding schema.
- Native agent files are not converted between formats
  ([native-agent decision](../../installer/adr/0001-native-agent-formats.md)). Text
  that both harnesses need must therefore live outside the agent files, or it drifts.
- The protocol inside `pr` could not serve a review that is not a commit: a branch,
  a pull request, or a direct request.
- One reviewer by default keeps the cost of every commit low. The return format
  requires one section per assigned lens, so a lens cannot vanish inside one context.

## Rejected alternatives

- **One agent per lens per harness.** Duplicates authority and schema; see above.
- **No named agent** (a general-purpose subagent with an assembled prompt). Loses the
  model pin, the tool restriction on Claude Code, and the memory switch on Codex.
- **The name `code-review`.** Claude Code ships a built-in skill with that name.
- **Scaling by file partition.** Reviewers that each see part of the diff miss
  defects that cross files. Scaling splits lenses, never files.
- **A fixed code-smell baseline** in the standards lens. A catalogue of well-known
  smells is competence the model already has; the lens cites only what the
  repository documents.
- **One name for both agent files.** Needs the installer to select a definition by
  target format; that amends the native-agent decision and is deferred.
- **Cross-harness review** (one harness launching the other). Out of scope; each
  harness reviews with its own models.

## Codex verification adjustment (2026-11-15)

The runtime accepted a terra/high spawn request but used the named role's sol/xhigh
pins. A separate documentation-only role therefore pins `gpt-6.1-terra`/`high`;
the authority and lens contract stay shared. This is a model-tier distinction,
not one agent per lens. The [official subagent reference](https://learn.chatgpt.com/docs/agent-configuration/subagents)
also specifies that native model and effort settings take precedence.

## Consequences

- `reproducibility-reviewer.toml` and `pr/references/reproducibility-review.md` are
  deleted. An installed copy of the old Codex role stays on each machine: the
  installer owns a copied file only while its source exists, so `--prune` does not
  remove it and `--check` does not report it. Delete `reproducibility-reviewer.toml`
  by hand from the Codex `agents` directory that `bin/targets.toml` names.
- A new lens is one file under `references/lenses/` and one row in the skill; no
  agent change.
- Read-only behaviour remains an instruction on Codex. On Claude Code the agent has
  no edit tools, but it keeps a shell; the authority text still applies.

Evidence and open items: [tracker](../progress/v1.md).
