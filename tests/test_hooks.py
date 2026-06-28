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
    marker: str | None,
    docs: dict[str, str],
    docs_dir: str = "docs",
) -> Path:
    """Build a project dir with optional marker and a docs dir of {name: content}."""
    proj = base / "proj"
    (proj / docs_dir).mkdir(parents=True)
    for name, content in docs.items():
        (proj / docs_dir / name).write_text(content)
    if marker is not None:
        (proj / ".docs-index.toml").write_text(marker)
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
            proj = make_project(
                Path(d), marker='dir = "docs"\n', docs={"cache.md": ANNOTATED}
            )
            ctx = self.context_of(run_hook(proj))
            self.assertIn("cache.md", ctx)
            self.assertIn("Read when: touching cache", ctx)

    def test_no_marker_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), marker=None, docs={"cache.md": ANNOTATED})
            self.assert_silent(run_hook(proj))

    def test_website_docs_not_surfaced(self):
        # Opted in, but the only doc has `description` (no summary) -> stay silent.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), marker="", docs={"index.md": WEBSITE})
            self.assert_silent(run_hook(proj))

    def test_empty_marker_uses_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), marker="", docs={"cache.md": ANNOTATED})
            self.assertIn("cache.md", self.context_of(run_hook(proj)))

    def test_custom_dir(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d),
                marker='dir = "agent-docs"\n',
                docs={"cache.md": ANNOTATED},
                docs_dir="agent-docs",
            )
            self.assertIn("cache.md", self.context_of(run_hook(proj)))

    def test_exclude_respected(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d), marker='exclude = ["private"]\n', docs={"cache.md": ANNOTATED}
            )
            private = proj / "docs" / "private"
            private.mkdir()
            (private / "secret.md").write_text(ANNOTATED.replace("cache", "secret"))
            ctx = self.context_of(run_hook(proj))
            self.assertIn("cache.md", ctx)
            self.assertNotIn("secret.md", ctx)

    def test_marker_pointing_at_missing_dir_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "proj"
            proj.mkdir()
            (proj / ".docs-index.toml").write_text('dir = "nonexistent"\n')
            self.assert_silent(run_hook(proj))

    def test_malformed_marker_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d), marker="[unclosed\n", docs={"cache.md": ANNOTATED}
            )
            self.assert_silent(run_hook(proj))


if __name__ == "__main__":
    unittest.main()
