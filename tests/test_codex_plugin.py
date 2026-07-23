#!/usr/bin/env python3
"""Packaging contract tests for the standalone notebook-tools plugin."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "notebook-tools"


class NotebookPluginCase(unittest.TestCase):
    def load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_dual_manifests_and_marketplaces_have_one_versioned_plugin(self) -> None:
        codex = self.load(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
        claude = self.load(PLUGIN_ROOT / ".claude-plugin" / "plugin.json")
        self.assertEqual(codex["name"], "notebook-tools")
        self.assertEqual(codex["version"], "0.3.0")
        self.assertEqual(claude["name"], codex["name"])
        self.assertEqual(claude["version"], codex["version"])

        codex_market = self.load(REPO_ROOT / ".agents" / "plugins" / "marketplace.json")
        self.assertEqual(codex_market["name"], "lightbridge-tools")
        entries = {entry["name"]: entry for entry in codex_market["plugins"]}
        entry = entries["notebook-tools"]
        self.assertEqual(entry["source"]["path"], "./plugins/notebook-tools")
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")

        claude_market = self.load(REPO_ROOT / ".claude-plugin" / "marketplace.json")
        claude_entries = {entry["name"]: entry for entry in claude_market["plugins"]}
        self.assertEqual(
            claude_entries["notebook-tools"]["source"],
            "./plugins/notebook-tools",
        )

    def test_mcp_launch_is_relative_fail_closed_and_has_no_user_paths(self) -> None:
        mcp = self.load(PLUGIN_ROOT / ".mcp.json")["mcpServers"]["notebook-tools"]
        self.assertEqual(mcp["command"], "uv")
        self.assertEqual(mcp["cwd"], ".")
        self.assertEqual(
            mcp["args"],
            ["run", "--script", "./mcp/notebook_mcp.py", "--use-client-roots"],
        )
        for path in PLUGIN_ROOT.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".md", ".py"}:
                self.assertNotIn("/Users/", path.read_text(encoding="utf-8"), path)

    def test_manifest_is_runtime_version_source(self) -> None:
        result = subprocess.run(
            [
                "uv",
                "run",
                "--script",
                str(PLUGIN_ROOT / "mcp" / "notebook_mcp.py"),
                "--version",
            ],
            cwd=REPO_ROOT,
            text=True, encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.3.0")

    def test_old_maintained_locations_are_gone(self) -> None:
        self.assertFalse(
            (REPO_ROOT / "scripts" / "notebook-tools" / "README.md").exists()
        )
        self.assertFalse(
            (REPO_ROOT / "scripts" / "notebook-tools" / "notebook_mcp.py").exists()
        )
        self.assertFalse(
            (
                REPO_ROOT
                / "plugins"
                / "coding"
                / "skills"
                / "notebook-tools"
                / "SKILL.md"
            ).exists()
        )
        tracked_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                REPO_ROOT / "justfile",
                REPO_ROOT / ".github" / "workflows" / "validate.yml",
                REPO_ROOT / "tests" / "test_notebook_tools.py",
            ]
        )
        self.assertNotIn("scripts/notebook-tools", tracked_text)
        self.assertNotIn("plugins/coding/skills/notebook-tools", tracked_text)


if __name__ == "__main__":
    unittest.main()
