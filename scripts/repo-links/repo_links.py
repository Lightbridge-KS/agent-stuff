#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Project a repo's ego view from the central cross-repo graph.

Multi-repo work needs the agent to know its neighborhood: where the upstream
counterpart, the live test service, or the OSS reference clone lives on THIS
machine. Two user-level layers — nothing ever lives inside the repo:

  1. `~/.lightbridge/graph.toml` — the SSOT: typed edges between logical repo
     names, each declared ONCE. An edge A -> B carries a `type` (what B is to A);
     the graph's `[types]` table declares each type's `inverse` (what A is to B)
     and default `backlink` mode (full | compact | off). Spec: the repo-graph
     skill; managed with `lb graph`.
  2. `~/.lightbridge/repos.toml` — maps names to paths on this machine.

The repo at `--start` is matched to its registry name by path, then its incident
edges project into the map the SessionStart hook injects:

    Linked repos (.lightbridge graph):
    - <to> → /verified/path (<type>) — <from_note>        # outgoing edges
    Backlinks:
    - <from> → /verified/path (<inverse>) — <to_note>     # incoming, mode full
    Also referenced by: a (<inverse>), b (<inverse>)      # incoming, mode compact

Dead names, stale paths, and undeclared types surface as WARNING lines instead of
rotting silently. A leftover `[repo-links]` section in the project's lightbridge
config (pre-graph) earns a one-line deprecation warning.

    repo-links                       # human map for the repo at CWD
    repo-links --start path/to/repo  # another repo's map
    repo-links --json                # machine-readable (for hooks/tooling)
    repo-links --check               # audit mode: exit 1 if anything is rotten
    repo-links --graph alt.toml --registry alt-repos.toml

Exit codes: 0 on success (warnings included); 1 under --check when anything is
unresolved or warned; 2 when there is nothing to read (no graph on this machine,
repo not registered, no incident edges, or an unreadable graph).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

LIGHTBRIDGE = Path(__file__).resolve().parents[1] / "lightbridge" / "lb_resolve.py"
DEFAULT_REGISTRY = "~/.lightbridge/repos.toml"
DEFAULT_GRAPH = "~/.lightbridge/graph.toml"
REMINDER = (
    "When a task involves a linked repo, work with it at the absolute path above."
)


def load_lightbridge():
    """Import the lightbridge resolver from its file path (single source of truth)."""
    spec = importlib.util.spec_from_file_location("lightbridge", LIGHTBRIDGE)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def section_warning(config_path: Path) -> str:
    """The one deprecation line for a leftover pre-graph `[repo-links]` section."""
    return (
        f"WARNING — the [repo-links] section in {config_path} is no longer read: "
        f"the graph at {DEFAULT_GRAPH} replaced it. Migrate the links "
        f"(`lb graph link`, spec: the repo-graph skill) and delete the section."
    )


def node_for_root(root: Path, registry: dict[str, str]) -> str | None:
    """The registry name whose path is `root` — how a repo learns its own node name."""
    target = str(root.resolve())
    for name, raw in registry.items():
        try:
            if str(Path(raw).expanduser().resolve()) == target:
                return name
        except OSError:
            continue
    return None


def find_aliases(registry: dict, relevant: set[str] | None = None) -> list[str]:
    """
    Names that resolve to the SAME repo — an identity split, and invisible without this check.

    Both names resolve, so nothing ever errors; the registry just quietly says one repo is
    two. That breaks any cross-referencing keyed on the name — a graph edge declared against
    one spelling will not match the other, even though they are the same clone. `relevant`
    scopes the report to alias groups touching the names this repo's view actually uses.
    """
    by_path: dict[str, list[str]] = {}
    for name, raw in registry.items():
        if not isinstance(raw, str):
            continue
        try:
            resolved = str(Path(raw).expanduser().resolve())
        except OSError:
            continue
        by_path.setdefault(resolved, []).append(name)

    warnings: list[str] = []
    for path, names in sorted(by_path.items()):
        if len(names) < 2:
            continue
        if relevant is not None and not relevant.intersection(names):
            continue
        warnings.append(
            f"registry aliases: {', '.join(sorted(names))} all resolve to {path} — "
            f"pick one canonical name; the rest split that repo's identity"
        )
    return warnings


def resolve_name(
    name: str, registry: dict[str, str], registry_display: str = DEFAULT_REGISTRY
) -> dict:
    """One name → `{path, status, detail}`, path verified on disk.

    `status`: ok | unregistered | relative-path | missing | not-a-dir. Paths are
    expanded but NOT resolve()d — a symlinked path renders as the user wrote it;
    is_dir() follows symlinks.
    """
    raw = registry.get(name)
    if not isinstance(raw, str) or not raw.strip():
        return {
            "path": None,
            "status": "unregistered",
            "detail": f"not registered in {registry_display} "
            f"(add it there: `lb repos add {name} PATH`)",
        }
    path = Path(raw).expanduser()
    if not path.is_absolute():
        return {
            "path": str(path),
            "status": "relative-path",
            "detail": f"registered path '{raw}' is not absolute",
        }
    if not path.exists():
        return {
            "path": str(path),
            "status": "missing",
            "detail": f"registered path {path} does not exist (stale registry entry?)",
        }
    if not path.is_dir():
        return {
            "path": str(path),
            "status": "not-a-dir",
            "detail": f"registered path {path} is not a directory",
        }
    return {"path": str(path), "status": "ok", "detail": None}


def build_view(
    graph: dict,
    node: str,
    registry: dict[str, str],
    lb,
    registry_display: str = DEFAULT_REGISTRY,
) -> dict:
    """The node's projected, path-verified view plus its warning stream.

    Projection semantics (out / backlinks / mentions, inverse labels, backlink
    modes and per-edge overrides) come from `lb_resolve.project_node` — the one
    implementation the `lb graph` verbs share. This adds what injection needs:
    verified paths for the full-line tiers and the rot warnings. Compact mentions
    stay names-only by design — low salience, no path to verify.
    """
    projection = lb.project_node(graph, node)
    warnings: list[str] = []
    if graph.get("skipped"):
        warnings.append(
            f"{graph['skipped']} malformed edge block(s) in the graph — run `lb graph doctor`"
        )
    for group in ("out", "backlinks"):
        for entry in projection[group]:
            entry.update(resolve_name(entry["other"], registry, registry_display))
            if not entry.pop("declared"):
                warnings.append(
                    f"edge type '{entry['type']}' is not declared in the graph's [types] — "
                    f"run `lb graph doctor`"
                )
    for entry in projection["mentions"]:
        entry.pop("declared")
    incident = {node} | {
        e["other"] for group in projection.values() for e in group
    }
    warnings.extend(find_aliases(registry, relevant=incident))
    return {**projection, "warnings": sorted(set(warnings))}


def render_human(view: dict, registry_error: str | None = None) -> str:
    """Render the linked-repos map: full tiers, one compact line, WARNING lines.

    A registry-wide error collapses the map to a single warning line — per-link
    state is unknowable without a readable registry.
    """
    header = "Linked repos (.lightbridge graph):"
    if registry_error is not None:
        return f"{header} WARNING — the repo registry is {registry_error}; links not resolved."

    def link_line(entry: dict) -> str:
        if entry["status"] == "ok":
            line = f"- {entry['other']} → {entry['path']} ({entry['label']})"
            if entry["note"]:
                line += f" — {entry['note']}"
            return line
        return f"- {entry['other']}: WARNING — {entry['detail']}"

    lines = [header] + [link_line(e) for e in view["out"]]
    if view["backlinks"]:
        lines.append("Backlinks:")
        lines += [link_line(e) for e in view["backlinks"]]
    if view["mentions"]:
        mentions = ", ".join(f"{m['other']} ({m['label']})" for m in view["mentions"])
        lines.append(f"Also referenced by: {mentions}")
    for warning in view["warnings"]:
        lines.append(f"- WARNING — {warning}")
    if any(e["status"] == "ok" for e in view["out"] + view["backlinks"]):
        lines += ["", REMINDER]
    return "\n".join(lines)


def has_problems(view: dict, registry_error: str | None) -> bool:
    """What `--check` fails on: any unresolved link or any warning."""
    return (
        registry_error is not None
        or bool(view["warnings"])
        or any(e["status"] != "ok" for e in view["out"] + view["backlinks"])
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="repo-links",
        description="Project a repo's cross-repo ego view from the central graph, "
        "with verified local paths.",
    )
    parser.add_argument(
        "--start",
        default=".",
        help="Directory whose project root (git toplevel) is matched to its "
        "registry name (default: CWD).",
    )
    parser.add_argument(
        "--graph",
        default=DEFAULT_GRAPH,
        help=f"Cross-repo graph file (default: {DEFAULT_GRAPH}).",
    )
    parser.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY,
        help=f"Personal name→path registry (default: {DEFAULT_REGISTRY}).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human text."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Audit mode: exit 1 when anything in this repo's view is unresolved "
        "or warned.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    start = Path(args.start).expanduser().resolve()

    lb = load_lightbridge()
    if lb is None:
        print(f"repo-links: resolver not found at {LIGHTBRIDGE}.", file=sys.stderr)
        return 2
    lb.use_utf8_console()  # CLI-only: the hook importing this module owns its stdout

    # Deprecation nudges — never fatal for the CLI.
    legacy = lb.legacy_config(start)
    if legacy is not None:
        print(lb.legacy_warning(legacy), file=sys.stderr)
    config, config_path, _config_error = lb.load_config(start)
    if isinstance(config, dict) and isinstance(config.get("repo-links"), dict):
        print(section_warning(config_path), file=sys.stderr)

    graph_path = Path(args.graph).expanduser()
    graph, graph_error = lb.load_graph(graph_path)
    if graph is None and graph_error is None:
        print(
            f"repo-links: no graph at {graph_path} — this machine has not opted in. "
            f"Seed one: `lb graph init` (spec: the repo-graph skill).",
            file=sys.stderr,
        )
        return 2
    if graph_error is not None:
        print(f"repo-links: graph {graph_path} is {graph_error}", file=sys.stderr)
        return 2

    registry_path = Path(args.registry).expanduser()
    registry, registry_error = lb.load_registry(registry_path)
    if registry is None and registry_error is None:
        print(
            f"repo-links: the graph exists but there is no registry at {registry_path} — "
            f"names cannot resolve to paths. Create it: `lb repos add NAME PATH`.",
            file=sys.stderr,
        )
        return 2

    root = lb.repo_root(start)
    node = None if registry is None else node_for_root(root, registry)
    if registry is not None and node is None:
        print(
            f"repo-links: {root} is not in {registry_path} — this repo has no node "
            f"name. Register it (`lb repos add NAME {root}`), then link it "
            f"(`lb graph link`).",
            file=sys.stderr,
        )
        return 2

    if registry is not None:
        view = build_view(graph, node, registry, lb, registry_display=args.registry)
        if not (view["out"] or view["backlinks"] or view["mentions"]):
            print(
                f"repo-links: no edges touch '{node}' in {graph_path} — link one: "
                f"`lb graph link {node} OTHER --type T`.",
                file=sys.stderr,
            )
            return 2
    else:  # registry unreadable — per-link state is unknowable
        view = {"out": [], "backlinks": [], "mentions": [], "warnings": []}

    if args.json:
        print(
            json.dumps(
                {
                    "graph": str(graph_path),
                    "registry": str(registry_path),
                    "registry_error": registry_error,
                    "root": str(root),
                    "node": node,
                    **view,
                },
                indent=2,
            )
        )
    else:
        print(render_human(view, registry_error))

    if args.check and has_problems(view, registry_error):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
