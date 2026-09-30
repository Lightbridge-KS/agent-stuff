#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SessionStart hook: say which fleet nodes lag this repo's `origin/main` — hub only.

Registered ONCE (user-level settings) but fires only for repos that opt in with a
`[fleet]` section in their user-level lightbridge config, and only on a machine that
holds a fleet inventory (`~/.lightbridge/fleet.toml` — the hub). Everywhere else it is
silent, so one global registration is safe.

**Network-free by contract.** It compares each node's last `lb fleet sync` receipt
(`~/.lightbridge/fleet/<node>.json`, `repos.<repo>.after`) against the local
`origin/main` ref — two or three local git calls, no fetch, no ssh. The receipt is the
hub's memory, not the node's truth: the injected line is a nudge to *offer*
`lb fleet sync`, which the agent must not run without the user's go-ahead; `lb fleet
status` verifies live first.

Config (all keys optional except the section's presence):

    [fleet]                  # presence = opt in
    enabled = true           # optional; default true
    repo = "agent-stuff"     # optional; the [repos.<name>] this checkout is. Default:
                             # the repo folder's name.

Input  (stdin JSON): { "cwd": "...", "hook_event_name": "SessionStart", ... }
Output (stdout JSON): { "hookSpecificOutput": { "additionalContext": "..." } }  or nothing.
Fails open and quiet on every error (ADR 0004; `CLAUDE.md` hooks contract).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
LIGHTBRIDGE = SCRIPTS / "lightbridge" / "lb_resolve.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def emit(context: str) -> None:
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
        )
    )


def git(repo: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def run() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    start = Path(payload.get("cwd") or os.getcwd())

    lb = load_module("lightbridge", LIGHTBRIDGE)
    if lb is None:
        return 0

    config, _config_path, error = lb.load_config(start)
    if config is None or error is not None:
        return 0
    section = config.get("fleet")
    if not isinstance(section, dict) or section.get("enabled", True) is False:
        return 0

    fleet_path = Path(lb.DEFAULT_FLEET).expanduser()
    fleet, _fleet_error = lb.load_fleet(fleet_path)
    if fleet is None:
        return 0  # not a hub (or an unusable inventory — `lb fleet status` will say so)

    root = lb.repo_root(start)
    configured = section.get("repo")
    repo = configured.strip() if isinstance(configured, str) and configured.strip() else root.name
    if repo not in fleet["repos"]:
        return 0
    nodes = [name for name, spec in fleet["nodes"].items() if repo in spec["repos"]]
    if not nodes:
        return 0

    origin_main = git(root, "rev-parse", "--verify", "--quiet", "origin/main")
    if not origin_main:
        return 0

    lines: list[str] = []
    receipts_dir = lb.fleet_receipts_dir(fleet_path)
    for node in nodes:
        receipt, _receipt_error = lb.load_receipt(receipts_dir / f"{node}.json")
        entry = (receipt or {}).get("repos", {}).get(repo) if receipt else None
        after = entry.get("after") if isinstance(entry, dict) else None
        if not after:
            lines.append(f"`{node}` has never been synced for `{repo}` from this hub.")
            continue
        if after == origin_main:
            if receipt is not None and receipt.get("ok") is False:
                lines.append(f"`{node}` is at origin/main for `{repo}`, but its last sync reported problems (receipt: {node}.json).")
            continue
        count = git(root, "rev-list", "--count", f"{after}..{origin_main}")
        distance = f"{count} commit(s) ahead" if count and count.isdigit() else "distance unknown"
        lines.append(
            f"`{node}` last synced `{repo}` at {after[:7]}; origin/main is {origin_main[:7]} "
            f"as of the last local fetch ({distance})."
        )
    if not lines:
        return 0

    context = (
        "Fleet lag (hub-and-spoke sync of the agent repos; spec: the fleet-sync skill):\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nOffer `lb fleet sync <node>` — it changes the node, so it needs the user's "
        "go-ahead; `lb fleet status` verifies live first."
    )
    emit(context)
    return 0


def main() -> int:
    try:
        return run()
    except Exception:  # noqa: BLE001 — a hook that cries wolf gets ignored; stay silent
        return 0


if __name__ == "__main__":
    sys.exit(main())
