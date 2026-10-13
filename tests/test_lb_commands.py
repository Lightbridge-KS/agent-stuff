#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Command-package compatibility, dependency rules and installed-script acceptance."""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "lightbridge"
sys.path.insert(0, str(TOOL))

import lb_commands  # noqa: E402

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


def dependency_errors(sources: dict[str, str]) -> list[str]:
    """Check all local imports, including conditional and type-only imports.

    Transitive checks prevent a family hiding a forbidden dependency behind a helper.
    Package-relative imports resolve to the same module names as absolute imports.
    """
    edges: dict[str, set[str]] = {name: set() for name in sources}
    for name, source in sources.items():
        package = "lb_commands" if name == "lb_commands" else name.rpartition(".")[0]
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
        if name not in FAMILIES:
            continue
        pending = list(edges[name])
        reached = set()
        while pending:
            target = pending.pop()
            if target in reached:
                continue
            reached.add(target)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
