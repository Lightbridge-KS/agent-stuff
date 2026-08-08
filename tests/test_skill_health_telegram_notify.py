#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for the skill-health Telegram notifier."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "scripts" / "skill-health" / "skill_health_telegram_notify.py"

_spec = importlib.util.spec_from_file_location("skill_health_telegram_notify", TOOL)
notify = importlib.util.module_from_spec(_spec)
sys.modules["skill_health_telegram_notify"] = notify
_spec.loader.exec_module(notify)


def alert(*, detail: str = "dangling symlink") -> dict:
    return {
        "severity": "warning",
        "type": "skill_health",
        "host": "example.local",
        "message": "skill-health: 1 of 5 checks red — skill-vendor",
        "metadata": {"report_path": "/tmp/skill-health.json"},
        "checks": [
            {
                "name": "skill-vendor",
                "what": "vendored skew + registry invariant",
                "status": "red",
                "detail": detail,
            },
            {"name": "lightbridge", "status": "ok"},
        ],
    }


class Config(unittest.TestCase):
    def test_loads_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "telegram.toml"
            path.write_text(
                'account = "default"\nchat_id = "-1001"\nthread_id = "42"\nsilent = true\n'
            )
            config = notify.load_config(path)
        self.assertEqual(config.chat_id, "-1001")
        self.assertEqual(config.thread_id, "42")
        self.assertTrue(config.silent)

    def test_missing_destination_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "telegram.toml"
            path.write_text('account = "default"\n')
            with self.assertRaisesRegex(ValueError, "chat_id"):
                notify.load_config(path)


class Payload(unittest.TestCase):
    def test_rejects_another_alert_type(self):
        payload = alert()
        payload["type"] = "cpu"
        with self.assertRaisesRegex(ValueError, "skill_health"):
            notify.parse_alert(json.dumps(payload))

    def test_message_names_failure_and_report(self):
        message = notify.render_message(alert())
        self.assertIn("Skill health [warning]", message)
        self.assertIn("skill-vendor", message)
        self.assertIn("dangling symlink", message)
        self.assertIn("Report: /tmp/skill-health.json", message)
        self.assertNotIn("lightbridge", message)

    def test_message_is_bounded(self):
        message = notify.render_message(alert(detail="x" * 20_000))
        self.assertLessEqual(len(message), notify.MAX_MESSAGE_CHARS)
        self.assertTrue(message.endswith("Report: /tmp/skill-health.json"))

    def test_command_targets_forum_thread_silently(self):
        config = notify.TelegramConfig("-1001", "42", "default", True)
        command = notify.build_command(config, "hello", "/openclaw", dry_run=True)
        self.assertEqual(command[:3], ["/openclaw", "message", "send"])
        self.assertIn("-1001", command)
        self.assertIn("42", command)
        self.assertIn("--silent", command)
        self.assertIn("--dry-run", command)


if __name__ == "__main__":
    unittest.main(verbosity=2)
