#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for bin/package.py — the skill archiver.

Discovery is checked against the real repo tree; archive behaviour (layout,
reproducibility, exclusions, .skill parity) runs against a throwaway
plugins/<domain>/skills/<name>/ fixture packaged to a temp --out dir, so nothing
touches the real dist/.

    uv run tests/test_package.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bin" / "package.py"


def load_module():
    """Import bin/package.py as a module (its REPO_ROOT points at this real repo)."""
    spec = importlib.util.spec_from_file_location("package_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_repo(base: Path) -> Path:
    """A minimal repo with one skill carrying a reference file and planted junk."""
    repo = base / "repo"
    (repo / "bin").mkdir(parents=True)
    (repo / "bin" / "package.py").write_bytes(SCRIPT.read_bytes())
    skill_dir = repo / "plugins" / "demo" / "skills" / "sample"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: sample\ndescription: sample\n"
        'metadata:\n  version: "2026-07-04"\n---\n\n# Sample\n'
    )
    (skill_dir / "references" / "note.md").write_text("ref\n")
    # Junk that must never ship.
    (skill_dir / ".DS_Store").write_text("junk")
    (skill_dir / "__pycache__").mkdir()
    (skill_dir / "__pycache__" / "x.pyc").write_text("junk")
    return repo


def run_package(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the packager copied into a throwaway repo so REPO_ROOT resolves there."""
    return subprocess.run(
        [sys.executable, str(repo / "bin" / "package.py"), *args],
        capture_output=True,
        text=True,
    )


class DiscoveryTest(unittest.TestCase):
    def test_real_skills_discovered_by_unique_bare_name(self):
        mod = load_module()
        skills = mod.available_skills()
        self.assertTrue(skills, "expected to discover skills in the real repo")
        # Bare names are the dict keys; a collision would silently drop a skill.
        skill_mds = sorted(mod.PLUGINS_ROOT.glob("*/skills/*/SKILL.md"))
        self.assertEqual(len(skills), len(skill_mds), "bare-name collision across domains")
        self.assertIn("dcmtk", skills)

    def test_domain_filter(self):
        mod = load_module()
        radiology = mod.skills_in_domain("radiology")
        self.assertIn("dcmtk", radiology)
        self.assertEqual(mod.skills_in_domain("no-such-domain"), [])


class ArchiveTest(unittest.TestCase):
    def test_layout_single_top_folder_and_excludes_junk(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            repo = make_repo(base)
            out = base / "out"

            result = run_package(repo, "sample", "--out", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)

            names = zipfile.ZipFile(out / "sample.zip").namelist()
            self.assertEqual(
                sorted(names), ["sample/SKILL.md", "sample/references/note.md"]
            )
            self.assertTrue(all(n.startswith("sample/") for n in names))
            self.assertFalse(any(".DS_Store" in n or ".pyc" in n for n in names))

    def test_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            repo = make_repo(base)
            out = base / "out"

            run_package(repo, "sample", "--out", str(out))
            first = (out / "sample.zip").read_bytes()
            run_package(repo, "sample", "--out", str(out))
            second = (out / "sample.zip").read_bytes()
            self.assertEqual(first, second, "archive not byte-reproducible")

    def test_skill_is_byte_identical_to_zip(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            repo = make_repo(base)
            out = base / "out"

            result = run_package(repo, "sample", "--skill", "--out", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (out / "sample.zip").read_bytes(),
                (out / "sample.skill").read_bytes(),
            )

    def test_versioned_names_by_frontmatter(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            repo = make_repo(base)
            out = base / "out"

            result = run_package(repo, "sample", "--versioned", "--out", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out / "sample-2026-07-04.zip").exists())

    def test_unknown_skill_errors(self):
        with tempfile.TemporaryDirectory() as dir_:
            repo = make_repo(Path(dir_))
            result = run_package(repo, "nope")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown skill", result.stderr)


if __name__ == "__main__":
    unittest.main()
