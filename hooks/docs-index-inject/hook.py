#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Claude Code SessionStart hook: inject a repo's docs index into context — opt-in.

This hook is registered ONCE (user-level `~/.claude/settings.json`) but only fires
in repos that explicitly opt in via a `[docs-index]` section in a committed
`.lightbridge/config.toml`. Repos without that section — no docs at all, or a
`docs/` used for a website — get nothing. A single global registration is therefore
safe across every project.

When a repo opts in, the hook runs the `docs-index` logic against the configured
docs dir and returns the map as `additionalContext`, so the agent knows which docs
exist — and when to read them — before writing any code.

`.lightbridge/config.toml` (all keys optional except the section's presence):

    [docs-index]              # presence of this section = opt in
    enabled = true            # optional; default true. Set false to disable.
    dir = "docs"              # docs directory, relative to repo root
    exclude = ["archive", "research"]
    include = ["CONTEXT.md", "CONTEXT-MAP.md"]  # extra root-level files outside `dir`

To stay DRY this reuses `scripts/docs-index/docs_index.py` as the single source of
truth. Unlike the CLI, it requires an explicit `summary` / `read_when` (no fallback
to `description`) so website frontmatter is never surfaced. Besides the docs `dir` it
also indexes the `include` files (default `CONTEXT.md` / `CONTEXT-MAP.md`), rendered as
a separate "Domain context (repo root)" group; missing ones are skipped, so a repo with
CONTEXT files but no docs dir still gets a map. It degrades silently: no config, no
`[docs-index]` section, `enabled = false`, nothing annotated, or malformed config →
emits nothing, exit 0.

Input  (stdin JSON, from Claude Code): { "cwd": "...", "hook_event_name": "SessionStart", ... }
Output (stdout JSON): { "hookSpecificOutput": { "additionalContext": "..." } }  or nothing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tomllib
from pathlib import Path

CONFIG_REL = Path(".lightbridge") / "config.toml"
DOCS_INDEX = (
    Path(__file__).resolve().parents[2] / "scripts" / "docs-index" / "docs_index.py"
)


def find_config(start: Path) -> Path | None:
    """Walk up from `start` for a `.lightbridge/config.toml`; None if not found."""
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_REL
        if candidate.is_file():
            return candidate
    return None


def load_docs_index():
    """Import the docs_index module from its file path (single source of truth)."""
    spec = importlib.util.spec_from_file_location("docs_index", DOCS_INDEX)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    start = Path(payload.get("cwd") or os.getcwd())
    config_path = find_config(start)
    if config_path is None:
        return 0  # repo has no .lightbridge/config.toml

    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return 0  # malformed config — fail open, no noise

    section = config.get("docs-index")
    if not isinstance(section, dict) or section.get("enabled", True) is False:
        return 0  # not opted in (no section) or explicitly disabled

    module = load_docs_index()
    if module is None:
        return 0  # docs-index source not found — fail open

    repo_root = config_path.parent.parent  # the dir containing .lightbridge/
    docs_rel = section.get("dir", "docs")
    docs_dir = repo_root / docs_rel

    excludes = section.get("exclude")
    if not isinstance(excludes, list):
        excludes = list(module.DEFAULT_EXCLUDES)
    excludes = {str(item) for item in excludes}

    # Hook path: require explicit summary/read_when (no description fallback).
    documented: list[dict] = []
    omitted = 0
    if docs_dir.is_dir():
        entries = module.build_index(docs_dir, excludes, fallback_description=False)
        documented = [e for e in entries if e["summary"]]
        omitted = len(entries) - len(documented)

    # Extra root-level files outside the docs dir (default: CONTEXT.md / CONTEXT-MAP.md).
    include = section.get("include")
    if not isinstance(include, list):
        include = ["CONTEXT.md", "CONTEXT-MAP.md"]
    include = [str(item) for item in include]
    extra = module.index_files(repo_root, include, fallback_description=False)
    extra_documented = [e for e in extra if e["summary"]]

    if not documented and not extra_documented:
        return 0  # nothing annotated — stay quiet

    context = module.render_human(
        documented, Path(docs_rel), omitted=omitted, extra=extra_documented or None
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
