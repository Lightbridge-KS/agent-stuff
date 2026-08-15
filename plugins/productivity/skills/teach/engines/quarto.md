# Engine: Quarto Book (default)

Mechanics for a `/teach` workspace whose book engine is **Quarto**. Read this only when
the workspace uses (or is about to bootstrap) this engine; the pedagogy lives in
`SKILL.md` and is engine-agnostic.

## Workspace layout

The teaching output is a **Quarto book** rooted in the workspace directory:

- `_quarto.yml`: The book config — parts and chapter order are the visible syllabus.
- `index.qmd`: The mission-facing preface — the promise, the organizing map, and a progress table updated each session from `learning-records/`.
- `./lessons/NN-<slug>.qmd`: The lessons, one chapter each. The primary unit of teaching.
- `./reference/*.qmd`: Appendices — cheat sheets, glossaries, reference algorithms. The compressed learnings, designed for quick reference and printing.
- `review.qmd`: The cumulative review deck appendix — retrieval practice across all lessons.
- `./assets/`: Reusable components — theme, quiz widget, question banks. See [Assets](#assets).
- `_book/`: Render output. Gitignored, never edited.

The workspace **is** a Quarto book. This buys navigation with a sidebar syllabus,
full-text search across all lessons, working cross-links, one consistent theme, and
print-ready references — for free, per lesson.

## Bootstrap (first session)

Copy the contents of the skill's `templates/quarto/` into the workspace — `_quarto.yml`,
`index.qmd`, `review.qmd`, and `assets/` (`theme.scss`, `quiz.html`) — then fill every
`{placeholder}`. `templates/quarto/lesson.qmd` and `templates/quarto/question-bank.qmd`
are skeletons to copy per lesson, not workspace files. Add `/_book/` to `.gitignore`.
Give the book a title that speaks to the mission, not the topic ("Reading the Wire", not
"Networking Basics").

## Authoring loop

Edit `.qmd` → `quarto render <file>` → fix errors → full `quarto render` when
`_quarto.yml` changed → open the result for the user (`quarto preview` for live-reload
during a session, or `open _book/...` for a single page). Never declare a lesson done
without a clean render. `execute: freeze: auto` is set in the template so executed
chapters only re-run when their source changes.

## Each session

When a lesson lands, add its chapter to `_quarto.yml` (grouped into parts as the
syllabus takes shape), add its question-bank include to `review.qmd`, and update the
progress table in `index.qmd`.

## Tier mechanisms

How the interactivity ladder (see `SKILL.md`) is realized in Quarto:

| Tier | Mechanism | Use for |
|---|---|---|
| 0 | Quarto built-ins: collapsible callouts, tabsets, code-copy, Mermaid/Graphviz | Free-recall Q&A (the collapse is the feedback loop), variant content, diagrams when ASCII fails |
| 1 | Quiz widget (`assets/quiz.html` + question banks) | Self-grading MCQs with shuffled options and instant feedback; the review deck |
| 2 | OJS cells (`{ojs}`) — reactive inputs, no server | Mini-simulators and live calculators: sliders the user moves to *see* the concept respond |
| 3 | `quarto-live` extension — editable, runnable Python/R cells in the browser (WASM), with graded exercises and hints | Code-skills practice with the tightest possible loop |

**Tier 3 is opt-in**, not shipped: it is a third-party extension (`quarto add
r-wasm/live`), and WASM Python/R has no network access and a limited package set.
Propose it when the mission is a code topic and the exercises fit those limits; record
the decision in `MISSION.md`. When practice needs a real environment — files, network,
heavy packages — fall back to `.ipynb` lessons following the `notebook-literate-python`
skill's mechanics (the kernel is the feedback loop); notebooks live in `lessons/` with
the same numbering but stay outside the book's chapter list.

## Lesson specifics

- Free recall: a visible question with the answer in a `collapse="true"` callout-tip.
- MCQs: author in a per-lesson partial `assets/questions/_NN-<slug>.qmd` (format:
  `templates/quarto/question-bank.qmd`), then `{{< include >}}` it from the lesson
  **and** list it in `review.qmd` — one source, two surfaces.
- Glossary links: `../reference/glossary.qmd#term-slug` on first use.

## Assets

- `assets/theme.scss` — the one stylesheet, linked from `_quarto.yml`. It defines the semantic components (`.thesis`, `.topo`, `.cap`, `.mission`, `.readnext`, quiz styles) and the print path. Extend it; never inline styles in a lesson.
- `assets/quiz.html` — the quiz widget script, included on every page via `include-after-body`. Its authoring contract is documented in the file header.
- `assets/questions/_NN-<slug>.qmd` — per-lesson question banks (partials; the `_` prefix keeps Quarto from rendering them standalone).
- Reusable OJS blocks (Tier 2) belong here too, as includable partials, once two lessons want the same widget.

## Print

The theme's print styles exist for the reference appendices: a cheatsheet should come
off a printer and onto a desk.
