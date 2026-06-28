#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for bin/install.py guards and multi-agent targets.

Each test spins up a throwaway repo layout (bin/ + plugins/<domain>/skills/<name>/)
in a temp dir and drives install.py as a subprocess. A per-test targets.toml points
the agent flags at temp directories so nothing touches the real home dir.

    uv run tests/test_install.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bin" / "install.py"
SKILL_MD = "---\nname: sample\ndescription: sample\n---\n"
# A harmless default so the registry loads; tests needing real agents override it.
DEFAULT_TARGETS = '[claude]\nskills = "~/.claude/skills"\n'


def make_repo(base: Path, targets_toml: str = DEFAULT_TARGETS) -> Path:
    """Create a minimal repo with one skill at plugins/demo/skills/sample/SKILL.md."""
    repo = base / "repo"
    (repo / "bin").mkdir(parents=True)
    skill_dir = repo / "plugins" / "demo" / "skills" / "sample"
    skill_dir.mkdir(parents=True)
    (repo / "bin" / "install.py").write_bytes(SCRIPT.read_bytes())
    (repo / "bin" / "targets.toml").write_text(targets_toml)
    (skill_dir / "SKILL.md").write_text(SKILL_MD)
    return repo


def make_hook(repo: Path, name: str = "sample-hook") -> Path:
    """Add a hooks/<name>/ with a hook.toml descriptor and its command file."""
    hook_dir = repo / "hooks" / name
    hook_dir.mkdir(parents=True)
    (hook_dir / "hook.py").write_text("#!/usr/bin/env python3\n")
    (hook_dir / "hook.toml").write_text(
        'event = "SessionStart"\n'
        'command = "hook.py"\n'
        'statusMessage = "Injecting docs index"\n'
    )
    return hook_dir


def section(text: str, start_marker: str, end_marker: str) -> str:
    """Return the slice of `text` between two markers (exclusive)."""
    body = text.split(start_marker, 1)[1]
    return body.split(end_marker, 1)[0]


def run_install(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the installer copied into a throwaway repo so REPO_ROOT resolves to that repo."""
    return subprocess.run(
        [sys.executable, str(repo / "bin" / "install.py"), *args],
        capture_output=True,
        text=True,
    )


class InstallTest(unittest.TestCase):
    def test_force_skips_target_that_is_source(self):
        with tempfile.TemporaryDirectory() as dir_:
            repo = make_repo(Path(dir_))
            source_parent = repo / "plugins" / "demo" / "skills"

            # Target dir IS the skills dir, so the "target" resolves to the source.
            result = run_install(
                repo,
                "--target", str(source_parent),
                "--force", "sample",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("target is source, skipping", result.stderr)
            self.assertTrue((source_parent / "sample" / "SKILL.md").exists())

    def test_force_copy_replaces_existing_symlink(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            repo = make_repo(base)
            target = base / "target"
            target.mkdir()
            source = repo / "plugins" / "demo" / "skills" / "sample"
            os.symlink(source, target / "sample")

            result = run_install(
                repo,
                "--target", str(target),
                "--force", "--mode", "copy", "sample",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("copy sample", result.stdout)
            self.assertFalse((target / "sample").is_symlink())
            self.assertTrue((target / "sample" / "SKILL.md").exists())
            self.assertTrue((source / "SKILL.md").exists())

    def test_multiple_agents_in_one_run(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            alpha = base / "alpha" / "skills"
            beta = base / "beta" / "skills"
            toml = (
                f"[alpha]\nskills = {str(alpha)!r}\n"
                f"[beta]\nskills = {str(beta)!r}\n"
            )
            repo = make_repo(base, targets_toml=toml)

            result = run_install(repo, "--alpha", "--beta", "--mode", "copy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((alpha / "sample" / "SKILL.md").exists())
            self.assertTrue((beta / "sample" / "SKILL.md").exists())

    def test_all_installs_only_present_agents(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            present = base / "present" / "skills"
            absent = base / "absent" / "skills"
            # "present" agent: its parent dir exists, so it is detected.
            (base / "present").mkdir(parents=True)
            toml = (
                f"[present]\nskills = {str(present)!r}\n"
                f"[absent]\nskills = {str(absent)!r}\n"
            )
            repo = make_repo(base, targets_toml=toml)

            result = run_install(repo, "--all", "--mode", "copy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((present / "sample" / "SKILL.md").exists())
            self.assertFalse(absent.exists())

    def test_hooks_render_emits_claude_and_codex(self):
        with tempfile.TemporaryDirectory() as dir_:
            repo = make_repo(Path(dir_))
            hook_dir = make_hook(repo)

            result = run_install(repo, "--hooks")

            self.assertEqual(result.returncode, 0, result.stderr)
            out = result.stdout
            # The command path is resolved for this checkout's hook folder.
            self.assertIn(str((hook_dir / "hook.py").resolve()), out)
            self.assertIn("SessionStart", out)
            # All three destinations are surfaced.
            self.assertIn("~/.claude/settings.json", out)
            self.assertIn("~/.codex/hooks.json", out)
            self.assertIn("~/.codex/config.toml", out)
            # The "pick one Codex form" + trust guidance is present.
            self.assertIn("EXACTLY ONE", out)
            self.assertIn("/hooks", out)

    def test_hooks_render_blocks_are_valid(self):
        with tempfile.TemporaryDirectory() as dir_:
            repo = make_repo(Path(dir_))
            # install.py resolves REPO_ROOT, so compare against the realpath.
            command = str((make_hook(repo) / "hook.py").resolve())

            out = run_install(repo, "--hooks").stdout

            claude = json.loads(
                section(out, "~/.claude/settings.json ---\n", "\n# ---")
            )
            codex = json.loads(
                section(out, "~/.codex/hooks.json ---\n", "\n# ---")
            )
            for block in (claude, codex):
                handler = block["hooks"]["SessionStart"][0]["hooks"][0]
                self.assertEqual(handler["type"], "command")
                self.assertEqual(handler["command"], command)
            # Codex shows statusMessage; the Claude block omits it.
            self.assertNotIn("statusMessage", claude["hooks"]["SessionStart"][0]["hooks"][0])
            self.assertIn("statusMessage", codex["hooks"]["SessionStart"][0]["hooks"][0])

    def test_target_rejects_agent_combo(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml = f"[alpha]\nskills = {str(base / 'a' / 'skills')!r}\n"
            repo = make_repo(base, targets_toml=toml)

            result = run_install(repo, "--target", str(base / "x"), "--alpha")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--target cannot be combined", result.stderr)


if __name__ == "__main__":
    unittest.main()
