---
name: retro
description: Review a coding session for durable improvements to the agent's working environment. Use when the user asks for a retro or session retrospective.
metadata:
  version: "2026-10-24"
---

# Retro

Turn session evidence into a few improvements to future working conditions:
navigation, instructions, checks, tools, and available information. Product bugs
matter here when they expose a reusable improvement.

Present findings and concrete proposals by default. Implement when requested,
within the authorized scope. A retro alone does not authorize persistent edits,
memory writes, installation, or expanded access.

## Read, diagnose, propose

1. **Read the session.** Default to the current conversation; retrieve another
   session when identified. Corroborate with relevant artifacts and state gaps in
   the available history.
2. **Find consequential friction.** Look for corrections, repeated discovery,
   failed checks, costly tool output, missing evidence, and useful workarounds
   worth preserving. These are lenses, not mandatory report sections.
3. **Diagnose before prescribing.** Was guidance absent, unreachable, ambiguous,
   contradictory, stale, or available but not followed? Inspect existing checks
   and their wiring before proposing more. Separate environmental causes from
   isolated execution mistakes; label hypotheses.
4. **Choose the smallest durable intervention.** Repair an existing mechanism
   first. Weigh consequence and likely recurrence against maintenance and context
   cost. Leaving things unchanged is a valid outcome.

## Put the change where it belongs

- Mechanical mistake → existing lint, test, hook, or CI mechanism when the benefit
  warrants automation. A skipped check calls for fixing its execution path.
- Hard-to-find knowledge → repair its pointer, skill description, or `read_when`
  before duplicating the content.
- Project decision → existing project design or API docs.
- Reusable, non-default judgment → an existing skill first; a new skill must earn
  a distinct trigger. Use `skill-taxonomy` for the castle gate: explain what future
  decision changes and why existing context does not cover it.
- Cross-project steering → canonical instruction source; follow its generation
  workflow rather than editing generated files.
- Temporary state → existing tracker or handoff, when persistence is requested.

One successful session does not prove an instruction redundant; one failure does
not justify another rule. Treat suspected no-ops as candidates for a behavioral
comparison, preserving deliberate contracts. Keep relevant constraints available
to implementation as well as review.

## Deliver

Rank the strongest findings by consequence and likely recurrence. For each, give
**evidence → cause or hypothesis → concrete change and canonical home → verification**.
Name the correction, tool result, or artifact supporting it. Mark judgment choices
with 💡. When evidence supports no worthwhile persistent change, say so.

Deliver in chat; a report file is optional when requested. Retro improves future
working conditions; handoff preserves current state.

Inspired by [Matt Pocock's retro](https://github.com/mattpocock/skills/blob/5beb35b/skills/engineering/retro/SKILL.md)
(MIT), adapted to the authored-skill castle gate.
