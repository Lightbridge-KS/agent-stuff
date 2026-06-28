# Extending `.lightbridge/`

The protocol for adding a new `config.toml` section. Follow it whenever we design a new
per-repo config feature, so the catalog grows by a known recipe instead of ad hoc.

## Steps

1. **Build the reader.** A script (`scripts/<tool>/`) or hook (`hooks/<hook>/`) that parses
   `[<name>]` from `.lightbridge/config.toml`. Rules:
   - Opt-in = section presence; honor `enabled = false`.
   - Fail open and quiet (no section / missing keys / malformed file → do nothing, exit 0).
   - A sensible default for every optional key.
2. **Register in [`catalog.md`](catalog.md).** Add a `### [<name>]` entry: purpose · reader
   (+ internals link) · opt-in rule · keys with defaults · notes.
3. **Add a template block** to [`../assets/config.toml`](../assets/config.toml) — commented,
   with the default keys.
4. **Sync the brief.** If it changes the cross-cutting story, add or adjust one line in
   `agent-instruction/AGENTS.qmd` (brief only — the catalog stays canonical), then `make build`.
5. **Version + validate.** Bump `SKILL.md` `metadata.version`; run `uv run bin/validate.py`.

## Invariants to preserve

- One file; sections independent; opt-in by presence.
- The skill links to feature internals — it never re-documents them.
- Bootstrap stays idempotent (never clobber a user's `config.toml`).
- No secrets/PHI in `.lightbridge/` (repos may be public).
