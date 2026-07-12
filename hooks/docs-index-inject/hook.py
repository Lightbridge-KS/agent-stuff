#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Claude Code SessionStart hook: inject a repo's docs index into context — opt-in.

This hook is registered ONCE (user-level `~/.claude/settings.json`) but only fires
for projects that explicitly opt in via a `[docs-index]` section in their user-level
config, `~/.lightbridge/projects/<project-key>/config.toml` (the "local scope" model
— nothing lives inside the repo). Projects without that section — no docs at all, or
a `docs/` used for a website — get nothing. A single global registration is therefore
safe across every project.

When a project opts in, the hook runs the `docs-index` logic against the configured
docs dir and returns the map as `additionalContext`, so the agent knows which docs
exist — and when to read them — before writing any code.

Config (all keys optional except the section's presence):

    root = "/abs/path/to/repo"  # staleness marker for `lightbridge doctor`
    [docs-index]              # presence of this section = opt in
    enabled = true            # optional; default true. Set false to disable.
    dir = "docs"              # docs directory, relative to repo root
    exclude = ["archive", "research"]
    include = ["CONTEXT.md", "CONTEXT-MAP.md"]  # extra root-level files outside `dir`

Config resolution (repo root via git toplevel, project-key encoding) is owned by
`scripts/lightbridge/lightbridge.py`; the index logic by `scripts/docs-index/
docs_index.py` — both imported, single source of truth. Unlike the CLI, this hook
requires an explicit `summary` / `read_when` (no fallback to `description`) so website
frontmatter is never surfaced. Besides the docs `dir` it also indexes the `include`
files (default `CONTEXT.md` / `CONTEXT-MAP.md`), rendered as a separate "Domain
context (repo root)" group; missing ones are skipped, so a repo with CONTEXT files but
no docs dir still gets a map. It degrades silently: no config, no `[docs-index]`
section, `enabled = false`, nothing annotated, or malformed config → emits nothing,
exit 0. A stray pre-migration `<repo>/.lightbridge/config.toml` (no longer read) earns
a one-line deprecation warning.

Input  (stdin JSON, from Claude Code): { "cwd": "...", "hook_event_name": "SessionStart", ... }
Output (stdout JSON): { "hookSpecificOutput": { "additionalContext": "..." } }  or nothing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
DOCS_INDEX = SCRIPTS / "docs-index" / "docs_index.py"
LIGHTBRIDGE = SCRIPTS / "lightbridge" / "lightbridge.py"


def load_module(name: str, path: Path):
    """Import a module from its file path (single source of truth)."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def emit(context: str) -> None:
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


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    start = Path(payload.get("cwd") or os.getcwd())
    lb = load_module("lightbridge", LIGHTBRIDGE)
    if lb is None:
        return 0  # resolver source not found — fail open

    config, _config_path, error = lb.load_config(start)
    legacy = lb.legacy_config(start)
    warning = lb.legacy_warning(legacy) if legacy else None

    if config is None or error is not None:
        # No config for this project (or unreadable — fail open, no noise). Still
        # surface the migration nudge if a stray per-repo file exists.
        if warning:
            emit(warning)
        return 0

    section = config.get("docs-index")
    if not isinstance(section, dict) or section.get("enabled", True) is False:
        if warning:
            emit(warning)
        return 0  # not opted in (no section) or explicitly disabled

    module = load_module("docs_index", DOCS_INDEX)
    if module is None:
        return 0  # docs-index source not found — fail open

    repo_root = lb.repo_root(start)
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
        if warning:
            emit(warning)
        return 0  # nothing annotated — stay quiet

    context = module.render_human(
        documented, Path(docs_rel), omitted=omitted, extra=extra_documented or None
    )
    if warning:
        context = f"{context}\n\n{warning}"
    emit(context)
    return 0


if __name__ == "__main__":
    sys.exit(main())
