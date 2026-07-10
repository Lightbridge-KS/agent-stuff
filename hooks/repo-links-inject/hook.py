#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code SessionStart hook: inject a repo's resolved cross-repo links — opt-in twice.

This hook is registered ONCE (user-level `~/.claude/settings.json`) but only speaks
when BOTH layers opt in:

  1. The repo — a `[repo-links]` section in its committed `.lightbridge/config.toml`
     declares links by logical NAME (never a path).
  2. The machine — a personal `~/.lightbridge/repos.toml` maps those names to local
     paths. No registry file → the hook stays completely silent, so the committed
     section imposes nothing on a colleague's machine.

When both are present, each link is resolved and VERIFIED: the agent gets a compact
"Linked repos" map with absolute paths, and any dead name or stale path surfaces as
a WARNING line — the rot detector hand-maintained `CLAUDE.local.md` paths never had.

To stay DRY this reuses `scripts/repo-links/repo_links.py` as the single source of
truth. It degrades silently: no config, malformed config, no `[repo-links]` section,
`enabled = false`, zero declared links, or no registry on this machine → emits
nothing, exit 0. A registry that exists but is unreadable (or lacks its `[repos]`
table) CAN only happen on the owner's machine, so that one warning is injected.

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

REPO_LINKS = (
    Path(__file__).resolve().parents[2] / "scripts" / "repo-links" / "repo_links.py"
)


def load_repo_links():
    """Import the repo_links module from its file path (single source of truth)."""
    spec = importlib.util.spec_from_file_location("repo_links", REPO_LINKS)
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

    module = load_repo_links()
    if module is None:
        return 0  # repo-links source not found — fail open

    start = Path(payload.get("cwd") or os.getcwd())
    config_path = module.find_config(start)
    if config_path is None:
        return 0  # repo has no .lightbridge/config.toml

    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return 0  # malformed config — fail open, no noise

    section = config.get("repo-links")
    if not isinstance(section, dict) or section.get("enabled", True) is False:
        return 0  # not opted in (no section) or explicitly disabled

    links, config_warnings = module.parse_links(section)
    if not links and not config_warnings:
        return 0  # nothing declared — stay quiet

    registry_path = Path(module.DEFAULT_REGISTRY).expanduser()
    registry, registry_error = module.load_registry(registry_path)
    if registry is None and registry_error is None:
        return 0  # no personal registry — a colleague's machine; committed config imposes nothing

    if registry_error is not None:
        context = module.render_human(links, registry_error=registry_error)
    else:
        resolved = module.resolve_links(links, registry)
        context = module.render_human(resolved, config_warnings)

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
