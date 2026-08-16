#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.27"]
# ///
"""The `lightbridge` (`lb`) CLI — entrypoint and Typer wiring only.

**Do not import this file.** It is the entrypoint; the library is `lb_resolve.py`, which
hooks and sibling scripts path-load. A test asserts nothing under `hooks/` or `scripts/`
loads this one. See `docs/lightbridge/adr/0001-modular-lightbridge.md`.

    lb_resolve.py   the read path — resolution, toml_str, console (PATH-LOADED)
    lb_tomledit.py  surgical TOML line edits
    lb_catalog.py   the section catalog + config-document assembly
    lb_registry.py  ~/.lightbridge/repos.toml
    lb_graph.py     ~/.lightbridge/graph.toml — the cross-repo graph document
    lb_doctor.py    tree audit
    lb_mv.py        plan_mv + apply_mv
    lb_commands.py  the cmd_* verb handlers
    lightbridge.py  this file

Sibling imports resolve because `uv run --script` puts the **symlink-resolved** script
directory on `sys.path[0]` — so they work through the `~/.local/bin/lb` shim too.

    lightbridge status               # one-shot dashboard: config, sections, sibling state
    lightbridge init                 # create this project's config (refuses to clobber)
    lightbridge init docs-index research
    lightbridge add repo-links       # append a section to an existing config
    lightbridge show                 # print the stored config; `show SECTION` for one block
    lightbridge enable research      # flip a section's `enabled` in place (or `disable`)
    lightbridge sections             # what can go in a config, and who reads it
    lightbridge path                 # this project's config path (+ exists?)
    lightbridge path --start DIR     # another project's
    lightbridge repos list           # manage ~/.lightbridge/repos.toml (add NAME PATH · rm NAME)
    lightbridge graph init           # seed ~/.lightbridge/graph.toml (types vocabulary)
    lightbridge graph show [NAME]    # whole-graph summary, or one node's projected ego view
    lightbridge graph types          # the edge vocabulary, each with its direction reading
    lightbridge mv OLD NEW           # move/rename a repo (or parent dir) + repair all bookkeeping
    lightbridge doctor               # audit the whole tree; exit 1 on problems
    lightbridge doctor --json

Link it onto PATH as `lightbridge` (and `lb`) — see this tool's README.

Exit codes: 0 ok (incl. an idempotent no-op); 1 refused (`doctor` found problems or the
config/section/registry entry a verb needs is absent, would clobber, or is unreadable);
2 usage.
"""

from __future__ import annotations

import sys
from pathlib import Path

from lb_catalog import SECTIONS, SectionName
from lb_commands import (
    cmd_add,
    cmd_doctor,
    cmd_graph_init,
    cmd_graph_show,
    cmd_graph_types,
    cmd_init,
    cmd_mv,
    cmd_path,
    cmd_repos_add,
    cmd_repos_list,
    cmd_repos_rm,
    cmd_sections,
    cmd_show,
    cmd_status,
    cmd_toggle,
)
from lb_resolve import (
    DEFAULT_GRAPH,
    DEFAULT_REGISTRY,
    DEFAULT_STATE_DIR,
    STATE_DIR_ENV,
    use_utf8_console,
)

__version__ = "0.5.0"

DESCRIPTION = (
    "Create, inspect, and audit user-level .lightbridge project config "
    "— plus the personal repo registry."
)
EPILOG = (
    "Exit: 0 ok · 1 refused (doctor problems, would clobber, missing "
    "config/section/name, unreadable file) · 2 usage. "
    "Siblings (own their state, not wrapped here): plan_store.py (plans/), "
    "handoff.py (handoffs/), repo_links.py ([repo-links] resolution), "
    "docs-index ([docs-index] rendering). Spec: the lightbridge-config skill."
)
START_HELP = "Directory whose project root is resolved (default: CWD)."


def main() -> None:
    # typer stays a CLI-only import, built inside main() rather than at module scope.
    # The sibling modules above are all stdlib-pure, and `lb_resolve.py` additionally
    # imports no siblings — hooks and sibling tools exec_module *that* file inside their
    # own dependency-free PEP 723 envs. The `# dependencies` header is read only when
    # this file is the `uv run` entrypoint — exactly the case that reaches main().
    import typer

    use_utf8_console()

    prog = Path(sys.argv[0]).stem  # `lb` when invoked through the short PATH shim
    section_list = ", ".join(sorted(SECTIONS))

    # rich_markup_mode=None keeps `--help` plain click text: no box-drawing or
    # padding for a piped (agent) reader — the two-audience rule from the design doc.
    app = typer.Typer(
        help=DESCRIPTION,
        epilog=EPILOG,
        rich_markup_mode=None,
        no_args_is_help=False,
    )

    def _version(value: bool) -> None:
        if value:
            print(f"{prog} {__version__}")
            raise typer.Exit(0)

    @app.callback()
    def _root(
        version: bool = typer.Option(
            False,
            "--version",
            callback=_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ) -> None:
        pass

    start_opt = typer.Option(".", "--start", metavar="DIR", help=START_HELP)
    json_opt = typer.Option(False, "--json", help="Emit JSON.")
    registry_opt = typer.Option(
        DEFAULT_REGISTRY,
        "--registry",
        metavar="FILE",
        help=f"Personal repo registry (default: {DEFAULT_REGISTRY}).",
    )

    @app.command(help="One-shot dashboard: config, sections, sibling state, registry.")
    def status(
        start: str = start_opt,
        registry: str = registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_status(start, registry, json_out))

    @app.command(help="Create this project's config (never clobbers).")
    def init(
        sections: list[SectionName] = typer.Argument(
            None,
            metavar="SECTION",
            help=f"Section(s) to write: {section_list}. Omitted: detected from the repo layout.",
        ),
        start: str = start_opt,
        dry_run: bool = typer.Option(False, "--dry-run", help="Print the config; write nothing."),
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(
            cmd_init([s.value for s in sections or []], start, dry_run, json_out)
        )

    @app.command(help="Append section(s) to an existing config.")
    def add(
        sections: list[SectionName] = typer.Argument(
            ...,
            metavar="SECTION",
            help=f"Section(s) to add: {section_list}.",
        ),
        start: str = start_opt,
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Print what would be appended; write nothing."
        ),
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(
            cmd_add([s.value for s in sections], start, dry_run, json_out)
        )

    @app.command(help="Print the stored config, or one section's block, verbatim.")
    def show(
        section: str = typer.Argument(
            None,
            metavar="SECTION",
            help="Only this section (any table present in the config).",
        ),
        start: str = start_opt,
        json_out: bool = typer.Option(False, "--json", help="Emit JSON (parsed TOML)."),
    ) -> None:
        raise typer.Exit(cmd_show(section, start, json_out))

    def _toggle_command(verb: str, sense: str, value: bool) -> None:
        @app.command(name=verb, help=f"Set `enabled = {sense}` on a section, in place.")
        def _toggle(
            section: SectionName = typer.Argument(
                ...,
                metavar="SECTION",
                help=f"Section to {verb}: {section_list}.",
            ),
            start: str = start_opt,
            json_out: bool = json_opt,
        ) -> None:
            raise typer.Exit(cmd_toggle(section.value, start, json_out, value))

    _toggle_command("enable", "true", True)
    _toggle_command("disable", "false", False)

    repos_app = typer.Typer(rich_markup_mode=None)
    app.add_typer(
        repos_app, name="repos", help="Manage the personal repo registry (never clobbers a name)."
    )
    repos_registry_opt = typer.Option(
        DEFAULT_REGISTRY,
        "--registry",
        metavar="FILE",
        help=f"Registry file (default: {DEFAULT_REGISTRY}).",
    )

    @repos_app.command(name="list", help="Every registered name → path; dead paths marked.")
    def repos_list(
        registry: str = repos_registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_repos_list(registry, json_out))

    @repos_app.command(name="add", help="Register NAME → PATH (refuses an existing name).")
    def repos_add(
        name: str = typer.Argument(..., help="Logical repo name (a bare TOML key)."),
        path: str = typer.Argument(
            ..., help="Local path, ~-relative or absolute; stored as given."
        ),
        registry: str = repos_registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_repos_add(name, path, registry, json_out))

    @repos_app.command(name="rm", help="Unregister NAME.")
    def repos_rm(
        name: str = typer.Argument(..., help="Registered repo name — see `repos list`."),
        registry: str = repos_registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_repos_rm(name, registry, json_out))

    graph_app = typer.Typer(rich_markup_mode=None)
    app.add_typer(
        graph_app,
        name="graph",
        help="The cross-repo knowledge graph (~/.lightbridge/graph.toml): typed edges "
        "between registered repos, projected into each repo's session context.",
    )
    graph_opt = typer.Option(
        DEFAULT_GRAPH,
        "--graph",
        metavar="FILE",
        help=f"Graph file (default: {DEFAULT_GRAPH}).",
    )

    @graph_app.command(
        name="init", help="Seed the graph file with the types vocabulary (never clobbers)."
    )
    def graph_init(
        graph: str = graph_opt,
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Print the seeded document; write nothing."
        ),
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_graph_init(graph, dry_run, json_out))

    @graph_app.command(
        name="show", help="Whole-graph summary, or NAME's projected ego view (with backlinks)."
    )
    def graph_show(
        name: str = typer.Argument(
            None, metavar="NAME", help="A node (registered repo name); omitted: the summary."
        ),
        graph: str = graph_opt,
        registry: str = repos_registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_graph_show(name, graph, registry, json_out))

    @graph_app.command(
        name="types", help="The edge vocabulary: each type with its direction reading."
    )
    def graph_types(
        graph: str = graph_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_graph_types(graph, json_out))

    @app.command(
        help="Move/rename a repo (or parent dir) and repair all lightbridge bookkeeping. "
        "OLD exists: performs the move too; OLD gone: repairs after a manual move. "
        "Confirms on a TTY; spec: docs/lightbridge/lightbridge-mv.md."
    )
    def mv(
        old: str = typer.Argument(..., metavar="OLD", help="Current path (repo or parent dir)."),
        new: str = typer.Argument(..., metavar="NEW", help="Target path."),
        yes: bool = typer.Option(
            False,
            "--yes",
            help="Skip the confirmation prompt. Agents: pass this only when the human "
            "explicitly instructed this move.",
        ),
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Print the blast-radius plan; change nothing."
        ),
        state_dir: Path | None = typer.Option(
            None,
            "--state-dir",
            metavar="DIR",
            help=f"Projects state dir (default: ${STATE_DIR_ENV} or {DEFAULT_STATE_DIR}).",
        ),
        registry: str = registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(
            cmd_mv(
                old,
                new,
                yes=yes,
                dry_run=dry_run,
                json_out=json_out,
                state_dir=state_dir,
                registry_file=registry,
            )
        )

    @app.command(help="List the known config sections.")
    def sections(json_out: bool = json_opt) -> None:
        raise typer.Exit(cmd_sections(json_out))

    @app.command(help="Print this project's config path.")
    def path(start: str = start_opt, json_out: bool = json_opt) -> None:
        raise typer.Exit(cmd_path(start, json_out))

    @app.command(help="Audit the projects tree for rot.")
    def doctor(
        state_dir: Path | None = typer.Option(
            None,
            "--state-dir",
            metavar="DIR",
            help=f"Projects state dir (default: ${STATE_DIR_ENV} or {DEFAULT_STATE_DIR}).",
        ),
        registry: str = typer.Option(
            DEFAULT_REGISTRY,
            "--registry",
            metavar="FILE",
            help=f"Personal repo registry, scanned for legacy per-repo configs "
            f"(default: {DEFAULT_REGISTRY}).",
        ),
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_doctor(state_dir, registry, json_out))

    app(prog_name=prog)


if __name__ == "__main__":
    main()
