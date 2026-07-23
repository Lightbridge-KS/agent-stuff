#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Behavioral tests for hooks/docs-index-inject/hook.py — the opt-in gating.

Each test builds a throwaway *project* dir (the repo the hook would run inside) and
a throwaway *state* dir standing in for `~/.lightbridge/projects` (wired via
`$LIGHTBRIDGE_STATE_DIR`, the documented testing seam), then drives the real hook.py
as a subprocess with a SessionStart payload on stdin — executing the FILE directly,
exactly as Claude Code's /bin/sh registration does, so a missing executable bit or
broken shebang fails here too. The hook resolves its paired docs_index.py and
lightbridge.py relative to its own location in this repo, so it is exercised in
place — only the project and state under inspection are synthetic.

Opt-in is via a `[docs-index]` section in the project's user-level config,
`<state>/<project-key>/config.toml` (the "local scope" model — nothing in the repo).

    uv run tests/test_hooks.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "docs-index-inject" / "hook.py"


def script_argv(script: Path, *args: str) -> list[str]:
    """argv launching a PEP 723 script the way its real consumer does.

    POSIX execs the file directly, keeping the executable bit and the `uv run`
    shebang under test. Windows CreateProcess cannot launch a shebang script at all
    (WinError 193), so go through Git Bash — the shell Claude Code registers these
    hooks with there — via `exec`, the one form that still lets the shebang choose
    the interpreter. (`bash <script>` would be wrong: bash reads the Python as
    shell.) With no bash, fall back to `uv run`, losing only the shebang assertion.
    """
    if os.name != "nt":
        return [str(script), *args]
    if shutil.which("bash"):
        return ["bash", "-c", 'exec "$0" "$@"', str(script), *args]
    return ["uv", "run", str(script), *args]


# A doc the hook should surface: explicit summary + read_when.
ANNOTATED = "---\nsummary: The cache layer.\nread_when:\n  - touching cache\n---\n# Cache\n"
# Website-style frontmatter: only `description` — must NOT be surfaced by the hook.
WEBSITE = "---\ntitle: Home\ndescription: Landing page.\n---\n# Home\n"
# A root-level CONTEXT.md the hook should surface via the `include` default.
CONTEXT = (
    "---\nsummary: The domain glossary.\nread_when:\n  - naming a domain term\n---\n# Context\n"
)

# Common config.toml bodies.
OPTED_IN = "[docs-index]\n"  # section present, all defaults
DISABLED = "[docs-index]\nenabled = false\n"
NO_SECTION = "[something-else]\nkey = 1\n"  # config exists for another feature


def project_key(path: Path) -> str:
    """Mirror of the lightbridge encoding (resolved path, drive colon dropped, separators → '-')."""
    text = str(path.resolve())
    if len(text) > 1 and text[1] == ":":  # Windows drive letter
        text = text[0] + text[2:]
    return text.replace(os.sep, "-").replace("/", "-")


def run_hook(cwd: Path, state: Path) -> subprocess.CompletedProcess:
    # Execute the file directly (not `sys.executable hook.py`) — the same path as
    # Claude Code's /bin/sh registration, so +x and the uv shebang are under test.
    return subprocess.run(
        script_argv(HOOK),
        input=json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True, encoding="utf-8",
        env={**os.environ, "LIGHTBRIDGE_STATE_DIR": str(state)},
    )


def make_project(
    base: Path,
    *,
    docs: dict[str, str],
    docs_dir: str = "docs",
    root_files: dict[str, str] | None = None,
) -> Path:
    """Build a project dir: a docs dir plus optional repo-root files (e.g. CONTEXT.md)."""
    proj = base / "proj"
    (proj / docs_dir).mkdir(parents=True)
    for name, content in docs.items():
        (proj / docs_dir / name).write_text(content)
    for name, content in (root_files or {}).items():
        (proj / name).write_text(content)
    return proj


def make_state(base: Path, proj: Path, config: str | None) -> Path:
    """Build the user-level state dir; write the project's config.toml when given."""
    state = base / "state"
    state.mkdir(exist_ok=True)
    if config is not None:
        cfg_dir = state / project_key(proj)
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "config.toml").write_text(config)
    return state


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
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            state = make_state(Path(d), proj, OPTED_IN)
            ctx = self.context_of(run_hook(proj, state))
            self.assertIn("cache.md", ctx)
            self.assertIn("Read when: touching cache", ctx)

    def test_no_config_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            state = make_state(Path(d), proj, None)
            self.assert_silent(run_hook(proj, state))

    def test_missing_state_dir_is_silent(self):
        # No ~/.lightbridge/projects equivalent at all — a fresh machine.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            self.assert_silent(run_hook(proj, Path(d) / "nonexistent"))

    def test_section_absent_is_silent(self):
        # config.toml exists but has no [docs-index] section.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            state = make_state(Path(d), proj, NO_SECTION)
            self.assert_silent(run_hook(proj, state))

    def test_disabled_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            state = make_state(Path(d), proj, DISABLED)
            self.assert_silent(run_hook(proj, state))

    def test_website_docs_not_surfaced(self):
        # Opted in, but the only doc has `description` (no summary) -> stay silent.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"index.md": WEBSITE})
            state = make_state(Path(d), proj, OPTED_IN)
            self.assert_silent(run_hook(proj, state))

    def test_empty_section_uses_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            state = make_state(Path(d), proj, OPTED_IN)
            self.assertIn("cache.md", self.context_of(run_hook(proj, state)))

    def test_custom_dir(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d), docs={"cache.md": ANNOTATED}, docs_dir="agent-docs"
            )
            state = make_state(Path(d), proj, '[docs-index]\ndir = "agent-docs"\n')
            self.assertIn("cache.md", self.context_of(run_hook(proj, state)))

    def test_exclude_respected(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            state = make_state(Path(d), proj, '[docs-index]\nexclude = ["private"]\n')
            private = proj / "docs" / "private"
            private.mkdir()
            (private / "secret.md").write_text(ANNOTATED.replace("cache", "secret"))
            ctx = self.context_of(run_hook(proj, state))
            self.assertIn("cache.md", ctx)
            self.assertNotIn("secret.md", ctx)

    def test_config_missing_dir_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            state = make_state(Path(d), proj, '[docs-index]\ndir = "nonexistent"\n')
            self.assert_silent(run_hook(proj, state))

    def test_malformed_config_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            state = make_state(Path(d), proj, "[unclosed\n")
            self.assert_silent(run_hook(proj, state))

    def test_git_subdir_resolves_to_toplevel(self):
        # Launched from a subdirectory of a git repo, the hook must key on the
        # toplevel — the config written for the repo root is still found.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            subprocess.run(
                ["git", "init", "-q", str(proj)], check=True, capture_output=True
            )
            sub = proj / "src" / "inner"
            sub.mkdir(parents=True)
            state = make_state(Path(d), proj, OPTED_IN)
            ctx = self.context_of(run_hook(sub, state))
            self.assertIn("cache.md", ctx)

    def test_legacy_per_repo_config_warns(self):
        # A stray pre-migration <repo>/.lightbridge/config.toml is NOT read, but
        # earns a one-line deprecation warning — even with no user-level config.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            lb = proj / ".lightbridge"
            lb.mkdir()
            (lb / "config.toml").write_text(OPTED_IN)
            state = make_state(Path(d), proj, None)
            ctx = self.context_of(run_hook(proj, state))
            self.assertIn("WARNING", ctx)
            self.assertIn("no longer read", ctx)
            self.assertNotIn("cache.md", ctx)  # the legacy file must not opt in

    def test_legacy_warning_appended_to_index(self):
        # User-level config active AND a stray per-repo file -> index + warning.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={"cache.md": ANNOTATED})
            lb = proj / ".lightbridge"
            lb.mkdir()
            (lb / "config.toml").write_text(OPTED_IN)
            state = make_state(Path(d), proj, OPTED_IN)
            ctx = self.context_of(run_hook(proj, state))
            self.assertIn("cache.md", ctx)
            self.assertIn("no longer read", ctx)

    def test_context_file_surfaced_by_default(self):
        # Root CONTEXT.md appears in its own group, alongside the docs index.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d),
                docs={"cache.md": ANNOTATED},
                root_files={"CONTEXT.md": CONTEXT},
            )
            state = make_state(Path(d), proj, OPTED_IN)
            ctx = self.context_of(run_hook(proj, state))
            self.assertIn("Charter docs (repo root)", ctx)
            self.assertIn("CONTEXT.md", ctx)
            self.assertIn("Read when: naming a domain term", ctx)

    def test_context_injects_without_docs(self):
        # No annotated docs, but a root CONTEXT.md is enough to inject.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(Path(d), docs={}, root_files={"CONTEXT.md": CONTEXT})
            state = make_state(Path(d), proj, OPTED_IN)
            ctx = self.context_of(run_hook(proj, state))
            self.assertIn("CONTEXT.md", ctx)
            self.assertNotIn("Docs index", ctx)  # no docs group when the dir is empty

    def test_context_without_summary_not_surfaced(self):
        # A CONTEXT.md carrying only `description` must not be surfaced.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d),
                docs={"cache.md": ANNOTATED},
                root_files={"CONTEXT.md": WEBSITE},
            )
            state = make_state(Path(d), proj, OPTED_IN)
            ctx = self.context_of(run_hook(proj, state))
            self.assertIn("cache.md", ctx)
            self.assertNotIn("CONTEXT.md", ctx)

    def test_include_empty_suppresses_context(self):
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d),
                docs={"cache.md": ANNOTATED},
                root_files={"CONTEXT.md": CONTEXT},
            )
            state = make_state(Path(d), proj, "[docs-index]\ninclude = []\n")
            ctx = self.context_of(run_hook(proj, state))
            self.assertIn("cache.md", ctx)
            self.assertNotIn("CONTEXT.md", ctx)

    def test_custom_include_path(self):
        # An explicit include list honors its paths and ignores the defaults.
        with tempfile.TemporaryDirectory() as d:
            proj = make_project(
                Path(d),
                docs={"cache.md": ANNOTATED},
                root_files={"GLOSSARY.md": CONTEXT, "CONTEXT.md": CONTEXT},
            )
            state = make_state(Path(d), proj, '[docs-index]\ninclude = ["GLOSSARY.md"]\n')
            ctx = self.context_of(run_hook(proj, state))
            self.assertIn("GLOSSARY.md", ctx)
            self.assertNotIn("CONTEXT.md", ctx)


if __name__ == "__main__":
    unittest.main()
