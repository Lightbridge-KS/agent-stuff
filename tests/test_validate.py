#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for bin/validate.py — first coverage, focused on `--root`.

The load-bearing claims, each pinned by a test:

  - self-validation of this real repo stays green (full mode, marketplace-driven);
  - a marketplace-less foreign root is validated in CONTENT MODE: the two
    marketplace hard-fail checks are replaced by a direct walk of
    `plugins/*/.claude-plugin/plugin.json` (present, valid JSON, name == domain);
  - the skill contract is still enforced under --root;
  - foreign-root display paths never crash (`relative_to` raises ValueError on
    paths outside the validator's own repo — the trap that forced the Repo object);
  - exit codes: 0 green, 1 problems, and stderr never shows a traceback.

    uv run tests/test_validate.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bin" / "validate.py"

SKILL_MD = (
    "---\nname: {name}\ndescription: test skill\n"
    'metadata:\n  version: "2026-07-26"\n---\n\n# {name}\n'
)


def script_argv(*args: str) -> list[str]:
    """Launch validate.py the way its consumer does (needs pyyaml → via the shebang/uv)."""
    if os.name != "nt":
        return [str(SCRIPT), *args]
    return ["uv", "run", str(SCRIPT), *args]


def run_validate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(script_argv(*args), capture_output=True, text=True, encoding="utf-8")


def make_tree(base: Path, domain: str = "demo", skill: str = "sample") -> Path:
    """A content-only tree: plugins/<domain>/{.claude-plugin/plugin.json, skills/<skill>/}."""
    root = base / "content"
    plugin_dir = root / "plugins" / domain
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": domain}), encoding="utf-8"
    )
    skill_dir = plugin_dir / "skills" / skill
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_MD.format(name=skill), encoding="utf-8")
    return root


class ValidateCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def assert_no_traceback(self, proc: subprocess.CompletedProcess) -> None:
        self.assertNotIn("Traceback", proc.stderr, proc.stderr)

    # ── full mode: this repo validates itself ───────────────────────────────

    def test_self_validation_green(self) -> None:
        proc = run_validate()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("plugin manifests", proc.stdout)
        self.assertNotIn("content mode", proc.stdout)

    # ── content mode on a foreign root ──────────────────────────────────────

    def test_content_mode_green(self) -> None:
        root = make_tree(self.base)
        proc = run_validate("--root", str(root))
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("content mode", proc.stdout)

    def test_content_mode_missing_plugin_json(self) -> None:
        root = make_tree(self.base)
        (root / "plugins" / "demo" / ".claude-plugin" / "plugin.json").unlink()
        proc = run_validate("--root", str(root))
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing .claude-plugin/plugin.json", proc.stderr)

    def test_content_mode_bad_json(self) -> None:
        root = make_tree(self.base)
        (root / "plugins" / "demo" / ".claude-plugin" / "plugin.json").write_text("{nope")
        proc = run_validate("--root", str(root))
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("invalid JSON", proc.stderr)

    def test_content_mode_name_domain_mismatch(self) -> None:
        root = make_tree(self.base)
        (root / "plugins" / "demo" / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "other"})
        )
        proc = run_validate("--root", str(root))
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("must match domain 'demo'", proc.stderr)

    # ── the skill contract still bites under --root ─────────────────────────

    def test_skill_contract_enforced_on_foreign_root(self) -> None:
        root = make_tree(self.base)
        bad = root / "plugins" / "demo" / "skills" / "renamed"
        (root / "plugins" / "demo" / "skills" / "sample").rename(bad)
        # frontmatter still says `name: sample` — must fail name==folder
        proc = run_validate("--root", str(root))
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("must match folder name 'renamed'", proc.stderr)

    def test_empty_root_names_the_root(self) -> None:
        empty = self.base / "empty"
        empty.mkdir()
        proc = run_validate("--root", str(empty))
        self.assert_no_traceback(proc)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(str(empty), proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
