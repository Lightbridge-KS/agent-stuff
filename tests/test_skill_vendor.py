#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for scripts/skill-vendor.

The load-bearing claims, each pinned by a test:

  - mode is selected by manifest key shape, and `tag` xor `ref` is enforced;
  - the doctor question is one question across modes — installed binary version vs
    the version the skill is bound to — with skew (1) vs broken (2) kept distinct;
  - sync is failure-honest: an unresolvable pin (missing tag, no SKILL.md) exits 2
    and leaves existing registry symlinks byte-for-byte where they were;
  - attest touches exactly two lines of the manifest; every other line survives
    byte-identical (the lb_tomledit invariant, reimplemented locally);
  - the registry scan reports real directories and dangling symlinks as skew (1),
    never touching foreign symlinks that resolve.

    uv run tests/test_skill_vendor.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "scripts" / "skill-vendor" / "skill_vendor.py"

_spec = importlib.util.spec_from_file_location("skill_vendor", TOOL)
sv = importlib.util.module_from_spec(_spec)
sys.modules["skill_vendor"] = sv  # dataclasses resolve annotations via sys.modules
_spec.loader.exec_module(sv)

SKILL_MD = "---\nname: {name}\ndescription: test skill\n---\n\n# {name}\n"


def script_argv(script: Path, *args: str) -> list[str]:
    """argv launching a PEP 723 script the way its real consumer does (see test_plan_store)."""
    if os.name != "nt":
        return [str(script), *args]
    return ["uv", "run", str(script), *args]


def git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def make_shim(directory: Path, name: str, version: str) -> None:
    """A fake binary printing `<name> <version>` — POSIX script + .bat for Windows."""
    posix = directory / name
    posix.write_text(f'#!/bin/sh\necho "{name} {version}"\n', encoding="utf-8")
    posix.chmod(posix.stat().st_mode | stat.S_IEXEC)
    (directory / f"{name}.bat").write_text(f"@echo {name} {version}\n", encoding="utf-8")


class SkillVendorCase(unittest.TestCase):
    """Shared rig: fake upstream repo (two tags, skill path moves), shim binary,
    two fake registries, manifest under a private home."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.home = base / "lightbridge"
        self.home.mkdir()
        self.reg_a = base / "claude-skills"
        self.reg_b = base / "codex-skills"
        self.reg_a.mkdir()
        self.reg_b.mkdir()

        # Upstream repo: v1.0.0 keeps the skill at .agents/skills/x (old layout),
        # v2.0.0 moves it to skills/x — mirrors crabbox's real history.
        self.repo = base / "upstream"
        self.repo.mkdir()
        git("init", "-q", cwd=self.repo)
        old = self.repo / ".agents" / "skills" / "x"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text(SKILL_MD.format(name="x"), encoding="utf-8")
        git("add", "-A", cwd=self.repo)
        git("commit", "-qm", "v1 layout", cwd=self.repo)
        git("tag", "v1.0.0", cwd=self.repo)
        new = self.repo / "skills" / "x"
        new.mkdir(parents=True)
        (new / "SKILL.md").write_text(SKILL_MD.format(name="x"), encoding="utf-8")
        git("rm", "-rq", ".agents", cwd=self.repo)
        git("add", "-A", cwd=self.repo)
        git("commit", "-qm", "v2 layout", cwd=self.repo)
        git("tag", "v2.0.0", cwd=self.repo)

        self.shims = base / "shims"
        self.shims.mkdir()
        make_shim(self.shims, "x", "1.0.0")
        self._old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{self.shims}{os.pathsep}{self._old_path}"
        self.addCleanup(os.environ.__setitem__, "PATH", self._old_path)

    def manifest(self, body: str) -> None:
        defaults = (
            f'[defaults]\nregistries = [{sv.toml_str(str(self.reg_a))}, '
            f"{sv.toml_str(str(self.reg_b))}]\n\n"
        )
        (self.home / "skill-vendors.toml").write_text(defaults + body, encoding="utf-8")

    def first_party(self) -> None:
        self.manifest(
            "[x]\n"
            'binary = "x"\n'
            'source = "repo"\n'
            f"repo = {sv.toml_str(str(self.repo))}\n"
            'tag = "v{version}"\n'
            '# layout moved at v2\n'
            'skill-paths = ["skills/x", ".agents/skills/x"]\n'
        )

    def third_party(self, extra: str = "") -> None:
        ref = git("rev-parse", "v1.0.0", cwd=self.repo)
        self.manifest(
            "[x]\n"
            'binary = "x"\n'
            'source = "repo"\n'
            f"repo = {sv.toml_str(str(self.repo))}\n"
            f"ref = {sv.toml_str(ref)}\n"
            f"{extra}"
            'skill-paths = ["skills/x", ".agents/skills/x"]\n'
        )

    # ── manifest validation ─────────────────────────────────────────────────

    def test_missing_manifest_names_path_and_sample(self) -> None:
        entries, _, problems = sv.load_manifest(self.home)
        self.assertEqual(entries, [])
        self.assertEqual(len(problems), 1)
        self.assertIn(str(self.home / "skill-vendors.toml"), problems[0])
        self.assertIn("[defaults]", problems[0])  # the copyable sample

    def test_tag_xor_ref_enforced(self) -> None:
        for both_or_neither in ('tag = "v{version}"\nref = "abc"\n', ""):
            self.manifest(
                f'[x]\nbinary = "x"\nsource = "repo"\n'
                f"repo = {sv.toml_str(str(self.repo))}\n"
                f'{both_or_neither}skill-paths = ["skills/x"]\n'
            )
            _, _, problems = sv.load_manifest(self.home)
            self.assertTrue(any("exactly one" in p for p in problems), both_or_neither)

    def test_install_tree_rejects_repo_keys(self) -> None:
        self.manifest('[x]\nbinary = "x"\nsource = "install-tree"\nskill-path = "/opt/x"\ntag = "v1"\n')
        _, _, problems = sv.load_manifest(self.home)
        self.assertTrue(any("no `repo`/`tag`/`ref`" in p for p in problems))

    def test_version_parse_from_shim(self) -> None:
        self.first_party()
        entries, _, _ = sv.load_manifest(self.home)
        version, problem = sv.installed_version(entries[0])
        self.assertIsNone(problem)
        self.assertEqual(version, "1.0.0")

    # ── sync: first-party ───────────────────────────────────────────────────

    def links(self) -> list[Path]:
        return [self.reg_a / "x", self.reg_b / "x"]

    def test_sync_creates_worktree_and_links(self) -> None:
        self.first_party()
        self.assertEqual(sv.cmd_sync([], self.home, as_json=False), 0)
        wt = self.home / "skill-vendors" / "worktrees" / "x"
        self.assertEqual(git("describe", "--tags", cwd=wt), "v1.0.0")
        for link in self.links():
            self.assertTrue(link.is_symlink())
            # v1.0.0 has no skills/x — the probe must fall through to .agents/skills/x.
            self.assertEqual(link.resolve(), (wt / ".agents" / "skills" / "x").resolve())
            self.assertTrue((link / "SKILL.md").is_file())
        # idempotent re-run, then a clean doctor
        self.assertEqual(sv.cmd_sync([], self.home, as_json=False), 0)
        self.assertEqual(sv.cmd_status([], self.home, as_json=False, exit_semantics=True), 0)

    def test_doctor_before_first_sync_is_broken(self) -> None:
        self.first_party()
        self.assertEqual(sv.cmd_status([], self.home, as_json=False, exit_semantics=True), 2)

    def test_upgrade_skews_then_sync_heals_and_path_probe_moves(self) -> None:
        self.first_party()
        sv.cmd_sync([], self.home, as_json=False)
        make_shim(self.shims, "x", "2.0.0")  # the "brew upgrade"
        reports = [sv.assess(e, self.home) for e in sv.load_manifest(self.home)[0]]
        self.assertEqual(reports[0].severity, 1)
        self.assertTrue(any("skill-vendor sync x" in n for n in reports[0].notes))
        self.assertEqual(sv.cmd_sync([], self.home, as_json=False), 0)
        wt = self.home / "skill-vendors" / "worktrees" / "x"
        self.assertEqual(git("describe", "--tags", cwd=wt), "v2.0.0")
        for link in self.links():  # v2 layout: probe now hits skills/x first
            self.assertEqual(link.resolve(), (wt / "skills" / "x").resolve())
        self.assertEqual(sv.cmd_status([], self.home, as_json=False, exit_semantics=True), 0)

    def test_sync_missing_tag_is_honest(self) -> None:
        self.first_party()
        sv.cmd_sync([], self.home, as_json=False)
        before = [link.resolve() for link in self.links()]
        make_shim(self.shims, "x", "3.0.0")  # no v3.0.0 tag exists
        self.assertEqual(sv.cmd_sync([], self.home, as_json=False), 2)
        self.assertEqual([link.resolve() for link in self.links()], before)

    def test_sync_refuses_to_replace_real_directory(self) -> None:
        self.first_party()
        (self.reg_a / "x").mkdir()  # a real dir squatting on the entry's name
        self.assertEqual(sv.cmd_sync([], self.home, as_json=False), 2)
        self.assertFalse((self.reg_a / "x").is_symlink())
        self.assertTrue((self.reg_b / "x").is_symlink())  # the healthy registry still linked

    # ── third-party: attestation ────────────────────────────────────────────

    def test_never_attested_is_skew(self) -> None:
        self.third_party()
        sv.cmd_sync([], self.home, as_json=False)
        self.assertEqual(sv.cmd_status([], self.home, as_json=False, exit_semantics=True), 1)
        report = sv.assess(sv.load_manifest(self.home)[0][0], self.home)
        self.assertTrue(any("never attested" in n for n in report.notes))

    def test_attest_stamps_and_touches_nothing_else(self) -> None:
        self.third_party()
        sv.cmd_sync([], self.home, as_json=False)
        path = self.home / "skill-vendors.toml"
        before = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sv.cmd_attest("x", self.home), 0)
        after = path.read_text(encoding="utf-8").splitlines()
        added = [line for line in after if line not in before]
        self.assertEqual(
            sorted(line.split(" =")[0] for line in added), ["verified-against", "verified-on"]
        )
        self.assertIn("verified-against = '1.0.0'", added)
        self.assertTrue(any(re.match(r"verified-on = \d{4}-\d{2}-\d{2}$", line) for line in added))
        self.assertEqual([line for line in before if line not in after], [])  # nothing lost
        self.assertEqual(sv.cmd_status([], self.home, as_json=False, exit_semantics=True), 0)

    def test_stale_attestation_is_skew_and_reattest_updates_in_place(self) -> None:
        self.third_party("verified-against = '0.9.0'\nverified-on = 2026-01-01\n")
        sv.cmd_sync([], self.home, as_json=False)
        report = sv.assess(sv.load_manifest(self.home)[0][0], self.home)
        self.assertEqual(report.severity, 1)
        self.assertTrue(any("re-verify" in n for n in report.notes))
        self.assertEqual(sv.cmd_attest("x", self.home), 0)
        text = (self.home / "skill-vendors.toml").read_text(encoding="utf-8")
        self.assertIn("verified-against = '1.0.0'", text)
        self.assertNotIn("0.9.0", text)  # replaced in place, not duplicated

    def test_attest_refuses_first_party(self) -> None:
        self.first_party()
        self.assertEqual(sv.cmd_attest("x", self.home), 2)

    # ── co-shipped ──────────────────────────────────────────────────────────

    def test_co_shipped_links_and_breaks_when_tree_vanishes(self) -> None:
        tree = Path(self.tmp.name) / "install" / "skills" / "x"
        tree.mkdir(parents=True)
        (tree / "SKILL.md").write_text(SKILL_MD.format(name="x"), encoding="utf-8")
        self.manifest(
            f'[x]\nbinary = "x"\nsource = "install-tree"\nskill-path = {sv.toml_str(str(tree))}\n'
        )
        self.assertEqual(sv.cmd_sync([], self.home, as_json=False), 0)
        self.assertEqual((self.reg_a / "x").resolve(), tree.resolve())
        self.assertEqual(sv.cmd_status([], self.home, as_json=False, exit_semantics=True), 0)
        (tree / "SKILL.md").unlink()
        self.assertEqual(sv.cmd_status([], self.home, as_json=False, exit_semantics=True), 2)

    # ── registry scan ───────────────────────────────────────────────────────

    def test_registry_scan_flags_real_dirs_and_dangling_links_as_skew(self) -> None:
        self.first_party()
        sv.cmd_sync([], self.home, as_json=False)
        (self.reg_a / "squatter").mkdir()
        (self.reg_b / "dangler").symlink_to(Path(self.tmp.name) / "gone")
        foreign = Path(self.tmp.name) / "foreign-skill"
        foreign.mkdir()
        (self.reg_a / "foreign").symlink_to(foreign)  # resolves → not our business
        self.assertEqual(sv.cmd_status([], self.home, as_json=False, exit_semantics=True), 1)
        findings = sv.scan_registries([self.reg_a, self.reg_b], {"x"})
        notes = [note for _, note in findings]
        self.assertTrue(any("real directory" in n for n in notes))
        self.assertTrue(any("dangling" in n for n in notes))
        self.assertFalse(any("foreign" in n for n in notes))

    def test_named_selection_skips_registry_scan(self) -> None:
        self.first_party()
        sv.cmd_sync([], self.home, as_json=False)
        (self.reg_a / "squatter").mkdir()
        self.assertEqual(sv.cmd_status(["x"], self.home, as_json=False, exit_semantics=True), 0)

    # ── end-to-end through the shebang ──────────────────────────────────────

    def test_subprocess_doctor_json(self) -> None:
        self.first_party()
        sv.cmd_sync([], self.home, as_json=False)
        env = os.environ | {"SKILL_VENDOR_HOME": str(self.home)}
        proc = subprocess.run(
            script_argv(TOOL, "doctor", "--json"), capture_output=True, text=True, env=env
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["entries"][0]["name"], "x")
        self.assertEqual(payload["entries"][0]["pinned"], "v1.0.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
