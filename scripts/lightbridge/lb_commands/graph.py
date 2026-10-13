"""Graph command handlers; document operations remain owned by lb_graph."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lb_graph import (
    GRAPH_HEADER,
    SEED_TYPE_NAMES,
    SEED_TYPES_BLOCK,
    append_edge,
    audit,
    edge_fields,
    edge_sentence,
    find_edge_spans,
    html_text,
    mermaid_text,
    remove_span,
    set_edge_key,
)
from lb_resolve import load_graph, load_registry, project_node
from lb_style import paint, row

from .repos import open_registry

# ── graph ───────────────────────────────────────────────────────────────────


def _open_graph(graph_file: str) -> tuple[dict | None, Path, str | None]:
    """The shared graph preamble: expanded path + parsed graph (or its error)."""
    graph_path = Path(graph_file).expanduser()
    graph, error = load_graph(graph_path)
    if error is not None:
        print(f"graph is unusable: {graph_path}\n{error}", file=sys.stderr)
    return graph, graph_path, error


def _node_path(name: str, repos: dict[str, str] | None) -> str | None:
    """A node's registered path (as written, tilde-expanded), or None."""
    raw = (repos or {}).get(name)
    return str(Path(raw).expanduser()) if raw else None


def cmd_graph_init(graph_file: str, dry_run: bool, json_out: bool) -> int:
    graph_path = Path(graph_file).expanduser()
    if graph_path.is_file():
        print(
            f"graph already exists: {graph_path}\n"
            f"`graph init` never clobbers — edit the file, or use `graph link`.",
            file=sys.stderr,
        )
        return 1
    text = GRAPH_HEADER + "\n" + SEED_TYPES_BLOCK
    if dry_run:
        print(text, end="")
        return 0
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(text, encoding="utf-8")
    if json_out:
        print(
            json.dumps(
                {"graph": str(graph_path), "created": True, "types": SEED_TYPE_NAMES},
                indent=2,
            )
        )
        return 0
    print(row("created", str(graph_path)))
    print(
        row(
            "types",
            f"{len(SEED_TYPE_NAMES)} seeded — the file owns the vocabulary from here",
        )
    )
    print(row("next", "graph link FROM TO --type T  (names from `repos list`)"))
    return 0


def cmd_graph_types(graph_file: str, json_out: bool) -> int:
    graph, graph_path, error = _open_graph(graph_file)
    if error is not None:
        return 1
    if graph is None:
        print(f"no graph: {graph_path}\nCreate it: `graph init`.", file=sys.stderr)
        return 1
    types = graph["types"]
    if json_out:
        print(json.dumps({"graph": str(graph_path), "types": types}, indent=2))
        return 0
    if not types:
        print(
            f"{graph_path}: no [types] declared  (seed a vocabulary: `graph init` on a fresh file)"
        )
        return 0
    width = max(len(name) for name in types)
    for name, spec in types.items():
        inverse = spec.get("inverse") if isinstance(spec.get("inverse"), str) else "?"
        mode = spec.get("backlink") if isinstance(spec.get("backlink"), str) else "?"
        print(
            f"{name:<{width}}  A -[{name}]-> B: B is A's {name}; "
            f"B sees A as ({inverse}); backlink {mode}"
        )
    return 0


def cmd_graph_show(
    name: str | None, graph_file: str, registry_file: str, json_out: bool
) -> int:
    graph, graph_path, error = _open_graph(graph_file)
    if error is not None:
        return 1
    if graph is None:
        print(f"no graph: {graph_path}\nCreate it: `graph init`.", file=sys.stderr)
        return 1
    repos, _ = load_registry(Path(registry_file).expanduser())
    edges = graph["edges"]
    nodes = sorted({e["from"] for e in edges} | {e["to"] for e in edges})

    if name is None:
        by_type: dict[str, int] = {}
        for edge in edges:
            by_type[edge["type"]] = by_type.get(edge["type"], 0) + 1
        if json_out:
            print(
                json.dumps(
                    {
                        "graph": str(graph_path),
                        "types": len(graph["types"]),
                        "nodes": nodes,
                        "edges": len(edges),
                        "by_type": dict(sorted(by_type.items())),
                        "skipped": graph["skipped"],
                    },
                    indent=2,
                )
            )
            return 0
        print(row("graph", str(graph_path)))
        print(row("types", str(len(graph["types"]))))
        print(row("nodes", str(len(nodes))))
        breakdown = ", ".join(f"{t} {n}" for t, n in sorted(by_type.items()))
        print(row("edges", f"{len(edges)}" + (f"  ({breakdown})" if breakdown else "")))
        if graph["skipped"]:
            print(
                row(
                    "skipped",
                    f"{graph['skipped']} malformed edge block(s) — run `graph doctor`",
                )
            )
        return 0

    if name not in nodes:
        print(
            f"'{name}' has no edges in {graph_path}\n"
            f"Nodes: {', '.join(nodes) if nodes else '(none)'} — or link one: `graph link`.",
            file=sys.stderr,
        )
        return 1
    projection = project_node(graph, name)
    if json_out:
        enriched = {
            group: [
                {**entry, "path": _node_path(entry["other"], repos)}
                for entry in entries
            ]
            for group, entries in projection.items()
        }
        print(
            json.dumps({"graph": str(graph_path), "node": name, **enriched}, indent=2)
        )
        return 0

    print(row("node", f"{name} → {_node_path(name, repos) or '(not in repos.toml)'}"))
    for entry in projection["out"]:
        path = _node_path(entry["other"], repos) or "(not in repos.toml)"
        line = f"- {entry['other']} → {path} ({entry['label']})"
        if entry["note"]:
            line += f" — {entry['note']}"
        print(line)
    if projection["backlinks"]:
        print("Backlinks:")
        for entry in projection["backlinks"]:
            path = _node_path(entry["other"], repos) or "(not in repos.toml)"
            line = f"- {entry['other']} → {path} ({entry['label']})"
            if entry["note"]:
                line += f" — {entry['note']}"
            print(line)
    if projection["mentions"]:
        mentions = ", ".join(
            f"{m['other']} ({m['label']})" for m in projection["mentions"]
        )
        print(f"Also referenced by: {mentions}")
    return 0


def _graph_write_preamble(
    graph_file: str,
) -> tuple[dict | None, Path | None, int | None]:
    """Shared open-for-writing checks: (graph, path, refusal-exit-code)."""
    graph, graph_path, error = _open_graph(graph_file)
    if error is not None:
        return None, graph_path, 1
    if graph is None:
        print(f"no graph: {graph_path}\nCreate it: `graph init`.", file=sys.stderr)
        return None, graph_path, 1
    return graph, graph_path, None


def _edge_json(graph_path: Path, action: str, edge: dict) -> str:
    """The one JSON shape every graph write verb prints."""
    return json.dumps(
        {"graph": str(graph_path), "action": action, "edge": edge}, indent=2
    )


def cmd_graph_link(
    frm: str,
    to: str,
    etype: str,
    from_note: str | None,
    to_note: str | None,
    backlink: str | None,
    graph_file: str,
    registry_file: str,
    json_out: bool,
) -> int:
    graph, graph_path, refused = _graph_write_preamble(graph_file)
    if refused is not None:
        return refused

    repos, registry, reg_error = open_registry(registry_file)
    if reg_error is not None:
        return 1
    if repos is None:
        print(
            f"no registry: {registry} — edge endpoints must be registered names.\n"
            f"Create it: `repos add NAME PATH`.",
            file=sys.stderr,
        )
        return 1
    for name in (frm, to):
        if name not in repos:
            print(
                f"{name!r} is not registered in {registry} — edges connect registered "
                f"names.\nRegister it first: `repos add {name} PATH`.",
                file=sys.stderr,
            )
            return 1
    if etype not in graph["types"]:
        declared = ", ".join(graph["types"]) or "(none)"
        print(
            f"type {etype!r} is not declared in {graph_path}'s [types].\n"
            f"Declared: {declared}. See `graph types`; add new types in the file.",
            file=sys.stderr,
        )
        return 1

    edge = {
        "from": frm,
        "to": to,
        "type": etype,
        "from_note": from_note or None,
        "to_note": to_note or None,
        "backlink": backlink or None,
    }
    for existing in graph["edges"]:
        if (existing["from"], existing["to"], existing["type"]) == (frm, to, etype):
            if existing == edge:
                if json_out:
                    print(_edge_json(graph_path, "unchanged", edge))
                else:
                    print(row("unchanged", f"{frm} -[{etype}]-> {to} already declared"))
                return 0
            print(
                f"{frm} -[{etype}]-> {to} exists with different notes/backlink.\n"
                f"Edit it: `graph set {frm} {to} --type {etype} ...`.",
                file=sys.stderr,
            )
            return 1
        if (existing["from"], existing["to"], existing["type"]) == (to, frm, etype):
            print(
                f"the REVERSED edge {to} -[{etype}]-> {frm} already exists — one edge "
                f"covers both directions (the inverse projects automatically).\n"
                f"If the direction is wrong there, `graph unlink {to} {frm} --type {etype}` "
                f"first.",
                file=sys.stderr,
            )
            return 1
    parallel = [e["type"] for e in graph["edges"] if {e["from"], e["to"]} == {frm, to}]
    if parallel:
        print(
            f"note: {frm} and {to} are already linked as {', '.join(sorted(parallel))} — "
            f"adding a parallel {etype} edge.",
            file=sys.stderr,
        )

    text = graph_path.read_text(encoding="utf-8")
    graph_path.write_text(append_edge(text, edge), encoding="utf-8")

    if json_out:
        print(_edge_json(graph_path, "linked", edge))
        return 0
    print(row("updated", str(graph_path)))
    print(row("linked", edge_sentence(edge, graph["types"])))
    return 0


def cmd_graph_unlink(
    frm: str, to: str, etype: str | None, graph_file: str, json_out: bool
) -> int:
    graph, graph_path, refused = _graph_write_preamble(graph_file)
    if refused is not None:
        return refused

    text = graph_path.read_text(encoding="utf-8")
    spans = find_edge_spans(text, frm, to, etype)
    if not spans:
        reversed_types = sorted(
            e["type"] for e in graph["edges"] if (e["from"], e["to"]) == (to, frm)
        )
        if reversed_types:
            print(
                f"note: no {frm} -> {to} edge, but the reverse direction exists "
                f"({to} -[{', '.join(reversed_types)}]-> {frm}) — swap the arguments "
                f"if that is the one to remove.",
                file=sys.stderr,
            )
        if json_out:
            print(
                _edge_json(
                    graph_path, "unchanged", {"from": frm, "to": to, "type": etype}
                )
            )
        else:
            print(row("unchanged", f"no {frm} -> {to} edge — nothing to do"))
        return 0
    matched_types = sorted(
        {e["type"] for e in graph["edges"] if (e["from"], e["to"]) == (frm, to)}
    )
    if len(spans) > 1 and etype is None:
        print(
            f"{frm} -> {to} has {len(spans)} parallel edges: {', '.join(matched_types)}.\n"
            f"Pass --type to pick one.",
            file=sys.stderr,
        )
        return 1
    for span in reversed(spans):
        text = remove_span(text, span)
    graph_path.write_text(text, encoding="utf-8")

    removed = etype or matched_types[0]
    if json_out:
        print(
            _edge_json(graph_path, "unlinked", {"from": frm, "to": to, "type": removed})
        )
        return 0
    print(row("updated", str(graph_path)))
    print(row("unlinked", f"{frm} -[{removed}]-> {to}"))
    return 0


def cmd_graph_set(
    frm: str,
    to: str,
    etype: str | None,
    from_note: str | None,
    to_note: str | None,
    backlink: str | None,
    graph_file: str,
    json_out: bool,
) -> int:
    if from_note is None and to_note is None and backlink is None:
        print(
            "nothing to set — pass --from-note, --to-note, and/or --backlink "
            "(empty string / `default` clears).",
            file=sys.stderr,
        )
        return 2
    graph, graph_path, refused = _graph_write_preamble(graph_file)
    if refused is not None:
        return refused

    text = graph_path.read_text(encoding="utf-8")
    spans = find_edge_spans(text, frm, to, etype)
    if not spans:
        print(
            f"no {frm} -> {to} edge"
            + (f" of type {etype!r}" if etype else "")
            + f" in {graph_path}.\nCreate it: `graph link {frm} {to} --type T`.",
            file=sys.stderr,
        )
        return 1
    if len(spans) > 1:
        types = sorted(
            {e["type"] for e in graph["edges"] if (e["from"], e["to"]) == (frm, to)}
        )
        print(
            f"{frm} -> {to} has {len(spans)} parallel edges: {', '.join(types)}.\n"
            f"Pass --type to pick one.",
            file=sys.stderr,
        )
        return 1

    changes = {
        "from_note": from_note,
        "to_note": to_note,
        # `default` clears the per-edge override, falling back to the type's mode.
        "backlink": None if backlink == "default" else backlink,
    }
    for key, value in changes.items():
        if (key == "backlink" and backlink is None) or (
            key != "backlink" and changes[key] is None
        ):
            continue
        span = find_edge_spans(text, frm, to, etype)[0]
        text = set_edge_key(text, span, key, value or None)
    graph_path.write_text(text, encoding="utf-8")

    span = find_edge_spans(text, frm, to, etype)[0]
    edge = edge_fields(text, span)
    if json_out:
        print(_edge_json(graph_path, "updated", edge))
        return 0
    print(row("updated", str(graph_path)))
    print(row("edge", edge_sentence(edge, graph["types"])))
    return 0


def cmd_graph_doctor(graph_file: str, registry_file: str, json_out: bool) -> int:
    graph, graph_path, refused = _graph_write_preamble(graph_file)
    if refused is not None:
        return refused
    registry = Path(registry_file).expanduser()
    repos, reg_error = load_registry(registry)
    problems = audit(graph, repos)
    if reg_error is not None:
        problems.insert(
            0, {"kind": "bad-registry", "subject": str(registry), "detail": reg_error}
        )
    if json_out:
        print(json.dumps({"graph": str(graph_path), "problems": problems}, indent=2))
    elif not problems:
        print(f"graph doctor: {graph_path} — {paint('no problems.', 'ok')}")
    else:
        print(
            f"graph doctor: {paint(f'{len(problems)} problem(s)', 'bad')} in {graph_path}:"
        )
        for problem in problems:
            kind = paint(f"[{problem['kind']}]", "warn")
            print(f"- {kind} {problem['subject']}: {problem['detail']}")
    return 1 if problems else 0


def cmd_graph_mermaid(graph_file: str, registry_file: str, json_out: bool) -> int:
    graph, graph_path, refused = _graph_write_preamble(graph_file)
    if refused is not None:
        return refused
    repos, _ = load_registry(Path(registry_file).expanduser())
    text = mermaid_text(graph, repos)
    if json_out:
        print(json.dumps({"graph": str(graph_path), "mermaid": text}, indent=2))
    else:
        print(text, end="")
    return 0


def cmd_graph_html(
    graph_file: str, registry_file: str, out_file: str, json_out: bool
) -> int:
    graph, graph_path, refused = _graph_write_preamble(graph_file)
    if refused is not None:
        return refused
    out = Path(out_file).expanduser()
    if out.exists():
        print(
            f"{out} already exists — this verb never clobbers; delete it first.",
            file=sys.stderr,
        )
        return 1
    repos, _ = load_registry(Path(registry_file).expanduser())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text(graph, repos), encoding="utf-8")
    edges = len(graph["edges"])
    nodes = len({e["from"] for e in graph["edges"]} | {e["to"] for e in graph["edges"]})
    if json_out:
        print(
            json.dumps(
                {
                    "graph": str(graph_path),
                    "out": str(out),
                    "nodes": nodes,
                    "edges": edges,
                },
                indent=2,
            )
        )
        return 0
    print(row("created", str(out)))
    print(row("graph", f"{nodes} node(s), {edges} edge(s) — open it in a browser"))
    return 0
