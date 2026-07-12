#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse(ExitPlanMode) — file the approved plan into ~/.lightbridge.

`PostToolUse` fires *iff* the tool executed, and `ExitPlanMode` only executes when the plan
was approved. So this hook IS the approval signal: rejecting a plan ("keep planning with
feedback") never runs the tool, and nothing is filed. That single fact is what
`~/.claude/plans/` — which keeps every draft, approved or not — cannot tell you.

Opt-in: the project's lightbridge config has a `[plans]` section (`lb add plans`).
No section → silent no-op.

All the work lives in `scripts/plan-store`; this is just the wire.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_STORE = Path(__file__).resolve().parents[2] / "scripts" / "plan-store" / "plan_store.py"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, ValueError):
        return 0  # fail open — a hook must never break a session

    try:
        spec = importlib.util.spec_from_file_location("plan_store", _STORE)
        store = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(store)
        store.capture(payload)
    except Exception:  # noqa: BLE001 — fail open and quiet, whatever went wrong
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
