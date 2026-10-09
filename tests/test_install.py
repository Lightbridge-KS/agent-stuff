#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for bin/install.py guards and multi-agent targets.

Each test spins up a throwaway repo layout (bin/ + plugins/<domain>/skills/<name>/)
in a temp dir and drives install.py as a subprocess. A per-test targets.toml points
the agent flags at temp directories so nothing touches the real home dir.

    uv run tests/test_install.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bin" / "install.py"
SKILL_MD = "---\nname: sample\ndescription: sample\n---\n"
AGENT_MD = "---\nname: sample-agent\ndescription: sample agent\n---\nBody.\n"
# A harmless default so the registry loads; tests needing real agents override it.
DEFAULT_TARGETS = '[claude]\nskills = "~/.claude/skills"\n'


def make_repo(base: Path, targets_toml: str = DEFAULT_TARGETS) -> Path:
    """Create a minimal repo with one skill at plugins/demo/skills/sample/SKILL.md."""
    repo = base / "repo"
    (repo / "bin").mkdir(parents=True)
    skill_dir = repo / "plugins" / "demo" / "skills" / "sample"
    skill_dir.mkdir(parents=True)
    (repo / "bin" / "install.py").write_bytes(SCRIPT.read_bytes())
    (repo / "bin" / "targets.toml").write_text(targets_toml)
    (skill_dir / "SKILL.md").write_text(SKILL_MD)
    return repo


def make_agent(repo: Path, domain: str = "demo", name: str = "sample-agent") -> Path:
    """Add a subagent file at plugins/<domain>/agents/<name>.md."""
    agents_dir = repo / "plugins" / domain / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_md = agents_dir / f"{name}.md"
    agent_md.write_text(AGENT_MD)
    return agent_md


def make_hook(repo: Path, name: str = "sample-hook") -> Path:
    """Add a hooks/<name>/ with a hook.toml descriptor and its command file."""
    hook_dir = repo / "hooks" / name
    hook_dir.mkdir(parents=True)
    (hook_dir / "hook.py").write_text("#!/usr/bin/env python3\n")
    (hook_dir / "hook.toml").write_text(
        'event = "SessionStart"\n'
        'command = "hook.py"\n'
        'statusMessage = "Injecting docs index"\n'
    )
    return hook_dir


def section(text: str, start_marker: str, end_marker: str) -> str:
    """Return the slice of `text` between two markers (exclusive)."""
    body = text.split(start_marker, 1)[1]
    return body.split(end_marker, 1)[0]


def run_install(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the installer copied into a throwaway repo so REPO_ROOT resolves to that repo."""
    return subprocess.run(
        [sys.executable, str(repo / "bin" / "install.py"), *args],
        capture_output=True,
        text=True, encoding="utf-8",
    )


class InstallTest(unittest.TestCase):
    def test_force_skips_target_that_is_source(self):
        with tempfile.TemporaryDirectory() as dir_:
            repo = make_repo(Path(dir_))
            source_parent = repo / "plugins" / "demo" / "skills"

            # Target dir IS the skills dir, so the "target" resolves to the source.
            result = run_install(
                repo,
                "--target", str(source_parent),
                "--force", "sample",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("target is source, skipping", result.stderr)
            self.assertTrue((source_parent / "sample" / "SKILL.md").exists())

    def test_force_copy_replaces_existing_symlink(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            repo = make_repo(base)
            target = base / "target"
            target.mkdir()
            source = repo / "plugins" / "demo" / "skills" / "sample"
            os.symlink(source, target / "sample")

            result = run_install(
                repo,
                "--target", str(target),
                "--force", "--mode", "copy", "sample",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("copy sample", result.stdout)
            self.assertFalse((target / "sample").is_symlink())
            self.assertTrue((target / "sample" / "SKILL.md").exists())
            self.assertTrue((source / "SKILL.md").exists())

    def test_multiple_agents_in_one_run(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            alpha = base / "alpha" / "skills"
            beta = base / "beta" / "skills"
            toml = (
                f"[alpha]\nskills = {str(alpha)!r}\n"
                f"[beta]\nskills = {str(beta)!r}\n"
            )
            repo = make_repo(base, targets_toml=toml)

            result = run_install(repo, "--alpha", "--beta", "--mode", "copy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((alpha / "sample" / "SKILL.md").exists())
            self.assertTrue((beta / "sample" / "SKILL.md").exists())

    def test_all_installs_only_present_agents(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            present = base / "present" / "skills"
            absent = base / "absent" / "skills"
            # "present" agent: its parent dir exists, so it is detected.
            (base / "present").mkdir(parents=True)
            toml = (
                f"[present]\nskills = {str(present)!r}\n"
                f"[absent]\nskills = {str(absent)!r}\n"
            )
            repo = make_repo(base, targets_toml=toml)

            result = run_install(repo, "--all", "--mode", "copy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((present / "sample" / "SKILL.md").exists())
            self.assertFalse(absent.exists())

    def test_hooks_render_emits_claude_and_codex(self):
        with tempfile.TemporaryDirectory() as dir_:
            repo = make_repo(Path(dir_))
            hook_dir = make_hook(repo)

            result = run_install(repo, "--hooks")

            self.assertEqual(result.returncode, 0, result.stderr)
            out = result.stdout
            # The command path is resolved for this checkout's hook folder. It is
            # embedded in JSON, so compare against the JSON-encoded form — on Windows
            # the separators come back escaped (C:\\Users\\...), on POSIX unchanged.
            encoded = json.dumps(str((hook_dir / "hook.py").resolve()))[1:-1]
            self.assertIn(encoded, out)
            self.assertIn("SessionStart", out)
            # All three destinations are surfaced.
            self.assertIn("~/.claude/settings.json", out)
            self.assertIn("~/.codex/hooks.json", out)
            self.assertIn("~/.codex/config.toml", out)
            # The "pick one Codex form" + trust guidance is present.
            self.assertIn("EXACTLY ONE", out)
            self.assertIn("/hooks", out)

    def test_hooks_render_blocks_are_valid(self):
        with tempfile.TemporaryDirectory() as dir_:
            repo = make_repo(Path(dir_))
            # install.py resolves REPO_ROOT, so compare against the realpath.
            command = str((make_hook(repo) / "hook.py").resolve())

            out = run_install(repo, "--hooks").stdout

            claude = json.loads(
                section(out, "~/.claude/settings.json ---\n", "\n# ---")
            )
            codex = json.loads(
                section(out, "~/.codex/hooks.json ---\n", "\n# ---")
            )
            for block in (claude, codex):
                handler = block["hooks"]["SessionStart"][0]["hooks"][0]
                self.assertEqual(handler["type"], "command")
                self.assertEqual(handler["command"], command)
            # Codex shows statusMessage; the Claude block omits it.
            self.assertNotIn("statusMessage", claude["hooks"]["SessionStart"][0]["hooks"][0])
            self.assertIn("statusMessage", codex["hooks"]["SessionStart"][0]["hooks"][0])

    def test_subagents_install_alongside_skills(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            skills = base / "alpha" / "skills"
            agents = base / "alpha" / "agents"
            toml = (
                f"[alpha]\nskills = {str(skills)!r}\nagents = {str(agents)!r}\n"
            )
            repo = make_repo(base, targets_toml=toml)
            make_agent(repo)

            result = run_install(repo, "--alpha", "--mode", "copy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((skills / "sample" / "SKILL.md").exists())
            self.assertTrue((agents / "sample-agent.md").is_file())

    def test_subagent_symlinks_as_file(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            skills = base / "alpha" / "skills"
            agents = base / "alpha" / "agents"
            toml = (
                f"[alpha]\nskills = {str(skills)!r}\nagents = {str(agents)!r}\n"
            )
            repo = make_repo(base, targets_toml=toml)
            source = make_agent(repo)

            result = run_install(repo, "--alpha", "--mode", "symlink", "sample-agent")

            self.assertEqual(result.returncode, 0, result.stderr)
            link = agents / "sample-agent.md"
            self.assertTrue(link.is_symlink())
            self.assertEqual(os.path.realpath(link), str(source.resolve()))
            # Bare-name selection installed only the subagent, not the skill.
            self.assertFalse(skills.exists())

    def test_target_without_agents_key_skips_subagents(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            skills = base / "alpha" / "skills"
            toml = f"[alpha]\nskills = {str(skills)!r}\n"
            repo = make_repo(base, targets_toml=toml)
            make_agent(repo)

            result = run_install(repo, "--alpha", "--mode", "copy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("skipping subagent: demo/sample-agent", result.stderr)
            self.assertTrue((skills / "sample" / "SKILL.md").exists())
            self.assertFalse((base / "alpha" / "agents").exists())

    def test_target_rejects_agent_combo(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml = f"[alpha]\nskills = {str(base / 'a' / 'skills')!r}\n"
            repo = make_repo(base, targets_toml=toml)

            result = run_install(repo, "--target", str(base / "x"), "--alpha")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--target cannot be combined", result.stderr)

    def test_root_installs_from_foreign_content_tree(self):
        """The REAL installer serves a second content-only tree via --root."""
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            content = base / "private" / "plugins" / "demo" / "skills" / "sample"
            content.mkdir(parents=True)
            (content / "SKILL.md").write_text(SKILL_MD)
            dest = base / "dest"

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(base / "private"),
                 "--target", str(dest)],
                capture_output=True, text=True, encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((dest / "sample" / "SKILL.md").exists())

    def test_root_empty_tree_names_the_root(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            (base / "empty").mkdir()
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(base / "empty"),
                 "--target", str(base / "dest")],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn(str(base / "empty"), result.stderr)


def two_targets_toml(base: Path) -> tuple[str, Path, Path]:
    """A registry with two present targets: alpha and beta (parents created)."""
    alpha = base / "alpha" / "skills"
    beta = base / "beta" / "skills"
    (base / "alpha").mkdir(parents=True)
    (base / "beta").mkdir(parents=True)
    toml = f"[alpha]\nskills = {str(alpha)!r}\n[beta]\nskills = {str(beta)!r}\n"
    return toml, alpha, beta


def add_skill(repo: Path, domain: str, name: str) -> Path:
    skill_dir = repo / "plugins" / domain / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
    return skill_dir


class ProfileTest(unittest.TestCase):
    """profiles.toml: per-target selection, ownership-bounded prune, read-only check."""

    def test_no_profile_installs_everything_everywhere(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)

            result = run_install(repo, "--all", "--mode", "copy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((alpha / "sample" / "SKILL.md").exists())
            self.assertTrue((beta / "sample" / "SKILL.md").exists())

    def test_exclude_and_like(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            toml += f"[gamma]\nskills = {str(base / 'gamma' / 'skills')!r}\n"
            (base / "gamma").mkdir()
            repo = make_repo(base, targets_toml=toml)
            add_skill(repo, "other", "extra")
            (repo / "profiles.toml").write_text(
                '[beta]\nexclude = ["demo/*"]\n[gamma]\nlike = "beta"\n'
            )

            result = run_install(repo, "--all", "--mode", "copy")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((alpha / "sample").exists())  # no block → everything
            self.assertTrue((alpha / "extra").exists())
            self.assertFalse((beta / "sample").exists())
            self.assertTrue((beta / "extra").exists())
            gamma = base / "gamma" / "skills"
            self.assertFalse((gamma / "sample").exists())  # copied from beta
            self.assertTrue((gamma / "extra").exists())

    def test_explicit_name_bypasses_profile_with_notice(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)
            (repo / "profiles.toml").write_text('[beta]\nexclude = ["demo/sample"]\n')

            result = run_install(repo, "--beta", "--mode", "copy", "sample")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((beta / "sample").exists())
            self.assertIn("outside the beta profile", result.stderr)

    def test_domain_stays_within_profile(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)
            (repo / "profiles.toml").write_text('[beta]\nexclude = ["demo/sample"]\n')

            result = run_install(repo, "--beta", "--mode", "copy", "--domain", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((beta / "sample").exists())
            self.assertIn("excluded by the beta profile", result.stderr)

    def test_bad_profile_fails_before_installing(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)
            (repo / "profiles.toml").write_text('[nope]\ninclude = ["*"]\n')

            result = run_install(repo, "--all", "--mode", "copy")

            self.assertEqual(result.returncode, 1)
            self.assertIn("unknown target 'nope'", result.stderr)
            self.assertFalse(alpha.exists())

    def test_prune_removes_owned_only(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)
            add_skill(repo, "other", "extra")
            alpha.mkdir(parents=True)
            # Owned but unwanted after the profile lands: a link into this tree.
            os.symlink(repo / "plugins" / "demo" / "skills" / "sample", alpha / "sample")
            # Owned and dangling: a link into a skill this tree renamed away.
            os.symlink(repo / "plugins" / "demo" / "skills" / "gone", alpha / "gone")
            # Foreign: a link elsewhere, and a real adopted dir.
            elsewhere = base / "elsewhere" / "vendored"
            elsewhere.mkdir(parents=True)
            os.symlink(elsewhere, alpha / "vendored")
            (alpha / "adopted").mkdir()
            (alpha / "adopted" / "SKILL.md").write_text("---\nname: adopted\n---\n")
            (repo / "profiles.toml").write_text('[alpha]\nexclude = ["demo/*"]\n')

            dry = run_install(repo, "--alpha", "--mode", "symlink", "--prune", "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("would prune", dry.stdout)
            self.assertTrue((alpha / "sample").is_symlink())  # dry-run touched nothing

            result = run_install(repo, "--alpha", "--mode", "symlink", "--prune")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((alpha / "sample").is_symlink())
            self.assertFalse((alpha / "gone").is_symlink())
            self.assertTrue((alpha / "extra").is_symlink())
            self.assertTrue((alpha / "vendored").is_symlink())
            self.assertTrue((alpha / "adopted" / "SKILL.md").is_file())

    def test_prune_copy_mode_matches_catalog_and_frontmatter(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)
            add_skill(repo, "other", "extra")
            alpha.mkdir(parents=True)
            # A stale copy of a catalog skill → owned; a same-named dir with a
            # different frontmatter name, and an unknown name → foreign.
            (alpha / "sample").mkdir()
            (alpha / "sample" / "SKILL.md").write_text("---\nname: sample\n---\n")
            (alpha / "extra").mkdir()
            (alpha / "extra" / "SKILL.md").write_text("---\nname: theirs\n---\n")
            (alpha / "unknown").mkdir()
            (alpha / "unknown" / "SKILL.md").write_text("---\nname: unknown\n---\n")
            (repo / "profiles.toml").write_text('[alpha]\nexclude = ["*"]\n')

            result = run_install(repo, "--alpha", "--mode", "copy", "--prune")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((alpha / "sample").exists())
            self.assertTrue((alpha / "extra" / "SKILL.md").is_file())
            self.assertTrue((alpha / "unknown" / "SKILL.md").is_file())

    def test_check_reports_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)
            add_skill(repo, "other", "extra")
            (repo / "profiles.toml").write_text('[beta]\nexclude = ["other/*"]\n')
            alpha.mkdir(parents=True)
            beta.mkdir(parents=True)
            os.symlink(repo / "plugins" / "demo" / "skills" / "sample", alpha / "sample")
            os.symlink(repo / "plugins" / "demo" / "skills" / "gone", alpha / "gone")
            (alpha / "extra").mkdir()  # foreign dir squatting on a wanted name
            os.symlink(repo / "plugins" / "other" / "skills" / "extra", beta / "extra")

            result = run_install(repo, "--check")

            self.assertEqual(result.returncode, 1)
            lines = {" ".join(line.split()) for line in result.stdout.splitlines()}
            self.assertIn("alpha stray gone", lines)
            self.assertIn("alpha foreign other/extra", lines)
            self.assertIn("beta missing demo/sample", lines)
            self.assertIn("beta stray extra", lines)
            self.assertNotIn("alpha missing demo/sample", lines)
            self.assertTrue((alpha / "gone").is_symlink())  # read-only
            self.assertTrue((beta / "extra").is_symlink())

            # --force replaces the squatter (as it always did); --prune drops the strays.
            converge = run_install(repo, "--all", "--mode", "symlink", "--force", "--prune")
            self.assertEqual(converge.returncode, 0, converge.stderr)
            again = run_install(repo, "--check")
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    def test_check_rejects_write_flags(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)

            result = run_install(repo, "--check", "--prune")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("read-only", result.stderr)

    def test_list_prints_matrix(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)
            (repo / "profiles.toml").write_text('[beta]\nexclude = ["demo/*"]\n')

            result = run_install(repo, "--list")

            self.assertEqual(result.returncode, 0, result.stderr)
            matrix = result.stdout.split("Profile matrix", 1)[1]
            row = next(l for l in matrix.splitlines() if "demo/sample" in l)
            self.assertEqual(row.split()[1:], ["x", "."])

    def test_root_reads_its_own_profile(self):
        with tempfile.TemporaryDirectory() as dir_:
            base = Path(dir_)
            toml, alpha, beta = two_targets_toml(base)
            repo = make_repo(base, targets_toml=toml)
            (repo / "profiles.toml").write_text('[alpha]\nexclude = ["*"]\n')  # not used
            private = base / "private"
            skill_dir = private / "plugins" / "secret" / "skills" / "hidden"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: hidden\ndescription: h\n---\n")
            (private / "profiles.toml").write_text('[beta]\nexclude = ["secret/*"]\n')

            result = run_install(
                repo, "--root", str(private), "--all", "--mode", "copy"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((alpha / "hidden").exists())
            self.assertFalse((beta / "hidden").exists())


if __name__ == "__main__":
    unittest.main()
