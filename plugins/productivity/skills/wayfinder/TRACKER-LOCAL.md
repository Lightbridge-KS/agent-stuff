# Wayfinding operations — local markdown (`docs/wayfinder/`)

How a wayfinder map, its child tickets, blocking, claiming, and the frontier query are expressed as committed files in the repo — the frontier layer of the `docs/` repo-memory tree. The **map** is a file with one **child** file per ticket.

- **Map**: `docs/wayfinder/<effort>/map.md` — the Destination / Notes / Decisions-so-far / Fog body. Like every doc in `docs/`, it opens with `summary:` + `read_when:` frontmatter so the docs-index hook can surface it.
- **Child ticket**: `docs/wayfinder/<effort>/tickets/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `docs/wayfinder/<effort>/tickets/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.

Commit map and ticket changes as part of the session's normal git flow — the tracker is repo state, and concurrent sessions coordinate through it.

_Adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)._
