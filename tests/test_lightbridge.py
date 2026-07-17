#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for scripts/lightbridge — the canonical config resolver.

Library functions (project_key, repo_root, config_path, load_config, legacy_config)
are tested by importing the module the same way the hooks do (importlib from file
path). The CLI (`status` · `init` · `add` · `show` · `enable`/`disable` · `path` ·
`repos` · `doctor`) is driven as a subprocess, executing the file directly — the same
path as an agent's `uv run`, so the shebang is under test.

    uv run tests/test_lightbridge.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import tempfile
import tomllib
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


class CliHarness(unittest.TestCase):
    """Shared subprocess harness for the project-scoped verbs, isolated via
    $LIGHTBRIDGE_STATE_DIR — every verb resolves through config_path()."""

    def run_cli(self, state: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={**os.environ, lb.STATE_DIR_ENV: str(state)},
        )

    def repo(self, d: str, *, docs: bool) -> Path:
        """A git repo, with or without a `docs/` dir — the trigger `init` detects on."""
        proj = Path(d) / "repo"
        proj.mkdir()
        if docs:
            (proj / "docs").mkdir()
        git_init(proj)
        return proj.resolve()

    def config_of(self, state: Path, proj: Path) -> Path:
        return state / lb.project_key(proj) / "config.toml"


class BootstrapCliTest(CliHarness):
    """`init` / `add` — the deterministic bootstrap."""

    def test_init_creates_config_with_root(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            result = self.run_cli(state, "init", "--start", str(proj))
            self.assertEqual(result.returncode, 0, result.stderr)
            config = self.config_of(state, proj)
            self.assertTrue(config.is_file())
            data = tomllib.loads(config.read_text())
            self.assertEqual(data["root"], str(proj))

    def test_init_detects_docs_dir(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            result = self.run_cli(state, "init", "--start", str(proj), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(
                set(data),
                {
                    "root",
                    "key",
                    "config",
                    "created",
                    "sections_added",
                    "sections_skipped",
                    "detected",
                },
            )
            self.assertTrue(data["created"])
            self.assertEqual(data["detected"], ["docs-index"])
            self.assertEqual(data["sections_added"], ["docs-index"])
            self.assertIn("docs-index", tomllib.loads(Path(data["config"]).read_text()))

    def test_init_bare_when_no_docs(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            result = self.run_cli(state, "init", "--start", str(proj), "--json")
            self.assertEqual(json.loads(result.stdout)["sections_added"], [])
            data = tomllib.loads(self.config_of(state, proj).read_text())
            self.assertEqual(set(data), {"root"})

    def test_init_explicit_sections_override_detection(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)  # docs/ IS present
            result = self.run_cli(
                state, "init", "research", "--start", str(proj), "--json"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["sections_added"], ["research"])
            data = tomllib.loads(self.config_of(state, proj).read_text())
            self.assertEqual(set(data), {"root", "research"})  # detection did NOT fire

    def test_init_refuses_existing_config(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            config = write_config(state, proj, body='[docs-index]\ndir = "guide"\n')
            before = config.read_bytes()
            result = self.run_cli(state, "init", "--start", str(proj))
            self.assertEqual(result.returncode, 1)
            self.assertIn("never clobbers", result.stderr)
            self.assertEqual(config.read_bytes(), before)  # not one byte touched

    def test_init_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            result = self.run_cli(state, "init", "--start", str(proj), "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[docs-index]", result.stdout)
            self.assertFalse(self.config_of(state, proj).exists())

    def test_add_appends_missing_section(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            self.run_cli(state, "init", "--start", str(proj))
            result = self.run_cli(state, "add", "repo-links", "--start", str(proj), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["created"])
            self.assertEqual(payload["sections_added"], ["repo-links"])
            data = tomllib.loads(self.config_of(state, proj).read_text())
            self.assertEqual(set(data), {"root", "docs-index", "repo-links"})
            # `enabled` must land on the section, not on the [[link]] appended after it
            self.assertTrue(data["repo-links"]["enabled"])
            self.assertEqual(data["repo-links"]["link"][0]["name"], "example-service")

    def test_add_skips_present_section(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            self.run_cli(state, "init", "--start", str(proj))
            config = self.config_of(state, proj)
            before = config.read_bytes()
            result = self.run_cli(state, "add", "docs-index", "--start", str(proj), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)  # idempotent, not an error
            payload = json.loads(result.stdout)
            self.assertEqual(payload["sections_added"], [])
            self.assertEqual(payload["sections_skipped"], ["docs-index"])
            self.assertEqual(config.read_bytes(), before)

    def test_add_without_config_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            result = self.run_cli(state, "add", "research", "--start", str(proj))
            self.assertEqual(result.returncode, 1)
            self.assertIn("init", result.stderr)

    def test_unknown_section_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            for args in (
                ("init", "nope", "--start", str(proj)),
                ("add", "nope", "--start", str(proj)),
            ):
                result = self.run_cli(state, *args)
                self.assertEqual(result.returncode, 2, args)
                self.assertIn("docs-index", result.stderr, args)  # names the valid set

    def test_init_output_survives_doctor(self):
        """The writer and the auditor agree — a config `init` wrote is clean to `doctor`."""
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            self.run_cli(state, "init", "--start", str(proj))
            self.run_cli(state, "add", "research", "repo-links", "--start", str(proj))
            result = subprocess.run(
                [
                    str(SCRIPT), "doctor",
                    "--state-dir", str(state),
                    "--registry", str(state / "no-registry.toml"),
                    "--json",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(json.loads(result.stdout)["problems"], [])


class ShowCliTest(CliHarness):
    def test_show_whole_config_verbatim_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            self.run_cli(state, "init", "--start", str(proj))
            result = self.run_cli(state, "show", "--start", str(proj))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[docs-index]", result.stdout)
            self.assertIn("# ~/.lightbridge/projects", result.stdout)  # comments verbatim
            result = self.run_cli(state, "show", "--start", str(proj), "--json")
            self.assertEqual(set(json.loads(result.stdout)), {"root", "docs-index"})

    def test_show_one_section_block_only(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            self.run_cli(state, "init", "--start", str(proj))
            result = self.run_cli(state, "show", "docs-index", "--start", str(proj))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.startswith("[docs-index]"))
            self.assertIn("dir =", result.stdout)
            self.assertNotIn("root =", result.stdout)  # the block, not the file
            result = self.run_cli(state, "show", "docs-index", "--start", str(proj), "--json")
            self.assertEqual(set(json.loads(result.stdout)), {"docs-index"})

    def test_show_absent_config_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            result = self.run_cli(state, "show", "--start", str(proj))
            self.assertEqual(result.returncode, 1)
            self.assertIn("init", result.stderr)

    def test_show_absent_section_exits_1_names_add(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            self.run_cli(state, "init", "--start", str(proj))
            result = self.run_cli(state, "show", "research", "--start", str(proj))
            self.assertEqual(result.returncode, 1)
            self.assertIn("add research", result.stderr)


class ToggleCliTest(CliHarness):
    def test_disable_flips_in_place_comments_survive(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            self.run_cli(state, "init", "--start", str(proj))
            result = self.run_cli(state, "disable", "docs-index", "--start", str(proj))
            self.assertEqual(result.returncode, 0, result.stderr)
            text = self.config_of(state, proj).read_text()
            self.assertFalse(tomllib.loads(text)["docs-index"]["enabled"])
            self.assertIn("# ~/.lightbridge/projects", text)  # header comment intact
            self.assertIn("# optional; default true", text)  # trailing comment survives

    def test_enable_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            self.run_cli(state, "init", "--start", str(proj))
            config = self.config_of(state, proj)
            before = config.read_bytes()
            result = self.run_cli(state, "enable", "docs-index", "--start", str(proj), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(
                set(payload), {"root", "key", "config", "section", "enabled", "changed"}
            )
            self.assertFalse(payload["changed"])
            self.assertEqual(config.read_bytes(), before)  # no-op wrote nothing

    def test_toggle_absent_section_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            self.run_cli(state, "init", "--start", str(proj))
            result = self.run_cli(state, "disable", "research", "--start", str(proj))
            self.assertEqual(result.returncode, 1)
            self.assertIn("add research", result.stderr)

    def test_toggle_unknown_section_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            result = self.run_cli(state, "disable", "nope", "--start", str(proj))
            self.assertEqual(result.returncode, 2)
            self.assertIn("docs-index", result.stderr)  # names the valid set

    def test_disable_repo_links_enabled_precedes_links(self):
        """The TOML invariant: `enabled` must stay attached to [repo-links], never to
        the [[repo-links.link]] entries after it."""
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            self.run_cli(state, "init", "--start", str(proj))
            self.run_cli(state, "add", "repo-links", "--start", str(proj))
            result = self.run_cli(state, "disable", "repo-links", "--start", str(proj))
            self.assertEqual(result.returncode, 0, result.stderr)
            text = self.config_of(state, proj).read_text()
            self.assertLess(text.index("enabled = false"), text.index("[[repo-links.link]]"))
            data = tomllib.loads(text)
            self.assertFalse(data["repo-links"]["enabled"])
            self.assertEqual(data["repo-links"]["link"][0]["name"], "example-service")


class StatusCliTest(CliHarness):
    JSON_KEYS = {
        "root", "key", "config", "exists", "error", "sections",
        "unknown_sections", "state", "registry", "legacy",
    }

    def status(self, state: Path, proj: Path, *extra: str) -> subprocess.CompletedProcess:
        # --registry pinned to a missing file so the runner's real ~/.lightbridge
        # never leaks into assertions.
        return self.run_cli(
            state, "status", "--start", str(proj),
            "--registry", str(state / "no-registry.toml"), *extra,
        )

    def test_absent_config_exits_0_and_teaches_init(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            result = self.status(state, proj)
            self.assertEqual(result.returncode, 0, result.stderr)  # absence is a state
            self.assertIn("init", result.stdout)

    def test_json_dashboard_sections_state_and_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=True)
            self.run_cli(state, "init", "--start", str(proj))
            self.run_cli(state, "add", "repo-links", "--start", str(proj))
            self.run_cli(state, "disable", "repo-links", "--start", str(proj))
            config = self.config_of(state, proj)
            config.write_text(config.read_text() + "\n[mystery]\n")
            project_dir = config.parent
            (project_dir / "handoffs" / "inbox").mkdir(parents=True)
            (project_dir / "handoffs" / "a.md").write_text("x")
            (project_dir / "handoffs" / "b.md").write_text("x")
            (project_dir / "handoffs" / "inbox" / "c.md").write_text("x")
            (project_dir / "plans").mkdir()
            (project_dir / "plans" / "p.md").write_text("x")

            result = self.status(state, proj, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(set(data), self.JSON_KEYS)
            self.assertTrue(data["exists"])
            self.assertIsNone(data["error"])
            self.assertEqual(data["sections"], {"docs-index": True, "repo-links": False})
            self.assertEqual(data["unknown_sections"], ["mystery"])
            self.assertEqual(data["state"], {"handoffs": 2, "inbox": 1, "plans": 1})
            self.assertFalse(data["registry"])

    def test_unreadable_config_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            write_config(state, proj).write_text("[unclosed\n")
            result = self.status(state, proj, "--json")
            self.assertEqual(result.returncode, 1)
            self.assertIsNotNone(json.loads(result.stdout)["error"])

    def test_registry_presence_reported(self):
        with tempfile.TemporaryDirectory() as d:
            state, proj = Path(d) / "state", self.repo(d, docs=False)
            registry = Path(d) / "repos.toml"
            registry.write_text("[repos]\n")
            result = self.run_cli(
                state, "status", "--start", str(proj), "--registry", str(registry), "--json"
            )
            self.assertTrue(json.loads(result.stdout)["registry"])


class ReposCliTest(unittest.TestCase):
    def run_repos(self, registry: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(SCRIPT), "repos", *args, "--registry", str(registry)],
            capture_output=True,
            text=True,
        )

    def test_add_creates_registry_then_lists(self):
        with tempfile.TemporaryDirectory() as d:
            registry = Path(d) / "repos.toml"
            target = Path(d) / "svc"
            target.mkdir()
            result = self.run_repos(registry, "add", "svc", str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = tomllib.loads(registry.read_text())
            self.assertEqual(data["repos"]["svc"], str(target))
            result = self.run_repos(registry, "list", "--json")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["repos"]["svc"], {"path": str(target), "exists": True})

    def test_add_duplicate_name_exits_1_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            registry = Path(d) / "repos.toml"
            self.run_repos(registry, "add", "svc", str(d))
            before = registry.read_bytes()
            result = self.run_repos(registry, "add", "svc", "/elsewhere")
            self.assertEqual(result.returncode, 1)
            self.assertIn("already registered", result.stderr)
            self.assertEqual(registry.read_bytes(), before)

    def test_add_missing_path_warns_but_registers(self):
        with tempfile.TemporaryDirectory() as d:
            registry = Path(d) / "repos.toml"
            result = self.run_repos(registry, "add", "ghost", str(Path(d) / "nowhere"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("does not exist", result.stderr)
            result = self.run_repos(registry, "list")
            self.assertIn("MISSING", result.stdout)

    def test_rm_removes_line_comments_survive_unknown_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            registry = Path(d) / "repos.toml"
            self.run_repos(registry, "add", "one", str(d))
            self.run_repos(registry, "add", "two", str(d))
            result = self.run_repos(registry, "rm", "one")
            self.assertEqual(result.returncode, 0, result.stderr)
            text = registry.read_text()
            self.assertEqual(set(tomllib.loads(text)["repos"]), {"two"})
            self.assertIn("# ~/.lightbridge/repos.toml", text)  # header comment intact
            result = self.run_repos(registry, "rm", "one")
            self.assertEqual(result.returncode, 1)
            self.assertIn("repos list", result.stderr)

    def test_add_invalid_name_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            registry = Path(d) / "repos.toml"
            result = self.run_repos(registry, "add", "bad name!", "/x")
            self.assertEqual(result.returncode, 2)
            self.assertFalse(registry.exists())

    def test_list_absent_registry_is_informational(self):
        with tempfile.TemporaryDirectory() as d:
            registry = Path(d) / "repos.toml"
            result = self.run_repos(registry, "list", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(json.loads(result.stdout)["repos"])


class CliContractTest(unittest.TestCase):
    """The parser-layer contracts the Typer migration must not drift on."""

    def test_bare_invocation_is_usage_error(self):
        """Design decision 5: bare `lb` → exit 2, not help-and-exit-0."""
        result = subprocess.run([str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_help_is_plain_text(self):
        """Help stays plain click text (no rich box-drawing/padding) so a piped
        agent reader pays no decoration tokens — the design doc's two-audience rule."""
        result = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("╭", result.stdout)
        self.assertIn("Spec: the lightbridge-config skill.", result.stdout)


class SectionsTest(unittest.TestCase):
    def test_sections_lists_every_known_section(self):
        result = subprocess.run(
            [str(SCRIPT), "sections", "--json"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)), set(lb.SECTIONS))

    def test_sections_match_catalog(self):
        """The anti-drift guard: the CLI's emittable templates and the catalog's prose
        must describe the SAME set of sections. The catalog is canonical for what a key
        means; SECTIONS is canonical for what gets written. Neither may grow alone."""
        catalog = (
            REPO_ROOT
            / "plugins/lightbridge/skills/lightbridge-config/references/catalog.md"
        ).read_text(encoding="utf-8")
        documented = set(re.findall(r"^### `\[([^\]]+)\]`", catalog, flags=re.MULTILINE))
        self.assertEqual(
            documented,
            set(lb.SECTIONS),
            "catalog.md and lightbridge.SECTIONS disagree — a section was added to one "
            "and not the other (see references/extending.md).",
        )


if __name__ == "__main__":
    unittest.main()
