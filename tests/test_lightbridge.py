#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for scripts/lightbridge — the canonical config resolver.

Library functions (project_key, repo_root, config_path, load_config, legacy_config)
are tested by importing the module the same way the hooks do (importlib from file
path). The CLI (`path`, `doctor`) is driven as a subprocess, executing the file
directly — the same path as an agent's `uv run`, so the shebang is under test.

    uv run tests/test_lightbridge.py
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
SCRIPT = REPO_ROOT / "scripts" / "lightbridge" / "lightbridge.py"

_spec = importlib.util.spec_from_file_location("lightbridge", SCRIPT)
lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lb)


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)


def write_config(state: Path, root: Path, body: str = "", *, key: str | None = None) -> Path:
    """A projects-tree config for `root`; `key` overrides the folder name (mismatch tests)."""
    cfg_dir = state / (key or lb.project_key(root))
    cfg_dir.mkdir(parents=True, exist_ok=True)
    config = cfg_dir / "config.toml"
    config.write_text(f'root = "{root}"\n{body}')
    return config


class ResolverTest(unittest.TestCase):
    def test_project_key_encoding(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "my_repo"
            proj.mkdir()
            key = lb.project_key(proj)
            self.assertEqual(key, str(proj.resolve()).replace("/", "-"))
            self.assertTrue(key.startswith("-"))
            self.assertNotIn("/", key)

    def test_repo_root_git_toplevel_from_subdir(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "repo"
            sub = proj / "src" / "inner"
            sub.mkdir(parents=True)
            git_init(proj)
            self.assertEqual(lb.repo_root(sub), proj.resolve())
            self.assertEqual(lb.repo_root(proj), proj.resolve())

    def test_repo_root_non_git_falls_back_to_start(self):
        with tempfile.TemporaryDirectory() as d:
            plain = Path(d) / "plain"
            plain.mkdir()
            self.assertEqual(lb.repo_root(plain), plain.resolve())

    def test_config_path_honors_state_dir_env(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "repo"
            proj.mkdir()
            state = Path(d) / "state"
            old = os.environ.get(lb.STATE_DIR_ENV)
            os.environ[lb.STATE_DIR_ENV] = str(state)
            try:
                expected = state / lb.project_key(proj) / "config.toml"
                self.assertEqual(lb.config_path(proj), expected)
            finally:
                if old is None:
                    del os.environ[lb.STATE_DIR_ENV]
                else:
                    os.environ[lb.STATE_DIR_ENV] = old

    def test_load_config_absent_readable_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "repo"
            proj.mkdir()
            state = Path(d) / "state"

            config, path, error = lb.load_config(proj, state)
            self.assertIsNone(config)
            self.assertIsNone(error)

            write_config(state, proj, "[docs-index]\n")
            config, path, error = lb.load_config(proj, state)
            self.assertIsNone(error)
            self.assertIn("docs-index", config)
            self.assertEqual(config["root"], str(proj))

            path.write_text("[unclosed\n")
            config, _, error = lb.load_config(proj, state)
            self.assertIsNone(config)
            self.assertIsNotNone(error)

    def test_legacy_config_detected_at_repo_root(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "repo"
            sub = proj / "src"
            sub.mkdir(parents=True)
            git_init(proj)
            self.assertIsNone(lb.legacy_config(proj))
            legacy_dir = proj / ".lightbridge"
            legacy_dir.mkdir()
            (legacy_dir / "config.toml").write_text("[docs-index]\n")
            # Found from the root AND from a subdir (via git toplevel).
            self.assertIsNotNone(lb.legacy_config(proj))
            self.assertIsNotNone(lb.legacy_config(sub))


class DoctorTest(unittest.TestCase):
    def run_doctor(self, state: Path, registry: Path | None = None) -> subprocess.CompletedProcess:
        args = [str(SCRIPT), "doctor", "--state-dir", str(state), "--json"]
        args += ["--registry", str(registry or (state / "no-registry.toml"))]
        return subprocess.run(args, capture_output=True, text=True)

    def problems_of(self, result: subprocess.CompletedProcess) -> list[dict]:
        return json.loads(result.stdout)["problems"]

    def test_clean_tree_exits_0(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "repo"
            proj.mkdir()
            state = Path(d) / "state"
            write_config(state, proj)
            result = self.run_doctor(state)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(self.problems_of(result), [])

    def test_stale_root_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "repo"
            proj.mkdir()
            state = Path(d) / "state"
            write_config(state, proj)
            proj.rmdir()  # the repo "moved"
            result = self.run_doctor(state)
            self.assertEqual(result.returncode, 1)
            (problem,) = self.problems_of(result)
            self.assertEqual(problem["kind"], "stale")

    def test_missing_root_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "state"
            cfg_dir = state / "-some-key"
            cfg_dir.mkdir(parents=True)
            (cfg_dir / "config.toml").write_text("[docs-index]\n")
            result = self.run_doctor(state)
            self.assertEqual(result.returncode, 1)
            (problem,) = self.problems_of(result)
            self.assertEqual(problem["kind"], "missing-root")

    def test_unreadable_config_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "state"
            cfg_dir = state / "-some-key"
            cfg_dir.mkdir(parents=True)
            (cfg_dir / "config.toml").write_text("[unclosed\n")
            result = self.run_doctor(state)
            self.assertEqual(result.returncode, 1)
            (problem,) = self.problems_of(result)
            self.assertEqual(problem["kind"], "unreadable")

    def test_key_mismatch_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "repo"
            proj.mkdir()
            state = Path(d) / "state"
            write_config(state, proj, key="-wrong-key")
            result = self.run_doctor(state)
            self.assertEqual(result.returncode, 1)
            (problem,) = self.problems_of(result)
            self.assertEqual(problem["kind"], "key-mismatch")

    def test_legacy_per_repo_config_flagged_via_registry(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "repo"
            legacy = proj / ".lightbridge"
            legacy.mkdir(parents=True)
            (legacy / "config.toml").write_text("[docs-index]\n")
            state = Path(d) / "state"
            state.mkdir()
            registry = Path(d) / "repos.toml"
            registry.write_text(f'[repos]\nrepo = "{proj}"\n')
            result = self.run_doctor(state, registry)
            self.assertEqual(result.returncode, 1)
            (problem,) = self.problems_of(result)
            self.assertEqual(problem["kind"], "legacy")


class PathCliTest(unittest.TestCase):
    def test_path_json(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "repo"
            proj.mkdir()
            state = Path(d) / "state"
            result = subprocess.run(
                [str(SCRIPT), "path", "--start", str(proj), "--json"],
                capture_output=True,
                text=True,
                env={**os.environ, lb.STATE_DIR_ENV: str(state)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(set(data), {"root", "key", "config", "exists", "legacy"})
            self.assertEqual(data["root"], str(proj.resolve()))
            self.assertFalse(data["exists"])
            self.assertIsNone(data["legacy"])


if __name__ == "__main__":
    unittest.main()
