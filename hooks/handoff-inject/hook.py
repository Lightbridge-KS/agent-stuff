#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code / Codex SessionStart hook: announce cross-repo handoffs addressed to this repo.

A **same-repo** handoff is *pulled* — the user says "resume" and pickup runs because someone
asked for it. A **cross-repo** handoff is *pushed*: repo A writes it into repo B's project-key
because A changed something B depends on. **Nothing prompts B to look.** Without this hook the
artifact is a letter with no postman — and a `breaking: true` flag that nobody reads is worth
nothing at all.

So this hook announces **only** cross-repo handoffs (`from:` present in the frontmatter) that
have not been acknowledged. Same-repo handoffs are deliberately never injected: they are pulled
on demand, and surfacing one every session would fight the harness's own context management —
worse, it could resurrect a plan the session has already moved past.

To stay DRY this reuses `scripts/handoff/handoff.py` as the single source of truth. It degrades
silently in every direction: no `~/.lightbridge` state dir, no handoffs dir for this repo, no
cross-repo handoffs, all acknowledged, or an unparseable file → emits nothing, exit 0. A hook
that cries wolf is a hook that gets ignored, which is the exact failure it exists to prevent.

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
