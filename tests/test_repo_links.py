#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for repo-links: the resolver CLI and its SessionStart hook.

Each test builds a throwaway *project* dir (committed `[repo-links]` layer) and a
throwaway *home* dir (personal `~/.lightbridge/repos.toml` layer), then drives the
real hook.py / repo_links.py as a subprocess with `HOME` pointed at the fake home —
so the `~` convention is exercised end to end. Files are executed directly, the
same path as Claude Code's /bin/sh registration, so a missing executable bit or
broken shebang fails here too (`UV_CACHE_DIR` is pinned to the real cache, since
the fake `HOME` would otherwise cold-start uv on every subprocess). The hook resolves its paired
repo_links.py relative to its own location in this repo, so it is exercised in
place — only the project and home under inspection are synthetic.

Opt-in is twice: a `[repo-links]` section in `<repo>/.lightbridge/config.toml`
AND a `~/.lightbridge/repos.toml` registry on the machine.

    uv run tests/test_repo_links.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "repo-links-inject" / "hook.py"
SCRIPT = REPO_ROOT / "scripts" / "repo-links" / "repo_links.py"

# Resolved against the REAL home before tests override HOME, so uv's environment
# cache stays warm across the fake-HOME subprocesses.
UV_CACHE_DIR = os.environ.get("UV_CACHE_DIR", str(Path("~/.cache/uv").expanduser()))

# Common .lightbridge/config.toml bodies.
ONE_LINK = (
    "[repo-links]\n"
    "[[repo-links.link]]\n"
    'name = "example-service"\n'
    'role = "upstream"\n'
    'note = "Commercial counterpart"\n'
)
NAME_ONLY = '[repo-links]\n[[repo-links.link]]\nname = "example-service"\n'
EMPTY_SECTION = "[repo-links]\n"  # opted in, zero links declared
DISABLED = "[repo-links]\nenabled = false\n[[repo-links.link]]\nname = \"example-service\"\n"
NO_SECTION = "[something-else]\nkey = 1\n"

# Common ~/.lightbridge/repos.toml bodies.
REGISTRY_OK = '[repos]\nexample-service = "~/work/example-service"\n'


def run_hook(cwd: Path, home: Path) -> subprocess.CompletedProcess:
    # Execute the file directly (not `sys.executable hook.py`) — the same path as
    # Claude Code's /bin/sh registration, so +x and the uv shebang are under test.
    return subprocess.run(
        [str(HOOK)],
        input=json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home), "UV_CACHE_DIR": UV_CACHE_DIR},
    )


def run_cli(args: list[str], home: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home), "UV_CACHE_DIR": UV_CACHE_DIR},
    )


def make_project(base: Path, *, config: str | None) -> Path:
    """Build a project dir with an optional .lightbridge/config.toml."""
    proj = base / "proj"
    proj.mkdir(parents=True)
    if config is not None:
        lb = proj / ".lightbridge"
        lb.mkdir()
        (lb / "config.toml").write_text(config)
    return proj


def make_home(base: Path, *, registry: str | None, repos: list[str] = ()) -> Path:
    """Build a fake home: optional ~/.lightbridge/repos.toml plus target repo dirs."""
    home = base / "home"
    home.mkdir(parents=True)
    if registry is not None:
        lb = home / ".lightbridge"
        lb.mkdir()
        (lb / "repos.toml").write_text(registry)
    for rel in repos:
        (home / rel).mkdir(parents=True)
    return home


class RepoLinksHookTest(unittest.TestCase):
    def assert_silent(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def context_of(self, result: subprocess.CompletedProcess) -> str:
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        return data["hookSpecificOutput"]["additionalContext"]

    # --- gating -------------------------------------------------------------

    def test_no_config_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=None)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            self.assert_silent(run_hook(proj, home))

    def test_section_absent_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=NO_SECTION)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            self.assert_silent(run_hook(proj, home))

    def test_disabled_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=DISABLED)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            self.assert_silent(run_hook(proj, home))

    def test_malformed_config_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config="[unclosed\n")
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            self.assert_silent(run_hook(proj, home))

    def test_registry_absent_is_silent(self):
        # THE colleague-safety contract: links declared, but this machine has no
        # personal registry -> the committed section imposes nothing. Dead quiet.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry=None)
            self.assert_silent(run_hook(proj, home))

    def test_zero_links_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=EMPTY_SECTION)
            home = make_home(Path(d), registry=REGISTRY_OK)
            self.assert_silent(run_hook(proj, home))

    def test_malformed_registry_warns(self):
        # A registry file can only exist on the owner's machine -> rot must show.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry="not toml [[[\n")
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("WARNING", ctx)
            self.assertIn("unreadable", ctx)

    def test_registry_without_repos_table_warns(self):
        # Flat root keys (no [repos] table) are a registry error, not a silent skip.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry='example-service = "~/work/example-service"\n')
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("WARNING", ctx)
            self.assertIn("[repos]", ctx)

    # --- resolution ---------------------------------------------------------

    def test_resolved_link_renders_path_role_note(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            ctx = self.context_of(run_hook(proj, home))
            # Tilde in the registry expanded against the fake HOME.
            self.assertIn(f"example-service → {home / 'work' / 'example-service'}", ctx)
            self.assertIn("(upstream)", ctx)
            self.assertIn("— Commercial counterpart", ctx)

    def test_name_only_link_renders_bare(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=NAME_ONLY)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("example-service →", ctx)
            self.assertNotIn("(", ctx.split("\n")[1])  # no role parens on the link line

    def test_unregistered_name_warns(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d), config='[repo-links]\n[[repo-links.link]]\nname = "ghost"\n'
            )
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("ghost: WARNING — not registered", ctx)

    def test_stale_path_warns(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry=REGISTRY_OK)  # no work/ dir created
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("example-service: WARNING", ctx)
            self.assertIn("does not exist", ctx)

    def test_path_is_file_warns(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work"])
            (home / "work" / "example-service").write_text("a file, not a repo")
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("not a directory", ctx)

    def test_symlinked_repo_is_ok_and_renders_as_declared(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["elsewhere/real-repo", "work"])
            (home / "work" / "example-service").symlink_to(home / "elsewhere" / "real-repo")
            ctx = self.context_of(run_hook(proj, home))
            # Resolves (is_dir follows symlinks) and renders the declared path, not realpath.
            self.assertIn(f"example-service → {home / 'work' / 'example-service'}", ctx)
            self.assertNotIn("real-repo", ctx)
            self.assertNotIn("WARNING", ctx)

    def test_mixed_ok_and_warning_in_one_map(self):
        config = ONE_LINK + '[[repo-links.link]]\nname = "ghost"\n'
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=config)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("example-service →", ctx)
            self.assertIn("ghost: WARNING", ctx)

    def test_duplicate_name_first_wins_with_warning(self):
        config = ONE_LINK + '[[repo-links.link]]\nname = "example-service"\nrole = "dup"\n'
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=config)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("(upstream)", ctx)  # first occurrence kept
            self.assertNotIn("(dup)", ctx)
            self.assertIn("duplicate name", ctx)

    def test_link_missing_name_skipped_with_warning(self):
        config = '[repo-links]\n[[repo-links.link]]\nrole = "upstream"\n' + (
            '[[repo-links.link]]\nname = "example-service"\n'
        )
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=config)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("missing required key 'name'", ctx)
            self.assertIn("example-service →", ctx)  # the valid link still resolves


class RepoLinksCliTest(unittest.TestCase):
    def test_json_schema(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            result = run_cli(["--start", str(proj), "--json"], home)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(
                set(data),
                {"config", "registry", "registry_found", "registry_error", "links", "warnings"},
            )
            (link,) = data["links"]
            self.assertEqual(
                set(link), {"name", "role", "note", "path", "status", "detail"}
            )
            self.assertEqual(link["status"], "ok")
            self.assertTrue(data["registry_found"])
            self.assertIsNone(data["registry_error"])

    def test_no_config_exits_2_with_next_move(self):
        with tempfile.TemporaryDirectory() as d:
            bare = Path(d) / "bare"
            bare.mkdir()
            home = make_home(Path(d), registry=REGISTRY_OK)
            result = run_cli(["--start", str(bare)], home)
            self.assertEqual(result.returncode, 2)
            self.assertIn("lightbridge-config", result.stderr)

    def test_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            self.assertEqual(run_cli(["--start", str(proj), "--check"], home).returncode, 0)
            ghost = make_project(
                Path(d) / "g", config='[repo-links]\n[[repo-links.link]]\nname = "ghost"\n'
            )
            self.assertEqual(run_cli(["--start", str(ghost), "--check"], home).returncode, 1)

    def test_registry_override(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=ONE_LINK)
            home = make_home(Path(d), registry=None, repos=["work/example-service"])
            alt = Path(d) / "alt.toml"
            alt.write_text(REGISTRY_OK)
            result = run_cli(["--start", str(proj), "--registry", str(alt), "--json"], home)
            data = json.loads(result.stdout)
            self.assertEqual(data["links"][0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
