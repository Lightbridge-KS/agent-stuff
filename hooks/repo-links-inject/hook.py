#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code SessionStart hook: inject the repo's ego view from the central graph.

This hook is registered ONCE (user-level `~/.claude/settings.json`) but only speaks
when BOTH user-level layers opt in — nothing lives inside the repo:

  1. The machine's graph — `~/.lightbridge/graph.toml` declares typed edges between
     logical repo names (one edge per relationship; spec: the repo-graph skill).
  2. The machine's registry — `~/.lightbridge/repos.toml` maps those names to local
     paths. No graph file → the hook stays completely silent.

When both are present and the session's repo is a registered node, the agent gets a
compact "Linked repos" map — outgoing edges with absolute paths, full backlinks
labeled with each type's inverse, and one compact "Also referenced by" line — and
any dead name, stale path, or undeclared type surfaces as a WARNING line.

Graph resolution is owned by `scripts/lightbridge/lb_resolve.py` (`load_graph`,
`project_node`); path verification and rendering by `scripts/repo-links/
repo_links.py` — both imported, single source of truth. It degrades silently: no
graph, repo not registered, zero incident edges, or no registry on this machine →
emits nothing, exit 0. A malformed graph/registry CAN only happen on the owner's
machine, so that one warning is injected. Two deprecation nudges ride along: a
stray pre-migration `<repo>/.lightbridge/config.toml`, and a leftover pre-graph
`[repo-links]` section in the project's user-level config.

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
LIGHTBRIDGE = SCRIPTS / "lightbridge" / "lb_resolve.py"


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


def emit_joined(*parts: str | None) -> int:
    """Emit the non-empty parts joined by a blank line; stay silent when none."""
    text = "\n\n".join(part for part in parts if part)
    if text:
        emit(text)
    return 0


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

    # Deprecation nudges (independent of whether the graph renders anything).
    legacy = lb.legacy_config(start)
    legacy_note = lb.legacy_warning(legacy) if legacy else None
    config, config_path, _error = lb.load_config(start)
    section_note = (
        module.section_warning(config_path)
        if isinstance(config, dict) and isinstance(config.get("repo-links"), dict)
        else None
    )

    graph_path = Path(module.DEFAULT_GRAPH).expanduser()
    graph, graph_error = lb.load_graph(graph_path)
    if graph is None and graph_error is None:
        return emit_joined(section_note, legacy_note)  # not opted in on this machine
    if graph_error is not None:
        # A graph file can only exist on the owner's machine — rot must show.
        return emit_joined(
            f"Linked repos (.lightbridge graph): WARNING — {graph_path} is {graph_error}.",
            section_note,
            legacy_note,
        )

    registry_path = Path(module.DEFAULT_REGISTRY).expanduser()
    registry, registry_error = lb.load_registry(registry_path)
    if registry is None and registry_error is None:
        return emit_joined(
            f"Linked repos (.lightbridge graph): WARNING — the graph exists but "
            f"{registry_path} is absent; names cannot resolve to paths.",
            section_note,
            legacy_note,
        )
    if registry_error is not None:
        return emit_joined(
            module.render_human(
                {"out": [], "backlinks": [], "mentions": [], "warnings": []},
                registry_error,
            ),
            section_note,
            legacy_note,
        )

    node = module.node_for_root(lb.repo_root(start), registry)
    if node is None:
        return emit_joined(section_note, legacy_note)  # repo not registered — quiet

    view = module.build_view(graph, node, registry, lb)
    if not (view["out"] or view["backlinks"] or view["mentions"]):
        return emit_joined(section_note, legacy_note)  # a node with no edges — quiet

    return emit_joined(module.render_human(view), section_note, legacy_note)


if __name__ == "__main__":
    sys.exit(main())
