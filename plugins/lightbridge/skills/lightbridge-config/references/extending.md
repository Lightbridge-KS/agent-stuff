# Extending `.lightbridge`

The protocol for adding a new `config.toml` section. Follow it whenever we design a new
per-project config feature, so the catalog grows by a known recipe instead of ad hoc.

## Steps

1. **Build the reader.** A script (`scripts/<tool>/`) or hook (`hooks/<hook>/`) that parses
   `[<name>]` from the project's user-level config. Rules:
   - Resolve the config through `scripts/lightbridge/lightbridge.py` (`load_config`) — never
     reimplement root/key/config resolution, and never read from inside the repo.
   - Opt-in = section presence; honor `enabled = false`.
   - Fail open and quiet (no section / missing keys / malformed file → do nothing, exit 0).
   - A sensible default for every optional key.
2. **Register in [`catalog.md`](catalog.md).** Add a `### [<name>]` entry: purpose · reader
   (+ internals link) · opt-in rule · keys with defaults · notes.
3. **Add the emittable template** to `SECTIONS` in `scripts/lightbridge/lightbridge.py`
   (`purpose` · `reader` · `block` — the TOML `lb init` / `lb add` will write, with the
   default keys). Note the deliberate asymmetry: a feature's *reader* lives with the
   feature, but its *template* lives in the resolver, because that is what writes configs.
   `tests/test_lightbridge.py::test_sections_match_catalog` fails if you do step 2 or 3
   without the other.
4. **Sync the brief.** If it changes the cross-cutting story, add or adjust one line in
   `agent-instruction/AGENTS.qmd` (brief only — the catalog stays canonical), then `make build`.
5. **Version + validate.** Bump `SKILL.md` `metadata.version`; run `uv run bin/validate.py`
   and `uv run tests/test_lightbridge.py`.

## Invariants to preserve

- One file per project, user-level (`~/.lightbridge/projects/<key>/config.toml`) — never a
  file inside the repo; sections independent; opt-in by presence.
- One resolver: `scripts/lightbridge` owns root/key/config resolution — and, since it also
  writes configs, the section templates. Never hand-write a `config.toml`; run `lb init`.
- The skill links to feature internals — it never re-documents them.
- Bootstrap stays idempotent (never clobber a user's `config.toml`).
- No secrets/PHI in the tree (treat it as private regardless).
