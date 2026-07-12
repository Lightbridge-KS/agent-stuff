#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code SessionStart hook: inject a repo's resolved cross-repo links — opt-in twice.

This hook is registered ONCE (user-level `~/.claude/settings.json`) but only speaks
when BOTH user-level layers opt in — nothing lives inside the repo:

  1. The project — a `[repo-links]` section in its user-level config,
     `~/.lightbridge/projects/<project-key>/config.toml`, declares links by logical
     NAME (never a path).
  2. The machine — a personal `~/.lightbridge/repos.toml` maps those names to local
     paths. No registry file → the hook stays completely silent.

When both are present, each link is resolved and VERIFIED: the agent gets a compact
"Linked repos" map with absolute paths, and any dead name or stale path surfaces as
a WARNING line — the rot detector hand-maintained `CLAUDE.local.md` paths never had.

Config resolution is owned by `scripts/lightbridge/lightbridge.py`; the link logic by
`scripts/repo-links/repo_links.py` — both imported, single source of truth. It
degrades silently: no config, malformed config, no `[repo-links]` section,
`enabled = false`, zero declared links, or no registry on this machine → emits
nothing, exit 0. A registry that exists but is unreadable (or lacks its `[repos]`
table) CAN only happen on the owner's machine, so that one warning is injected. A
stray pre-migration `<repo>/.lightbridge/config.toml` (no longer read) earns a
one-line deprecation warning.

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
REPO_LINKS = SCRIPTS / "repo-links" / "repo_links.py"
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

    module = load_module("repo_links", REPO_LINKS)
    lb = load_module("lightbridge", LIGHTBRIDGE)
    if module is None or lb is None:
        return 0  # source not found — fail open

    start = Path(payload.get("cwd") or os.getcwd())
    config, _config_path, error = lb.load_config(start)
    legacy = lb.legacy_config(start)
    warning = lb.legacy_warning(legacy) if legacy else None

    if config is None or error is not None:
        # No config for this project (or unreadable — fail open, no noise). Still
        # surface the migration nudge if a stray per-repo file exists.
        if warning:
            emit(warning)
        return 0

    section = config.get("repo-links")
    if not isinstance(section, dict) or section.get("enabled", True) is False:
        if warning:
            emit(warning)
        return 0  # not opted in (no section) or explicitly disabled

    links, config_warnings = module.parse_links(section)
    if not links and not config_warnings:
        if warning:
            emit(warning)
        return 0  # nothing declared — stay quiet

    registry_path = Path(module.DEFAULT_REGISTRY).expanduser()
    registry, registry_error = module.load_registry(registry_path)
    if registry is None and registry_error is None:
        if warning:
            emit(warning)
        return 0  # no personal registry on this machine — stay quiet

    if registry_error is not None:
        context = module.render_human(links, registry_error=registry_error)
    else:
        resolved = module.resolve_links(links, registry)
        context = module.render_human(resolved, config_warnings)

    if warning:
        context = f"{context}\n\n{warning}"
    emit(context)
    return 0


if __name__ == "__main__":
    sys.exit(main())
