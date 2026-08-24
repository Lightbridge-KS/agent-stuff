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
    lightbridge graph link A B --type upstream   # declare one edge (reverse auto-projects)
    lightbridge graph unlink A B     # remove an edge (`--type` when parallel edges exist)
    lightbridge graph set A B --from-note "..."  # edit one edge in place
    lightbridge graph doctor         # audit the graph; exit 1 on problems
    lightbridge graph mermaid        # flowchart of the whole graph, to stdout
    lightbridge graph html --out g.html          # self-contained interactive viz
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
    cmd_graph_doctor,
    cmd_graph_html,
    cmd_graph_init,
    cmd_graph_link,
    cmd_graph_mermaid,
    cmd_graph_set,
    cmd_graph_show,
    cmd_graph_types,
    cmd_graph_unlink,
    cmd_init,
    cmd_key_add,
    cmd_key_doctor,
    cmd_key_ls,
    cmd_key_rm,
    cmd_key_run,
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
from lb_graph import BacklinkMode, BacklinkSetting
from lb_keys import DEFAULT_KEYS, DEFAULT_SECRETS
from lb_resolve import (
    DEFAULT_GRAPH,
    DEFAULT_REGISTRY,
    DEFAULT_STATE_DIR,
    STATE_DIR_ENV,
    use_utf8_console,
)

__version__ = "0.6.0"

DESCRIPTION = (
    "Create, inspect, and audit user-level .lightbridge project config "
    "— plus the personal repo registry."
)
EPILOG = (
    "Exit: 0 ok · 1 refused (doctor problems, would clobber, missing "
    "config/section/name, unreadable file) · 2 usage. "
    "Siblings (own their state, not wrapped here): plan_store.py (plans/), "
    "handoff.py (handoffs/), repo_links.py (graph.toml ego-view projection; "
    "spec: the repo-graph skill), docs-index ([docs-index] rendering). "
    "Spec: the lightbridge-config skill."
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

    @app.command(
        help="One-shot dashboard: config, sections, sibling state, registry, graph, keys."
    )
    def status(
        start: str = start_opt,
        registry: str = registry_opt,
        graph: str = typer.Option(
            DEFAULT_GRAPH,
            "--graph",
            metavar="FILE",
            help=f"Cross-repo graph file (default: {DEFAULT_GRAPH}).",
        ),
        keys: str = typer.Option(
            DEFAULT_KEYS,
            "--keys",
            metavar="FILE",
            help=f"LLM key catalog (default: {DEFAULT_KEYS}).",
        ),
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_status(start, registry, json_out, graph, keys))

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

    from_arg = typer.Argument(..., metavar="FROM", help="Edge source (a registered repo name).")
    to_arg = typer.Argument(..., metavar="TO", help="Edge target (a registered repo name).")

    @graph_app.command(
        name="link",
        help="Declare FROM -[TYPE]-> TO once — the reverse direction projects "
        "automatically as the type's inverse. Echoes the direction so a swapped "
        "edge is caught on sight.",
    )
    def graph_link(
        frm: str = from_arg,
        to: str = to_arg,
        etype: str = typer.Option(
            ..., "--type", metavar="TYPE", help="Edge type — see `graph types`."
        ),
        from_note: str = typer.Option(
            None, "--from-note", metavar="TEXT", help="Why TO matters when working in FROM."
        ),
        to_note: str = typer.Option(
            None, "--to-note", metavar="TEXT", help="Why FROM matters when working in TO."
        ),
        backlink: BacklinkMode = typer.Option(
            None,
            "--backlink",
            help="Per-edge override of the type's backlink mode.",
        ),
        graph: str = graph_opt,
        registry: str = repos_registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(
            cmd_graph_link(
                frm, to, etype, from_note, to_note,
                backlink.value if backlink else None,
                graph, registry, json_out,
            )
        )

    @graph_app.command(
        name="unlink", help="Remove the FROM -> TO edge (its block only; the rest is untouched)."
    )
    def graph_unlink(
        frm: str = from_arg,
        to: str = to_arg,
        etype: str = typer.Option(
            None, "--type", metavar="TYPE", help="Required when parallel edges exist."
        ),
        graph: str = graph_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_graph_unlink(frm, to, etype, graph, json_out))

    @graph_app.command(
        name="set",
        help="Edit one existing edge's notes or backlink override in place. "
        "An empty-string note clears it; `--backlink default` clears the override.",
    )
    def graph_set(
        frm: str = from_arg,
        to: str = to_arg,
        etype: str = typer.Option(
            None, "--type", metavar="TYPE", help="Required when parallel edges exist."
        ),
        from_note: str = typer.Option(
            None, "--from-note", metavar="TEXT", help="Replace FROM's note ('' clears)."
        ),
        to_note: str = typer.Option(
            None, "--to-note", metavar="TEXT", help="Replace TO's note ('' clears)."
        ),
        backlink: BacklinkSetting = typer.Option(
            None, "--backlink", help="Override mode, or `default` to clear the override."
        ),
        graph: str = graph_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(
            cmd_graph_set(
                frm, to, etype, from_note, to_note,
                backlink.value if backlink else None,
                graph, json_out,
            )
        )

    @graph_app.command(name="doctor", help="Audit the graph for rot; exit 1 on problems.")
    def graph_doctor(
        graph: str = graph_opt,
        registry: str = repos_registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_graph_doctor(graph, registry, json_out))

    @graph_app.command(
        name="mermaid", help="A flowchart of the whole graph (Mermaid, to stdout)."
    )
    def graph_mermaid(
        graph: str = graph_opt,
        registry: str = repos_registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_graph_mermaid(graph, registry, json_out))

    @graph_app.command(
        name="html",
        help="Write the self-contained interactive graph page (never clobbers OUT).",
    )
    def graph_html(
        out: str = typer.Option(..., "--out", metavar="FILE", help="Output HTML path."),
        graph: str = graph_opt,
        registry: str = repos_registry_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_graph_html(graph, registry, out, json_out))

    key_app = typer.Typer(rich_markup_mode=None)
    app.add_typer(
        key_app,
        name="key",
        help="Personal LLM API keys: agent-readable catalog (keys.toml) + values "
        "(secrets.toml) that are only ever injected into a child process by `key run` "
        "— no verb prints a value, and there is no `key get`.",
    )
    keys_opt = typer.Option(
        DEFAULT_KEYS,
        "--keys",
        metavar="FILE",
        help=f"Key catalog (default: {DEFAULT_KEYS}).",
    )
    secrets_opt = typer.Option(
        DEFAULT_SECRETS,
        "--secrets",
        metavar="FILE",
        help=f"Secret values file (default: {DEFAULT_SECRETS}).",
    )

    @key_app.command(name="ls", help="The catalog: name, provider, env var, scope — never values.")
    def key_ls(
        keys: str = keys_opt,
        secrets: str = secrets_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_key_ls(keys, secrets, json_out))

    @key_app.command(
        name="add",
        help="Catalogue NAME and store its value (hidden prompt on a TTY; piped stdin "
        "otherwise, e.g. `pbpaste | lb key add ...`). Refuses an existing name — "
        "`key rm` first; that is how you rotate.",
    )
    def key_add(
        name: str = typer.Argument(
            ..., metavar="NAME", help="Per-scope key name, e.g. openai-image-gen."
        ),
        provider: str = typer.Option(
            ..., "--provider", metavar="P", help="Who issued it (openai, anthropic, ...)."
        ),
        env: str = typer.Option(
            ..., "--env", metavar="VAR", help="Env var `key run` injects, e.g. OPENAI_API_KEY."
        ),
        scope: str = typer.Option(
            ..., "--scope", metavar="TEXT", help="One line: what this key is FOR."
        ),
        keys: str = keys_opt,
        secrets: str = secrets_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_key_add(name, provider, env, scope, keys, secrets, json_out))

    @key_app.command(
        name="run",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
        help="Inject NAME's value(s) as env var(s) and exec CMD — the `--` is required. "
        "The child's exit code passes through; 127 means the exec itself failed.",
    )
    def key_run(
        names: str = typer.Argument(
            ...,
            metavar="NAME[,NAME...]",
            help="Catalogued name(s); comma-separated to inject several.",
        ),
        cmd: list[str] = typer.Argument(None, metavar="CMD..."),
        keys: str = keys_opt,
        secrets: str = secrets_opt,
    ) -> None:
        # The `--` is mandatory so lb can never steal the child's flags; everything
        # after the first `--` reaches `cmd` verbatim (a second `--` survives).
        # sys.argv is entrypoint-only global access — this file is never imported.
        if "--" not in sys.argv:
            print(
                "usage: lb key run NAME[,NAME...] -- CMD...\n"
                "The `--` is required — everything after it is the child command.",
                file=sys.stderr,
            )
            raise typer.Exit(2)
        raise typer.Exit(cmd_key_run(names, cmd or [], keys, secrets))

    @key_app.command(name="rm", help="Remove NAME from the catalog and its stored value.")
    def key_rm(
        name: str = typer.Argument(..., metavar="NAME", help="Catalogued name — see `key ls`."),
        keys: str = keys_opt,
        secrets: str = secrets_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_key_rm(name, keys, secrets, json_out))

    @key_app.command(
        name="doctor",
        help="Audit the catalog/values pair for rot (valueless entries, orphan values, "
        "loose file mode); exit 1 on problems.",
    )
    def key_doctor(
        keys: str = keys_opt,
        secrets: str = secrets_opt,
        json_out: bool = json_opt,
    ) -> None:
        raise typer.Exit(cmd_key_doctor(keys, secrets, json_out))

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
