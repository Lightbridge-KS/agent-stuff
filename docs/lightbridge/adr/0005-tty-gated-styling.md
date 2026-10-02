---
summary: >-
  Decision to style `lb` output for a person at a terminal — rich help panels plus colour —
  while every non-TTY reader (agent shells, pipes, CI) keeps the exact plain text it had.
  One stdlib predicate, lb_style.styled(), gates both surfaces; NO_COLOR / FORCE_COLOR
  override; colour is purely additive. Amends the CLI design's "nothing that needs a TTY"
  non-goal.
read_when:
  - adding or changing colour in any `lb` output, or touching lb_style.py
  - writing an `lb` help string (rich markup eats `[lowercase…]` and `:emoji:`)
  - a test sees ANSI escapes or box-drawing it did not expect
  - considering agent-environment detection (CLAUDECODE, …) or a `--color` flag
---

# ADR 0005 — TTY-gated styling: colour for a person, plain text for everyone else

Accepted 2026-10-02 (KS). Amends the non-goal in
[`../lightbridge-cli-design.md`](../lightbridge-cli-design.md#non-goals).

## Context

The two-audience rule kept `lb` entirely plain: `rich_markup_mode=None` for help, no
colour anywhere. That served the agent — rich panels are box-drawing padded to 80
columns even when piped, a token tax on every `--help` read — but left the human at a
terminal reading monochrome dashboards (`status`, `fleet status`, the doctors) where a
red `offline` or yellow `behind 3` is the whole point. Flipping help to `"rich"`
unconditionally broke the plain-help contract test and, worse, **silently dropped help
text**: rich markup parsed `[nodes.<name>]` and `[docs-index]` as style tags.

`--json` already serves the agent's *data* channel on every verb, but it does not cover
`--help` — the agent's only onboarding.

## Decision

1. **One predicate, two surfaces.** `lb_style.styled()` decides both whether Typer
   renders rich help (`rich_markup_mode="rich"`, else None) and whether `paint()` emits
   ANSI. Help and output can never disagree.
2. **Precedence:** `NO_COLOR` (set, non-empty) → plain · `FORCE_COLOR` (set, non-empty,
   not `"0"`) → styled · stdout is a TTY and `TERM ≠ dumb` → styled (on Windows only in
   a VT-capable terminal) · otherwise plain. Evaluated per call, never cached.
3. **Colour is purely additive.** Strip the escapes from styled output and the plain
   output remains, byte for byte (locked by `test_colour_is_purely_additive`). Labels
   are padded *before* painting so columns hold.
4. **Stdlib ANSI, not rich, for output.** `lb_style.py` is a CLI-side sibling and stays
   stdlib-pure like the rest; rich arrives only through Typer, only for help.
5. **Help strings must be markup-safe** in both modes — reword rather than escape (a
   `\[` escape would show in the plain branch). An AST test rejects `[lowercase…]` and
   `:word:` in `lightbridge.py`'s string constants.
6. **Semantic palette:** cyan labels; green ok/in-sync/applied; yellow attention
   (behind, DISABLED, absent); bold red broken (offline, REFUSED, FAILED, UNREADABLE,
   problem counts); dim for not-opted-in absences.

## Rejected alternatives

- **`--json` alone.** Covers command output, not `--help`.
- **Detect the agent from its environment** (`CLAUDECODE=1`, …). Harness-specific and
  brittle; "is stdout a TTY" is the signal every agent, pipe, and CI shares.
- **Always-rich help with escaped strings.** Escapes leak into the plain branch, and the
  agent pays the box-drawing tax.
- **A `--color=auto|always|never` flag on every verb.** Duplicates the env conventions
  (`NO_COLOR`, `FORCE_COLOR`) at the cost of a flag on every signature.
- **`rich_markup_mode="markdown"`.** Keeps `[…]` but drops `<…>` as inline HTML — the
  same silent-loss class.

## Consequences

- Agents, pipes, and CI see no change; the plain-help test still holds (it pipes).
- A test that runs `lb` in-process or as a subprocess under an exported `FORCE_COLOR`
  would see escapes — the two lightbridge test modules pop it at import.
- Errors on stderr stay uncoloured; extending colour there would need a stderr-scoped
  predicate.
