# Engine: Astro Starlight (opt-in)

Mechanics for a `/teach` workspace whose book engine is **Astro + Starlight**. Read this
only when `MISSION.md ## Medium` names this engine (or the user chose it at bootstrap);
the pedagogy lives in `SKILL.md` and is engine-agnostic. The selection rubric — when
Starlight over Quarto — also lives in `SKILL.md`.

## Workspace layout

State files (`MISSION.md`, `RESOURCES.md`, `learning-records/`, `NOTES.md`) stay at the
workspace root. Only `src/content/docs/` is published — learning records are
structurally unpublishable, no exclusion list needed.

| Role | File |
|---|---|
| Visible syllabus | `astro.config.mjs` — **manual sidebar**; groups = parts |
| Preface + progress table | `src/content/docs/index.mdx` |
| Lessons | `src/content/docs/lessons/NN-<slug>.mdx` |
| Reference appendices | `src/content/docs/reference/*.md` |
| Review deck | `src/content/docs/review.mdx` |
| Theme (semantic components) | `src/styles/teach.css` via Starlight `customCss` |
| Quiz widget | `public/quiz.js`, loaded site-wide via the config's `head:` script |
| Question banks | `src/partials/questions/NN-<slug>.mdx` — no `_` prefix needed: partials outside `content/docs` are never routed |
| Render output | `dist/` — gitignored, never edited; `pnpm build` only |

## Bootstrap (first session)

1. Scaffold with the official CLI (needs network; `create-astro` runs its own
   connectivity probe that a restrictive sandbox fails even when the registry is
   reachable — rerun outside the sandbox if it reports "Unable to connect"):

   ```bash
   pnpm create astro@latest <dir> --template starlight --install --no-git --no-ai --skip-houston --yes
   ```

   `create-astro` refuses a non-empty directory, and the workspace usually already
   holds `MISSION.md` — scaffold into a temporary subdirectory, then move the generated
   files (including dotfiles) up into the workspace root.
2. `pnpm add astro-mermaid mermaid`
3. Delete the sample content: `src/content/docs/guides/`,
   `src/content/docs/reference/*` samples, `src/assets/houston.webp`.
4. Copy the skill's `templates/starlight/` over the scaffold, preserving its layout
   (`astro.config.mjs` and `public/quiz.js` at root, pages under `src/content/docs/`,
   `src/styles/teach.css`), then fill every `{placeholder}`.
   `templates/starlight/lesson.mdx` and `templates/starlight/question-bank.mdx` are
   skeletons to copy per lesson, not workspace files. Give the book a title that speaks
   to the mission, not the topic.
5. The scaffold's `.gitignore` already covers `node_modules/`, `dist/`, `.astro/` —
   verify rather than duplicate.
6. `pnpm build` to prove the site renders before the first lesson.

## Authoring loop

Edit `.mdx` → `pnpm dev` for live reload during the session → `pnpm build` as the
"clean render" gate before declaring a lesson done. Pagefind search only indexes the
production build, so a lesson is not searchable until `pnpm build` has run.

## Each session

When a lesson lands: add its entry to the sidebar in `astro.config.mjs` (group into
parts as the syllabus takes shape), import its question bank in `review.mdx`, and
update the progress table in `index.mdx`.

## Tier mechanisms

How the interactivity ladder (see `SKILL.md`) is realized in Starlight — honest about
the gaps:

| Tier | Mechanism | Parity with Quarto |
|---|---|---|
| 0 | `:::note` / `:::tip` asides, `<Tabs>`, `<details><summary>` for free-recall collapse, code-copy built-in, Mermaid via `astro-mermaid` | Full |
| 1 | Quiz widget (`public/quiz.js` + question-bank partials) — same authoring contract as the Quarto widget | Full |
| 2 | Hand-rolled vanilla-JS islands (a slider + `<script>` in the page) — no OJS runtime | Costlier; propose only when a simulator really earns it |
| 3 | **Unavailable** — no `quarto-live` equivalent | Fall back to companion `.ipynb` lessons per the `notebook-literate-python` skill, same rule as the Quarto pathway |

Also missing relative to Quarto: executed code chunks (all outputs are pre-computed or
notebook-borne) and the polished print/cheatsheet path. Gained: Pagefind full-text
search, dark mode for free, a web-native reading UI, and a one-command static deploy if
the book is ever worth sharing (deploy stays a user-initiated follow-up — never wire it
unbidden).

## Authoring notes

- **Lessons are `.mdx`** by default — they import their question-bank partial and use
  raw `<div class="…">` for the semantic components (`.thesis`, `.cap`, `.mission`,
  `.readnext`, styled by `src/styles/teach.css`). Pure-prose reference pages can stay
  `.md`.
- **MDX parses `{` and `<` as JSX** — in prose, escape literal braces/angles or wrap
  them in backticks; unfilled `{placeholder}` text will fail the build.
- **ASCII diagrams**: author as a JSX template literal — keeps whitespace, needs no
  escaping. Do **not** use a fenced code block: expressive-code would wrap it in a
  syntax-highlighted frame with a copy button, which fights the figure styling.

  ```mdx
  <pre class="topo">{`
    [App] --> [Router] --> [App]
  `}</pre>
  ```
- **Frontmatter**: `title:` is required (Starlight errors without it); quote titles
  containing backticks or colons. Add `description:` and a short `sidebar.label`.
- **Question banks**: author one `<div class="quiz">` per question in
  `src/partials/questions/NN-<slug>.mdx`, then import it from the lesson **and** from
  `review.mdx` — one source, two surfaces:

  ```mdx
  import QuizNN from '../../../partials/questions/NN-<slug>.mdx';

  <QuizNN />
  ```

- **Free recall**: `<details><summary>Show answer</summary> … </details>` — recall
  before reveal, works in `.md` and `.mdx`, degrades to visible text in print.
- **Links between pages**: absolute site paths with a trailing slash
  (`/lessons/01-slug/`); relative `.md` links are not rewritten and 404 in the build.
- **Mermaid**: fenced ```` ```mermaid ```` blocks in `.md` and `.mdx`; `autoTheme`
  follows the light/dark toggle, so never hardcode colors in a diagram.
- **Sidebar**: manual, in `astro.config.mjs` — the per-session edit *is* the syllabus,
  mirroring `_quarto.yml` chapters. Starlight ≥ 0.39 requires nested groups to wrap
  content in `items:`.
