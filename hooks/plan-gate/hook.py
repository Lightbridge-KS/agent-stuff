#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse(ExitPlanMode) — opt-in auto-approve for Claude Code's plan gate.

When `[plans].auto_approve = true`, emit `permissionDecision: "allow"` so the plan-approval
dialog never renders and execution proceeds straight from the plan. Anything else — no
config, no section, `enabled = false`, `auto_approve` absent or false — stays SILENT, which
leaves the native dialog exactly as it was.

Default off, deliberately. Bypassing the gate costs you three things:
  1. "Keep planning with feedback" — the only way to iterate a plan before it runs.
  2. The post-approval mode choice (auto / acceptEdits / review-each-edit).
  3. The last human checkpoint before writes.
If you only wanted plan mode's *exploration* side effect, don't enter plan mode at all —
ask for the grounding directly ("explore with subagents first, then implement").

Verified on Claude Code 2.1.207: `allow` bypasses the dialog in an interactive session.
(The docs claim this needs headless `-p`; it does not, and `ExitPlanMode` is not even
offered under `-p`. Behavior here is from a live rig, not the docs.)
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_LIGHTBRIDGE = Path(__file__).resolve().parents[2] / "scripts" / "lightbridge" / "lightbridge.py"
SECTION = "plans"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, ValueError):
        return 0  # fail open — silence means "use the normal dialog"

    try:
        spec = importlib.util.spec_from_file_location("lightbridge", _LIGHTBRIDGE)
        lb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lb)

        cwd = Path(payload.get("cwd") or ".").expanduser()
        config, _path, error = lb.load_config(cwd)
        if error or not config:
            return 0
        section = config.get(SECTION)
        if not isinstance(section, dict) or section.get("enabled", True) is False:
            return 0
        if section.get("auto_approve", False) is not True:
            return 0  # the default path: say nothing, let the human decide
    except Exception:  # noqa: BLE001 — any failure falls back to the native gate
        return 0

    # `updatedInput` is required alongside `allow` for interaction-gated tools; echo the
    # plan through unchanged — we are approving it, not rewriting it.
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": "[plans].auto_approve = true (lightbridge)",
                    "updatedInput": payload.get("tool_input") or {},
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
