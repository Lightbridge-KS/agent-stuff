---
name: skill-taxonomy
description: The two-axis classification of skills and instruction text — kind (Concept / Contract / Reference, by which deficit it compensates for) and vendor (Authored / Vendored / Harness-provided / Adopted, by who guarantees freshness). Use when creating, adopting, vendoring, classifying, or auditing a skill; when deciding where a skill or instruction text should live or how it will age as models improve; or whenever these terms or "castle gate", "context castle", "drain obligation", or "registry invariant" come up.
metadata:
  version: "2026-07-28"
---

# Skill taxonomy

Skills — and instruction text generally — classify along two orthogonal axes: **kind** (which deficit the text compensates for) and **vendor** (who guarantees its freshness). Kinds predict how a skill *ages* as models improve; vendors determine its *maintenance obligation*. Use these terms exactly when discussing, creating, or auditing skills.

Governing rule: context encodes **decisions, not competence** — anything a strong model derives by default is dead weight.

## Kinds — which deficit it compensates for

- **Concept** — compresses *judgment*: names a move and **pins its expansion** so the term decompresses the same way every session (`grilling`, `blindspot-pass`). Shared vocabulary with the agent — DDD ubiquitous language applied to context engineering. Value **rises** with model intelligence (stronger decoder → one word fans out further); write only where my intended expansion diverges from the model's default. Re-test each model generation — upgrades silently re-roll unpinned terms.
- **Contract** — a coordination protocol: deterministic artifacts, file formats, state/phase machines, exit codes (`handoff`, `commit-push-pr` state contract). **Invariant** to model growth — contracts buy predictability across parties and time, not capability; more autonomy needs *more* of them, not fewer. Version them.
- **Reference** — caches *facts* the model can't derive and might hallucinate: flag names, endpoints, version quirks. Doesn't compress — guarantees fresh ground truth. Migrates toward retrieval (docs lookup, MCP) as models grow, but never to zero — the world outruns training. Needs freshness checks.

A skill can mix kinds — classify by where its *value* lives (e.g. `handoff` reads conceptual but its value is the deterministic artifact → contract).

## Vendors — who guarantees freshness

Orthogonal to kinds (kinds = what deficit a skill fills; vendors = who keeps it true), but correlated: vendored skills are usually Reference-kind, which is exactly why they need sync and `grilling` doesn't.

- **Authored** — the context castle: `agent-stuff` (public) and `agent-stuff-private` (private sibling; content-only, machinery via `--root`). Freshness by **ownership**; entry by the **castle gate** — a human–AI discussion that fits the skill into the whole context layer (system prompt, sibling skills, hooks) before it lands. Skills adapted from elsewhere pass the same gate; after it, they're mine.
- **Vendored** — ships from an upstream product, pinned to the **installed binary version**, never edited locally. Two delivery modes: **co-shipped** (skill inside the install unit, arriving and upgrading atomically with the binary — a symlink into the install tree is self-syncing) vs **detached** (binary and skill travel separately — pinned to the tag matching the installed version, re-synced after every upgrade, with a doctor for skew; mechanized by the `skill-vendor` tool + skill in `agent-stuff`).
- **Harness-provided** — ships with the harness itself (Claude Code plugins, Codex `.system`), out of the box. Zero maintenance, zero adaptability. Acceptable only for Reference-kind; the moment I need to bend one, that's a fork → Adopted → castle gate.
- **Adopted** — a third-party copy with **no guarantor**: a snapshot aging silently from copy day. A **staging state, not a home** — the shelf is `~/.agents/skills/`, and everything on it carries a drain obligation: pass the castle gate into Authored (public or private), or re-wire to upstream as Vendored (= a `skill-vendor` manifest entry). Never symlink new adoptions anywhere else.

**Registry invariant:** `~/.claude/skills/` and `~/.codex/skills/` are pure proxies — **symlinks only**, every skill resolving to a governed home above. A real directory in a registry is unvendored drift by definition (checkable: `skill-vendor doctor` — violations report as skew, exit 1).

## Related skills

- `skill-vendor` (`agent-stuff/plugins/lightbridge`) — the mechanics for the Vendored column: manifest, sync, doctor.
- `writing-great-skills` (`agent-stuff/plugins/productivity`) — how to write the skill once its kind and vendor are decided.
