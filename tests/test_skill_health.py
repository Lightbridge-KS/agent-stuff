#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for scripts/skill-health.

The load-bearing claims, each pinned by a test:

  - green is exit 0 and red is exit 1, and a red run names the offending checks in both
    the human summary and the alert metadata;
  - an absent sibling tree is SKIPPED (a clone elsewhere has no private castle), but a
    checker missing from PATH is RED — it was meant to run and did not, so the surface
    it covers is unverified and silence would be a lie;
  - the notifier fires on red only, receives the alert JSON on stdin, and cannot change
    the health verdict by failing;
  - the report file is written on every run, green or red;
  - detail output is trimmed, so a notifier push and an agent's context stay bounded.

    uv run tests/test_skill_health.py
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "scripts" / "skill-health" / "skill_health.py"

_spec = importlib.util.spec_from_file_location("skill_health", TOOL)
sh = importlib.util.module_from_spec(_spec)
sys.modules["skill_health"] = sh  # dataclasses resolve annotations via sys.modules
_spec.loader.exec_module(sh)


def check(name: str, *argv: str, **kw) -> "sh.Check":
    return sh.Check(name=name, what="test check", argv=tuple(argv), **kw)


PASS = ("sh", "-c", "echo fine; exit 0")
FAIL = ("sh", "-c", "echo boom; exit 1")


class RunCheck(unittest.TestCase):
    def test_pass_is_ok_and_drops_detail(self):
        r = sh.run_check(check("a", *PASS))
        self.assertEqual(r.status, sh.STATUS_OK)
        self.assertEqual(r.exit_code, 0)
        # A green check's chatter is noise a notifier would have to carry.
        self.assertEqual(r.detail, "")

    def test_fail_is_red_and_keeps_detail(self):
        r = sh.run_check(check("a", *FAIL))
        self.assertEqual(r.status, sh.STATUS_RED)
        self.assertEqual(r.exit_code, 1)
        self.assertIn("boom", r.detail)

    def test_absent_required_tree_is_skipped_not_red(self):
        r = sh.run_check(check("a", *PASS, requires=Path("/nope/does/not/exist")))
        self.assertEqual(r.status, sh.STATUS_SKIPPED)
        self.assertFalse(r.is_red)

    def test_missing_command_is_red_not_skipped(self):
        r = sh.run_check(check("a", "definitely-not-a-real-binary-xyz"))
        self.assertEqual(r.status, sh.STATUS_RED)
        self.assertIn("not found on PATH", r.detail)

    def test_search_path_includes_user_install_dirs(self):
        # The launchd failure mode this defends against: minimal PATH, checkers vanish.
        saved = os.environ["PATH"]
        os.environ["PATH"] = "/usr/bin:/bin"
        try:
            parts = sh.search_path().split(os.pathsep)
        finally:
            os.environ["PATH"] = saved
        local = str(Path("~/.local/bin").expanduser())
        if Path(local).is_dir():
            self.assertIn(local, parts)


class Trim(unittest.TestCase):
    def test_caps_lines(self):
        out = sh.trim("\n".join(f"line{i}" for i in range(200)))
        self.assertLessEqual(len(out.splitlines()), sh.DETAIL_LINES + 1)
        self.assertIn("line199", out)  # keeps the tail, where failures print

    def test_caps_chars(self):
        self.assertLessEqual(len(sh.trim("x" * 99999)), sh.DETAIL_CHARS + 1)

    def test_drops_blank_lines_but_keeps_indentation(self):
        # Indentation carries meaning — `skill-vendor doctor` indents each finding
        # under its entry — so only trailing whitespace and blank lines go.
        self.assertEqual(sh.trim("\n\nfirst \n\n    indented  \n\n"), "first\n    indented")


class ReportShape(unittest.TestCase):
    def test_green_alert(self):
        rep = sh.collect([check("a", *PASS), check("b", *PASS)])
        alert = rep.as_alert()
        self.assertEqual(alert["severity"], "info")
        self.assertEqual(alert["type"], "skill_health")
        self.assertEqual(alert["metadata"]["checks_red"], "0")
        self.assertIn("all 2 checks green", alert["message"])

    def test_red_alert_names_offenders(self):
        rep = sh.collect([check("good", *PASS), check("bad", *FAIL)])
        alert = rep.as_alert()
        self.assertEqual(alert["severity"], "warning")
        self.assertEqual(alert["metadata"]["red"], "bad")
        self.assertEqual(alert["metadata"]["checks_red"], "1")
        self.assertIn("bad", alert["message"])

    def test_metadata_values_are_all_strings(self):
        # mac-cpu-watchdog's Alert.Metadata is map[string]string; a non-string here
        # would fail to unmarshal in a shared notifier.
        rep = sh.collect([check("bad", *FAIL)])
        for key, value in rep.as_alert(Path("/tmp/x.json"))["metadata"].items():
            self.assertIsInstance(value, str, key)

    def test_skipped_excluded_from_totals(self):
        rep = sh.collect(
            [check("a", *PASS), check("b", *PASS, requires=Path("/nope/nope"))]
        )
        self.assertEqual(rep.as_alert()["metadata"]["checks_total"], "1")
        self.assertEqual(len(rep.results), 2)  # still reported, just not counted


class BuildChecks(unittest.TestCase):
    def test_siblings_marked_optional_and_validate_path_derived(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "agent-stuff"
            (root / "bin").mkdir(parents=True)
            checks = sh.build_checks(root)
            names = [c.name for c in checks]
            self.assertEqual(
                names,
                ["skill-vendor", "lightbridge", "agent-stuff",
                 "agent-stuff-private", "skills-island"],
            )
            optional = [c for c in checks if c.requires is not None]
            self.assertEqual({c.name for c in optional},
                             {"agent-stuff-private", "skills-island"})
            self.assertIn(str(root / "bin" / "validate.py"), checks[2].argv)


class EndToEnd(unittest.TestCase):
    """cmd_run with synthetic checks — the real ones need the live machine."""

    def setUp(self):
        self._real = sh.build_checks
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "lb"

    def tearDown(self):
        sh.build_checks = self._real
        self.tmp.cleanup()

    def run_with(self, checks, **kw):
        sh.build_checks = lambda root=None: checks
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = sh.cmd_run(
                kw.get("as_json", False), kw.get("notify"), self.home, None
            )
        return code, out.getvalue(), err.getvalue()

    def notifier(self, dest: Path, exit_code: int = 0) -> str:
        script = Path(self.tmp.name) / f"notify{exit_code}.sh"
        script.write_text(f'#!/bin/sh\ncat > "{dest}"\nexit {exit_code}\n')
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return str(script)

    def test_green_exits_zero(self):
        code, out, _ = self.run_with([check("a", *PASS)])
        self.assertEqual(code, sh.OK)
        self.assertIn("all 1 checks green", out)

    def test_red_exits_one(self):
        code, out, _ = self.run_with([check("a", *PASS), check("b", *FAIL)])
        self.assertEqual(code, sh.RED)
        self.assertIn("RED", out)
        self.assertIn("b", out)

    def test_report_written_on_green_and_red(self):
        for checks in ([check("a", *PASS)], [check("a", *FAIL)]):
            self.run_with(checks)
            path = self.home.joinpath(*sh.REPORT_RELPATH)
            self.assertTrue(path.exists())
            json.loads(path.read_text())  # parses

    def test_json_mode_is_parseable(self):
        code, out, _ = self.run_with([check("a", *FAIL)], as_json=True)
        payload = json.loads(out)
        self.assertEqual(code, sh.RED)
        self.assertEqual(payload["checks"][0]["status"], "red")
        self.assertIn("report_path", payload["metadata"])

    def test_notifier_fires_on_red_with_json_on_stdin(self):
        dest = Path(self.tmp.name) / "payload.json"
        code, _, _ = self.run_with([check("a", *FAIL)], notify=self.notifier(dest))
        self.assertEqual(code, sh.RED)
        self.assertTrue(dest.exists(), "notifier did not run")
        payload = json.loads(dest.read_text())
        self.assertEqual(payload["severity"], "warning")
        self.assertEqual(payload["metadata"]["red"], "a")

    def test_notifier_inherits_repaired_search_path(self):
        # The notifier shells out further (openclaw, curl, …), so it needs the repaired
        # PATH too — resolving the notifier binary against it is not enough. Asserted
        # against search_path() rather than a named directory: which dirs exist is a
        # property of the machine, but inheriting whatever was repaired is the contract.
        dest = Path(self.tmp.name) / "path.txt"
        script = Path(self.tmp.name) / "capture-path.sh"
        script.write_text(f'#!/bin/sh\nprintf "%s" "$PATH" > "{dest}"\ncat >/dev/null\n')
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        self.run_with([check("a", *FAIL)], notify=str(script))
        self.assertEqual(dest.read_text(), sh.search_path())

    def test_notifier_silent_on_green(self):
        dest = Path(self.tmp.name) / "payload.json"
        code, _, _ = self.run_with([check("a", *PASS)], notify=self.notifier(dest))
        self.assertEqual(code, sh.OK)
        self.assertFalse(dest.exists(), "notifier ran on a green sweep")

    def test_notifier_failure_does_not_change_verdict(self):
        dest = Path(self.tmp.name) / "payload.json"
        code, _, err = self.run_with(
            [check("a", *FAIL)], notify=self.notifier(dest, exit_code=3)
        )
        self.assertEqual(code, sh.RED)  # the checks already answered
        self.assertIn("notify-command exited 3", err)

    def test_missing_notifier_reports_but_keeps_verdict(self):
        code, _, err = self.run_with([check("a", *FAIL)], notify="no-such-notifier-xyz")
        self.assertEqual(code, sh.RED)
        self.assertIn("notify-command", err)

    def test_unwritable_home_is_error_not_red(self):
        sh.build_checks = lambda root=None: [check("a", *PASS)]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = sh.cmd_run(False, None, Path("/dev/null/nope"), None)
        self.assertEqual(code, sh.ERROR)
        self.assertIn("could not write report", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
