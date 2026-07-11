#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for the handoff split: a pulled journal, and a pushed inbox.

Each test builds a throwaway lightbridge state dir (pointed at by $LIGHTBRIDGE_STATE_DIR) and
drives the real hook.py as a subprocess with a SessionStart payload on stdin — executing the
FILE directly, exactly as Claude Code's /bin/sh registration does, so a missing executable bit
or a broken shebang fails here too.

The load-bearing behaviours:

  * the inbox is ANNOUNCED — nobody asked for it, so nothing else would surface it;
  * the journal is NEVER announced — it is pulled on demand, and injecting it every session
    would fight the harness's own context management and could resurrect a stale plan;
  * `--journal` never returns an inbox item — the bug the split exists to kill, where "resume"
    handed the user an unrelated cross-repo notification instead of their own work;
  * delivery is not origin — a same-repo item in the inbox (a scheduled/background session
    leaving a note) is announced too, and `breaking` works without any `from:` block;
  * an acknowledged item goes quiet, durably.

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

# Pushed by a sibling repo. Origin recorded in `from:`; impact in top-level `breaking`.
CROSS_REPO = """\
---
project: /work/dest
created: 2026-07-11T17:39
harness: claude-code
focus: "The dataset landed; it exposes a routing gap in you."
git: main @ d04d639
breaking: true
from:
  repo: orthanc-test-pacs
  project: /work/origin
  git: main @ 72745e1
---

## Impact here
You will route laterals.
"""

CROSS_REPO_SAFE = CROSS_REPO.replace("breaking: true", "breaking: false").replace(
    "The dataset landed; it exposes a routing gap in you.", "FYI only."
)

# Pushed from WITHIN this repo — a scheduled/background run leaving a note for the next human.
# No `from:` block (same origin), but unsolicited all the same. This is the case that proves
# delivery and origin are different axes.
SAME_REPO_PUSHED = """\
---
project: /work/dest
created: 2026-07-11T03:00
harness: claude-code
focus: "Nightly run left the tree needing a migration."
git: main @ abc1234
breaking: true
---

## Impact here
Run the migration before touching the schema.
"""

# An ordinary journal entry: the user's own resumable work.
JOURNAL = """\
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


def make_state(
    base: Path, repo: Path, journal: dict[str, str] | None = None, inbox: dict[str, str] | None = None
) -> Path:
    """Build a lightbridge state dir with a journal and/or an inbox for `repo`."""
    state = base / "state"
    root = state / project_key(repo) / "handoffs"
    root.mkdir(parents=True)
    for name, content in (journal or {}).items():
        (root / name).write_text(content)
    if inbox is not None:
        (root / "inbox").mkdir()
        for name, content in inbox.items():
            (root / "inbox" / name).write_text(content)
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


class HandoffTest(unittest.TestCase):
    def assert_silent(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def context_of(self, result: subprocess.CompletedProcess) -> str:
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def repo_and_base(self, d: str) -> tuple[Path, Path]:
        base = Path(d)
        repo = base / "dest"
        repo.mkdir()
        return base, repo

    # ── the inbox is announced ────────────────────────────────────────────────────────

    def test_inbox_is_announced(self):
        with tempfile.TemporaryDirectory() as d:
            base, repo = self.repo_and_base(d)
            state = make_state(base, repo, inbox={"2026-07-11_1739_x.md": CROSS_REPO})

            ctx = self.context_of(run_hook(repo, state))
            self.assertIn("orthanc-test-pacs", ctx)
            self.assertIn("BREAKING", ctx)
            self.assertIn("main @ 72745e1", ctx)  # the ORIGIN's sha, not the destination's

    def test_journal_is_never_announced(self):
        """Pulled on demand. Injecting it would fight the harness and resurrect stale plans."""
        with tempfile.TemporaryDirectory() as d:
            base, repo = self.repo_and_base(d)
            state = make_state(base, repo, journal={"2026-07-10_0900_x.md": JOURNAL})

            self.assert_silent(run_hook(repo, state))

    # ── delivery is not origin ────────────────────────────────────────────────────────

    def test_same_repo_push_is_announced_too(self):
        """A scheduled/background run leaving a note is unsolicited — no `from:` block needed."""
        with tempfile.TemporaryDirectory() as d:
            base, repo = self.repo_and_base(d)
            state = make_state(base, repo, inbox={"2026-07-11_0300_nightly.md": SAME_REPO_PUSHED})

            ctx = self.context_of(run_hook(repo, state))
            self.assertIn("BREAKING", ctx)  # breaking works with no `from:` at all
            self.assertIn("this repo", ctx)  # and it says where it came from
            self.assertIn("migration", ctx)

    # ── the bug the split exists to kill ──────────────────────────────────────────────

    def test_journal_lookup_never_returns_an_inbox_item(self):
        """
        Pre-split, `resume` took the last file in a flat dir — so a newer cross-repo
        notification shadowed the user's own work. Now it is structurally impossible.
        """
        with tempfile.TemporaryDirectory() as d:
            base, repo = self.repo_and_base(d)
            state = make_state(
                base,
                repo,
                journal={"2026-07-10_0900_mine.md": JOURNAL},
                # newer than the journal entry — under the old flat layout this would win
                inbox={"2026-07-11_1739_theirs.md": CROSS_REPO},
            )

            result = run_script(state, "--cwd", str(repo), "--journal")
            self.assertEqual(result.returncode, 0, result.stderr)
            picked = result.stdout.strip()

            self.assertTrue(picked.endswith("2026-07-10_0900_mine.md"), picked)
            self.assertNotIn("inbox", picked)

    # ── acknowledgement ───────────────────────────────────────────────────────────────

    def test_ack_silences_it_durably(self):
        with tempfile.TemporaryDirectory() as d:
            base, repo = self.repo_and_base(d)
            state = make_state(base, repo, inbox={"2026-07-11_1739_x.md": CROSS_REPO})

            self.assertIn("BREAKING", self.context_of(run_hook(repo, state)))

            acked = run_script(state, "--cwd", str(repo), "--ack", "2026-07-11_1739_x.md")
            self.assertEqual(acked.returncode, 0, acked.stderr)

            # ...and it stays quiet on every later session, not just this one.
            self.assert_silent(run_hook(repo, state))
            self.assert_silent(run_hook(repo, state))

    def test_breaking_is_ordered_first(self):
        with tempfile.TemporaryDirectory() as d:
            base, repo = self.repo_and_base(d)
            state = make_state(
                base,
                repo,
                inbox={
                    "2026-07-09_0900_safe.md": CROSS_REPO_SAFE,  # older, non-breaking
                    "2026-07-11_1739_bad.md": CROSS_REPO,  # newer, breaking
                },
            )

            ctx = self.context_of(run_hook(repo, state))
            self.assertLess(
                ctx.index("2026-07-11_1739_bad.md"),
                ctx.index("2026-07-09_0900_safe.md"),
                "the breaking item must be surfaced before the harmless one",
            )

    # ── fail open ─────────────────────────────────────────────────────────────────────

    def test_fails_open(self):
        """No state, no inbox, an unparseable file — never crash a session, never cry wolf."""
        with tempfile.TemporaryDirectory() as d:
            base, repo = self.repo_and_base(d)

            self.assert_silent(run_hook(repo, base / "nonexistent"))  # no state dir

            state = make_state(base, repo, journal={"j.md": JOURNAL})  # journal, no inbox dir
            self.assert_silent(run_hook(repo, state))

    def test_addressed_to_a_different_repo_is_not_announced(self):
        with tempfile.TemporaryDirectory() as d:
            base, mine = self.repo_and_base(d)
            theirs = base / "theirs"
            theirs.mkdir()
            state = make_state(base, theirs, inbox={"2026-07-11_1739_x.md": CROSS_REPO})

            self.assert_silent(run_hook(mine, state))


if __name__ == "__main__":
    unittest.main(verbosity=2)
