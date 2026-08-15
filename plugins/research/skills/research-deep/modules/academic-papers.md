# Strategy module: academic-papers

Tools required: PubMed MCP tools (`search_articles`, `get_article_metadata`,
`get_full_text_article`, `find_related_articles`) when present; otherwise fall back to
`WebSearch` + `WebFetch` for PubMed/arXiv/publisher pages.

## Search tactics

- Start from the sub-question's clinical/technical concepts; combine as 2–3 PubMed
  queries (MeSH-style terms + free text). For methods/CS topics, add an arXiv pass via
  web search (`site:arxiv.org <terms>`).
- Respect the scope digest's time range; default to the last 5 years for clinical
  evidence unless the question is historical.
- **Citation chasing, one hop:** when one paper is clearly load-bearing, follow its
  references / related-articles once to find the primary evidence or a newer superseding
  study. Do not chase recursively.

## Evidence weighting

- Systematic reviews / meta-analyses / clinical guidelines > primary studies > preprints.
- Note the study type inline next to the claim ("a 2025 meta-analysis of 12 trials
  [S{nn}-2]"), so the writer can weight it without re-reading the paper.
- Preprints (arXiv, medRxiv) are citable but say so: "a preprint reports ...".

## Full text vs abstract

- Prefer full text for load-bearing claims (effect sizes, methods, limitations).
- A claim taken from an abstract alone, where the full text was inaccessible and the
  abstract is ambiguous, gets an `[uncertain U{nn}-k]` marker — the verify wave will
  attack it.

## Fragment capture

- `type: paper`. **Always capture `doi` and/or `pmid`** when the backend provides them —
  they drive deduplication now and BibTeX generation later.
- `title`: the paper title (not the journal page title). `accessed`: today.
- Cite the paper's canonical page (DOI URL or PubMed page), not an aggregator.
