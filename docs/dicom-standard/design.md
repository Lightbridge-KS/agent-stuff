---
summary: Settled design for the `dicom-standard` skill (plugins/radiology) — the DICOM standard
  (PS3.1–PS3.22) mirrored from NEMA's per-part DocBook XML into ~/.lightbridge/data/dicom-standard/,
  indexed into SQLite (structure + FTS5), and queried through the bundled deterministic CLI
  (scripts/dicom_std.py) — status / pull / toc / show / table / search / tag — with an edition +
  canonical URL on every answer. Source facts, cache layout, index schema, renderer and table-grid
  rules, ref grammar, exit codes, and what is deliberately out.
read_when:
  - implementing or changing plugins/radiology/skills/dicom-standard (SKILL.md, dicom_std.py, parts.md)
  - deciding whether a DICOM question belongs here or in dcmtk / orthanc-api / deidentify
  - adding a verb, a DocBook element to the renderer, a new part, or an edition-diff feature
  - wondering why the skill mirrors DocBook XML rather than scraping HTML or using a JSON dump
---

# `dicom-standard` — design

Approved 2026-10-17 (KS). Tracker: [`progress/v1.md`](progress/v1.md).

## Problem

Agents answer DICOM-standard questions from memory, and memory drifts: NEMA publishes about
five editions a year (2026d on 2026-09-21), and the facts that matter in a radiology AI unit —
the de-identification actions of PS3.15 Table E.1-1, a tag's VR, which attributes a module
requires — are exactly the ones that change in small ways. The first use case: *"query PS3.15
Annex E to obtain up-to-date info"*, reproducibly and with a citation.

## Decision

Mirror the standard's **DocBook XML source** (one file per part, the same source NEMA renders
its HTML/PDF from), index it into **SQLite + FTS5**, and expose it through a **bundled
deterministic CLI** the skill drives. Facts live in the cache, never in the skill text, so the
skill does not age; the agent supplies the judgment (which part, which section, how to read a
cell) and quotes the `source:` line.

| Alternative | Why not |
|---|---|
| Scrape the chtml/HTML | Derived and lossy; the DocBook is what generates it and carries the stable ids. |
| innolitics `dicom-standard` JSON | PS3.3/3.4/3.6 only, lags editions, no PS3.15. |
| pydicom's dictionary | PS3.6 only, pinned to the library release. |
| PDF | No structure. |
| An MCP server | A CLI is harness-neutral (Claude Code, Codex, Pi); an MCP wrapper can come later. |
| Embeddings / semantic search | Deferred: the TOC gives the agent structure and FTS5 finds the rest; same keyword-first rule as `gitcrawl`. |

## Source facts (verified 2026-10-17)

- Per-part XML: `https://dicom.nema.org/medical/dicom/current/source/docbook/part{NN}/part{NN}.xml`,
  NN ∈ {01 02 03 04 05 06 07 08 10 11 12 14 15 16 17 18 19 20 21 22}. Server returns `ETag`,
  `Last-Modified`, `Accept-Ranges: bytes`, `Cache-Control: max-age=1y`.
- Superseded editions keep pinned paths (`/medical/dicom/2025b/source/docbook/…`); the live
  edition exists **only** under `current` (its pinned path is 404 until superseded).
- Edition string in `<book><subtitle>DICOM PS3.15 2026d - …</subtitle>`.
- DocBook 5: annexes are `<chapter label="E">`; `<glossary>`/`<bibliography>` are book-level;
  tables are HTML-style (`<thead>/<tbody>/<tr>/<td>` with explicit `colspan`/`rowspan`, empty
  cells self-closed, every `<td>` wrapping `<para>`); `<xref linkend>` intra-part,
  `<olink targetdoc="PS3.6" targetptr="sect_6">` cross-part; figures reference SVGs.
- Sizes: PS3.16 54 MB, PS3.3 24 MB, PS3.17 15 MB, PS3.6 9 MB, PS3.15 3.4 MB, total ~124 MB.
  Observed ~55 KB/s from the hub Mac, so pulls are resumable and lazy.
- Table E.1-1 (2026d): 657 body rows × 15 columns. Table E.1-1a has no `<thead>` (columns
  synthesized `col1`, `col2`) — the only such table in PS3.15.

## Cache (`~/.lightbridge/data/dicom-standard/`, `DICOM_STD_HOME` overrides)

```
manifest.json                    schema_version, per part: edition, path, url, fetched_at, etag,
                                 last_modified, sha256, bytes
editions/<edition>/partNN.xml    raw DocBook, immutable; one dir per edition, superseded editions kept
incoming/partNN.xml.part + .meta.json   resume state (url, etag, length); gone after a complete pull
index.sqlite                     derived; one row set per part = the edition in the manifest
```

Registered in the lightbridge catalog as the first `data/<dataset>/` subtree. Public text, no
PHI; safe to delete and re-pull.

## CLI contract

| Verb | Behaviour |
|---|---|
| `status [--max-age-days 90]` | per-part edition/age/index; exit 1 when stale or editions mixed; empty cache is exit 0 |
| `pull [PART…] [--all] [--edition X] [--check] [--force]` | HEAD → skip when ETag unchanged; Range resume (206 append / 200 restart / 416 complete); size checked against `Content-Length`; progress to stderr ≥ 1 s; edition pre-pass from `<subtitle>`; `os.replace` into `editions/<ed>/`; manifest, then index. `--check` = HEAD only (exit 1 on change). 404 on a pinned edition names the `current`-only rule |
| `toc PART [--under REF] [--depth 2]` | outline; tables as `[table rows×cols]`, figures `[figure]` |
| `show REF [--max-chars 12000] [--depth 0]` | own blocks + `Subsections:` list; tables ≤ 8×4 inline else a `→ table` pointer; truncation at a line boundary; last line `source:` |
| `table REF [--where col=val \| col~re]… [--columns] [--format md\|json\|csv] [--limit 50]` | AND of filters; `=` exact case-insensitive, `~` regex search; column keys lowercase alnum, exact else unique substring else exit 2 listing columns |
| `search QUERY [--part]… [--kind section\|table\|row] [--limit 20]` | FTS5 MATCH, BM25; FTS syntax error → every token quoted and retried; row hits print `PART:table_X#rowN` |
| `tag (gggg,eeee)\|Keyword` | PS3.6 `dict` row (wildcard groups `(60xx,…)` matched) + PS3.15 E.1-1 actions when cached |

Exit codes: `0` ok · `1` stale / not cached / not found (well-formed) · `2` fix the request ·
`3` network or environment. **Read verbs never touch the network**; `--pull` opts in.
`source:` = `DICOM PS3.<n> <edition> — <url fetched from>/output/chtml/part<NN>/<chapter_id>.html#<id>`.

Refs: `^(?:PS3\.)?(\d{1,2}):(.+)$`; tail with a known prefix (`sect_`, `table_`, `figure_`,
`chapter_`, `para_`, `biblio_`, `glossary`, `bibliography`) is used as-is; `^[A-Z]$|^\d+$` →
`chapter_X`; contains `-` → `table_X` then `figure_X`; contains `.` → `sect_X`; else prefix
probes then label lookup.

## Index (SCHEMA_VERSION 1, WAL, checkpointed after each part)

`parts(part PK, edition, sha256, schema_version, indexed_at)` ·
`nodes(part,id PK; kind chapter|section|table|figure|glossary|bibliography, label, title,
parent_id, chapter_id, ord, depth)` · `blocks(part,node_id,ord PK; kind, text_md)` ·
`tables(part,id PK; caption, columns_json [{name,key}], nrows)` · `rows(part,table_id,ord PK;
cells_json)` · `dict(part,tag PK; name, keyword, vr, vm, retired, source_table)` (PS3.6 only) ·
`docs(rowid; part, node_id, kind section|table|row, label, title, body)` + `docs_fts`
(external-content FTS5 over title/body, `unicode61 remove_diacritics 2`, insert/delete
triggers).

- One edition per part in the index (the manifest's); pulling a new edition deletes the part's
  rows and re-inserts in one transaction. Older editions remain as raw XML for a future `diff`.
- Reconciliation on open: a part whose `sha256`/`schema_version` differs from the manifest is
  reindexed from its cached XML (no network); parts no longer in the manifest are dropped.
- Parsing: `lxml.iterparse` on `chapter|appendix|preface|glossary|bibliography` end events
  with `huge_tree=True`; each top-level element is walked then cleared, so peak memory is one
  chapter (PS3.15: 75 MB RSS end-to-end).
- Cross-refs are stored as `[[ref:PART:id]]` placeholders and resolved at display time from the
  DB (`§E.1.1 De-identifier (15:sect_E.1.1)`; part not cached → `PS3.6 sect_6 (6:sect_6)`);
  FTS bodies get the lookup-free `plain_ref` form (`Table E.1-1`).

## Renderer and table grid

- Whitelist renderer: `para` · `emphasis` (`**bold**`, `*other*`) · lists (`-`, `1.`, nested
  by two spaces) · `variablelist` (`- **term**: …`) · `note`/`warning`/… (`> **Note:** …`) ·
  `programlisting` (fenced) · `link` · `xref`/`olink` (placeholders) · `figure`
  (`[Figure 7-1: title — image not cached]`) · `glossentry` · `biblioentry`. Unknown elements
  render their children and are counted; `pull` prints the count to stderr (the structural-
  surprise detector for PS3.3/16). Block elements met inline (a list inside a table cell) are
  flattened to one line. MathML (`inlineequation`, `m:math`…) renders as the formula's plain text.
  Bibliographic inlines (`authorgroup`, `issuenum`, …) are known, not counted.
- Table cells are **plain text** (no Markdown markers): data, not prose. Zero-width spaces
  (PS3.6 keywords) are stripped everywhere.
- Grid: HTML span algorithm → dense grid, `colspan` repeats across, `rowspan` fills down,
  empty cell `""`; multi-row `<thead>` joins per column with ` / `. Column `key` = lowercase
  alnum of the name, de-duplicated with `_2`. Rationale: filters need `len(cells) == ncols`
  with stable positions, and PS3.3 module tables use spans — so an `Include Table 10-18` row
  shows that text in every column (verified on PS3.3 2026d).
- `dict`: PS3.6 tables whose first column is Tag and that have Keyword + VR columns; tag
  normalised `(GGGG,EEEE)` keeping `x` wildcards; retired when a trailing cell starts `RET`.

## Out of scope (v1)

Figures and images; semantic search; a `diff <edition> <edition>` verb (the per-edition raw
XML is the prerequisite); an MCP wrapper; a SessionStart freshness nudge (pull-side only, as
with `gitcrawl`); PS3.9 and PS3.13 (retired, no DocBook).
