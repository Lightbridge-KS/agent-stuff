#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for repo-links: the resolver CLI and its SessionStart hook.

Each test builds a throwaway *project* dir and a throwaway *home* dir carrying BOTH
user-level layers — the project's `~/.lightbridge/projects/<project-key>/config.toml`
(the "local scope" model; nothing lives in the repo) and the personal
`~/.lightbridge/repos.toml` registry — then drives the real hook.py / repo_links.py
as a subprocess with `HOME` pointed at the fake home, so the `~` convention is
exercised end to end. Files are executed directly, the same path as Claude Code's
/bin/sh registration, so a missing executable bit or broken shebang fails here too
(`UV_CACHE_DIR` is pinned to the real cache, since the fake `HOME` would otherwise
cold-start uv on every subprocess). The hook resolves its paired repo_links.py and
lightbridge.py relative to its own location in this repo, so it is exercised in
place — only the project and home under inspection are synthetic.

Opt-in is twice: a `[repo-links]` section in the project's user-level config AND a
`~/.lightbridge/repos.toml` registry on the machine.

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

# Common config.toml bodies.
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


def project_key(path: Path) -> str:
    """Mirror of the lightbridge encoding (resolved absolute path, separators → '-')."""
    return str(path.resolve()).replace(os.sep, "-").replace("/", "-")


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


def make_home(base: Path, *, registry: str | None, repos: list[str] = ()) -> Path:
    """Build a fake home: optional ~/.lightbridge/repos.toml plus target repo dirs."""
    home = base / "home"
    home.mkdir(parents=True, exist_ok=True)
    if registry is not None:
        lb = home / ".lightbridge"
        lb.mkdir(exist_ok=True)
        (lb / "repos.toml").write_text(registry)
    for rel in repos:
        (home / rel).mkdir(parents=True)
    return home


def make_project(base: Path, *, config: str | None, home: Path) -> Path:
    """Build a project dir; its config goes to the fake home's projects tree —
    `~/.lightbridge/projects/<project-key>/config.toml` — never into the repo."""
    proj = base / "proj"
    proj.mkdir(parents=True)
    if config is not None:
        cfg_dir = home / ".lightbridge" / "projects" / project_key(proj)
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "config.toml").write_text(config)
    return proj


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
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=None, home=home)
            self.assert_silent(run_hook(proj, home))

    def test_section_absent_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=NO_SECTION, home=home)
            self.assert_silent(run_hook(proj, home))

    def test_disabled_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=DISABLED, home=home)
            self.assert_silent(run_hook(proj, home))

    def test_malformed_config_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config="[unclosed\n", home=home)
            self.assert_silent(run_hook(proj, home))

    def test_registry_absent_is_silent(self):
        # Links declared, but this machine has no personal registry -> dead quiet.
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=None)
            # Config lives user-level, so the projects tree exists even without a registry.
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            self.assert_silent(run_hook(proj, home))

    def test_zero_links_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK)
            proj = make_project(Path(d), config=EMPTY_SECTION, home=home)
            self.assert_silent(run_hook(proj, home))

    def test_legacy_per_repo_config_warns(self):
        # A stray pre-migration <repo>/.lightbridge/config.toml is NOT read, but
        # earns a one-line deprecation warning.
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=None, home=home)
            lb = proj / ".lightbridge"
            lb.mkdir()
            (lb / "config.toml").write_text(ONE_LINK)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("no longer read", ctx)
            self.assertNotIn("example-service →", ctx)  # legacy file must not opt in

    def test_malformed_registry_warns(self):
        # A registry file can only exist on the owner's machine -> rot must show.
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry="not toml [[[\n")
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("WARNING", ctx)
            self.assertIn("unreadable", ctx)

    def test_registry_without_repos_table_warns(self):
        # Flat root keys (no [repos] table) are a registry error, not a silent skip.
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry='example-service = "~/work/example-service"\n')
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("WARNING", ctx)
            self.assertIn("[repos]", ctx)

    # --- resolution ---------------------------------------------------------

    def test_resolved_link_renders_path_role_note(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            ctx = self.context_of(run_hook(proj, home))
            # Tilde in the registry expanded against the fake HOME.
            self.assertIn(f"example-service → {home / 'work' / 'example-service'}", ctx)
            self.assertIn("(upstream)", ctx)
            self.assertIn("— Commercial counterpart", ctx)

    def test_name_only_link_renders_bare(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=NAME_ONLY, home=home)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("example-service →", ctx)
            self.assertNotIn("(", ctx.split("\n")[1])  # no role parens on the link line

    def test_unregistered_name_warns(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(
                Path(d), config='[repo-links]\n[[repo-links.link]]\nname = "ghost"\n', home=home
            )
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("ghost: WARNING — not registered", ctx)

    def test_stale_path_warns(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK)  # no work/ dir created
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("example-service: WARNING", ctx)
            self.assertIn("does not exist", ctx)

    def test_path_is_file_warns(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work"])
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            (home / "work" / "example-service").write_text("a file, not a repo")
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("not a directory", ctx)

    def test_symlinked_repo_is_ok_and_renders_as_declared(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["elsewhere/real-repo", "work"])
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            (home / "work" / "example-service").symlink_to(home / "elsewhere" / "real-repo")
            ctx = self.context_of(run_hook(proj, home))
            # Resolves (is_dir follows symlinks) and renders the declared path, not realpath.
            self.assertIn(f"example-service → {home / 'work' / 'example-service'}", ctx)
            self.assertNotIn("real-repo", ctx)
            self.assertNotIn("WARNING", ctx)

    def test_mixed_ok_and_warning_in_one_map(self):
        config = ONE_LINK + '[[repo-links.link]]\nname = "ghost"\n'
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=config, home=home)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("example-service →", ctx)
            self.assertIn("ghost: WARNING", ctx)

    def test_duplicate_name_first_wins_with_warning(self):
        config = ONE_LINK + '[[repo-links.link]]\nname = "example-service"\nrole = "dup"\n'
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=config, home=home)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("(upstream)", ctx)  # first occurrence kept
            self.assertNotIn("(dup)", ctx)
            self.assertIn("duplicate name", ctx)

    def test_link_missing_name_skipped_with_warning(self):
        config = '[repo-links]\n[[repo-links.link]]\nrole = "upstream"\n' + (
            '[[repo-links.link]]\nname = "example-service"\n'
        )
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=config, home=home)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("missing required key 'name'", ctx)
            self.assertIn("example-service →", ctx)  # the valid link still resolves


class RepoLinksCliTest(unittest.TestCase):
    def test_json_schema(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=ONE_LINK, home=home)
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

    def test_legacy_per_repo_config_warns_on_stderr(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            lb = proj / ".lightbridge"
            lb.mkdir()
            (lb / "config.toml").write_text(ONE_LINK)
            result = run_cli(["--start", str(proj)], home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("no longer read", result.stderr)
            self.assertIn("example-service →", result.stdout)  # user-level config wins

    def test_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=REGISTRY_OK, repos=["work/example-service"])
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            self.assertEqual(run_cli(["--start", str(proj), "--check"], home).returncode, 0)
            ghost_base = Path(d) / "g"
            ghost = make_project(
                ghost_base, config='[repo-links]\n[[repo-links.link]]\nname = "ghost"\n', home=home
            )
            self.assertEqual(run_cli(["--start", str(ghost), "--check"], home).returncode, 1)

    def test_registry_override(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_home(Path(d), registry=None, repos=["work/example-service"])
            proj = make_project(Path(d), config=ONE_LINK, home=home)
            alt = Path(d) / "alt.toml"
            alt.write_text(REGISTRY_OK)
            result = run_cli(["--start", str(proj), "--registry", str(alt), "--json"], home)
            data = json.loads(result.stdout)
            self.assertEqual(data["links"][0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
