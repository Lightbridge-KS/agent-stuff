#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for `lb fleet` (ADR 0004): the inventory + receipt readers in
`lb_resolve`, the node program and hub-side mechanics in `lb_fleet.py`, and the
`fleet init|status|sync` verbs.

No network. The node program is executed locally against a "world" of real git repos
(a bare origin, a hub clone, a node clone). The CLI runs as a subprocess with an `ssh`
shim on PATH that logs its argv and execs the local interpreter on stdin — so the whole
transport path is exercised except the wire. `LB_TEST_SSH_EXIT=255` makes the shim
play an offline node.

    uv run tests/test_lb_fleet.py
"""

from __future__ import annotations

import ast
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIGHTBRIDGE_DIR = REPO_ROOT / "scripts" / "lightbridge"
SCRIPT = LIGHTBRIDGE_DIR / "lightbridge.py"

sys.path.insert(0, str(LIGHTBRIDGE_DIR))

import lb_fleet  # noqa: E402
import lb_resolve  # noqa: E402

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_TERMINAL_PROMPT": "0",
}


def script_argv(script: Path, *args: str) -> list[str]:
    if os.name != "nt":
        return [str(script), *args]
    return ["uv", "run", str(script), *args]


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=GIT_ENV
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {repo}:\n{proc.stdout}{proc.stderr}")
    return proc.stdout.strip()


def commit(repo: Path, name: str, message: str = "change") -> str:
    (repo / name).write_text(f"{name}\n", encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


class World:
    """One repo mirrored three ways: bare origin, hub clone, node clone — all on `main`."""

    def __init__(self, base: Path, name: str = "alpha") -> None:
        self.name = name
        self.origin = base / "origin" / f"{name}.git"
        self.hub_root = base / "hub"
        self.node_root = base / "node"
        self.hub = self.hub_root / name
        self.node = self.node_root / name
        self.origin.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "-q", "--bare", "--initial-branch=main", str(self.origin)],
            check=True, capture_output=True, env=GIT_ENV,
        )
        seed = base / "seed" / name
        seed.mkdir(parents=True)
        git(seed, "init", "-q", "--initial-branch=main")
        commit(seed, "README.md", "init")
        git(seed, "remote", "add", "origin", str(self.origin))
        git(seed, "push", "-q", "-u", "origin", "main")
        for clone in (self.hub, self.node):
            clone.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "-q", str(self.origin), str(clone)],
                check=True, capture_output=True, env=GIT_ENV,
            )
        self.work = seed  # a fourth clone used to push "upstream" changes

    def advance_origin(self, n: int = 1) -> str:
        for i in range(n):
            sha = commit(self.work, f"f{i}-{os.urandom(2).hex()}.txt", f"upstream {i}")
        git(self.work, "push", "-q", "origin", "main")
        git(self.hub, "fetch", "-q", "origin")
        return sha

    def spec(self, apply: str = "touch applied", verify: str | None = None, requires=()) -> dict:
        return {"name": self.name, "apply": apply, "verify": verify, "requires": list(requires)}


def run_node_locally(script: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-"], input=script, capture_output=True, text=True, env=GIT_ENV
    )
    report = lb_fleet.parse_report(proc.stdout)
    if report is None:
        raise AssertionError(f"no report (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return report


# ── readers (lb_resolve) ────────────────────────────────────────────────────


GOOD_FLEET = """\
[hub]
root = "~/my_config"
[repos.alpha]
apply = "make install"
verify = "make check"
requires = [".device"]
[repos.beta]
apply = "uv run bin/install.py --all"
[nodes.box]
ssh = "box"
repos = ["alpha", "beta"]
[nodes.other]
ssh = "other"
root = "/srv/cfg"
repos = ["beta"]
"""


class LoadFleetTest(unittest.TestCase):
    def load(self, text: str):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "fleet.toml"
            path.write_text(text, encoding="utf-8")
            return lb_resolve.load_fleet(path)

    def test_absent_is_not_a_hub(self):
        self.assertEqual(lb_resolve.load_fleet(Path("/nonexistent/fleet.toml")), (None, None))

    def test_bad_toml_is_unusable(self):
        fleet, error = self.load("[hub\n")
        self.assertIsNone(fleet)
        self.assertIn("unreadable", error)

    def test_missing_hub_root(self):
        fleet, error = self.load('[repos.a]\napply = "x"\n')
        self.assertIsNone(fleet)
        self.assertIn("[hub] root", error)

    def test_repo_without_apply(self):
        fleet, error = self.load('[hub]\nroot = "~/c"\n[repos.a]\nverify = "x"\n')
        self.assertIn("[repos.a] is missing `apply`", error)

    def test_node_naming_undeclared_repo(self):
        text = '[hub]\nroot = "~/c"\n[repos.a]\napply = "x"\n[nodes.n]\nssh = "n"\nrepos = ["a", "zeta"]\n'
        fleet, error = self.load(text)
        self.assertIsNone(fleet)
        self.assertIn("zeta", error)

    def test_node_without_ssh(self):
        fleet, error = self.load('[hub]\nroot = "~/c"\n[nodes.n]\nrepos = []\n')
        self.assertIn("[nodes.n] is missing `ssh`", error)

    def test_good_inventory_is_normalized(self):
        fleet, error = self.load(GOOD_FLEET)
        self.assertIsNone(error)
        self.assertEqual(fleet["hub"], {"root": "~/my_config"})
        self.assertEqual(fleet["repos"]["alpha"], {"apply": "make install", "verify": "make check", "requires": [".device"]})
        self.assertEqual(fleet["repos"]["beta"], {"apply": "uv run bin/install.py --all", "verify": None, "requires": []})
        self.assertEqual(fleet["nodes"]["box"], {"ssh": "box", "root": "~/my_config", "repos": ["alpha", "beta"]})
        self.assertEqual(fleet["nodes"]["other"]["root"], "/srv/cfg")  # node override survives

    def test_receipts_dir_is_the_sibling_folder(self):
        self.assertEqual(
            lb_resolve.fleet_receipts_dir(Path("/x/.lightbridge/fleet.toml")),
            Path("/x/.lightbridge/fleet"),
        )


class LoadReceiptTest(unittest.TestCase):
    def test_states(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "box.json"
            self.assertEqual(lb_resolve.load_receipt(path), (None, None))
            path.write_text("{not json", encoding="utf-8")
            data, error = lb_resolve.load_receipt(path)
            self.assertIsNone(data)
            self.assertIn("unreadable", error)
            path.write_text('{"node": "box"}', encoding="utf-8")
            self.assertIn("malformed", lb_resolve.load_receipt(path)[1])
            fleet_path = Path(d) / "fleet.toml"
            written = lb_fleet.write_receipt(fleet_path, "box", {"node": "box", "repos": {"a": {"after": "abc"}}})
            self.assertEqual(written, Path(d) / "fleet" / "box.json")
            data, error = lb_resolve.load_receipt(written)
            self.assertIsNone(error)
            self.assertEqual(data["repos"]["a"]["after"], "abc")
            # atomic: no temp file left behind
            self.assertEqual(sorted(p.name for p in written.parent.iterdir()), ["box.json"])


# ── rendering + report parsing ──────────────────────────────────────────────


class RenderTest(unittest.TestCase):
    def test_config_round_trips_through_the_literal(self):
        script = lb_fleet.render_node_script("sync", "~/cfg", [{"name": "a", "apply": "x", "verify": None, "requires": []}], reinstall=True)
        self.assertNotIn("__CONFIG_JSON__", script)
        self.assertNotIn("__REPORT_MARK__", script)
        # The embedded literal must be valid Python that evaluates to the JSON text.
        line = next(l for l in script.splitlines() if l.startswith("CONFIG = json.loads("))
        literal = line[len("CONFIG = json.loads("):-1]
        config = json.loads(ast.literal_eval(literal))  # a plain str literal, no code
        self.assertEqual(config["mode"], "sync")
        self.assertTrue(config["reinstall"])
        self.assertEqual(config["repos"][0]["name"], "a")

    def test_parse_report_skips_shell_noise_and_rejects_garbage(self):
        good = json.dumps({"host": "h", "repos": {}})
        stdout = f"motd banner\n{lb_fleet.REPORT_MARK} {good}\n"
        self.assertEqual(lb_fleet.parse_report(stdout)["host"], "h")
        self.assertIsNone(lb_fleet.parse_report("nothing here\n"))
        self.assertIsNone(lb_fleet.parse_report(f"{lb_fleet.REPORT_MARK} {{broken\n"))
        self.assertIsNone(lb_fleet.parse_report(f"{lb_fleet.REPORT_MARK} [1,2]\n"))

    def test_ssh_argv_is_batch_and_bounded(self):
        argv = lb_fleet.ssh_argv("box")
        self.assertEqual(argv[0], "ssh")
        self.assertIn("BatchMode=yes", argv)
        self.assertTrue(any(a.startswith("ConnectTimeout=") for a in argv))
        self.assertEqual(argv[-3:], ["box", "python3", "-"])


# ── the node program, run locally against real repos ────────────────────────


class NodeScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.w = World(self.base)

    def run_mode(self, mode: str, spec: dict | None = None, **kw) -> dict:
        spec = spec or self.w.spec()
        script = lb_fleet.render_node_script(mode, str(self.w.node_root), [spec], **kw)
        return run_node_locally(script)

    def entry(self, report: dict) -> dict:
        return report["repos"][self.w.name]

    def test_status_observes_without_touching(self):
        self.w.advance_origin(2)
        (self.w.node / "scratch.txt").write_text("x")
        head_before = git(self.w.node, "rev-parse", "HEAD")
        e = self.entry(self.run_mode("status", self.w.spec(requires=[".device"])))
        self.assertEqual(e["status"], "observed")
        self.assertEqual(e["branch"], "main")
        self.assertEqual(e["before"], head_before)
        self.assertEqual(len(e["dirty"]), 1)
        self.assertEqual(e["missing_requires"], [".device"])
        self.assertEqual(git(self.w.node, "rev-parse", "HEAD"), head_before)  # untouched
        self.assertFalse((self.w.node / "applied").exists())

    def test_sync_behind_pulls_ff_only_then_applies_and_verifies(self):
        target = self.w.advance_origin(3)
        spec = self.w.spec(apply="touch applied", verify="test -f applied && echo verified")
        report = self.run_mode("sync", spec)
        e = self.entry(report)
        self.assertEqual(e["status"], "applied", e)
        self.assertEqual(e["behind"], 3)
        self.assertEqual(e["after"], target)
        self.assertEqual(e["apply"]["exit"], 0)
        self.assertIn("verified", e["verify"]["tail"])
        self.assertTrue((self.w.node / "applied").exists())
        self.assertEqual(git(self.w.node, "rev-parse", "HEAD"), target)

    def test_sync_in_sync_does_nothing_unless_reinstall(self):
        e = self.entry(self.run_mode("sync"))
        self.assertEqual(e["status"], "in-sync")
        self.assertIsNone(e["apply"])
        self.assertFalse((self.w.node / "applied").exists())
        e = self.entry(self.run_mode("sync", reinstall=True))
        self.assertEqual(e["status"], "applied")
        self.assertEqual(e["before"], e["after"])
        self.assertTrue((self.w.node / "applied").exists())

    def test_dirty_is_refused_and_never_stashed(self):
        self.w.advance_origin()
        (self.w.node / "README.md").write_text("local edit\n")
        e = self.entry(self.run_mode("sync"))
        self.assertEqual((e["status"], e["reason"]), ("refused", "dirty"))
        self.assertEqual(len(e["dirty"]), 1)
        self.assertEqual((self.w.node / "README.md").read_text(), "local edit\n")
        self.assertIsNone(e["apply"])
        self.assertEqual(e["before"], e["after"])  # no pull happened

    def test_ahead_is_refused(self):
        commit(self.w.node, "local.txt", "node-only commit")
        self.w.advance_origin()
        e = self.entry(self.run_mode("sync"))
        self.assertEqual((e["status"], e["reason"]), ("refused", "ahead"))
        self.assertEqual(e["ahead"], 1)
        self.assertEqual(e["behind"], 1)

    def test_not_on_main_is_refused(self):
        git(self.w.node, "switch", "-q", "-c", "feat/x")
        e = self.entry(self.run_mode("sync"))
        self.assertEqual((e["status"], e["reason"]), ("refused", "not-on-main"))
        self.assertEqual(e["branch"], "feat/x")

    def test_missing_required_file_is_refused_before_pulling(self):
        target = self.w.advance_origin()
        e = self.entry(self.run_mode("sync", self.w.spec(requires=[".device"])))
        self.assertEqual((e["status"], e["reason"]), ("refused", "missing-requires"))
        self.assertNotEqual(git(self.w.node, "rev-parse", "HEAD"), target)

    def test_not_cloned_is_refused(self):
        script = lb_fleet.render_node_script("sync", str(self.w.node_root), [{"name": "ghost", "apply": "true", "verify": None, "requires": []}])
        e = run_node_locally(script)["repos"]["ghost"]
        self.assertEqual((e["status"], e["reason"]), ("refused", "not-cloned"))

    def test_apply_failure_is_failed_with_tail(self):
        self.w.advance_origin()
        e = self.entry(self.run_mode("sync", self.w.spec(apply="echo boom >&2; exit 3", verify="touch verified")))
        self.assertEqual((e["status"], e["reason"]), ("failed", "apply"))
        self.assertEqual(e["apply"]["exit"], 3)
        self.assertIn("boom", e["apply"]["tail"])
        self.assertIsNone(e["verify"])  # verify never runs after a failed apply
        self.assertFalse((self.w.node / "verified").exists())

    def test_verify_failure_is_failed(self):
        self.w.advance_origin()
        e = self.entry(self.run_mode("sync", self.w.spec(verify="exit 2")))
        self.assertEqual((e["status"], e["reason"]), ("failed", "verify"))
        self.assertEqual(e["verify"]["exit"], 2)

    def test_apply_timeout_kills_the_process_group(self):
        self.w.advance_origin()
        e = self.entry(self.run_mode("sync", self.w.spec(apply="sleep 30"), timeout=1))
        self.assertEqual((e["status"], e["reason"]), ("failed", "apply"))
        self.assertEqual(e["apply"]["exit"], 124)
        self.assertIn("timeout", e["apply"]["tail"])

    def test_apply_order_follows_the_inventory(self):
        second = World(self.base / "two", name="beta")
        # Both worlds share the node root by symlinking beta's clone beside alpha's.
        os.symlink(second.node, self.w.node_root / "beta")
        self.w.advance_origin()
        second.advance_origin()
        log = self.base / "order.log"
        specs = [
            {"name": "alpha", "apply": f"echo alpha >> {log}", "verify": None, "requires": []},
            {"name": "beta", "apply": f"echo beta >> {log}", "verify": None, "requires": []},
        ]
        report = run_node_locally(lb_fleet.render_node_script("sync", str(self.w.node_root), specs))
        self.assertEqual({e["status"] for e in report["repos"].values()}, {"applied"})
        self.assertEqual(log.read_text().split(), ["alpha", "beta"])

    def test_broken_symlink_check(self):
        registry = self.base / "skills"
        registry.mkdir()
        os.symlink(self.base / "gone", registry / "dangling")
        os.symlink(self.w.node, registry / "fine")
        report = self.run_mode("status", registries=(str(registry), str(self.base / "absent")))
        self.assertEqual(report["checks"]["broken_symlinks"], [str(registry / "dangling")])


# ── hub-side distance ───────────────────────────────────────────────────────


class DistanceTest(unittest.TestCase):
    def test_behind_ahead_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            w = World(Path(d))
            node_head = git(w.node, "rev-parse", "HEAD")
            self.assertEqual(lb_fleet.distance(w.hub, node_head)["behind"], 0)
            w.advance_origin(2)
            self.assertIsNone(lb_fleet.hub_fetch(w.hub))
            dist = lb_fleet.distance(w.hub, node_head)
            self.assertEqual((dist["behind"], dist["ahead"]), (2, False))
            self.assertEqual(dist["origin_main"], git(w.hub, "rev-parse", "origin/main"))
            local_only = commit(w.node, "x.txt")
            dist = lb_fleet.distance(w.hub, local_only)
            self.assertTrue(dist["ahead"])  # unknown to the hub ⇒ ahead
            self.assertIsNone(dist["behind"])
            self.assertIn("missing", lb_fleet.distance(Path(d) / "nope", node_head)["error"])
            self.assertIn("missing", lb_fleet.hub_fetch(Path(d) / "nope"))


# ── the CLI, through an ssh shim ────────────────────────────────────────────


SHIM = """#!/bin/sh
# ssh stand-in: record argv, optionally play offline, else run the streamed program here.
printf '%s\\n' "$*" >> "$LB_TEST_SSH_LOG"
if [ -n "$LB_TEST_SSH_EXIT" ]; then exit "$LB_TEST_SSH_EXIT"; fi
exec "$LB_TEST_PYTHON" -
"""


@unittest.skipIf(os.name == "nt", "POSIX shim")
class FleetCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.w = World(self.base)
        shim_dir = self.base / "bin"
        shim_dir.mkdir()
        shim = shim_dir / "ssh"
        shim.write_text(SHIM, encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
        self.log = self.base / "ssh.log"
        self.env = {
            **GIT_ENV,
            "PATH": f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "LB_TEST_SSH_LOG": str(self.log),
            "LB_TEST_PYTHON": sys.executable,
        }
        self.fleet = self.base / "lb" / "fleet.toml"
        self.fleet.parent.mkdir()
        # A real apply writes outside the tracked tree (gitignored dist/, ~/.claude); the
        # marker lives outside the clone too, or the next status would see it as dirty.
        self.marker = self.base / "applied"
        self.fleet.write_text(
            f'[hub]\nroot = {lb_resolve.toml_str(str(self.w.hub_root))}\n'
            f'[repos.alpha]\napply = {lb_resolve.toml_str(f"touch {self.marker}")}\n'
            f'verify = {lb_resolve.toml_str(f"test -f {self.marker}")}\n'
            f'[nodes.box]\nssh = "box-alias"\nroot = {lb_resolve.toml_str(str(self.w.node_root))}\nrepos = ["alpha"]\n',
            encoding="utf-8",
        )

    def lb(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            script_argv(SCRIPT, *args, "--fleet", str(self.fleet)),
            capture_output=True, text=True, encoding="utf-8", env={**self.env, **env},
        )

    def test_init_seeds_once_and_never_clobbers(self):
        fresh = self.base / "new" / "fleet.toml"
        result = subprocess.run(
            script_argv(SCRIPT, "fleet", "init", "--json", "--fleet", str(fresh)),
            capture_output=True, text=True, encoding="utf-8", env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["created"])
        self.assertEqual(data["nodes"], ["beelink-ubuntu"])
        fleet, error = lb_resolve.load_fleet(fresh)
        self.assertIsNone(error)
        self.assertEqual(fleet["nodes"]["beelink-ubuntu"]["repos"], ["agent-instruction", "agent-stuff", "agent-stuff-private"])
        again = subprocess.run(
            script_argv(SCRIPT, "fleet", "init", "--fleet", str(fresh)),
            capture_output=True, text=True, encoding="utf-8", env=self.env,
        )
        self.assertEqual(again.returncode, 1)
        self.assertIn("never clobbers", again.stderr)

    def test_missing_inventory_teaches_init(self):
        result = subprocess.run(
            script_argv(SCRIPT, "fleet", "status", "--fleet", str(self.base / "none.toml")),
            capture_output=True, text=True, encoding="utf-8", env=self.env,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("fleet init", result.stderr)

    def test_status_then_sync_then_status(self):
        self.w.advance_origin(2)
        status = self.lb("fleet", "status", "--json")
        self.assertEqual(status.returncode, 1, status.stderr)  # lagging ⇒ 1
        data = json.loads(status.stdout)["nodes"]["box"]
        self.assertTrue(data["online"])
        repo = data["repos"]["alpha"]
        self.assertEqual((repo["state"], repo["behind"], repo["ahead"]), ("behind", 2, False))
        self.assertIsNone(repo["last_synced"])
        self.assertIn("box-alias python3 -", self.log.read_text())
        self.assertIn("-o BatchMode=yes", self.log.read_text())

        sync = self.lb("fleet", "sync", "box")
        self.assertEqual(sync.returncode, 0, sync.stderr + sync.stdout)
        self.assertIn("applied", sync.stdout)
        receipt_file = self.fleet.parent / "fleet" / "box.json"
        self.assertTrue(receipt_file.is_file())
        receipt = json.loads(receipt_file.read_text())
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["repos"]["alpha"]["after"], git(self.w.hub, "rev-parse", "origin/main"))
        self.assertTrue(self.marker.exists())

        status = self.lb("fleet", "status", "--json")
        self.assertEqual(status.returncode, 0, status.stderr)
        repo = json.loads(status.stdout)["nodes"]["box"]["repos"]["alpha"]
        self.assertEqual(repo["state"], "in-sync")
        self.assertEqual(repo["last_synced"], receipt["repos"]["alpha"]["after"])

        again = self.lb("fleet", "sync", "box")
        self.assertEqual(again.returncode, 0)
        self.assertIn("in-sync", again.stdout)

    def test_human_status_lines(self):
        self.w.advance_origin()
        (self.w.node / "README.md").write_text("edit\n")
        result = self.lb("fleet", "status")
        self.assertEqual(result.returncode, 1)
        lines = result.stdout.splitlines()
        self.assertTrue(any(l.startswith("node") and "online" in l and "last sync never" in l for l in lines), lines)
        repo_line = next(l for l in lines if l.startswith("repo"))
        self.assertIn("behind 1", repo_line)
        self.assertIn("DIRTY 1", repo_line)
        self.assertTrue(any(l.startswith("next") for l in lines))

    def test_sync_refuses_dirty_and_exits_1(self):
        self.w.advance_origin()
        (self.w.node / "README.md").write_text("edit\n")
        result = self.lb("fleet", "sync", "box")
        self.assertEqual(result.returncode, 1)
        self.assertIn("REFUSED", result.stdout)
        self.assertIn("dirty: 1 file(s)", result.stdout)
        receipt = json.loads((self.fleet.parent / "fleet" / "box.json").read_text())
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["repos"]["alpha"]["reason"], "dirty")

    def test_dry_run_contacts_nothing(self):
        result = self.lb("fleet", "sync", "box", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing sent", result.stdout)
        self.assertIn("touch ", result.stdout)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.fleet.parent / "fleet").exists())

    def test_offline_node_exits_1_without_a_receipt(self):
        result = self.lb("fleet", "sync", "box", LB_TEST_SSH_EXIT="255")
        self.assertEqual(result.returncode, 1)
        self.assertIn("offline", result.stderr)
        self.assertFalse((self.fleet.parent / "fleet" / "box.json").exists())
        status = self.lb("fleet", "status", "--json", LB_TEST_SSH_EXIT="255")
        self.assertEqual(status.returncode, 1)
        self.assertFalse(json.loads(status.stdout)["nodes"]["box"]["online"])

    def test_unknown_node_and_unknown_repo(self):
        self.assertEqual(self.lb("fleet", "sync", "ghost").returncode, 1)
        self.assertIn("Known: box", self.lb("fleet", "status", "ghost").stderr)
        result = self.lb("fleet", "sync", "box", "--repo", "zeta")
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not carry", result.stderr)

    def test_dashboard_fleet_row(self):
        result = subprocess.run(
            script_argv(
                SCRIPT, "status", "--json",
                "--registry", str(self.base / "no-registry.toml"),
                "--graph", str(self.base / "no-graph.toml"),
                "--keys", str(self.base / "no-keys.toml"),
                "--fleet", str(self.fleet),
            ),
            capture_output=True, text=True, encoding="utf-8",
            env={**self.env, "LIGHTBRIDGE_STATE_DIR": str(self.base / "state")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["fleet"], {"present": True, "error": None, "nodes": 1, "receipts": 0})
        human = subprocess.run(
            script_argv(
                SCRIPT, "status",
                "--registry", str(self.base / "no-registry.toml"),
                "--graph", str(self.base / "no-graph.toml"),
                "--keys", str(self.base / "no-keys.toml"),
                "--fleet", str(self.base / "absent.toml"),
            ),
            capture_output=True, text=True, encoding="utf-8",
            env={**self.env, "LIGHTBRIDGE_STATE_DIR": str(self.base / "state")},
        )
        line = next(l for l in human.stdout.splitlines() if l.startswith("fleet"))
        self.assertIn("not a hub", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
