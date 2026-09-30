#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for `hooks/fleet-inject` — the network-free SessionStart nudge.

The hook reads `~/.lightbridge/fleet.toml`, the receipts beside it, and the project's
config, so `HOME`/`USERPROFILE` point at a temp home (the `test_repo_links.py` pattern);
`UV_CACHE_DIR` stays on the real cache so the fake-HOME subprocesses start warm.

    uv run tests/test_fleet_hook.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "fleet-inject" / "hook.py"

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}
UV_CACHE_DIR = os.environ.get("UV_CACHE_DIR", str(Path("~/.cache/uv").expanduser()))


def script_argv(script: Path, *args: str) -> list[str]:
    if os.name != "nt":
        return [str(script), *args]
    return ["uv", "run", str(script), *args]


def home_vars(home: Path) -> dict[str, str]:
    return {"HOME": str(home), "USERPROFILE": str(home)}


def project_key(path: Path) -> str:
    text = str(path.resolve())
    if len(text) > 1 and text[1] == ":":
        text = text[0] + text[2:]
    return text.replace(os.sep, "-").replace("/", "-")


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=GIT_ENV)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {proc.stdout}{proc.stderr}")
    return proc.stdout.strip()


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", name)
    return git(repo, "rev-parse", "HEAD")


class FleetHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.lb = self.home / ".lightbridge"
        (self.lb / "fleet").mkdir(parents=True)
        # The repo under test is the hub's clone of "agent-stuff": three commits on main,
        # origin/main pointing at the tip (a fake remote-tracking ref is enough).
        self.repo = base / "hub" / "agent-stuff"
        self.repo.mkdir(parents=True)
        git(self.repo, "init", "-q", "--initial-branch=main")
        self.shas = [commit(self.repo, f"c{i}.txt") for i in range(3)]
        git(self.repo, "update-ref", "refs/remotes/origin/main", self.shas[-1])
        self.write_fleet()
        self.write_config("[fleet]\n")

    def write_fleet(self, nodes: str = '[nodes.box]\nssh = "box"\nrepos = ["agent-stuff", "agent-instruction"]\n') -> None:
        (self.lb / "fleet.toml").write_text(
            f'[hub]\nroot = "{self.repo.parent}"\n'
            '[repos.agent-stuff]\napply = "x"\n[repos.agent-instruction]\napply = "y"\n' + nodes,
            encoding="utf-8",
        )

    def write_config(self, body: str) -> None:
        cfg = self.lb / "projects" / project_key(self.repo) / "config.toml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(f'root = "{self.repo}"\n{body}', encoding="utf-8")

    def write_receipt(self, node: str, after: str | None, ok: bool = True) -> None:
        repos = {"agent-stuff": {"after": after}} if after else {}
        (self.lb / "fleet" / f"{node}.json").write_text(
            json.dumps({"node": node, "ok": ok, "repos": repos}), encoding="utf-8"
        )

    def run_hook(self, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            script_argv(HOOK),
            input=json.dumps({"cwd": str(cwd or self.repo), "hook_event_name": "SessionStart"}),
            capture_output=True, text=True, encoding="utf-8",
            env={**GIT_ENV, **home_vars(self.home), "UV_CACHE_DIR": UV_CACHE_DIR},
        )

    def context(self, result: subprocess.CompletedProcess) -> str:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip(), "expected a context, got silence")
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def assert_silent(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "", result.stdout)

    def test_never_synced_node_is_named(self):
        ctx = self.context(self.run_hook())
        self.assertIn("`box` has never been synced for `agent-stuff`", ctx)
        self.assertIn("lb fleet sync", ctx)
        self.assertIn("go-ahead", ctx)

    def test_lagging_receipt_counts_commits(self):
        self.write_receipt("box", self.shas[0])
        ctx = self.context(self.run_hook())
        self.assertIn(f"last synced `agent-stuff` at {self.shas[0][:7]}", ctx)
        self.assertIn(f"origin/main is {self.shas[-1][:7]}", ctx)
        self.assertIn("2 commit(s) ahead", ctx)

    def test_in_sync_receipt_is_silent(self):
        self.write_receipt("box", self.shas[-1])
        self.assert_silent(self.run_hook())

    def test_in_sync_but_last_sync_had_problems_is_mentioned(self):
        self.write_receipt("box", self.shas[-1], ok=False)
        self.assertIn("reported problems", self.context(self.run_hook()))

    def test_runs_from_a_subdirectory(self):
        sub = self.repo / "docs"
        sub.mkdir()
        self.assertIn("never been synced", self.context(self.run_hook(sub)))

    def test_repo_key_override(self):
        # The checkout folder is not named like the inventory entry: `repo` bridges it.
        renamed = self.repo.parent / "stuff-checkout"
        self.repo.rename(renamed)
        self.repo = renamed
        self.write_config('[fleet]\nrepo = "agent-stuff"\n')
        self.assertIn("`agent-stuff`", self.context(self.run_hook()))

    def test_silent_without_section_or_when_disabled(self):
        self.write_config("")
        self.assert_silent(self.run_hook())
        self.write_config("[fleet]\nenabled = false\n")
        self.assert_silent(self.run_hook())

    def test_silent_on_a_non_hub(self):
        (self.lb / "fleet.toml").unlink()
        self.assert_silent(self.run_hook())

    def test_silent_when_inventory_is_unusable(self):
        (self.lb / "fleet.toml").write_text("[hub\n", encoding="utf-8")
        self.assert_silent(self.run_hook())

    def test_silent_when_repo_is_not_in_the_fleet(self):
        self.write_config('[fleet]\nrepo = "unrelated"\n')
        self.assert_silent(self.run_hook())

    def test_silent_when_no_node_carries_the_repo(self):
        self.write_fleet('[nodes.box]\nssh = "box"\nrepos = ["agent-instruction"]\n')
        self.assert_silent(self.run_hook())

    def test_silent_without_origin_main(self):
        git(self.repo, "update-ref", "-d", "refs/remotes/origin/main")
        self.assert_silent(self.run_hook())

    def test_malformed_receipt_reads_as_never_synced(self):
        (self.lb / "fleet" / "box.json").write_text("{nope", encoding="utf-8")
        self.assertIn("never been synced", self.context(self.run_hook()))

    def test_fails_open_on_garbage_input(self):
        result = subprocess.run(
            script_argv(HOOK), input="not json", capture_output=True, text=True, encoding="utf-8",
            cwd=str(self.home), env={**GIT_ENV, **home_vars(self.home), "UV_CACHE_DIR": UV_CACHE_DIR},
        )
        self.assert_silent(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
