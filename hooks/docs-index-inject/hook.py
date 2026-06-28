#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Claude Code SessionStart hook: inject a repo's docs index into context — opt-in.

This hook is registered ONCE (user-level `~/.claude/settings.json`) but only fires
in repos that explicitly opt in by committing a `.docs-index.toml` marker at their
root. Repos without the marker — no docs at all, or a `docs/` used for a website —
get nothing. That makes a single global registration safe across every project.

When a repo opts in, the hook runs the `docs-index` logic against the configured
docs dir and returns the map as `additionalContext`, so the agent knows which docs
exist — and when to read them — before writing any code.

Marker file (`.docs-index.toml`, all keys optional; an empty file means defaults):

    dir = "docs"                       # docs directory, relative to repo root
    exclude = ["archive", "research"]  # subdir names to skip

To stay DRY this reuses `scripts/docs-index/docs_index.py` as the single source of
truth. Unlike the CLI, it requires an explicit `summary` / `read_when` (no fallback
to `description`) so website frontmatter is never surfaced. It degrades silently:
no marker, no docs, a malformed marker, or no annotated docs → emits nothing, exit 0.

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

MARKER = ".docs-index.toml"
DOCS_INDEX = (
    Path(__file__).resolve().parents[2] / "scripts" / "docs-index" / "docs_index.py"
)


def find_marker(start: Path) -> Path | None:
    """Walk up from `start` looking for the opt-in marker; None if not opted in."""
    for directory in (start, *start.parents):
        candidate = directory / MARKER
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
    marker = find_marker(start)
    if marker is None:
        return 0  # repo has not opted in

    try:
        config = tomllib.loads(marker.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return 0  # malformed marker — fail open, no noise

    module = load_docs_index()
    if module is None:
        return 0  # docs-index source not found — fail open

    repo_root = marker.parent
    docs_rel = config.get("dir", "docs")
    docs_dir = repo_root / docs_rel
    if not docs_dir.is_dir():
        return 0  # marker points at a missing dir — stay quiet

    excludes = config.get("exclude")
    if not isinstance(excludes, list):
        excludes = list(module.DEFAULT_EXCLUDES)
    excludes = {str(item) for item in excludes}

    # Hook path: require explicit summary/read_when (no description fallback).
    entries = module.build_index(docs_dir, excludes, fallback_description=False)
    documented = [e for e in entries if e["summary"]]
    if not documented:
        return 0  # nothing annotated — stay quiet

    context = module.render_human(documented, Path(docs_rel))
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
