---
name: keynote
description: >-
  Work with Apple Keynote decks on macOS through the bundled deterministic CLI — read a
  deck's outline, edit slide text and notes, add slides, build a deck from Markdown (from a
  theme or a template .key), export PDF/PPTX. Use when the user mentions Keynote or a .key
  file, or wants a deck built or edited in Keynote. Not for .pptx files (use pptx) or
  Google Slides (use gws-slides).
compatibility: macOS with Keynote 14+; osascript (built in) and uv. Apple Events must reach Keynote (see Sandbox contract).
metadata:
  version: "2026-09-29"
---

# Keynote (JXA behind a CLI)

Drive the bundled CLI; you supply the reasoning — what the deck should say, which layout
fits, whether to edit in place. Never hand-write JXA for a job the CLI has a verb for.
`<skill_dir>` = the directory this SKILL.md was read from.

```bash
uv run <skill_dir>/scripts/keynote.py <verb> [args]   # one JSON object on stdout
```

## Sandbox contract (read first)

Apple Events are **blocked inside the Bash sandbox**: every verb fails with
`code: -10004`, exit 4. The fix is a settings rule, not a per-call bypass:

```json
"permissions": { "allow": ["Bash(uv run /Users/<you>/.claude/skills/keynote/scripts/keynote.py:*)"] },
"sandbox":     { "excludedCommands": ["uv run /Users/<you>/.claude/skills/keynote/scripts/keynote.py:*"] }
```

The rule matches the **whole Bash command**, so a call is excluded only when every
segment is a CLI invocation: absolute path, no `cd …&&`, no `$VAR`, no `| jq`, no
trailing `echo`. A `;` chain of CLI calls is fine. Anything else silently drops back
into the sandbox — exit 4 tells you.

## Verbs

| Verb | Job | Mutates |
|---|---|---|
| `status` | Keynote running? version, open documents (never launches it) | no |
| `themes` | theme names for `build --theme` | no |
| `layouts DECK` | slide-layout names — **theme-dependent, read before add-slide/build** | no |
| `outline DECK [--slide N]` | per slide: layout, title, body, notes, visible texts, item counts, `titleShowing`/`bodyShowing` | no |
| `set-text DECK --slide N [--title] [--body] [--notes] [--out]` | edit one slide | yes |
| `add-slide DECK --layout L [--title] [--body] [--notes] [--image] [--out]` | append a slide | yes |
| `build SPEC.md --out X.key [--theme T \| --template Y.key] [--pdf]` | deck from Markdown | creates |
| `export DECK --to X.pdf\|.pptx\|.html [--all-stages] [--skipped-slides]` | export | no |

Slides are 1-based. `--body` takes `\n` for new lines. Absolute paths everywhere.
Mutating verbs **save in place**; `--out` edits a *copy* and leaves the original alone.
A deck already open in Keynote is used in place and stays open; one the CLI opened is
closed again (`--keep-open` to leave it for the user to look at).

Exit codes: `0` ok · `2` bad request, nothing touched · `3` Keynote/Apple Event error
(`error` names the next move, e.g. the available layouts) · `4` Apple Events blocked.

## Workflow

1. `status` once per task. Not running is fine — any deck verb launches Keynote.
2. Existing deck: `outline` before you change anything; `layouts` before you pick one.
3. Editing the user's real file: state what will change, prefer `--out` unless they asked
   for the file itself to change. Keynote keeps no undo across a CLI save.
4. New deck: write the Markdown spec, `build`, then `outline` the result and read the
   `--pdf` back (Read tool) before reporting — placement is theme-dependent.
5. Something the verbs can't do (tables, charts, transitions, moving slides): read
   `references/jxa-keynote.md` and write a one-off JXA — same sandbox rule applies to
   `osascript`, so that call needs `dangerouslyDisableSandbox`.

## Markdown spec for `build`

```markdown
# Deck title                 → title slide (layout --title-layout, default "Title")
Subtitle paragraph           → its body

## Slide heading             → new slide (layout --bullets-layout, default "Title & Bullets")
- bullet / plain paragraph   → body lines
![alt](figure.png)           → image on the slide, path relative to the .md
> speaker notes              → presenter notes
<!-- layout: Blank -->       → layout override — applies to the slide above it, so put
                               it directly under that slide's heading
```

`--template deck.key` builds inside a copy of that deck (its theme, its layouts, its own
slides removed) — the way to get a branded deck. Layout names are resolved exactly, then
case-insensitive substring, else exit 3 listing what exists.

## Pitfalls (verified on Keynote 14.5 / macOS 15)

- Layout names differ per theme: `White` has `Title - Top`, `Basic White` has `Title Only`
  and `Section`. Never assume — `layouts` first.
- `set-text --body` on a layout without a body placeholder writes hidden text
  (`bodyShowing: false` in the outline). Pick a layout with a body instead.
- A theme-born deck that is never saved gets **autosaved to iCloud** by Keynote. The CLI
  closes on failure for that reason; a hand-written JXA must do the same.
- Each slide is several Apple Events — a 60-slide `outline` takes seconds, not ms.
- `.key` can be a package directory on large decks; the CLI copies either form.

Adapted from `automating-keynote` in SpillwaveSolutions/automating-mac-apps-plugin (MIT),
re-verified against the live dictionary; the master-slide API there is dead on current Keynote.
