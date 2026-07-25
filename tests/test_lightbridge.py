#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for scripts/lightbridge — the canonical config resolver.

Each module is loaded the way its real consumer loads it (ADR 0001):

* **`lb_resolve.py`** is the one module hooks and sibling scripts path-load, so
  `ResolveModuleContractTest` exercises that protocol explicitly — `exec_module` inside a
  fresh `dependencies = []` PEP 723 env, where a sibling import genuinely cannot resolve.
  It also AST-checks the two properties that make the whole layout safe. The library tests
  below then use a plain import, so there is exactly one module object in play.
* **CLI-side modules** (`lb_tomledit`, `lb_catalog`, `lb_registry`, `lb_commands`) are
  reached by plain `import` from the entrypoint's directory — which is what `uv run
  --script` puts on `sys.path[0]` — so the tests import them the same way.
* **The CLI** (`status` · `init` · `add` · `show` · `enable`/`disable` · `path` · `repos` ·
  `mv` · `doctor`) is driven as a subprocess, executing `lightbridge.py` directly — the
  same path as an agent's `uv run`, so the shebang is under test.

    uv run tests/test_lightbridge.py
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIGHTBRIDGE_DIR = REPO_ROOT / "scripts" / "lightbridge"
SCRIPT = LIGHTBRIDGE_DIR / "lightbridge.py"
RESOLVE = LIGHTBRIDGE_DIR / "lb_resolve.py"

# The entrypoint's own protocol: `uv run --script` puts this directory on sys.path[0],
# so the CLI-side modules are plain imports. Tests do exactly what lightbridge.py does.
sys.path.insert(0, str(LIGHTBRIDGE_DIR))

import lb_catalog  # noqa: E402
import lb_commands  # noqa: E402
import lb_registry  # noqa: E402
import lb_resolve as lb  # noqa: E402  — the read path; `lb` keeps the historic name
import lb_tomledit  # noqa: E402


def script_argv(script: Path, *args: str) -> list[str]:
    """argv launching a PEP 723 script the way its real consumer does.

    POSIX execs the file directly, keeping the executable bit and the `uv run`
    shebang under test. Windows CreateProcess cannot launch a shebang script at all
    (WinError 193), so go through `uv run` — the very interpreter the shebang names.

    Deliberately NOT bare `bash`: on Windows that name is ambiguous, and
    CreateProcess resolves it to WSL's System32\bash.exe at least as often as to
    Git Bash, which then fails with a UTF-16 diagnostic and exit 1 regardless of
    what shutil.which() reported.
    """
    if os.name != "nt":
        return [str(script), *args]
    return ["uv", "run", str(script), *args]

def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)


def write_config(state: Path, root: Path, body: str = "", *, key: str | None = None) -> Path:
    """A projects-tree config for `root`; `key` overrides the folder name (mismatch tests)."""
    cfg_dir = state / (key or lb.project_key(root))
    cfg_dir.mkdir(parents=True, exist_ok=True)
    config = cfg_dir / "config.toml"
    config.write_text(f"root = {lb.toml_str(str(root))}\n{body}")
    return config


class ResolverTest(unittest.TestCase):
    def test_project_key_encoding(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "my_repo"
            proj.mkdir()
            key = lb.project_key(proj)
            text = str(proj.resolve())
            if os.name == "nt":
                # Windows drops the drive colon: C:\a\b -> C-a-b (see project_key).
                expected = (text[0] + text[2:]).replace(os.sep, "-").replace("/", "-")
                self.assertNotIn(":", key)
            else:
                expected = text.replace("/", "-")
                self.assertTrue(key.startswith("-"))
            self.assertEqual(key, expected)
            self.assertNotIn("/", key)
            self.assertNotIn(os.sep, key)

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
        args = script_argv(SCRIPT, "doctor", "--state-dir", str(state), "--json")
        args += ["--registry", str(registry or (state / "no-registry.toml"))]
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")

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
            registry.write_text(f"[repos]\nrepo = {lb.toml_str(str(proj))}\n")
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
                script_argv(SCRIPT, "path", "--start", str(proj), "--json"),
                capture_output=True,
                text=True, encoding="utf-8",
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
            script_argv(SCRIPT, *args),
            capture_output=True,
            text=True, encoding="utf-8",
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
                script_argv(
                    SCRIPT, "doctor",
                    "--state-dir", str(state),
                    "--registry", str(state / "no-registry.toml"),
                    "--json",
                ),
                capture_output=True,
                text=True, encoding="utf-8",
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
            script_argv(SCRIPT, "repos", *args, "--registry", str(registry)),
            capture_output=True,
            text=True, encoding="utf-8",
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


class MvHelperTest(unittest.TestCase):
    """`mv`'s pure helpers — rewrite spelling, root line edit — via module import."""

    def test_rewrite_path_preserves_tilde_style(self):
        old, new = lb_tomledit.norm("~/proj/alpha"), lb_tomledit.norm("~/proj/beta")
        self.assertEqual(lb_tomledit.rewrite_path("~/proj/alpha", old, new), os.path.join("~", "proj", "beta"))
        self.assertEqual(
            lb_tomledit.rewrite_path("~/proj/alpha/sub", old, new),
            os.path.join("~", "proj", "beta", "sub"),
        )

    def test_rewrite_path_absolute_stays_absolute(self):
        old, new = lb_tomledit.norm("~/proj/alpha"), lb_tomledit.norm("~/proj/beta")
        raw = str(lb_tomledit.norm("~/proj/alpha/sub"))
        self.assertEqual(lb_tomledit.rewrite_path(raw, old, new), str(lb_tomledit.norm("~/proj/beta/sub")))

    def test_rewrite_path_unrelated_is_none(self):
        old, new = lb_tomledit.norm("~/proj/alpha"), lb_tomledit.norm("~/proj/beta")
        self.assertIsNone(lb_tomledit.rewrite_path("~/elsewhere", old, new))
        self.assertIsNone(lb_tomledit.rewrite_path("~/proj/alphabet", old, new))  # not a prefix match

    def test_rename_registry_paths_line_edit_comments_survive(self):
        text = (
            "# header comment\n[repos]\n"
            "one = '~/proj/alpha'  # trailing comment\n"
            'two = "~/elsewhere"\n'
        )
        new_text, changed = lb_registry.rename_registry_paths(
            text, lb_tomledit.norm("~/proj/alpha"), lb_tomledit.norm("~/proj/beta")
        )
        self.assertEqual(changed, {"one": os.path.join("~", "proj", "beta")})
        self.assertIn("# header comment", new_text)
        self.assertIn("# trailing comment", new_text)
        self.assertIn('two = "~/elsewhere"', new_text)  # untouched line byte-identical
        self.assertIn("one = '" + os.path.join("~", "proj", "beta") + "'", new_text)

    def test_set_root_targets_top_level_only(self):
        text = "# comment\nroot = '/old/path'  # marker\n\n[section]\nroot = '/decoy'\n"
        out = lb_tomledit.set_root(text, Path("/new/path"))
        self.assertIn("root = '/new/path'", out)
        self.assertIn("root = '/decoy'", out)  # the section's key is untouched
        self.assertIn("# comment", out)

    def test_cmd_mv_ask_declined_aborts(self):
        """The TTY-prompt branch, unit-level via the injectable `ask`."""
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            old, new = base / "alpha", base / "beta"
            old.mkdir()
            state = base / "state"
            write_config(state, old)
            answers = {"asked": 0}

            def deny(prompt: str) -> bool:
                answers["asked"] += 1
                return False

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                code = lb_commands.cmd_mv(
                    str(old), str(new), yes=False, dry_run=False, json_out=False,
                    state_dir=state, registry_file=str(base / "repos.toml"), ask=deny,
                )
            self.assertEqual(code, 1)
            self.assertEqual(answers["asked"], 1)
            self.assertTrue(old.is_dir())  # nothing moved

    def test_cmd_mv_ask_accepted_proceeds(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            old, new = base / "alpha", base / "beta"
            old.mkdir()
            state = base / "state"
            write_config(state, old)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                code = lb_commands.cmd_mv(
                    str(old), str(new), yes=False, dry_run=False, json_out=False,
                    state_dir=state, registry_file=str(base / "repos.toml"),
                    ask=lambda prompt: True,
                )
            self.assertEqual(code, 0)
            self.assertFalse(old.exists())
            self.assertTrue(new.is_dir())


class MvCliTest(CliHarness):
    """`mv` — move/rename repair, driven as a subprocess (stdin is a pipe → non-TTY,
    so the --yes guard is exercised exactly as an agent hits it)."""

    def run_mv(self, state: Path, registry: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            script_argv(SCRIPT, "mv", *args, "--registry", str(registry)),
            capture_output=True,
            text=True, encoding="utf-8",
            stdin=subprocess.DEVNULL,
            env={**os.environ, lb.STATE_DIR_ENV: str(state)},
        )

    def seeded(self, base: Path) -> tuple[Path, Path, Path, Path]:
        """A repo at alpha with config + registry entry; returns (state, registry, old, new)."""
        old, new = base / "ws" / "alpha", base / "ws" / "beta"
        old.mkdir(parents=True)
        state = base / "state"
        write_config(state, old.resolve())
        registry = base / "repos.toml"
        registry.write_text(
            f"# my registry\n[repos]\nalpha = {lb.toml_str(str(old.resolve()))}  # note\n"
        )
        return state, registry, old.resolve(), new.resolve()

    def test_mv_non_tty_without_yes_exits_1_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            state, registry, old, new = self.seeded(Path(d))
            before = registry.read_bytes()
            result = self.run_mv(state, registry, str(old), str(new))
            self.assertEqual(result.returncode, 1)
            self.assertIn("--yes", result.stderr)
            self.assertTrue(old.is_dir())
            self.assertEqual(registry.read_bytes(), before)

    def test_mv_move_mode_moves_rekeys_and_rewrites(self):
        with tempfile.TemporaryDirectory() as d:
            state, registry, old, new = self.seeded(Path(d))
            (state / lb.project_key(old) / "handoffs").mkdir()
            result = self.run_mv(state, registry, str(old), str(new), "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(old.exists())
            self.assertTrue(new.is_dir())
            self.assertFalse((state / lb.project_key(old)).exists())
            config = state / lb.project_key(new) / "config.toml"
            self.assertTrue(config.is_file())
            self.assertEqual(tomllib.loads(config.read_text())["root"], str(new))
            self.assertTrue((state / lb.project_key(new) / "handoffs").is_dir())  # state travels
            text = registry.read_text()
            self.assertIn("# my registry", text)
            self.assertIn("# note", text)
            self.assertEqual(tomllib.loads(text)["repos"]["alpha"], str(new))

    def test_mv_repair_mode_after_manual_move(self):
        with tempfile.TemporaryDirectory() as d:
            state, registry, old, new = self.seeded(Path(d))
            old.rename(new)  # the manual move lb mv must repair
            result = self.run_mv(state, registry, str(old), str(new), "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            config = state / lb.project_key(new) / "config.toml"
            self.assertEqual(tomllib.loads(config.read_text())["root"], str(new))
            self.assertEqual(tomllib.loads(registry.read_text())["repos"]["alpha"], str(new))

    def seeded_parent(
        self, base: Path, *, configs: bool = True
    ) -> tuple[Path, Path, Path, Path]:
        """Two repos under a shared parent — the prefix-move fixture.

        `configs=False` leaves them tracked in `repos.toml` only, which is the shape that
        proves registry entries count as completion evidence on their own.
        """
        ws_old, ws_new = base / "ws", base / "workspace"
        for name in ("p1", "p2"):
            (ws_old / name).mkdir(parents=True)
        state = base / "state"
        state.mkdir(exist_ok=True)
        if configs:
            for name in ("p1", "p2"):
                write_config(state, (ws_old / name).resolve())
        registry = base / "repos.toml"
        registry.write_text(
            f"[repos]\np1 = {lb.toml_str(str((ws_old / 'p1').resolve()))}\n"
            f"p2 = {lb.toml_str(str((ws_old / 'p2').resolve()))}\n"
        )
        return state, registry, ws_old, ws_new

    def test_mv_parent_prefix_rekeys_multiple_projects(self):
        with tempfile.TemporaryDirectory() as d:
            state, registry, ws_old, ws_new = self.seeded_parent(Path(d))
            result = self.run_mv(state, registry, str(ws_old), str(ws_new), "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("p1", "p2"):
                moved = (ws_new / name).resolve()
                self.assertTrue(moved.is_dir())
                config = state / lb.project_key(moved) / "config.toml"
                self.assertEqual(tomllib.loads(config.read_text())["root"], str(moved))
                self.assertEqual(tomllib.loads(registry.read_text())["repos"][name], str(moved))

    def test_mv_parent_prefix_rerun_exits_0(self):
        """Regression, issue #17: verified idempotence must hold for a PREFIX move.

        A parent dir has no config of its own — its repos' configs live one level down —
        so the completion check has to look at everything under NEW, not at NEW itself.
        Before the fix this exited 1 with "nothing in lightbridge references OLD", which
        reads as though the move never happened.
        """
        with tempfile.TemporaryDirectory() as d:
            state, registry, ws_old, ws_new = self.seeded_parent(Path(d))
            self.assertEqual(
                self.run_mv(state, registry, str(ws_old), str(ws_new), "--yes").returncode, 0
            )
            for attempt in (1, 2):  # stable, not alternating
                result = self.run_mv(state, registry, str(ws_old), str(ws_new), "--yes")
                self.assertEqual(result.returncode, 0, f"attempt {attempt}: {result.stderr}")
                self.assertIn("already consistent", result.stdout)

    def test_mv_parent_prefix_rerun_evidence_is_registry_only(self):
        """A repo tracked only in repos.toml still proves completion — no config needed."""
        with tempfile.TemporaryDirectory() as d:
            state, registry, ws_old, ws_new = self.seeded_parent(Path(d), configs=False)
            self.assertEqual(
                self.run_mv(state, registry, str(ws_old), str(ws_new), "--yes").returncode, 0
            )
            result = self.run_mv(state, registry, str(ws_old), str(ws_new), "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already consistent", result.stdout)

    def test_mv_rerun_reports_the_evidence_it_found(self):
        """The message carries the count, so a typo'd OLD against a populated NEW — which
        is indistinguishable from a completed move — is at least visible in the output."""
        with tempfile.TemporaryDirectory() as d:
            state, registry, ws_old, ws_new = self.seeded_parent(Path(d))
            self.run_mv(state, registry, str(ws_old), str(ws_new), "--yes")
            result = self.run_mv(state, registry, str(ws_old), str(ws_new), "--yes")
            self.assertIn("4 reference(s)", result.stdout)  # 2 configs + 2 registry entries
            payload = json.loads(
                self.run_mv(
                    state, registry, str(ws_old), str(ws_new), "--yes", "--json"
                ).stdout
            )
            self.assertEqual(payload["mode"], "noop")
            self.assertEqual(payload["applied"], False)
            self.assertEqual(len(payload["settled"]), 4)

    def test_mv_both_exist_exits_1_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            state, registry, old, new = self.seeded(Path(d))
            new.mkdir()
            before = registry.read_bytes()
            result = self.run_mv(state, registry, str(old), str(new), "--yes")
            self.assertEqual(result.returncode, 1)
            self.assertIn("both paths exist", result.stderr)
            self.assertTrue(old.is_dir())
            self.assertEqual(registry.read_bytes(), before)

    def test_mv_neither_exists_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            result = self.run_mv(
                base / "state", base / "repos.toml", str(base / "gone"), str(base / "also-gone"), "--yes"
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("neither path exists", result.stderr)

    def test_mv_unknown_old_exits_1(self):
        """OLD exists on disk but lightbridge knows nothing about it — typo protection."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "untracked").mkdir()
            result = self.run_mv(
                base / "state", base / "repos.toml", str(base / "untracked"), str(base / "dest"), "--yes"
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("nothing in lightbridge references", result.stderr)
            self.assertTrue((base / "untracked").is_dir())  # untracked repo not moved

    def test_mv_rerun_after_completion_exits_0(self):
        """Verified idempotence: the same command after success is a clean no-op."""
        with tempfile.TemporaryDirectory() as d:
            state, registry, old, new = self.seeded(Path(d))
            self.assertEqual(self.run_mv(state, registry, str(old), str(new), "--yes").returncode, 0)
            result = self.run_mv(state, registry, str(old), str(new), "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already consistent", result.stdout)

    def test_mv_state_only_collision_merges(self):
        """State written at the new key before the repair ran (the late-repair flow)."""
        with tempfile.TemporaryDirectory() as d:
            state, registry, old, new = self.seeded(Path(d))
            old.rename(new)
            stray = state / lb.project_key(new) / "handoffs"
            stray.mkdir(parents=True)
            (stray / "2026-07-25_note.md").write_text("fresh handoff\n")
            old_side = state / lb.project_key(old) / "plans"
            old_side.mkdir()
            (old_side / "plan.md").write_text("old plan\n")
            result = self.run_mv(state, registry, str(old), str(new), "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            merged = state / lb.project_key(new)
            self.assertTrue((merged / "handoffs" / "2026-07-25_note.md").is_file())
            self.assertTrue((merged / "plans" / "plan.md").is_file())
            self.assertTrue((merged / "config.toml").is_file())
            self.assertFalse((state / lb.project_key(old)).exists())

    def test_mv_config_collision_exits_1_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            state, registry, old, new = self.seeded(Path(d))
            old.rename(new)
            write_config(state, new)  # a second config already claims the new key
            before = registry.read_bytes()
            result = self.run_mv(state, registry, str(old), str(new), "--yes")
            self.assertEqual(result.returncode, 1)
            self.assertIn("two configs claim", result.stderr)
            self.assertEqual(registry.read_bytes(), before)
            self.assertTrue((state / lb.project_key(old) / "config.toml").is_file())

    def test_mv_dry_run_changes_nothing_exits_0(self):
        with tempfile.TemporaryDirectory() as d:
            state, registry, old, new = self.seeded(Path(d))
            before = registry.read_bytes()
            result = self.run_mv(state, registry, str(old), str(new), "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("dry-run", result.stdout)
            self.assertIn(lb.project_key(old), result.stdout)  # blast radius shown
            self.assertTrue(old.is_dir())
            self.assertEqual(registry.read_bytes(), before)

    def test_mv_json_shape(self):
        with tempfile.TemporaryDirectory() as d:
            state, registry, old, new = self.seeded(Path(d))
            result = self.run_mv(state, registry, str(old), str(new), "--yes", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["mode"], "move")
            self.assertTrue(data["applied"])
            self.assertEqual(len(data["projects"]), 1)
            self.assertEqual(data["projects"][0]["new_key"], lb.project_key(new))
            self.assertIn("alpha", data["repos"])

    @unittest.skipUnless(os.name != "nt", "POSIX rename semantics")
    def test_mv_case_only_rename_when_fs_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            old = base / "Alpha"
            old.mkdir()
            if not (base / "alpha").exists():
                self.skipTest("filesystem is case-sensitive — samefile branch unreachable")
            new = base / "alpha"
            state = base / "state"
            write_config(state, old.resolve())
            registry = base / "repos.toml"
            registry.write_text(f"[repos]\nalpha = {lb.toml_str(str(old.resolve()))}\n")
            result = self.run_mv(state, registry, str(old), str(new), "--yes")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("alpha", [p.name for p in base.iterdir()])  # renamed on disk
            config = state / lb.project_key(new) / "config.toml"
            self.assertTrue(config.is_file())


class ResolveModuleContractTest(unittest.TestCase):
    """ADR 0001's load-bearing invariants. If any of these breaks, every hook breaks.

    `lb_resolve.py` is the one module path-loaded via `exec_module` from inside
    `dependencies = []` PEP 723 envs, which means it may import stdlib only and no
    siblings (relative/sibling imports do not resolve under `exec_module`). The
    entrypoint, conversely, must never be imported by anyone.
    """

    # The frozen importer API (ADR 0001, point 3). Narrowed from v0.3: SECTIONS left.
    FROZEN_API = (
        "project_key",
        "repo_root",
        "config_path",
        "load_config",
        "legacy_config",
        "legacy_warning",
        "default_state_dir",
        "DEFAULT_STATE_DIR",
        "STATE_DIR_ENV",
        "toml_str",
        "use_utf8_console",
    )

    def test_path_loads_in_a_dependency_free_env(self):
        """The real consumer protocol, reproduced exactly.

        Runs in a `uv run --script` subprocess with `dependencies = []`, from a directory
        that is NOT scripts/lightbridge — so a sibling import genuinely cannot resolve and
        a non-stdlib import genuinely is not installed. In-process this would pass
        vacuously, because the test harness has already put the folder on sys.path.
        """
        probe = (
            "#!/usr/bin/env -S uv run --script\n"
            "# /// script\n"
            '# requires-python = ">=3.11"\n'
            "# dependencies = []\n"
            "# ///\n"
            "import importlib.util, json, sys\n"
            f"spec = importlib.util.spec_from_file_location('lightbridge', {str(RESOLVE)!r})\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            f"print(json.dumps([n for n in {list(self.FROZEN_API)!r} if not hasattr(mod, n)]))\n"
        )
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "probe.py"
            script.write_text(probe, encoding="utf-8")
            result = subprocess.run(
                ["uv", "run", "--script", str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=d,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout.strip()),
            [],
            "lb_resolve.py lost a name from the frozen importer API — every hook and "
            "sibling script path-loads this module (see ADR 0001).",
        )

    def test_imports_are_stdlib_and_sibling_free(self):
        """Static guard: names the offending import rather than only failing somewhere.

        A *sibling* import is caught here with a readable message. A *non-stdlib* import
        usually kills this harness's own import chain first (it runs `dependencies = []`
        too), so the suite goes red via a ModuleNotFoundError before reaching this test —
        red either way, but the message is worse. The AST check earns its keep on the
        sibling case and on any import that happens to be installed locally but is absent
        from a hook's env.
        """
        siblings = {p.stem for p in LIGHTBRIDGE_DIR.glob("*.py")} - {"lb_resolve"}
        tree = ast.parse(RESOLVE.read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    offenders.append(f"relative import (level {node.level})")
                    continue
                roots = [node.module or ""]
            elif isinstance(node, ast.Import):
                roots = [alias.name for alias in node.names]
            else:
                continue
            for name in roots:
                root = name.split(".")[0]
                if root in siblings:
                    offenders.append(f"sibling import: {name}")
                elif root not in sys.stdlib_module_names:
                    offenders.append(f"non-stdlib import: {name}")
        self.assertEqual(
            offenders,
            [],
            "lb_resolve.py must import stdlib only and no siblings — it is path-loaded "
            "via exec_module inside dependency-free envs (see ADR 0001, point 1).",
        )

    def test_no_consumer_path_loads_the_entrypoint(self):
        """`lightbridge.py` is the entrypoint, not a library (ADR 0001, point 2).

        It imports typer and its siblings at module scope, so path-loading it from a
        hook's dependency-free env would crash. Consumers must target lb_resolve.py.
        """
        offenders = []
        for folder in ("hooks", "scripts"):
            for source in sorted((REPO_ROOT / folder).rglob("*.py")):
                if source.parent == LIGHTBRIDGE_DIR:
                    continue  # the tool's own modules import each other by design
                if '"lightbridge.py"' in source.read_text(encoding="utf-8"):
                    offenders.append(str(source.relative_to(REPO_ROOT)))
        self.assertEqual(
            offenders,
            [],
            "these files reference lightbridge.py as a loadable path — point them at "
            "scripts/lightbridge/lb_resolve.py instead (see ADR 0001, point 2).",
        )


class CliContractTest(unittest.TestCase):
    """The parser-layer contracts the Typer migration must not drift on."""

    def test_bare_invocation_is_usage_error(self):
        """Design decision 5: bare `lb` → exit 2, not help-and-exit-0."""
        result = subprocess.run(script_argv(SCRIPT), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_help_is_plain_text(self):
        """Help stays plain click text (no rich box-drawing/padding) so a piped
        agent reader pays no decoration tokens — the design doc's two-audience rule."""
        result = subprocess.run(
            script_argv(SCRIPT, "--help"), capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("╭", result.stdout)
        self.assertIn("Spec: the lightbridge-config skill.", result.stdout)


class SectionsTest(unittest.TestCase):
    def test_sections_lists_every_known_section(self):
        result = subprocess.run(
            script_argv(SCRIPT, "sections", "--json"), capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)), set(lb_catalog.SECTIONS))

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
            set(lb_catalog.SECTIONS),
            "catalog.md and lb_catalog.SECTIONS disagree — a section was added to one "
            "and not the other (see references/extending.md).",
        )


if __name__ == "__main__":
    unittest.main()
