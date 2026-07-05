# Strategy module: general-web

Tools required: `WebSearch`, `WebFetch` (load via ToolSearch if deferred).

## Query tactics

- Formulate 2–4 **distinct angles** per sub-question, not rephrasings: the direct
  question, the comparison/alternative framing, the failure-mode framing ("X problems",
  "X vs Y"), and the practitioner framing ("X in production", "X 2026").
- When results are thin, climb the reformulation ladder: broaden terms → swap synonyms →
  scope to a site (`site:github.com`, `site:news.ycombinator.com`) → scope by date.
- Prefer queries with the current year when recency matters; the scope digest gives the
  time range.

## Search → fetch → extract

1. WebSearch each angle; skim titles/snippets to pick candidates.
2. WebFetch the **3–6 most credible** candidates. **Never cite from a snippet** — a claim
   enters the note only after fetching the page it comes from.
3. Extract into the note: concrete numbers, dates, version-specific facts, direct quotes
   where wording matters. One fragment entry per fetched-and-cited page.

## Credibility heuristics

- Primary over secondary: official docs, changelogs, and repos beat blog posts; blog
  posts by the tool's authors beat third-party summaries.
- Check recency against today's date — a 3-year-old comparison of fast-moving tools is a
  history document, not evidence. Note the publication date when it qualifies the claim.
- Skip SEO farms: listicle domains, scraped/AI-boilerplate pages, pages that cite no
  primary sources. If two candidates say the same thing, cite the more primary one.
- Disagreement between credible sources is a finding — record both sides with cites and
  mark the unresolved claim `[uncertain U..-..]`.

## Fragment capture

- `type`: `docs` (official documentation), `repo` (source/README/issues), `article`
  (blog/news/analysis), `paper` (use the academic-papers module instead when possible),
  `dataset`.
- `accessed`: today's date. `url`: the fetched page, not the search result.
