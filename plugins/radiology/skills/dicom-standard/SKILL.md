---
name: dicom-standard
description: >-
  Offline, citable DICOM standard (PS3.1–PS3.22): pull a part, then TOC, sections, filterable
  tables (E.1-1 de-identification, data dictionary), search, tag lookup.
metadata:
  version: "2026-10-17"
---

# DICOM standard (offline, citable)

Facts come from the cached standard, never from memory: with this skill loaded, a claim about
what DICOM says is backed by a `show`/`table`/`tag` call and quoted with its `source:` line.
You supply the judgment — which part to pull, which section answers the question, how to read
a table cell; the CLI is deterministic.

`<skill_dir>` = the directory this SKILL.md was read from. Every verb:

```bash
uv run <skill_dir>/scripts/dicom_std.py <verb> ...
```

## Workflow

1. `status` — what is cached, which edition, how old. Exit 1 = stale (> 90 days) or editions
   mixed; "no parts cached" is normal (lazy by design).
2. Pick the part: [references/parts.md](references/parts.md) maps questions to parts. Not
   cached → `pull <part>` (PS3.15 is 3.4 MB, seconds; PS3.3 24 MB and PS3.16 54 MB take
   10–20 min at the server's ~50 KB/s — run those `pull`s in the background and resume on
   interruption by re-running). The user said "current" / "up to date" → `pull <part>` again
   (conditional GET: no change, no download) or `pull --check` first.
3. Navigate: `toc PART --under <annex>` before any `show`; never `show` a whole chapter.
4. Read: `show PART:ID` for prose, `table PART:ID --where …` for a table (big tables are
   never dumped: filter or `--columns`), `search` when the location is unknown, `tag` for a
   data element.
5. Answer with the fact **and** the citation: copy the `source:` line (edition + URL) into the
   reply. If the edition is older than the user expects, say so and offer a `pull`.

## Verbs

| Verb | Does | Exit |
|---|---|---|
| `status [--max-age-days 90]` | cached parts, edition, age, index state | 1 stale or mixed |
| `pull [PART…] [--all] [--edition 2025b] [--check] [--force]` | fetch/refresh + index; `--check` = HEAD only, no download | 1 changed (`--check`) · 3 network |
| `toc PART [--under REF] [--depth 2]` | outline with ids; tables show `[table rows×cols]` | 1 not cached / no node |
| `show REF [--max-chars 12000] [--depth 0]` | section → Markdown; subsections listed, not inlined; tables ≤ 8×4 inline, bigger → pointer; last line `source:` | 1 not cached / no node |
| `table REF [--where "col=val"]… [--where "col~regex"]… [--columns a,b] [--format md\|json\|csv] [--limit 50]` | filtered rows; `--where` repeats = AND; column keys are lowercase alnum (`Basic Prof.` → `basicprof`, unique substring ok) | 2 unknown column / bad regex |
| `search QUERY [--part N]… [--kind section\|table\|row] [--limit 20]` | FTS5 across cached parts (sections, table captions, table rows), BM25-ranked | 1 no hits |
| `tag (gggg,eeee)\|Keyword` | PS3.6 entry (VR, VM, retired) + its PS3.15 E.1-1 de-identification actions when PS3.15 is cached | 1 unknown element |

Every verb takes `--json`. Read verbs are **offline**: a missing part exits 1 naming the `pull`
to run; add `--pull` to fetch first. Exit `2` = fix the request (ref syntax, column, regex) ·
`3` = network or environment (FTS5 missing, unwritable cache).

**Refs** are `PART:ID`: `15:E.1.1` (section), `15:E` (annex/chapter), `15:E.1-1` (table or
figure), `15:table_E.1-1` / `15:sect_E.1` (explicit ids as in the standard's HTML anchors),
`PS3.6:6-1`. `toc` and `search` print them ready to paste.

## Recipes

```bash
# De-identification: what does the Basic Profile do to a tag? (the PS3.15 Annex E use case)
dicom_std.py table 15:E.1-1 --where "tag=(0010,0010)"
dicom_std.py table 15:E.1-1 --where "attributename~Institution" --columns attributename,tag,basicprof,rtninstidopt
dicom_std.py table 15:E.1-1 --where "cleandescopt=C" --format csv --limit 0      # every attribute the Clean Descriptors option touches
dicom_std.py show 15:E.3.10                                                       # Retain Safe Private Option — the prose
dicom_std.py tag (0008,0050)                                                      # VR/VM + E.1-1 actions in one call

# Where is it?
dicom_std.py search "Patient Identity Removed" --part 15
dicom_std.py toc 15 --under E --depth 1

# Other parts
dicom_std.py pull 3 && dicom_std.py search "Patient Module" --part 3 --kind table   # IOD modules
dicom_std.py table 6:6-1 --where "keyword~^Study" --columns tag,keyword,vr          # dictionary slice
dicom_std.py table 5:A.4-1 --where "name~JPEG" 2>/dev/null || dicom_std.py toc 5 --under A --depth 1   # transfer syntaxes
```

Token hygiene: `toc` before `show`; `--limit`/`--columns` on tables; `--max-chars` on long
sections; `--json` when the result feeds another step.

## Citation rule

Every `show`/`table`/`tag` ends with `source: DICOM PS3.15 2026d — https://dicom.nema.org/…#id`.
Quote it. The edition string is the citation of record; the URL under `current/` shows the
live edition, which may be newer than the cached one — `status` tells which.

## Cache

`~/.lightbridge/data/dicom-standard/` (override with `DICOM_STD_HOME`): `manifest.json`
(edition, ETag, sha256 per part), `editions/<edition>/partNN.xml` (raw DocBook, one dir per
edition — superseded editions are kept for later comparison), `index.sqlite` (derived; rebuilt
from the XML without network when the schema changes). `pull --edition 2025b` fetches a
superseded edition from its pinned URL; the live edition exists only under `current`.

Not covered: figures (named, not cached), PS3.9 and PS3.13 (retired, not published as DocBook).
For DICOM *tooling* — files, DIMSE, REST — use the `dcmtk` and `orthanc-api` skills; this skill
is the text of the standard.
