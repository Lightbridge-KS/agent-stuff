#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""CLI package compatibility, dependency rules and installed-script acceptance."""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "lightbridge"
sys.path.insert(0, str(TOOL))

import lb_commands  # noqa: E402
import lb_fleet  # noqa: E402

OWNERS = {
    "project": (
        "project_fields",
        "bootstrap_json",
        "cmd_sections",
        "cmd_init",
        "cmd_add",
        "cmd_show",
        "cmd_toggle",
        "cmd_status",
        "cmd_path",
        "cmd_doctor",
    ),
    "repos": ("cmd_repos_list", "cmd_repos_add", "cmd_repos_rm"),
    "graph": (
        "cmd_graph_init",
        "cmd_graph_types",
        "cmd_graph_show",
        "cmd_graph_link",
        "cmd_graph_unlink",
        "cmd_graph_set",
        "cmd_graph_doctor",
        "cmd_graph_mermaid",
        "cmd_graph_html",
    ),
    "keys": (
        "ADD_USAGE",
        "RUN_USAGE",
        "cmd_key_ls",
        "cmd_key_add",
        "cmd_key_run",
        "cmd_key_rm",
        "cmd_key_doctor",
    ),
    "fleet": (
        "REFUSALS",
        "STEP_OF",
        "cmd_fleet_init",
        "cmd_fleet_status",
        "cmd_fleet_sync",
    ),
    "move": ("cmd_mv",),
}
FAMILIES = {f"lb_commands.{name}" for name in OWNERS}
ALLOWED = {("lb_commands.graph", "lb_commands.repos")}
FLEET_OWNERS = {
    "node_program": (
        "REPORT_MARK",
        "REGISTRIES",
        "APPLY_TIMEOUT",
        "NODE_SCRIPT",
        "render_node_script",
        "parse_report",
    ),
    "transport": (
        "SSH_OPTS",
        "SSH_OFFLINE",
        "SESSION_TIMEOUT",
        "UNREACHABLE",
        "ssh_argv",
        "run_node",
        "classify_unreachable",
    ),
    "hub": (
        "FLEET_HEADER",
        "SEED_BLOCK",
        "repo_specs",
        "hub_repo_dir",
        "hub_fetch",
        "distance",
        "now_iso",
        "short",
        "receipt_path",
        "write_receipt",
    ),
}
FLEET_MODULES = {f"lb_fleet.{name}" for name in FLEET_OWNERS}


def signature_text(function):
    """Stable signature text, including defaults without function memory addresses."""
    signature = inspect.signature(function)
    parameters = [
        parameter.replace(
            default=f"{parameter.default.__module__}.{parameter.default.__qualname__}"
        )
        if callable(parameter.default)
        and parameter.default is not inspect.Parameter.empty
        else parameter
        for parameter in signature.parameters.values()
    ]
    return str(signature.replace(parameters=parameters))


class FleetCharacterizationTest(unittest.TestCase):
    def test_signatures_and_streamed_bytes_match_baseline(self):
        expected = json.loads(
            (ROOT / "tests/fixtures/lightbridge_fleet_contracts.json").read_text()
        )
        for name, signature in expected["signatures"].items():
            with self.subTest(name=name):
                self.assertEqual(signature_text(getattr(lb_fleet, name)), signature)
        self.assertEqual(
            hashlib.sha256(lb_fleet.NODE_SCRIPT.encode()).hexdigest(),
            expected["node_sha256"],
        )
        for case in expected["rendered"]:
            script = lb_fleet.render_node_script(**case["kwargs"])
            self.assertEqual(
                hashlib.sha256(script.encode()).hexdigest(), case["sha256"]
            )
            ast.parse(script, feature_version=(3, 8))

    def test_runner_arguments_and_exit_passthrough(self):
        for code in (0, 1, 7, 127, 255):
            with self.subTest(code=code):
                runner = Mock(
                    return_value=subprocess.CompletedProcess([], code, "out", "err")
                )
                self.assertEqual(
                    lb_fleet.run_node("fixture", "program", runner=runner, timeout=9),
                    (code, "out", "err"),
                )
                runner.assert_called_once_with(
                    [
                        "ssh",
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        "ConnectTimeout=8",
                        "fixture",
                        "python3",
                        "-",
                    ],
                    input="program",
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=9,
                )
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        lb_fleet.run_node("fixture", "program", runner=runner)
        self.assertEqual(runner.call_args.kwargs["timeout"], 1800)
        self.assertIs(
            inspect.signature(lb_fleet.run_node).parameters["runner"].default,
            subprocess.run,
        )

    def test_runner_exception_mappings(self):
        for error, code, message in (
            (FileNotFoundError("missing"), 127, "ssh: not found on PATH"),
            (OSError("unavailable"), 1, "unavailable"),
            (
                subprocess.TimeoutExpired("ssh", 9),
                1,
                str(subprocess.TimeoutExpired("ssh", 9)),
            ),
        ):
            with self.subTest(error=error):
                self.assertEqual(
                    lb_fleet.run_node(
                        "fixture", "program", runner=Mock(side_effect=error)
                    ),
                    (code, "", message),
                )

    def test_final_report_marker_wins_even_when_invalid(self):
        mark = lb_fleet.REPORT_MARK + " "
        first = mark + '{"repos": {}, "host": "first"}\n'
        second = mark + '{"repos": {}, "host": "last"}\n'
        self.assertEqual(
            lb_fleet.parse_report("noise\n" + first + second + "noise\n")["host"],
            "last",
        )
        for invalid in ("{broken", "[]", "null", "{}", '{"repos": []}'):
            with self.subTest(invalid=invalid):
                self.assertIsNone(lb_fleet.parse_report(first + mark + invalid))
        self.assertEqual(lb_fleet.parse_report(first + " " + second)["host"], "first")

    def test_unreachable_uses_pattern_priority_and_last_nonempty_line(self):
        kind, message = lb_fleet.classify_unreachable(
            "Permission denied\nCould not resolve hostname fixture\n final detail \n\n"
        )
        self.assertEqual(kind, "dns")
        self.assertTrue(message.endswith("(ssh exit 255: final detail)"))

    def test_receipt_failure_preserves_existing_file_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            fleet = Path(directory) / "fleet.toml"
            receipt = lb_fleet.write_receipt(fleet, "fixture", {"ok": True})
            original = receipt.read_bytes()
            # Patch the function's owning module both before and after extraction.
            owner = importlib.import_module(lb_fleet.write_receipt.__module__)
            for failure in (OSError("replace failed"), KeyboardInterrupt()):
                with self.subTest(failure=type(failure).__name__):
                    with patch.object(owner.os, "replace", side_effect=failure):
                        with self.assertRaises(type(failure)):
                            lb_fleet.write_receipt(fleet, "fixture", {"ok": False})
                    self.assertEqual(receipt.read_bytes(), original)
                    self.assertEqual(list(receipt.parent.iterdir()), [receipt])

    @unittest.skipIf(os.name == "nt", "node program uses POSIX shell")
    def test_all_pulls_precede_apply_and_all_applies_precede_verify(self):
        from test_lb_fleet import World, run_node_locally

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            alpha, beta = World(base / "one"), World(base / "two", name="beta")
            (alpha.node_root / "beta").symlink_to(beta.node, target_is_directory=True)
            alpha.advance_origin()
            beta.advance_origin()
            log = base / "order.log"
            specs = []
            for world in (alpha, beta):
                # Every apply must see both pulled files, and every verify must see
                # both apply markers. Per-repo pull/apply/verify interleaving fails.
                pulled = [next(w.work.glob("f0-*.txt")).name for w in (alpha, beta)]
                ready = " && ".join(
                    f"test -f {shlex.quote(str(w.node / filename))}"
                    for w, filename in zip((alpha, beta), pulled)
                )
                applied = " && ".join(
                    f"test -f {shlex.quote(str(w.node / 'applied'))}"
                    for w in (alpha, beta)
                )
                specs.append(
                    world.spec(
                        apply=f"{ready} && touch applied && echo apply-{world.name} >> {shlex.quote(str(log))}",
                        verify=f"{applied} && echo verify-{world.name} >> {shlex.quote(str(log))}",
                    )
                )
            report = run_node_locally(
                lb_fleet.render_node_script("sync", str(alpha.node_root), specs)
            )
            self.assertEqual(
                [entry["status"] for entry in report["repos"].values()],
                ["applied", "applied"],
            )
            self.assertEqual(
                log.read_text().splitlines(),
                ["apply-alpha", "apply-beta", "verify-alpha", "verify-beta"],
            )


def dependency_errors(sources: dict[str, str]) -> list[str]:
    """Check all local imports, including conditional and type-only imports.

    Transitive checks prevent a family hiding a forbidden dependency behind a helper.
    Package-relative imports resolve to the same module names as absolute imports.
    """
    edges: dict[str, set[str]] = {name: set() for name in sources}
    packages = {
        ".".join(name.split(".")[:index])
        for name in sources
        for index in range(1, len(name.split(".")))
    }
    for name, source in sources.items():
        package = name if name in packages else name.rpartition(".")[0]
        for node in ast.walk(ast.parse(source)):
            targets = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = package.split(".")
                    base = ".".join(parts[: len(parts) - node.level + 1])
                    base = ".".join(filter(None, (base, node.module)))
                else:
                    base = node.module or ""
                for alias in node.names:
                    child = f"{base}.{alias.name}"
                    targets.append(child if child in sources else base)
            edges[name].update(target for target in targets if target in sources)

    errors = []
    for name in edges:
        if name not in FAMILIES | FLEET_MODULES:
            continue
        pending = list(edges[name])
        reached = set()
        while pending:
            target = pending.pop()
            if target in reached:
                continue
            reached.add(target)
            if name in FLEET_MODULES:
                if target in {"lb_fleet", "lb_commands", "lightbridge"}:
                    errors.append(
                        f"{name} reaches forbidden facade/entrypoint {target}"
                    )
                elif target in FAMILIES or target in FLEET_MODULES - {name}:
                    errors.append(f"{name} reaches forbidden owner {target}")
                pending.extend(edges[target])
                continue
            if target == "lb_commands":
                errors.append(f"{name} reaches command facade")
            elif target == "lightbridge":
                errors.append(f"{name} reaches CLI entrypoint")
            elif (
                target in FAMILIES and target != name and (name, target) not in ALLOWED
            ):
                errors.append(f"{name} reaches forbidden family {target}")
            pending.extend(edges[target])

    # Domain/read modules must not depend back on the command package.
    for name, targets in edges.items():
        if name == "lightbridge" or name == "lb_commands" or name in FAMILIES:
            continue
        if any(target == "lb_commands" or target in FAMILIES for target in targets):
            errors.append(f"{name} imports command implementation")

    done, active = set(), set()

    def visit(name):
        if name in active:
            errors.append(f"import cycle at {name}")
            return
        if name in done:
            return
        active.add(name)
        for target in edges[name]:
            visit(target)
        active.remove(name)
        done.add(name)

    for name in edges:
        visit(name)
    return sorted(set(errors))


class CommandCompatibilityTest(unittest.TestCase):
    def test_explicit_exports_forward_the_original_objects(self):
        expected = {"row"}
        for owner, names in OWNERS.items():
            implementation = importlib.import_module(f"lb_commands.{owner}")
            for name in names:
                expected.add(name)
                with self.subTest(name=name):
                    self.assertIs(
                        getattr(lb_commands, name), getattr(implementation, name)
                    )
        import lb_style

        self.assertIs(lb_commands.row, lb_style.row)
        self.assertEqual(set(lb_commands.__all__), expected)
        self.assertEqual(len(lb_commands.__all__), len(expected))

    def test_signatures_match_the_pre_refactor_contract(self):
        expected = json.loads(
            (ROOT / "tests/fixtures/lightbridge_commands_signatures.json").read_text()
        )
        actual = {
            name: signature_text(getattr(lb_commands, name))
            for name in lb_commands.__all__
            if inspect.isfunction(getattr(lb_commands, name))
        }
        self.assertEqual(actual, expected)

    def test_package_ownership_and_import_graph(self):
        self.assertEqual(
            {
                path.relative_to(TOOL / "lb_commands").as_posix()
                for path in (TOOL / "lb_commands").rglob("*.py")
            },
            {f"{name}.py" for name in OWNERS} | {"__init__.py"},
        )
        self.assertFalse((TOOL / "lb_commands.py").exists())
        sources = {}
        for path in TOOL.rglob("*.py"):
            parts = list(path.relative_to(TOOL).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            sources[".".join(parts)] = path.read_text(encoding="utf-8")
        self.assertEqual(dependency_errors(sources), [])


class FleetCompatibilityTest(unittest.TestCase):
    def test_explicit_exports_forward_original_objects(self):
        import lb_resolve

        expected = {"DEFAULT_FLEET", "fleet_receipts_dir", "load_receipt"}
        for name in expected:
            self.assertIs(getattr(lb_fleet, name), getattr(lb_resolve, name))
        for owner, names in FLEET_OWNERS.items():
            implementation = importlib.import_module(f"lb_fleet.{owner}")
            for name in names:
                expected.add(name)
                with self.subTest(name=name):
                    self.assertIs(
                        getattr(lb_fleet, name), getattr(implementation, name)
                    )
        self.assertEqual(set(lb_fleet.__all__), expected)
        self.assertEqual(len(lb_fleet.__all__), len(expected))

    def test_package_has_only_the_approved_owners(self):
        self.assertFalse((TOOL / "lb_fleet.py").exists())
        self.assertEqual(
            {
                path.relative_to(TOOL / "lb_fleet").as_posix()
                for path in (TOOL / "lb_fleet").rglob("*.py")
            },
            {f"{name}.py" for name in FLEET_OWNERS} | {"__init__.py"},
        )


class DependencyCheckerTest(unittest.TestCase):
    def sources(self, **overrides):
        return {
            "lb_commands": "from .graph import cmd_graph_link\n",
            "lb_commands.graph": "from .repos import open_registry\n",
            "lb_commands.repos": "from lb_resolve import load_registry\n",
            "lb_commands.keys": "",
            "lb_resolve": "",
            **overrides,
        }

    def test_permitted_registry_dependency(self):
        self.assertEqual(dependency_errors(self.sources()), [])

    def test_absolute_family_import_is_rejected(self):
        errors = dependency_errors(
            self.sources(
                **{
                    "lb_commands.graph": "from lb_commands.keys import cmd_key_ls\n",
                }
            )
        )
        self.assertTrue(
            any("forbidden family lb_commands.keys" in error for error in errors)
        )

    def test_type_only_relative_import_is_rejected(self):
        errors = dependency_errors(
            self.sources(
                **{
                    "lb_commands.graph": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n from .keys import cmd_key_ls\n",
                }
            )
        )
        self.assertTrue(
            any("forbidden family lb_commands.keys" in error for error in errors)
        )

    def test_facade_import_is_rejected(self):
        errors = dependency_errors(
            self.sources(
                **{
                    "lb_commands.graph": "from lb_commands import cmd_key_ls\n",
                }
            )
        )
        self.assertTrue(any("reaches command facade" in error for error in errors))

    def test_transitive_dependency_is_rejected(self):
        errors = dependency_errors(
            self.sources(
                **{
                    "lb_commands.graph": "import lb_helper\n",
                    "lb_helper": "from lb_commands.keys import cmd_key_ls\n",
                }
            )
        )
        self.assertIn(
            "lb_commands.graph reaches forbidden family lb_commands.keys", errors
        )

    def test_cycle_is_rejected(self):
        errors = dependency_errors(
            self.sources(
                **{
                    "lb_resolve": "import lb_helper\n",
                    "lb_helper": "import lb_resolve\n",
                }
            )
        )
        self.assertTrue(any("import cycle" in error for error in errors))

    def test_resolver_cannot_depend_back_on_commands(self):
        errors = dependency_errors(
            self.sources(
                **{
                    "lb_resolve": "from lb_commands.repos import open_registry\n",
                }
            )
        )
        self.assertIn("lb_resolve imports command implementation", errors)

    def fleet_sources(self, **overrides):
        return self.sources(
            **{
                "lb_fleet": "from .hub import receipt_path\nfrom . import transport\nfrom .node_program import parse_report\n",
                "lb_fleet.hub": "from lb_resolve import fleet_receipts_dir\n",
                "lb_fleet.transport": "",
                "lb_fleet.node_program": "",
                **overrides,
            }
        )

    def test_independent_fleet_owners_are_permitted(self):
        self.assertEqual(dependency_errors(self.fleet_sources()), [])

    def test_fleet_cross_owner_imports_are_rejected(self):
        for statement in (
            "from .hub import receipt_path",
            "from . import hub",
            "import lb_fleet.hub",
            "from lb_fleet import hub",
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n from .hub import receipt_path",
        ):
            with self.subTest(statement=statement):
                errors = dependency_errors(
                    self.fleet_sources(**{"lb_fleet.transport": statement})
                )
                self.assertIn(
                    "lb_fleet.transport reaches forbidden owner lb_fleet.hub", errors
                )

    def test_fleet_cannot_reach_facades_commands_or_entrypoint(self):
        for target in ("lb_fleet", "lb_commands", "lb_commands.graph", "lightbridge"):
            with self.subTest(target=target):
                errors = dependency_errors(
                    self.fleet_sources(
                        **{
                            "lb_fleet.transport": f"import {target}\n",
                            "lightbridge": "",
                        }
                    )
                )
                self.assertTrue(
                    any(
                        "lb_fleet.transport reaches forbidden" in error
                        and target in error
                        for error in errors
                    )
                )

    def test_fleet_transitive_dependency_is_rejected(self):
        errors = dependency_errors(
            self.fleet_sources(
                **{
                    "lb_fleet.transport": "import lb_helper\n",
                    "lb_helper": "from lb_fleet.hub import receipt_path\n",
                }
            )
        )
        self.assertIn("lb_fleet.transport reaches forbidden owner lb_fleet.hub", errors)

    def test_fleet_facade_relative_imports_participate_in_cycles(self):
        # This cycle is invisible if the fleet package's relative import is
        # incorrectly resolved as top-level `hub` instead of `lb_fleet.hub`.
        errors = dependency_errors(
            self.fleet_sources(**{"lb_fleet.hub": "import lb_fleet\n"})
        )
        self.assertTrue(any("import cycle" in error for error in errors))

    def test_fleet_owner_cycle_is_rejected(self):
        errors = dependency_errors(
            self.fleet_sources(
                **{
                    "lb_fleet.transport": "from .node_program import parse_report\n",
                    "lb_fleet.node_program": "from .transport import run_node\n",
                }
            )
        )
        self.assertTrue(any("import cycle" in error for error in errors))


class InstalledCommandTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX executable symlink installation")
    def test_copied_tree_via_symlink_outside_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            installed = base / "installed"
            shutil.copytree(
                TOOL, installed, ignore=shutil.ignore_patterns("__pycache__")
            )
            link = base / "lb"
            link.symlink_to(installed / "lightbridge.py")
            cwd, home = base / "unrelated", base / "home"
            cwd.mkdir()
            home.mkdir()
            env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
            env.pop("PYTHONPATH", None)
            env.pop("LIGHTBRIDGE_STATE_DIR", None)
            env.pop("FORCE_COLOR", None)
            env["NO_COLOR"] = "1"
            # Keep the dependency cache reusable while isolating application state.
            env["UV_CACHE_DIR"] = subprocess.check_output(
                ["uv", "cache", "dir"], text=True
            ).strip()
            cases = (
                ("--help",),
                ("init", "docs-index", "--json"),
                ("show", "--json"),
                ("graph", "init", "--dry-run"),
                ("fleet", "init", "--dry-run"),
                ("key", "ls", "--json"),
            )
            for args in cases:
                with self.subTest(args=args):
                    result = subprocess.run(
                        [str(link), *args],
                        cwd=cwd,
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if args == ("--help",):
                        self.assertIn("Usage: lb", result.stdout)
                    if args == ("show", "--json"):
                        self.assertEqual(
                            json.loads(result.stdout)["docs-index"]["enabled"], True
                        )

            from test_lb_fleet import World

            world = World(base / "fleet-world")
            fleet = base / "fleet.toml"
            fleet.write_text(
                f"[hub]\nroot = {json.dumps(str(world.hub_root))}\n"
                '[repos.alpha]\napply = "touch installed-apply"\n'
                'verify = "test -f installed-apply"\n'
                '[nodes.fixture]\nssh = "fixture-only"\n'
                f"root = {json.dumps(str(world.node_root))}\n"
                'repos = ["alpha"]\n'
            )
            shim = base / "bin"
            shim.mkdir()
            ssh = shim / "ssh"
            ssh.write_text(
                f"#!{sys.executable}\nimport os, sys\n"
                "os.execv(sys.executable, [sys.executable, '-'])\n"
            )
            ssh.chmod(0o755)
            env["PATH"] = str(shim) + os.pathsep + env["PATH"]
            for args in (
                ("status", "fixture", "--no-fetch"),
                ("sync", "fixture", "--reinstall"),
            ):
                result = subprocess.run(
                    [str(link), "fleet", *args, "--fleet", str(fleet), "--json"],
                    cwd=cwd,
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                json.loads(result.stdout)
            self.assertTrue((world.node / "installed-apply").is_file())
            receipt = json.loads((base / "fleet/fixture.json").read_text())
            self.assertTrue(receipt["ok"])
            self.assertEqual(receipt["repos"]["alpha"]["status"], "applied")


if __name__ == "__main__":
    unittest.main(verbosity=2)
