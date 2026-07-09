# Strategy module: general-web

Tools required: `WebSearch`, `WebFetch` (load via ToolSearch if deferred). You already know
how to search well (distinct angles, reformulation, primary-over-secondary credibility);
this module pins only the contract.

## Rules

- WebFetch the **3–6 most credible** candidates per sub-question. **Never cite from a
  snippet** — a claim enters the note only after fetching the page it comes from.
- Extract into the note: concrete numbers, dates, version-specific facts, direct quotes
  where wording matters. One fragment entry per fetched-and-cited page.
- Disagreement between credible sources is a finding — record both sides with cites and
  mark the unresolved claim `[uncertain U..-..]`.

## Fragment capture

- `type`: `docs` (official documentation), `repo` (source/README/issues), `article`
  (blog/news/analysis), `paper` (use the academic-papers module instead when possible),
  `dataset`.
- `accessed`: today's date. `url`: the fetched page, not the search result.
