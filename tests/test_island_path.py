#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for island_path.py — the skills-island registry resolver.

Each test builds a throwaway *home* carrying a synthetic
`~/.lightbridge/islands.toml` plus the island workspace dirs it names, then drives
the real bin/island_path.py as a subprocess with `HOME` pointed there, so the `~`
convention is exercised end to end. Files are executed directly, the same path a
justfile recipe takes, so a missing executable bit or broken shebang fails here too
(`UV_CACHE_DIR` is pinned to the real cache, since the fake `HOME` would otherwise
cold-start uv on every subprocess).

`targets.toml` is NOT synthetic — the harness→directory mapping under test is the
real one, so a `~/`-rooted target added there is covered the moment it lands.

    uv run tests/test_island_path.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bin" / "island_path.py"

UV_CACHE_DIR = os.environ.get("UV_CACHE_DIR", str(Path("~/.cache/uv").expanduser()))

ONE_ISLAND = (
    'root = "~/my_config/skills-island"\n'
    "[islands]\n"
    'my-book = { path = "~/books", harnesses = ["claude", "agents"] }\n'
)
SHORTHAND = '[islands]\nmy-book = "~/books"\n'  # bare string, harnesses default
NO_HARNESS_KEY = '[islands]\nmy-book = { path = "~/books" }\n'
BAD_HARNESS = '[islands]\nmy-book = { path = "~/books", harnesses = ["nope"] }\n'
NO_PATH = '[islands]\nmy-book = { name = "oops" }\n'
NO_ROOT = '[islands]\nmy-book = { path = "~/books" }\n'


def script_argv(script: Path, *args: str) -> list[str]:
    """argv launching a PEP 723 script the way its real consumer does."""
    if os.name != "nt":
        return [str(script), *args]
    return ["uv", "run", str(script), *args]


def home_vars(home: Path) -> dict[str, str]:
    """Env redirecting `~` to `home` on both platforms."""
    return {"HOME": str(home), "USERPROFILE": str(home)}


class IslandPathCase(unittest.TestCase):
    def run_script(self, registry: str | None, *args: str, islands: tuple[str, ...] = ("books",)):
        """Build a fake home, optionally write islands.toml, run the resolver."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            if registry is not None:
                (home / ".lightbridge").mkdir(parents=True)
                (home / ".lightbridge" / "islands.toml").write_text(registry, encoding="utf-8")
            for name in islands:
                (home / name).mkdir(parents=True, exist_ok=True)
            env = {**os.environ, **home_vars(home), "UV_CACHE_DIR": UV_CACHE_DIR}
            proc = subprocess.run(
                script_argv(SCRIPT, *args), env=env, capture_output=True, text=True
            )
            return proc, home

    # --- resolution ------------------------------------------------------

    def test_path_resolves_tilde_against_home(self):
        proc, home = self.run_script(ONE_ISLAND, "path", "my-book")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(home / "books"))

    def test_root_is_the_vendoring_path(self):
        proc, home = self.run_script(ONE_ISLAND, "root")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(home / "my_config" / "skills-island"))

    def test_targets_one_line_per_declared_harness_in_order(self):
        proc, home = self.run_script(ONE_ISLAND, "targets", "my-book")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.split(),
            [str(home / "books" / ".claude" / "skills"), str(home / "books" / ".agents" / "skills")],
        )

    def test_harnesses_defaults_to_claude_only(self):
        proc, home = self.run_script(NO_HARNESS_KEY, "targets", "my-book")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.split(), [str(home / "books" / ".claude" / "skills")])

    def test_bare_string_shorthand_is_accepted(self):
        """`my-book = "~/books"` must behave as `{ path = "~/books" }`."""
        proc, home = self.run_script(SHORTHAND, "path", "my-book")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), str(home / "books"))

    # --- failure modes ---------------------------------------------------

    def test_missing_registry_names_the_file_it_wants(self):
        proc, _ = self.run_script(None, "path", "my-book")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("islands.toml", proc.stderr)

    def test_unknown_island_lists_the_known_ones(self):
        proc, _ = self.run_script(ONE_ISLAND, "path", "nope")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("my-book", proc.stderr)

    def test_unknown_harness_is_rejected_not_silently_skipped(self):
        """A typo'd harness must fail loudly — a skipped target installs nothing."""
        proc, _ = self.run_script(BAD_HARNESS, "targets", "my-book")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("targets.toml", proc.stderr)

    def test_island_without_path_is_rejected(self):
        proc, _ = self.run_script(NO_PATH, "path", "my-book")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("path", proc.stderr)

    def test_root_absent_is_an_error_not_an_empty_line(self):
        proc, _ = self.run_script(NO_ROOT, "root")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("root", proc.stderr)

    # --- list ------------------------------------------------------------

    def test_list_reports_a_missing_workspace(self):
        proc, _ = self.run_script(ONE_ISLAND, "list", islands=())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("MISSING", proc.stdout)

    def test_list_reports_a_present_workspace_and_its_targets(self):
        proc, home = self.run_script(ONE_ISLAND, "list")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ok", proc.stdout)
        self.assertIn(str(home / "books" / ".claude" / "skills"), proc.stdout)

    def test_list_flags_a_broken_symlink(self):
        """A link whose canonical target was moved/deleted is the drift `status` exists to catch."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".lightbridge").mkdir(parents=True)
            (home / ".lightbridge" / "islands.toml").write_text(ONE_ISLAND, encoding="utf-8")
            skills = home / "books" / ".claude" / "skills"
            skills.mkdir(parents=True)
            (skills / "ghost").symlink_to(home / "gone" / "ghost")
            env = {**os.environ, **home_vars(home), "UV_CACHE_DIR": UV_CACHE_DIR}
            proc = subprocess.run(
                script_argv(SCRIPT, "list"), env=env, capture_output=True, text=True
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("BROKEN", proc.stdout)
        self.assertIn("ghost", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
