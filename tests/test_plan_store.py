#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for scripts/plan-store and the two plan hooks.

The load-bearing claims, each pinned by a test:

  - capture is opt-in — no `[plans]` section means no file, ever;
  - the approved text comes from the file at `planFilePath`, NOT `tool_input.plan`
    (the user can edit a plan in the approval dialog; the draft field goes stale);
  - `approval: auto|human` is derived from `auto_approve`, with no cross-hook state;
  - plan-gate stays SILENT unless `auto_approve = true` — silence is what leaves the
    native dialog intact, so a chatty gate would be a real bug;
  - both hooks fail open on every malformed input a session could hand them.

Payload shapes below are the REAL ones, captured from a live Claude Code 2.1.207 rig —
not transcribed from the docs, which were wrong about this tool in both directions.

    uv run tests/test_plan_store.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STORE = REPO_ROOT / "scripts" / "plan-store" / "plan_store.py"
CAPTURE_HOOK = REPO_ROOT / "hooks" / "plan-capture" / "hook.py"
GATE_HOOK = REPO_ROOT / "hooks" / "plan-gate" / "hook.py"

_spec = importlib.util.spec_from_file_location("plan_store", STORE)
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

PLAN_BODY = "# Add subtract to calc.py\n\n## Change\n\nAppend `subtract(a, b)`.\n"


class PlanStoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.project = self.base / "proj"
        self.project.mkdir()
        # The harness's own plan file — capture must read THIS, not tool_input.plan.
        self.plan_file = self.base / "claude-plans" / "robust-shore.md"
        self.plan_file.parent.mkdir()
        self.plan_file.write_text(PLAN_BODY, encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def config(self, body: str) -> None:
        key = ps.project_key(ps.repo_root(self.project))
        target = self.state / key / "config.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'root = "{self.project}"\n\n{body}', encoding="utf-8")

    def payload(self, **over) -> dict:
        base = {
            "cwd": str(self.project),
            "hook_event_name": "PostToolUse",
            "tool_name": "ExitPlanMode",
            "session_id": "ade31e11-50f5-47eb-98ce-bb7d1ae1cbc4",
            "permission_mode": "plan",
            "tool_input": {
                "plan": "STALE PRE-EDIT DRAFT",
                "planFilePath": str(self.plan_file),
            },
        }
        base.update(over)
        return base

    def filed(self) -> list[Path]:
        return sorted(self.state.glob("*/plans/*.md"))

    # ── opt-in ──────────────────────────────────────────────────────────────

    def test_no_config_files_nothing(self) -> None:
        """No lightbridge config at all → the store is not this project's business."""
        self.assertIsNone(ps.capture(self.payload(), self.state))
        self.assertEqual(self.filed(), [])

    def test_no_plans_section_files_nothing(self) -> None:
        """Opt-in is by SECTION presence — a config without [plans] must stay untouched."""
        self.config("[docs-index]\nenabled = true\n")
        self.assertIsNone(ps.capture(self.payload(), self.state))
        self.assertEqual(self.filed(), [])

    def test_enabled_false_files_nothing(self) -> None:
        self.config("[plans]\nenabled = false\n")
        self.assertIsNone(ps.capture(self.payload(), self.state))
        self.assertEqual(self.filed(), [])

    # ── the artifact ────────────────────────────────────────────────────────

    def test_capture_writes_the_approved_plan(self) -> None:
        self.config("[plans]\nenabled = true\n")
        target = ps.capture(self.payload(), self.state)
        self.assertIsNotNone(target)
        meta, body = ps.parse_frontmatter(target.read_text(encoding="utf-8"))

        # Body is the APPROVED file, never the stale draft field.
        self.assertIn("Append `subtract(a, b)`.", body)
        self.assertNotIn("STALE PRE-EDIT DRAFT", body)

        self.assertEqual(meta["status"], "approved")
        self.assertEqual(meta["harness"], "claude-code")
        self.assertEqual(meta["project"], str(ps.repo_root(self.project)))
        self.assertEqual(meta["source"], str(self.plan_file))
        self.assertEqual(meta["session"], "ade31e11-50f5-47eb-98ce-bb7d1ae1cbc4")

    def test_slug_comes_from_the_plan_title(self) -> None:
        self.config("[plans]\nenabled = true\n")
        target = ps.capture(self.payload(), self.state)
        self.assertTrue(target.stem.endswith("add-subtract-to-calc-py"), target.stem)

    def test_draft_is_the_fallback_when_plan_file_is_gone(self) -> None:
        """planFilePath unreadable → fall back to tool_input.plan rather than lose the plan."""
        self.config("[plans]\nenabled = true\n")
        payload = self.payload()
        payload["tool_input"]["planFilePath"] = str(self.base / "vanished.md")
        target = ps.capture(payload, self.state)
        self.assertIsNotNone(target)
        _meta, body = ps.parse_frontmatter(target.read_text(encoding="utf-8"))
        self.assertIn("STALE PRE-EDIT DRAFT", body)

    def test_empty_plan_files_nothing(self) -> None:
        self.config("[plans]\nenabled = true\n")
        payload = self.payload(tool_input={"plan": "", "planFilePath": ""})
        self.assertIsNone(ps.capture(payload, self.state))

    def test_two_plans_same_minute_do_not_clobber(self) -> None:
        self.config("[plans]\nenabled = true\n")
        first = ps.capture(self.payload(), self.state)
        second = ps.capture(self.payload(), self.state)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.filed()), 2)

    # ── approval provenance (derived, not passed between hooks) ─────────────

    def test_approval_human_when_auto_approve_off(self) -> None:
        self.config("[plans]\nauto_approve = false\n")
        target = ps.capture(self.payload(), self.state)
        meta, _ = ps.parse_frontmatter(target.read_text(encoding="utf-8"))
        self.assertEqual(meta["approval"], "human")

    def test_approval_auto_when_auto_approve_on(self) -> None:
        """auto_approve on ⇒ the gate always bypassed ⇒ the approval WAS automatic.

        Derived from config, so there is no marker file to leak or garbage-collect.
        """
        self.config("[plans]\nauto_approve = true\n")
        target = ps.capture(self.payload(), self.state)
        meta, _ = ps.parse_frontmatter(target.read_text(encoding="utf-8"))
        self.assertEqual(meta["approval"], "auto")

    # ── lifecycle ───────────────────────────────────────────────────────────

    def test_status_transition_preserves_body(self) -> None:
        self.config("[plans]\nenabled = true\n")
        ps.capture(self.payload(), self.state)
        env = {**os.environ, ps.STATE_DIR_ENV: str(self.state)}
        proc = subprocess.run(
            [str(STORE), "status", "latest", "landed"],
            cwd=self.project, capture_output=True, text=True, env=env, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("approved → landed", proc.stdout)
        meta, body = ps.parse_frontmatter(self.filed()[0].read_text(encoding="utf-8"))
        self.assertEqual(meta["status"], "landed")
        self.assertIn("Append `subtract(a, b)`.", body)

    def test_unknown_state_is_refused(self) -> None:
        self.config("[plans]\nenabled = true\n")
        ps.capture(self.payload(), self.state)
        env = {**os.environ, ps.STATE_DIR_ENV: str(self.state)}
        proc = subprocess.run(
            [str(STORE), "status", "latest", "shipped"],
            cwd=self.project, capture_output=True, text=True, env=env, timeout=60,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unknown state", proc.stderr)

    def test_list_json_reports_the_plan(self) -> None:
        self.config("[plans]\nenabled = true\n")
        ps.capture(self.payload(), self.state)
        env = {**os.environ, ps.STATE_DIR_ENV: str(self.state)}
        proc = subprocess.run(
            [str(STORE), "list", "--json"],
            cwd=self.project, capture_output=True, text=True, env=env, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = json.loads(proc.stdout)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "approved")
        self.assertEqual(rows[0]["title"], "Add subtract to calc.py")


class PlanGateCase(unittest.TestCase):
    """The gate must be silent by default — silence is what preserves the native dialog."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.project = self.base / "proj"
        self.project.mkdir()
        self.addCleanup(self.tmp.cleanup)

    def config(self, body: str) -> None:
        key = ps.project_key(ps.repo_root(self.project))
        target = self.state / key / "config.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'root = "{self.project}"\n\n{body}', encoding="utf-8")

    def run_gate(self, payload: str) -> subprocess.CompletedProcess:
        env = {**os.environ, ps.STATE_DIR_ENV: str(self.state)}
        return subprocess.run(
            [str(GATE_HOOK)], input=payload, cwd=self.project,
            capture_output=True, text=True, env=env, timeout=60,
        )

    def payload(self) -> str:
        return json.dumps({
            "cwd": str(self.project),
            "hook_event_name": "PreToolUse",
            "tool_name": "ExitPlanMode",
            "tool_input": {"plan": "# Plan", "planFilePath": "/tmp/p.md"},
        })

    def test_silent_without_config(self) -> None:
        proc = self.run_gate(self.payload())
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_silent_when_auto_approve_absent(self) -> None:
        """The DEFAULT. A [plans] section alone must never bypass the gate."""
        self.config("[plans]\nenabled = true\n")
        proc = self.run_gate(self.payload())
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_silent_when_auto_approve_false(self) -> None:
        self.config("[plans]\nauto_approve = false\n")
        proc = self.run_gate(self.payload())
        self.assertEqual(proc.stdout.strip(), "")

    def test_allows_when_auto_approve_true(self) -> None:
        self.config("[plans]\nauto_approve = true\n")
        proc = self.run_gate(self.payload())
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "allow")
        # `updatedInput` is required alongside `allow` for interaction-gated tools.
        self.assertEqual(out["updatedInput"]["planFilePath"], "/tmp/p.md")

    def test_enabled_false_beats_auto_approve(self) -> None:
        self.config("[plans]\nenabled = false\nauto_approve = true\n")
        proc = self.run_gate(self.payload())
        self.assertEqual(proc.stdout.strip(), "")


class FailOpenCase(unittest.TestCase):
    """Neither hook may ever break a session, whatever it is handed."""

    def run_hook(self, hook: Path, payload: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(hook)], input=payload, capture_output=True, text=True, timeout=60
        )

    def test_hooks_survive_garbage(self) -> None:
        for hook in (CAPTURE_HOOK, GATE_HOOK):
            for payload in ("", "not json", "[]", "{}", '{"cwd": null}'):
                with self.subTest(hook=hook.parent.name, payload=payload):
                    proc = self.run_hook(hook, payload)
                    self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
