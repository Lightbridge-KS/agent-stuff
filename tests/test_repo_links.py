#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for repo-links: the graph projection CLI and its SessionStart hook.

Each test builds a throwaway *project* dir and a throwaway *home* dir carrying BOTH
user-level layers — the central `~/.lightbridge/graph.toml` (typed edges between
logical names) and the personal `~/.lightbridge/repos.toml` registry that names the
project itself — then drives the real hook.py / repo_links.py as a subprocess with
`HOME` pointed at the fake home, so the `~` convention is exercised end to end.
Files are executed directly, the same path as Claude Code's /bin/sh registration,
so a missing executable bit or broken shebang fails here too (`UV_CACHE_DIR` is
pinned to the real cache, since the fake `HOME` would otherwise cold-start uv on
every subprocess). The hook resolves its paired repo_links.py and lb_resolve.py
relative to its own location in this repo, so it is exercised in place — only the
project and home under inspection are synthetic.

Opt-in is the graph file itself; the repo participates when it is a registered
node with incident edges. The retired per-project `[repo-links]` section only
appears here to prove its deprecation warning.

    uv run tests/test_repo_links.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "repo-links-inject" / "hook.py"
SCRIPT = REPO_ROOT / "scripts" / "repo-links" / "repo_links.py"


def script_argv(script: Path, *args: str) -> list[str]:
    """argv launching a PEP 723 script the way its real consumer does.

    POSIX execs the file directly, keeping the executable bit and the `uv run`
    shebang under test. Windows CreateProcess cannot launch a shebang script at all
    (WinError 193), so go through `uv run` — the very interpreter the shebang names.
    """
    if os.name != "nt":
        return [str(script), *args]
    return ["uv", "run", str(script), *args]


def home_vars(home: Path) -> dict[str, str]:
    """Env that redirects `~` to `home` on both platforms.

    POSIX expanduser reads $HOME; Windows reads %USERPROFILE% and ignores HOME
    entirely — set only HOME there and every subprocess quietly resolves `~` to the
    REAL home, reading (and writing) the developer's own ~/.lightbridge.
    """
    return {"HOME": str(home), "USERPROFILE": str(home)}


# Resolved against the REAL home before tests override HOME, so uv's environment
# cache stays warm across the fake-HOME subprocesses.
UV_CACHE_DIR = os.environ.get("UV_CACHE_DIR", str(Path("~/.cache/uv").expanduser()))

# The standard one-edge graph: the project ("app") declares its upstream service.
GRAPH_ONE = """\
[types.upstream]
inverse = "downstream"
backlink = "full"

[[edge]]
from = 'app'
to = 'example-service'
type = 'upstream'
from_note = 'Commercial counterpart'
to_note = 'Derived variant'
"""

# The pre-graph per-project section — only used to prove its deprecation warning.
LEGACY_SECTION = (
    "[repo-links]\n"
    "[[repo-links.link]]\n"
    'name = "example-service"\n'
    'role = "upstream"\n'
)


def project_key(path: Path) -> str:
    """Mirror of the lightbridge encoding (resolved path, drive colon dropped, separators → '-')."""
    text = str(path.resolve())
    if len(text) > 1 and text[1] == ":":  # Windows drive letter
        text = text[0] + text[2:]
    return text.replace(os.sep, "-").replace("/", "-")


def run_hook(cwd: Path, home: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        script_argv(HOOK),
        input=json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True, encoding="utf-8",
        env={**os.environ, **home_vars(home), "UV_CACHE_DIR": UV_CACHE_DIR},
    )


def run_cli(args: list[str], home: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        script_argv(SCRIPT, *args),
        capture_output=True,
        text=True, encoding="utf-8",
        env={**os.environ, **home_vars(home), "UV_CACHE_DIR": UV_CACHE_DIR},
    )


def make_env(
    base: Path,
    *,
    graph: str | None,
    registry: str | None | object = "auto",
    register_app: bool = True,
    service_dir: bool = True,
    extra_registry: str = "",
) -> tuple[Path, Path]:
    """Build the fake (project, home) pair.

    `registry="auto"` writes the standard registry — the project itself as `app`
    plus `example-service` under the fake home; None skips the file; any other
    string is written verbatim (malformed-registry tests).
    """
    home = base / "home"
    (home / ".lightbridge").mkdir(parents=True)
    proj = base / "proj"
    proj.mkdir()
    if service_dir:
        (home / "work" / "example-service").mkdir(parents=True)
    if registry == "auto":
        registry = (
            "[repos]\n"
            + (f"app = '{proj}'\n" if register_app else "")
            + 'example-service = "~/work/example-service"\n'
            + extra_registry
        )
    if registry is not None:
        (home / ".lightbridge" / "repos.toml").write_text(registry)
    if graph is not None:
        (home / ".lightbridge" / "graph.toml").write_text(graph)
    return proj, home


def write_project_config(proj: Path, home: Path, body: str) -> Path:
    """A user-level project config for `proj` (only the legacy-section tests need one)."""
    cfg_dir = home / ".lightbridge" / "projects" / project_key(proj)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    config = cfg_dir / "config.toml"
    config.write_text(body)
    return config


class RepoLinksHookTest(unittest.TestCase):
    def assert_silent(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def context_of(self, result: subprocess.CompletedProcess) -> str:
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        return data["hookSpecificOutput"]["additionalContext"]

    # --- gating -------------------------------------------------------------

    def test_no_graph_is_silent(self):
        # The graph file is the machine's opt-in; without it the hook says nothing.
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=None)
            self.assert_silent(run_hook(proj, home))

    def test_unregistered_repo_is_silent(self):
        # The graph exists but this repo has no node name — not a participant.
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE, register_app=False)
            self.assert_silent(run_hook(proj, home))

    def test_node_without_edges_is_silent(self):
        graph = "[types.upstream]\ninverse = 'downstream'\nbacklink = 'full'\n"
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=graph)
            self.assert_silent(run_hook(proj, home))

    def test_malformed_graph_warns(self):
        # A graph file can only exist on the owner's machine -> rot must show.
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph="not toml [[[\n")
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("WARNING", ctx)
            self.assertIn("unreadable", ctx)

    def test_graph_without_registry_warns(self):
        # Graph present, repos.toml absent: names cannot resolve — owner rot, not silence.
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE, registry=None)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("WARNING", ctx)
            self.assertIn("absent", ctx)

    def test_malformed_registry_warns(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE, registry="not toml [[[\n")
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("WARNING", ctx)
            self.assertIn("unreadable", ctx)

    def test_registry_without_repos_table_warns(self):
        # Flat root keys (no [repos] table) are a registry error, not a silent skip;
        # since #18 the message names the stranded key and the fix.
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(
                Path(d), graph=GRAPH_ONE,
                registry='example-service = "~/work/example-service"\n',
            )
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("WARNING", ctx)
            self.assertIn("[repos]", ctx)
            self.assertIn("example-service", ctx)
            self.assertIn("indent", ctx)

    def test_legacy_per_repo_config_warns(self):
        # A stray pre-migration <repo>/.lightbridge/config.toml earns its one-liner
        # even when the machine has no graph at all.
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=None)
            lb_dir = proj / ".lightbridge"
            lb_dir.mkdir()
            (lb_dir / "config.toml").write_text(LEGACY_SECTION)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("no longer read", ctx)
            self.assertNotIn("example-service →", ctx)

    def test_leftover_repo_links_section_warns_and_is_not_read(self):
        """The pre-graph [repo-links] section deprecates: one warning line, and its
        declared links must NOT render — the graph is the only source."""
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=None)
            write_project_config(proj, home, LEGACY_SECTION)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("[repo-links]", ctx)
            self.assertIn("no longer read", ctx)
            self.assertNotIn("example-service →", ctx)

    def test_section_warning_rides_along_with_the_map(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE)
            write_project_config(proj, home, LEGACY_SECTION)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("example-service →", ctx)  # the graph's map renders
            self.assertIn("no longer read", ctx)  # and the nudge rides along

    # --- projection ---------------------------------------------------------

    def test_outgoing_edge_renders_path_type_note(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE)
            ctx = self.context_of(run_hook(proj, home))
            # Tilde in the registry expanded against the fake HOME.
            self.assertIn(f"example-service → {home / 'work' / 'example-service'}", ctx)
            self.assertIn("(upstream)", ctx)
            self.assertIn("— Commercial counterpart", ctx)
            self.assertIn("absolute path above", ctx)

    def test_one_edge_projects_both_ways(self):
        """The SSOT promise: the same edge renders in the other repo's session as a
        backlink labeled with the type's inverse, carrying the to_note."""
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE)
            service = home / "work" / "example-service"
            ctx = self.context_of(run_hook(service, home))
            self.assertIn("Backlinks:", ctx)
            self.assertIn("(downstream)", ctx)
            self.assertIn("— Derived variant", ctx)
            self.assertIn(f"app → {proj}", ctx)  # as registered, not resolve()d

    def test_compact_backlink_renders_one_mention_line(self):
        graph = GRAPH_ONE + (
            "\n[types.subject]\ninverse = 'studied-by'\nbacklink = 'compact'\n"
            "\n[[edge]]\nfrom = 'docs'\nto = 'app'\ntype = 'subject'\n"
        )
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=graph)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("Also referenced by: docs (studied-by)", ctx)
            self.assertNotIn("docs →", ctx)  # compact means names-only, no path line

    def test_off_backlink_stays_silent_in_the_targets_view(self):
        graph = GRAPH_ONE + (
            "\n[[edge]]\nfrom = 'spy'\nto = 'app'\ntype = 'upstream'\nbacklink = 'off'\n"
        )
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=graph)
            ctx = self.context_of(run_hook(proj, home))
            self.assertNotIn("spy", ctx)

    def test_unregistered_edge_target_warns(self):
        graph = GRAPH_ONE + "\n[[edge]]\nfrom = 'app'\nto = 'ghost'\ntype = 'upstream'\n"
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=graph)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("ghost: WARNING — not registered", ctx)
            self.assertIn("example-service →", ctx)  # the resolved edge still renders

    def test_stale_path_warns(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE, service_dir=False)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("example-service: WARNING", ctx)
            self.assertIn("does not exist", ctx)

    def test_path_is_file_warns(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE, service_dir=False)
            (home / "work").mkdir()
            (home / "work" / "example-service").write_text("a file, not a repo")
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("not a directory", ctx)

    def test_symlinked_repo_is_ok_and_renders_as_declared(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE, service_dir=False)
            (home / "elsewhere" / "real-repo").mkdir(parents=True)
            (home / "work").mkdir()
            (home / "work" / "example-service").symlink_to(home / "elsewhere" / "real-repo")
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn(f"example-service → {home / 'work' / 'example-service'}", ctx)
            self.assertNotIn("real-repo", ctx)
            self.assertNotIn("WARNING", ctx)

    def test_undeclared_edge_type_warns_but_renders(self):
        graph = GRAPH_ONE + "\n[[edge]]\nfrom = 'app'\nto = 'example-service'\ntype = 'mystery'\n"
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=graph)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("(mystery)", ctx)  # rot surfaces, never vanishes
            self.assertIn("not declared", ctx)

    def test_skipped_edge_blocks_warn(self):
        graph = GRAPH_ONE + "\n[[edge]]\nfrom = 'app'\nto = ''\ntype = 'upstream'\n"
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=graph)
            ctx = self.context_of(run_hook(proj, home))
            self.assertIn("malformed edge block", ctx)


class RepoLinksCliTest(unittest.TestCase):
    def test_json_schema(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE)
            result = run_cli(["--start", str(proj), "--json"], home)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(
                set(data),
                {"graph", "registry", "registry_error", "root", "node",
                 "out", "backlinks", "mentions", "warnings"},
            )
            self.assertEqual(data["node"], "app")
            (edge,) = data["out"]
            self.assertEqual(
                set(edge),
                {"other", "type", "label", "note", "path", "status", "detail"},
            )
            self.assertEqual(edge["status"], "ok")

    def test_no_graph_exits_2_naming_init(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=None)
            result = run_cli(["--start", str(proj)], home)
            self.assertEqual(result.returncode, 2)
            self.assertIn("lb graph init", result.stderr)

    def test_unregistered_repo_exits_2_naming_repos_add(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE, register_app=False)
            result = run_cli(["--start", str(proj)], home)
            self.assertEqual(result.returncode, 2)
            self.assertIn("lb repos add", result.stderr)

    def test_node_without_edges_exits_2_naming_link(self):
        graph = "[types.upstream]\ninverse = 'downstream'\nbacklink = 'full'\n"
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=graph)
            result = run_cli(["--start", str(proj)], home)
            self.assertEqual(result.returncode, 2)
            self.assertIn("lb graph link", result.stderr)

    def test_leftover_section_warns_on_stderr_and_map_still_renders(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE)
            write_project_config(proj, home, LEGACY_SECTION)
            result = run_cli(["--start", str(proj)], home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("no longer read", result.stderr)
            self.assertIn("example-service →", result.stdout)

    def test_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=GRAPH_ONE)
            self.assertEqual(run_cli(["--start", str(proj), "--check"], home).returncode, 0)
        ghost_graph = GRAPH_ONE + "\n[[edge]]\nfrom = 'app'\nto = 'ghost'\ntype = 'upstream'\n"
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=ghost_graph)
            self.assertEqual(run_cli(["--start", str(proj), "--check"], home).returncode, 1)

    def test_graph_and_registry_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            proj, home = make_env(Path(d), graph=None, registry=None)
            (home / "work" / "example-service").mkdir(parents=True, exist_ok=True)
            alt_graph = Path(d) / "alt-graph.toml"
            alt_graph.write_text(GRAPH_ONE)
            alt_registry = Path(d) / "alt-repos.toml"
            alt_registry.write_text(
                f"[repos]\napp = '{proj}'\nexample-service = \"~/work/example-service\"\n"
            )
            result = run_cli(
                ["--start", str(proj), "--graph", str(alt_graph),
                 "--registry", str(alt_registry), "--json"],
                home,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["out"][0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
