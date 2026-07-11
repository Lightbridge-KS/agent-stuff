#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for hooks/handoff-inject/hook.py — what it announces, and what it must not.

Each test builds a throwaway lightbridge state dir (pointed at by $LIGHTBRIDGE_STATE_DIR) and
drives the real hook.py as a subprocess with a SessionStart payload on stdin — executing the
FILE directly, exactly as Claude Code's /bin/sh registration does, so a missing executable bit
or a broken shebang fails here too.

The load-bearing behaviours:

  * a cross-repo handoff (`from:` present) is ANNOUNCED — nobody asked for it, so nothing else
    would surface it;
  * a same-repo handoff is NEVER announced — it is pulled on demand, and injecting it every
    session would fight the harness's own context management;
  * an acknowledged handoff goes quiet, durably — a notice that never stops firing is a notice
    that gets tuned out, which is the exact failure the hook exists to prevent.

    uv run tests/test_handoff_hook.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "handoff-inject" / "hook.py"
SCRIPT = REPO_ROOT / "scripts" / "handoff" / "handoff.py"

CROSS_REPO = """\
---
project: /work/dest
created: 2026-07-11T17:39
harness: claude-code
focus: "The dataset landed; it exposes a routing gap in you."
git: main @ d04d639
from:
  repo: orthanc-test-pacs
  project: /work/origin
  git: main @ 72745e1
  breaking: true
---

## Impact here
You will route laterals.
"""

CROSS_REPO_SAFE = CROSS_REPO.replace("breaking: true", "breaking: false").replace(
    "The dataset landed; it exposes a routing gap in you.", "FYI only."
)

SAME_REPO = """\
---
project: /work/dest
created: 2026-07-10T09:00
harness: claude-code
focus: "Continue the refactor."
git: main @ abc1234
---

## State
Half done.
"""

MALFORMED = "no frontmatter at all, just prose\n"


def project_key(path: Path) -> str:
    return str(path.resolve()).replace(os.sep, "-").replace("/", "-")


def make_state(base: Path, repo: Path, handoffs: dict[str, str]) -> Path:
    """Build a lightbridge state dir holding `handoffs` addressed to `repo`."""
    state = base / "state"
    directory = state / project_key(repo) / "handoffs"
    directory.mkdir(parents=True)
    for name, content in handoffs.items():
        (directory / name).write_text(content)
    return state


def run_hook(cwd: Path, state: Path) -> subprocess.CompletedProcess:
    # Execute the file directly — the same path as the agent's /bin/sh registration, so the
    # executable bit and the uv shebang are under test too.
    return subprocess.run(
        [str(HOOK)],
        input=json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True,
        env={**os.environ, "LIGHTBRIDGE_STATE_DIR": str(state)},
    )


def run_script(state: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "LIGHTBRIDGE_STATE_DIR": str(state)},
    )


class HandoffHookTest(unittest.TestCase):
    def assert_silent(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def context_of(self, result: subprocess.CompletedProcess) -> str:
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_cross_repo_handoff_is_announced(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            repo = base / "dest"
            repo.mkdir()
            state = make_state(base, repo, {"2026-07-11_1739_x.md": CROSS_REPO})

            ctx = self.context_of(run_hook(repo, state))
            self.assertIn("orthanc-test-pacs", ctx)
            self.assertIn("BREAKING", ctx)
            self.assertIn("main @ 72745e1", ctx)  # the ORIGIN's sha, not the destination's
            self.assertIn("Impact here", ctx)

    def test_same_repo_handoff_is_never_announced(self):
        """It is pulled on demand. Injecting it would fight the harness and resurrect stale plans."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            repo = base / "dest"
            repo.mkdir()
            state = make_state(base, repo, {"2026-07-10_0900_x.md": SAME_REPO})

            self.assert_silent(run_hook(repo, state))

    def test_mixed_inbox_announces_only_the_cross_repo_one(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            repo = base / "dest"
            repo.mkdir()
            state = make_state(
                base,
                repo,
                {"2026-07-10_0900_same.md": SAME_REPO, "2026-07-11_1739_cross.md": CROSS_REPO},
            )

            ctx = self.context_of(run_hook(repo, state))
            self.assertIn("2026-07-11_1739_cross.md", ctx)
            self.assertNotIn("2026-07-10_0900_same.md", ctx)
            self.assertIn(": 1", ctx)  # exactly one, not two

    def test_ack_silences_it_durably(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            repo = base / "dest"
            repo.mkdir()
            state = make_state(base, repo, {"2026-07-11_1739_x.md": CROSS_REPO})

            self.assertIn("BREAKING", self.context_of(run_hook(repo, state)))

            acked = run_script(state, "--cwd", str(repo), "--ack", "2026-07-11_1739_x.md")
            self.assertEqual(acked.returncode, 0, acked.stderr)

            # ...and it stays quiet on every later session, not just this one.
            self.assert_silent(run_hook(repo, state))
            self.assert_silent(run_hook(repo, state))

    def test_breaking_is_ordered_first(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            repo = base / "dest"
            repo.mkdir()
            state = make_state(
                base,
                repo,
                {
                    "2026-07-09_0900_safe.md": CROSS_REPO_SAFE,  # older, non-breaking
                    "2026-07-11_1739_bad.md": CROSS_REPO,  # newer, breaking
                },
            )

            ctx = self.context_of(run_hook(repo, state))
            self.assertLess(
                ctx.index("2026-07-11_1739_bad.md"),
                ctx.index("2026-07-09_0900_safe.md"),
                "the breaking handoff must be surfaced before the harmless one",
            )

    def test_fails_open(self):
        """No state, no inbox, an unparseable file — never crash a session, never cry wolf."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            repo = base / "dest"
            repo.mkdir()

            # no state dir at all
            self.assert_silent(run_hook(repo, base / "nonexistent"))

            # inbox exists but holds only junk
            state = make_state(base, repo, {"garbage.md": MALFORMED})
            self.assert_silent(run_hook(repo, state))

    def test_addressed_to_a_different_repo_is_not_announced(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            mine, theirs = base / "mine", base / "theirs"
            mine.mkdir()
            theirs.mkdir()
            state = make_state(base, theirs, {"2026-07-11_1739_x.md": CROSS_REPO})

            self.assert_silent(run_hook(mine, state))


if __name__ == "__main__":
    unittest.main(verbosity=2)
