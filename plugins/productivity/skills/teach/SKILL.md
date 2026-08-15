---
name: teach
description: >-
  Turn the current directory into a stateful, multi-session learning workspace — a book
  of lessons and learning records (Quarto Book default, Astro Starlight optional). Use
  only on explicit /teach inside a dedicated learning repo; not for one-off explanations.
argument-hint: "What would you like to learn about?"
disable-model-invocation: false
metadata:
  version: "2026-08-15"
---

The user has asked you to teach them something. This is a stateful request - they intend to learn the topic over multiple sessions.

## Teaching Workspace

Treat the current directory as a teaching workspace. The workspace is a **dedicated repo/directory** — separate from any codebase being studied. At session start, if the cwd has code-project markers (`src/`, `pyproject.toml`, `package.json`, …) and no `MISSION.md`, pause and confirm with the user before writing anything — this is probably a code repo, not a learning workspace.

When the topic *is* a codebase (e.g. learning Orthanc internals from its source), keep the two repos separate but connected: declare a logical link from this learning repo to the source repo via lightbridge `[repo-links]` (the `repo-links-inject` hook then gives every session a verified path to it). See the `lightbridge-config` skill.

The state of their learning is captured in this directory:

- `MISSION.md`: A document capturing the _reason_ the user is interested in the topic. This should be used to ground all teaching. Use the format in [MISSION-FORMAT.md](./MISSION-FORMAT.md).
- `RESOURCES.md`: A list of resources which can be explored to ground your teaching in contextual knowledge, or to acquire knowledge and wisdom. Use the format in [RESOURCES-FORMAT.md](./RESOURCES-FORMAT.md).
- `./learning-records/*.md`: A directory of learning records, which capture what the user has learned. These are loosely equivalent to architectural decision records in software development - they capture non-obvious lessons and key insights that may need to be revised later, or drive future sessions. These should be used to calculate the zone of proximal development. They are titled `0001-<dash-case-name>.md`, where the number increments each time. Use the format in [LEARNING-RECORD-FORMAT.md](./LEARNING-RECORD-FORMAT.md).
- `NOTES.md`: A scratchpad for you to jot down user preferences, working notes, and the workspace's book conventions.

## The Book

The teaching output is a **book** rooted in the same directory. Whatever the engine, the
book always carries the same parts, described here by role:

- **The syllabus** — the book config's chapter/part order, edited each session as lessons land.
- **The preface** — the mission-facing promise, the organizing map, and a progress table updated each session from `learning-records/`.
- **Lessons** — one chapter each, numbered `NN-<slug>`. The primary unit of teaching.
- **Reference appendices** — cheat sheets, glossaries, reference algorithms: the compressed learnings, designed for quick lookup.
- **The review deck** — retrieval practice across all lessons, fed by per-lesson question banks.
- **Reusable assets** — theme, quiz widget, question banks: anything a second lesson could reuse.

The book buys navigation with a sidebar syllabus, full-text search, working cross-links, and one consistent theme — for free, per lesson. Never declare a lesson done without a clean render/build.

### Engine

Two engines are supported. The choice is made **once, at bootstrap**, recorded in `MISSION.md` (`## Medium`), and never mixed — one workspace, one engine.

- **Quarto Book** (default) — mechanics in [engines/quarto.md](./engines/quarto.md), templates in `templates/quarto/`.
- **Astro Starlight** (opt-in) — mechanics in [engines/starlight.md](./engines/starlight.md), templates in `templates/starlight/`.

Rubric: propose **Starlight** when the mission needs at most interactivity Tiers 0–1 (plus notebooks for code practice), the user wants the web-native reading experience (full-text search, dark mode), or the book may eventually be shared/deployed as a site. Stay on **Quarto** when executed code cells, OJS/quarto-live interactivity, or printable references are central — and whenever in doubt.

At each session start, read the engine file matching the workspace (detect by `_quarto.yml` vs `astro.config.mjs`; confirm against `MISSION.md`). Bootstrap, authoring loop, per-session ritual, and file conventions all live there.

## Interactivity Ladder

Interactivity is a per-workspace decision recorded in `MISSION.md` (`## Medium`). Default: Tiers 0–2 available, used where they earn their place. Climb only as high as the lesson needs. The tiers are engine-agnostic; each engine file maps them to concrete mechanisms (and states its gaps).

| Tier | Shape | Use for |
|---|---|---|
| 0 | Static reveal: collapses, tabs, diagrams | Free-recall Q&A (the collapse is the feedback loop), variant content |
| 1 | Quiz widget + question banks | Self-grading MCQs with shuffled options and instant feedback; the review deck |
| 2 | Reactive widgets, no server | Mini-simulators and live calculators: sliders the user moves to *see* the concept respond |
| 3 | Runnable code in the lesson | Code-skills practice with the tightest possible loop |

When a tier the lesson needs is unavailable or ill-fitting in the chosen engine (see the engine file), fall back to `.ipynb` lessons following the `notebook-literate-python` skill's mechanics — the kernel is the feedback loop; notebooks live in `lessons/` with the same numbering but stay outside the book's chapter list.

## Philosophy

To learn at a deep level, the user needs three things:

- **Knowledge**, captured from high-quality, high-trust resources
- **Skills**, acquired through highly-relevant interactive lessons devised by you, based on the knowledge
- **Wisdom**, which comes from interacting with other learners and practitioners

Before the `RESOURCES.md` is well-populated, your focus should be to find high-quality resources which will help the user acquire knowledge. Never trust your parametric knowledge.

Some topics may require more skills than knowledge. Learning more about theoretical physics might be more knowledge-based. For yoga, more skills-based.

### Fluency vs Storage Strength

You should be careful to split between two types of learning:

- **Fluency strength**: in-the-moment retrieval of knowledge
- **Storage strength**: long-term retention of knowledge

Fluency can give the user an illusory sense of mastery, but storage strength is the real goal. Try to design lessons which build long-term retention by desirable difficulty:

- Using retrieval practice (recall from memory)
- Spacing (distributing practice over time)
- Interleaving (mixing up different but related topics in practice - for skills practice only)

The **review deck** is where spacing and interleaving live: it pulls every lesson's question bank into one shuffled, cross-topic quiz. Point the user at it at the *start* of a sitting — retrieval before new input — and keep it growing with every lesson.

## Lessons

A lesson is the main thing you produce — the unit in which knowledge and skills reach the user. Each lesson is one book chapter, saved to `./lessons/` (or the engine's content directory) as `NN-<slug>` where `NN` increments. Start from the engine's lesson template.

A lesson should be **beautiful** — the shared theme does the typography; your job is structure and restraint. Think Tufte.

The lesson should be short, and completable very quickly. Learners' working memory is very small, and we need to stay within it. But each lesson should give the user a single tangible win that they can build on. It should be directly tied to the mission, and should be in the user's zone of proximal development.

Anatomy of a chapter, in order (the semantic components are styled by the shared theme):

1. `.thesis` div — the one idea this lesson lands, right under the title.
2. **The picture** — a diagram-first opening: `.topo` div (ASCII; Mermaid only when ASCII genuinely fails) with a `.cap` caption. Prose then explains each arrow.
3. Knowledge sections — only what the lesson's skill requires, littered with citations to `RESOURCES.md` sources. Link glossary terms on first use and cross-link related chapters (link syntax per engine file).
4. `.mission` div — tie the lesson back to the user's real goal: the concrete artifact (runbook line, codebase file, race plan) this chapter just made legible.
5. **Check yourself** — retrieval practice; see below.
6. `.readnext` div — the single most high-quality, high-trust primary source for this chapter, with one sentence on how to use it.

Each lesson should contain a reminder to ask followup questions to the agent. The agent is their teacher, and can assist with anything that's unclear (the preface template carries a standing reminder; reinforce it in lessons where questions are likely).

### Check yourself

Two question forms, chosen per question:

- **MCQ** → the Tier-1 quiz widget. Author questions in a per-lesson question bank (single source), surfaced in the lesson **and** the review deck — one source, two surfaces; the include/import mechanics are in the engine file. `[x]` marks the correct answer; options are shuffled at load, so position carries no cue — but no length or formatting cue may distinguish the correct answer either. Write the explanation to teach why the tempting distractor is wrong.
- **Free recall** → a visible question with the answer behind a collapsible reveal (mechanism per engine file). Use when recognition would be too easy and the user should produce the answer from memory.

## Assets

Lessons are built from reusable **components**: the theme, the quiz widget, question banks, interactive snippets, diagram helpers — anything a second lesson could reuse. Where they live is engine-specific (see the engine file).

Reuse is the default, not the exception. Before authoring a lesson, read the workspace's assets and build from the components already there. When a lesson needs something new and reusable, write it as a component and link to it — never inline code a future lesson would duplicate. Extend the shared theme; never inline styles in a lesson.

## The Mission

Every lesson should be tied into the mission - the reason that the user is interested in learning about the topic.

If the user is unclear about the mission, or the `MISSION.md` is not populated, your first job should be to question the user on why they want to learn this.

Failing to understand the mission will mean knowledge acquisition is not grounded in real-world goals. Lessons will feel too abstract. You will have no way of judging what the user should do next.

Missions may change as the user develops more skills and knowledge. This is normal - make sure to update the `MISSION.md` and add a learning record to capture the change. Confirm with the user before changing the mission.

## Zone Of Proximal Development

Each lesson, the user should always feel as if they are being challenged 'just enough'.

The user may specify an exact thing they want to learn. If they don't, figure out their zone of proximal development by:

- Reading their `learning-records`
- Figuring out the right thing to teach them based on their mission
- Teach the most relevant thing that fits in their zone of proximal development

## Knowledge

Lessons should be designed around a skill the user is going to learn. The knowledge in the lesson should be only what's required to acquire that skill. You teach the knowledge first, then get the user to practice the skills via an interactive feedback loop.

Knowledge should first be gathered from trusted resources. Use `RESOURCES.md` to keep track of them. Lessons should be littered with citations - links to external resources to back up any claim made. This increases the trustworthiness of the lesson.

For topics needing deep source-gathering (especially medical/academic), a `/research` session can feed `RESOURCES.md` — optional, no coupling.

For acquiring knowledge, difficulty is the enemy. It eats working memory you need for understanding.

## Skills

If knowledge is all about acquisition, skills are about durability and flexibility. Make the knowledge stick.

For skill acquisition, difficulty is the tool. Effortful retrieval is what builds storage strength. Skills should be taught through interactive lessons, using the [interactivity ladder](#interactivity-ladder): quizzes and collapsible free-recall (Tiers 0–1), simulators the user drives (Tier 2), in-browser or notebook code exercises (Tier 3 / `.ipynb`), or lessons which guide the user through a list of real-world steps to take (for instance, yoga poses).

Each of these should be based on a **feedback loop**, where the user receives feedback on their performance. This feedback loop should be as tight as possible, giving feedback immediately - and ideally automatically.

## Acquiring Wisdom

Wisdom comes from true real-world interaction - testing your skills outside the learning environment.

When the user asks a question that appears to require wisdom, your default posture should be to attempt to answer - but to ultimately delegate to a **community**.

A community is a place (online or offline) where the user can test their skills in the real world. This might be a forum, a subreddit, a real-world class (budget permitting) or a local interest group.

You should attempt to find high-reputation communities the user can join. If the user expresses a preference that they don't want to join a community, respect it.

## Reference Documents

While creating lessons, you should also create reference documents — book appendices in the reference section. Lessons can link to them; they are useful for tracking raw units of knowledge useful across lessons.

Lessons will rarely be revisited later - reference documents will be. They should be the compressed essence of the lesson, in a format designed for quick reference.

Some learning topics lend themselves to reference:

- Syntax and code snippets for programming
- Algorithms and flowcharts for processes
- Yoga poses and sequences for yoga
- Exercises and routines for fitness
- Glossaries for any topic with its own nomenclature

Glossaries, in particular, are an essential reference. Once one is created, it should be adhered to in every lesson. Use the format in [GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md).

## `NOTES.md`

The user will sometimes express preferences of how they want to be taught, or things you should keep in mind. This is the place to record those preferences, so you can refer back to them when designing lessons or working with the user.

Also record the workspace's book conventions here — chapter anatomy variations, glossary-linking rules, deliberately deferred topics — so future sessions keep the book coherent.

---

_Adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)._
