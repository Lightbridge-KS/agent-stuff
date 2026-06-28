#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Behavioral tests for hooks/docs-index-inject/hook.py — the opt-in gating.

Each test builds a throwaway *project* dir (the repo the hook would run inside) and
drives the real hook.py as a subprocess with a SessionStart payload on stdin. The
hook resolves its paired docs_index.py relative to its own location in this repo, so
it is exercised in place — only the project under inspection is synthetic.

Opt-in is via a `[docs-index]` section in `<repo>/.lightbridge/config.toml`.

    uv run tests/test_hooks.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "docs-index-inject" / "hook.py"

# A doc the hook should surface: explicit summary + read_when.
ANNOTATED = "---\nsummary: The cache layer.\nread_when:\n  - touching cache\n---\n# Cache\n"
# Website-style frontmatter: only `description` — must NOT be surfaced by the hook.
WEBSITE = "---\ntitle: Home\ndescription: Landing page.\n---\n# Home\n"

# Common .lightbridge/config.toml bodies.
OPTED_IN = "[docs-index]\n"  # section present, all defaults
DISABLED = "[docs-index]\nenabled = false\n"
NO_SECTION = "[something-else]\nkey = 1\n"  # folder exists for another reason


def run_hook(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True,
    )


def make_project(
    base: Path,
    *,
    config: str | None,
    docs: dict[str, str],
    docs_dir: str = "docs",
) -> Path:
    """Build a project dir with optional .lightbridge/config.toml and a docs dir."""
    proj = base / "proj"
    (proj / docs_dir).mkdir(parents=True)
    for name, content in docs.items():
        (proj / docs_dir / name).write_text(content)
    if config is not None:
        lb = proj / ".lightbridge"
        lb.mkdir()
        (lb / "config.toml").write_text(config)
    return proj


class HookTest(unittest.TestCase):
    def assert_silent(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def context_of(self, result: subprocess.CompletedProcess) -> str:
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        return data["hookSpecificOutput"]["additionalContext"]

    def test_opted_in_injects_index(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=OPTED_IN, docs={"cache.md": ANNOTATED})
            ctx = self.context_of(run_hook(proj))
            self.assertIn("cache.md", ctx)
            self.assertIn("Read when: touching cache", ctx)

    def test_no_config_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=None, docs={"cache.md": ANNOTATED})
            self.assert_silent(run_hook(proj))

    def test_section_absent_is_silent(self):
        # .lightbridge/config.toml exists but has no [docs-index] section.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=NO_SECTION, docs={"cache.md": ANNOTATED})
            self.assert_silent(run_hook(proj))

    def test_disabled_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=DISABLED, docs={"cache.md": ANNOTATED})
            self.assert_silent(run_hook(proj))

    def test_website_docs_not_surfaced(self):
        # Opted in, but the only doc has `description` (no summary) -> stay silent.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=OPTED_IN, docs={"index.md": WEBSITE})
            self.assert_silent(run_hook(proj))

    def test_empty_section_uses_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), config=OPTED_IN, docs={"cache.md": ANNOTATED})
            self.assertIn("cache.md", self.context_of(run_hook(proj)))

    def test_custom_dir(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d),
                config='[docs-index]\ndir = "agent-docs"\n',
                docs={"cache.md": ANNOTATED},
                docs_dir="agent-docs",
            )
            self.assertIn("cache.md", self.context_of(run_hook(proj)))

    def test_exclude_respected(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d),
                config='[docs-index]\nexclude = ["private"]\n',
                docs={"cache.md": ANNOTATED},
            )
            private = proj / "docs" / "private"
            private.mkdir()
            (private / "secret.md").write_text(ANNOTATED.replace("cache", "secret"))
            ctx = self.context_of(run_hook(proj))
            self.assertIn("cache.md", ctx)
            self.assertNotIn("secret.md", ctx)

    def test_config_missing_dir_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d),
                config='[docs-index]\ndir = "nonexistent"\n',
                docs={"cache.md": ANNOTATED},
            )
            self.assert_silent(run_hook(proj))

    def test_malformed_config_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d), config="[unclosed\n", docs={"cache.md": ANNOTATED}
            )
            self.assert_silent(run_hook(proj))


if __name__ == "__main__":
    unittest.main()
