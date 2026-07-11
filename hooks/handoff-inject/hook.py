#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code / Codex SessionStart hook: announce the handoffs pushed at this repo.

Handoffs split on **delivery**. The *journal* (`handoffs/*.md`) is PULLED — the user says
"resume" and pickup runs because someone asked. The *inbox* (`handoffs/inbox/*.md`) is PUSHED:
another repo — or a scheduled/background session in this one — left something nobody asked for.
**Nothing prompts anyone to look.** Without this hook the artifact is a letter with no postman,
and a `breaking: true` flag nobody reads is worth nothing at all.

So this hook announces **the inbox, and only the inbox**. The journal is deliberately never
injected: it is pulled on demand, and surfacing it every session would fight the harness's own
context management — worse, it could resurrect a plan the session has already moved past. Push
must announce itself; pull is already announced by the user asking.

Note the hook does not classify anything. Delivery is decided at write time, by which directory
the handoff lands in, so this is a plain glob — no frontmatter parsing to work out whether an
item "counts". That is the point of the split.

To stay DRY this reuses `scripts/handoff/handoff.py` as the single source of truth. It degrades
silently in every direction: no `~/.lightbridge` state dir, no inbox for this repo, an empty
inbox, everything acknowledged, or an unparseable file → emits nothing, exit 0. A hook that
cries wolf is a hook that gets ignored, which is the exact failure it exists to prevent.

Input  (stdin JSON, from the agent): { "cwd": "...", "hook_event_name": "SessionStart", ... }
Output (stdout JSON): { "hookSpecificOutput": { "additionalContext": "..." } }  or nothing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

HANDOFF = Path(__file__).resolve().parents[2] / "scripts" / "handoff" / "handoff.py"


def load_handoff():
    """Import the handoff module from its file path (single source of truth)."""
    spec = importlib.util.spec_from_file_location("handoff", HANDOFF)
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

    module = load_handoff()
    if module is None:
        return 0  # handoff source not found — fail open

    cwd = Path(payload.get("cwd") or os.getcwd())
    state_dir = module.default_state_dir()
    if not state_dir.is_dir():
        return 0  # no lightbridge state on this machine — silent

    try:
        items = module.collect(cwd, state_dir)
    except OSError:
        return 0  # unreadable state — fail open, no noise

    unread = [item for item in items if not item["acked"]]
    if not unread:
        return 0  # nothing pushed here, or all acknowledged — stay quiet

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": module.render(unread),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
