"""The verb handlers — one `cmd_*` per CLI verb.

Each takes plain values (never Typer objects), prints the human or `--json` rendering, and
returns the exit code. Keeping them Typer-free is what lets the tests drive every verb
in-process as well as through the real subprocess.

Exit codes: 0 ok (incl. an idempotent no-op); 1 refused (`doctor` found problems or the
config/section/registry entry a verb needs is absent, would clobber, or is unreadable);
2 usage (raised by the parser in `lightbridge.py`, not here).
"""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

import lb_tomledit
from lb_catalog import (
    SECTIONS,
    append_sections,
    describe,
    detect_sections,
    present_sections,
    render_config,
)
from lb_doctor import doctor
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
from lb_keys import (
    ENV_NAME,
    KEY_NAME,
    KEYS_HEADER,
    SECRETS_HEADER,
    append_key,
    append_secret,
    load_keys,
    load_secret_names,
    load_secrets,
    remove_key,
    remove_secret,
    write_secrets,
)
from lb_mv import apply_mv, plan_mv
from lb_registry import REGISTRY_HEADER, REPO_NAME, append_repo, remove_repo
from lb_resolve import (
    DEFAULT_GRAPH,
    DEFAULT_REGISTRY,
    config_path,
    load_graph,
    load_registry,
    default_state_dir,
    legacy_config,
    legacy_warning,
    load_config,
    project_key,
    project_node,
    repo_root,
)

# ── rendering helpers ───────────────────────────────────────────────────────


def row(label: str, value: str) -> str:
    """One `label   value` line — every bootstrap label fits the same column."""
    return f"{label:<9} {value}"


def project_fields(root: Path, path: Path) -> dict:
    """The `{root, key, config}` preamble every project-scoped JSON shape opens with.

    One helper rather than four literals: `init`/`add`, `enable`/`disable`, `status`, and
    `path` all identify the same project the same way, so a caller can read the first
    three keys without knowing which verb produced them.
    """
    return {"root": str(root), "key": project_key(root), "config": str(path)}


def bootstrap_json(
    root: Path,
    path: Path,
    *,
    created: bool,
    added: list[str],
    skipped: list[str],
    detected: list[str],
) -> str:
    """One JSON shape for both `init` and `add`, so a caller never branches on the verb."""
    return json.dumps(
        {
            **project_fields(root, path),
            "created": created,
            "sections_added": added,
            "sections_skipped": skipped,
            "detected": detected,
        },
        indent=2,
    )


def _refuse_missing(config: dict | None, path: Path, error: str | None) -> int | None:
    """The shared show/enable/disable refusals; None when the config is usable."""
    if error is not None:
        print(f"config is unreadable: {path}\n{error}", file=sys.stderr)
        return 1
    if config is None:
        print(f"no config for this project: {path}\nRun `init` first.", file=sys.stderr)
        return 1
    return None


def _open_registry(registry_file: str) -> tuple[dict[str, str] | None, Path, str | None]:
    """The shared repos preamble: expanded path + parsed registry (or its error)."""
    registry = Path(registry_file).expanduser()
    repos, error = load_registry(registry)
    if error is not None:
        print(f"registry is unusable: {registry}\n{error}", file=sys.stderr)
    return repos, registry, error


# ── catalog ─────────────────────────────────────────────────────────────────


def cmd_sections(json_out: bool) -> int:
    if json_out:
        print(json.dumps(SECTIONS, indent=2))
        return 0
    width = max(len(name) for name in SECTIONS)
    for name, meta in SECTIONS.items():
        print(f"{name:<{width}}  {meta['purpose']}")
        print(f"{'':<{width}}  → read by {meta['reader']}")
    return 0


# ── bootstrap ───────────────────────────────────────────────────────────────


def cmd_init(sections: list[str], start_dir: str, dry_run: bool, json_out: bool) -> int:
    start = Path(start_dir).expanduser().resolve()
    root = repo_root(start)
    path = config_path(start)

    if path.is_file():
        print(
            f"config already exists: {path}\n"
            f"`init` never clobbers — use `add <section>` to extend it.",
            file=sys.stderr,
        )
        return 1

    detected = detect_sections(root)
    names = sections or detected
    text = render_config(root, names)

    if dry_run:
        print(text, end="")
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    if json_out:
        print(
            bootstrap_json(
                root, path, created=True, added=names, skipped=[], detected=detected
            )
        )
        return 0

    print(row("created", str(path)))
    print(row("root", str(root)))
    if names:
        why = "" if sections else "  ← detected"
        for name in names:
            print(row("sections", f"{describe(name)}{why}"))
    else:
        print(row("sections", "(none — `root` only; nothing is enabled yet)"))
    remaining = [name for name in SECTIONS if name not in names]
    if remaining:
        print(row("next", f"add {' '.join(remaining)}"))
    return 0


def cmd_add(sections: list[str], start_dir: str, dry_run: bool, json_out: bool) -> int:
    start = Path(start_dir).expanduser().resolve()
    root = repo_root(start)
    config, path, error = load_config(start)

    if error is not None:
        print(f"config is unreadable: {path}\n{error}", file=sys.stderr)
        return 1
    if config is None:
        print(
            f"no config for this project: {path}\nRun `init` first.",
            file=sys.stderr,
        )
        return 1

    present = present_sections(config)
    added = [name for name in sections if name not in present]
    skipped = [name for name in sections if name in present]

    if dry_run:
        print("".join(SECTIONS[name]["block"] for name in added), end="")
        return 0

    if added:
        path.write_text(
            append_sections(path.read_text(encoding="utf-8"), added), encoding="utf-8"
        )

    if json_out:
        print(
            bootstrap_json(
                root, path, created=False, added=added, skipped=skipped, detected=[]
            )
        )
        return 0

    print(row("updated" if added else "unchanged", str(path)))
    for name in added:
        print(row("added", describe(name)))
    for name in skipped:
        print(row("skipped", f"{name}  (already present)"))
    return 0


# ── read / toggle ───────────────────────────────────────────────────────────


def cmd_show(section: str | None, start_dir: str, json_out: bool) -> int:
    start = Path(start_dir).expanduser().resolve()
    config, path, error = load_config(start)

    refused = _refuse_missing(config, path, error)
    if refused is not None:
        return refused

    if section is None:
        if json_out:
            print(json.dumps(config, indent=2))
        else:
            print(path.read_text(encoding="utf-8"), end="")
        return 0

    if section not in config:
        hint = f"\nAdd it: `add {section}`." if section in SECTIONS else ""
        print(f"no [{section}] in this config: {path}{hint}", file=sys.stderr)
        return 1
    if json_out:
        print(json.dumps({section: config[section]}, indent=2))
        return 0
    block = lb_tomledit.slice_section(path.read_text(encoding="utf-8"), section)
    if block is None:  # keys exist but no literal [section] header (sub-tables only)
        block = json.dumps({section: config[section]}, indent=2) + "\n"
    print(block, end="")
    return 0


def cmd_toggle(section: str, start_dir: str, json_out: bool, value: bool) -> int:
    start = Path(start_dir).expanduser().resolve()
    root = repo_root(start)
    config, path, error = load_config(start)

    refused = _refuse_missing(config, path, error)
    if refused is not None:
        return refused
    if section not in present_sections(config):
        print(
            f"no [{section}] in this config: {path}\nAdd it: `add {section}`.",
            file=sys.stderr,
        )
        return 1

    changed = config[section].get("enabled", True) != value
    if changed:
        path.write_text(
            lb_tomledit.set_enabled(path.read_text(encoding="utf-8"), section, value),
            encoding="utf-8",
        )

    if json_out:
        print(
            json.dumps(
                {
                    **project_fields(root, path),
                    "section": section,
                    "enabled": value,
                    "changed": changed,
                },
                indent=2,
            )
        )
        return 0
    print(row("updated" if changed else "unchanged", str(path)))
    print(row("section", f"[{section}]  enabled = {'true' if value else 'false'}"))
    return 0


def cmd_status(
    start_dir: str, registry_file: str, json_out: bool, graph_file: str = DEFAULT_GRAPH
) -> int:
    start = Path(start_dir).expanduser().resolve()
    root = repo_root(start)
    config, path, error = load_config(start)
    registry = Path(registry_file).expanduser()
    legacy = legacy_config(start)

    sections = {
        name: bool(config[name].get("enabled", True))
        for name in SECTIONS
        if config is not None and isinstance(config.get(name), dict)
    }
    unknown = sorted(
        k for k, v in (config or {}).items() if k not in SECTIONS and isinstance(v, dict)
    )
    project_dir = path.parent
    state = {
        "handoffs": len(list(project_dir.glob("handoffs/*.md"))),
        "inbox": len(list(project_dir.glob("handoffs/inbox/*.md"))),
        "plans": len(list(project_dir.glob("plans/*.md"))),
    }
    graph_path = Path(graph_file).expanduser()
    graph, graph_error = load_graph(graph_path)

    if json_out:
        print(
            json.dumps(
                {
                    **project_fields(root, path),
                    "exists": path.is_file(),
                    "error": error,
                    "sections": sections,
                    "unknown_sections": unknown,
                    "state": state,
                    "registry": registry.is_file(),
                    "graph": {
                        "present": graph is not None or graph_error is not None,
                        "error": graph_error,
                        "edges": len(graph["edges"]) if graph else None,
                        "types": len(graph["types"]) if graph else None,
                    },
                    "legacy": str(legacy) if legacy else None,
                },
                indent=2,
            )
        )
        return 1 if error else 0

    print(row("root", str(root)))
    print(row("key", project_key(root)))
    if error is not None:
        print(row("config", f"{path}  (UNREADABLE: {error})"))
    elif config is None:
        print(row("config", f"{path}  (absent — create it with `init`)"))
    else:
        print(row("config", str(path)))
        if sections:
            for name, enabled in sections.items():
                print(row("sections", f"{name}  {'enabled' if enabled else 'DISABLED'}"))
        else:
            print(row("sections", "(none — nothing is enabled yet)"))
        for name in unknown:
            print(row("sections", f"[{name}]  (unknown — not in the catalog)"))
    print(row("state", f"handoffs {state['handoffs']} + {state['inbox']} inbox — handoff.py"))
    print(row("state", f"plans {state['plans']} — plan_store.py"))
    print(
        row(
            "registry",
            f"{registry}  ({'present' if registry.is_file() else 'absent'} — repo_links.py)",
        )
    )
    if graph_error is not None:
        print(row("graph", f"{graph_path}  (UNREADABLE: {graph_error})"))
    elif graph is None:
        print(row("graph", f"{graph_path}  (absent — seed it with `graph init`)"))
    else:
        print(
            row(
                "graph",
                f"{graph_path}  ({len(graph['edges'])} edges, {len(graph['types'])} types "
                f"— repo_links.py)",
            )
        )
    if legacy:
        print(legacy_warning(legacy), file=sys.stderr)
    return 1 if error else 0


def cmd_path(start_dir: str, json_out: bool) -> int:
    start = Path(start_dir).expanduser().resolve()
    root = repo_root(start)
    path = config_path(start)
    legacy = legacy_config(start)
    if json_out:
        print(
            json.dumps(
                {
                    **project_fields(root, path),
                    "exists": path.is_file(),
                    "legacy": str(legacy) if legacy else None,
                },
                indent=2,
            )
        )
    else:
        status = "exists" if path.is_file() else "absent — create it with `init`"
        print(f"{path}  ({status})")
        if legacy:
            print(legacy_warning(legacy), file=sys.stderr)
    return 0


# ── registry ────────────────────────────────────────────────────────────────


def cmd_repos_list(registry_file: str, json_out: bool) -> int:
    repos, registry, error = _open_registry(registry_file)
    if error is not None:
        return 1

    if json_out:
        print(
            json.dumps(
                {
                    "registry": str(registry),
                    "repos": None
                    if repos is None
                    else {
                        name: {
                            "path": raw,
                            "exists": Path(raw).expanduser().is_dir(),
                        }
                        for name, raw in sorted(repos.items())
                    },
                },
                indent=2,
            )
        )
        return 0
    if repos is None:
        print(f"no registry: {registry}  (create it with `repos add NAME PATH`)")
        return 0
    if not repos:
        print(f"{registry}: no repos registered  (add one: `repos add NAME PATH`)")
        return 0
    width = max(len(name) for name in repos)
    for name, raw in sorted(repos.items()):
        missing = "" if Path(raw).expanduser().is_dir() else "   ← MISSING on this machine"
        print(f"{name:<{width}}  {raw}{missing}")
    return 0


def cmd_repos_add(name: str, path_raw: str, registry_file: str, json_out: bool) -> int:
    repos, registry, error = _open_registry(registry_file)
    if error is not None:
        return 1

    if not REPO_NAME.match(name):
        print(
            f"invalid repo name {name!r} — letters, digits, '-', '_' only.",
            file=sys.stderr,
        )
        return 2
    if repos is not None and name in repos:
        print(
            f"{name!r} is already registered → {repos[name]}\n"
            f"`repos rm {name}` first, or pick another name.",
            file=sys.stderr,
        )
        return 1
    if repos is None:
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(append_repo(REGISTRY_HEADER, name, path_raw), encoding="utf-8")
    else:
        registry.write_text(
            append_repo(registry.read_text(encoding="utf-8"), name, path_raw),
            encoding="utf-8",
        )
    if not Path(path_raw).expanduser().is_dir():
        print(
            f"note: {path_raw} does not exist on this machine (yet) — registered anyway.",
            file=sys.stderr,
        )
    if json_out:
        print(
            json.dumps(
                {
                    "registry": str(registry),
                    "name": name,
                    "path": path_raw,
                    "changed": True,
                },
                indent=2,
            )
        )
        return 0
    print(row("updated", str(registry)))
    print(row("added", f'{name} = "{path_raw}"'))
    return 0


def cmd_repos_rm(name: str, registry_file: str, json_out: bool) -> int:
    repos, registry, error = _open_registry(registry_file)
    if error is not None:
        return 1

    if repos is None or name not in repos:
        print(f"{name!r} is not registered — see `repos list`.", file=sys.stderr)
        return 1
    text = remove_repo(registry.read_text(encoding="utf-8"), name)
    if text is None:
        print(
            f"couldn't find {name!r}'s line in {registry} — a key shape this tool "
            f"doesn't manage; edit the file directly.",
            file=sys.stderr,
        )
        return 1
    registry.write_text(text, encoding="utf-8")
    if json_out:
        print(
            json.dumps({"registry": str(registry), "name": name, "changed": True}, indent=2)
        )
        return 0
    print(row("updated", str(registry)))
    print(row("removed", name))
    return 0


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
    print(row("types", f"{len(SEED_TYPE_NAMES)} seeded — the file owns the vocabulary from here"))
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
        print(f"{graph_path}: no [types] declared  (seed a vocabulary: `graph init` on a fresh file)")
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
            print(row("skipped", f"{graph['skipped']} malformed edge block(s) — run `graph doctor`"))
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
            group: [{**entry, "path": _node_path(entry["other"], repos)} for entry in entries]
            for group, entries in projection.items()
        }
        print(json.dumps({"graph": str(graph_path), "node": name, **enriched}, indent=2))
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
        mentions = ", ".join(f"{m['other']} ({m['label']})" for m in projection["mentions"])
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
    return json.dumps({"graph": str(graph_path), "action": action, "edge": edge}, indent=2)


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

    repos, registry, reg_error = _open_registry(registry_file)
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
    parallel = [
        e["type"]
        for e in graph["edges"]
        if {e["from"], e["to"]} == {frm, to}
    ]
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
            print(_edge_json(graph_path, "unchanged", {"from": frm, "to": to, "type": etype}))
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
        print(_edge_json(graph_path, "unlinked", {"from": frm, "to": to, "type": removed}))
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
        print(f"graph doctor: {graph_path} — no problems.")
    else:
        print(f"graph doctor: {len(problems)} problem(s) in {graph_path}:")
        for problem in problems:
            print(f"- [{problem['kind']}] {problem['subject']}: {problem['detail']}")
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
                {"graph": str(graph_path), "out": str(out), "nodes": nodes, "edges": edges},
                indent=2,
            )
        )
        return 0
    print(row("created", str(out)))
    print(row("graph", f"{nodes} node(s), {edges} edge(s) — open it in a browser"))
    return 0


# ── keys ────────────────────────────────────────────────────────────────────


def _open_keys(keys_file: str) -> tuple[dict | None, Path, str | None]:
    """The shared key-catalog preamble: expanded path + parsed catalog (or its error)."""
    keys_path = Path(keys_file).expanduser()
    catalog, error = load_keys(keys_path)
    if error is not None:
        print(f"key catalog is unusable: {keys_path}\n{error}", file=sys.stderr)
    return catalog, keys_path, error


def _key_json(keys_path: Path, action: str, name: str, entry: dict | None) -> str:
    """The one JSON shape every key write verb prints — never a value field."""
    return json.dumps(
        {"keys": str(keys_path), "action": action, "name": name, "entry": entry},
        indent=2,
    )


ADD_USAGE = "key add NAME --provider P --env VAR --scope TEXT"


def cmd_key_ls(keys_file: str, secrets_file: str, json_out: bool) -> int:
    catalog, keys_path, error = _open_keys(keys_file)
    if error is not None:
        return 1
    if catalog is None:
        print(f"no key catalog: {keys_path}  (add one: `{ADD_USAGE}`)")
        return 0
    stored, sec_error = load_secret_names(Path(secrets_file).expanduser())
    if sec_error is not None:
        print(f"note: secrets file unusable ({sec_error}) — value presence unknown.", file=sys.stderr)

    if json_out:
        print(
            json.dumps(
                {
                    "keys": str(keys_path),
                    "entries": {
                        name: {
                            **entry,
                            "has_value": (name in stored) if sec_error is None else None,
                        }
                        for name, entry in catalog.items()
                    },
                },
                indent=2,
            )
        )
        return 0
    if not catalog:
        print(f"{keys_path}: no keys catalogued  (add one: `{ADD_USAGE}`)")
        return 0
    names = sorted(catalog)
    widths = [
        max(len(name) for name in names),
        max(len(catalog[n]["provider"] or "?") for n in names),
        max(len(catalog[n]["env"] or "?") for n in names),
    ]
    for name in names:
        entry = catalog[name]
        missing = ""
        if sec_error is None and (stored is None or name not in stored):
            missing = "   ← NO VALUE"
        print(
            f"{name:<{widths[0]}}  {(entry['provider'] or '?'):<{widths[1]}}  "
            f"{(entry['env'] or '?'):<{widths[2]}}  {entry['scope'] or '?'}{missing}"
        )
    return 0


def cmd_key_add(
    name: str, provider: str, env: str, scope: str,
    keys_file: str, secrets_file: str, json_out: bool,
) -> int:
    if not KEY_NAME.match(name):
        print(f"invalid key name {name!r} — letters, digits, '-', '_' only.", file=sys.stderr)
        return 2
    if not ENV_NAME.match(env):
        print(
            f"invalid env var name {env!r} — [A-Z_][A-Z0-9_]* (e.g. OPENAI_API_KEY).",
            file=sys.stderr,
        )
        return 2
    catalog, keys_path, error = _open_keys(keys_file)
    if error is not None:
        return 1
    if catalog is not None and name in catalog:
        print(
            f"{name!r} is already catalogued → ${catalog[name]['env']}\n"
            f"`key rm {name}` first — values are write-only, so re-adding is how you rotate.",
            file=sys.stderr,
        )
        return 1
    secrets_path = Path(secrets_file).expanduser()
    stored, sec_error = load_secret_names(secrets_path)
    if sec_error is not None:
        print(f"secrets file is unusable: {secrets_path}\n{sec_error}", file=sys.stderr)
        return 1
    if stored is not None and name in stored:
        print(
            f"a stored value for {name!r} already exists (no catalog entry — an orphan).\n"
            f"`key rm {name}` removes it, then re-add.",
            file=sys.stderr,
        )
        return 1

    # The value never transits argv or any output — hidden prompt on a TTY, piped
    # stdin otherwise (`pbpaste | lb key add ...`).
    if sys.stdin.isatty():
        value = getpass.getpass(f"value for {name} (hidden): ")
    else:
        value = sys.stdin.read().strip()
    if not value:
        print("empty value — nothing stored.", file=sys.stderr)
        return 1

    # Secrets first: a failed secret write must not leave catalog metadata pointing at
    # nothing (the reverse orphan is harmless and doctor-visible).
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    secrets_text = (
        secrets_path.read_text(encoding="utf-8") if secrets_path.is_file() else SECRETS_HEADER
    )
    write_secrets(secrets_path, append_secret(secrets_text, name, value))
    keys_text = (
        keys_path.read_text(encoding="utf-8") if keys_path.is_file() else KEYS_HEADER
    )
    keys_path.parent.mkdir(parents=True, exist_ok=True)
    keys_path.write_text(append_key(keys_text, name, provider, env, scope), encoding="utf-8")

    entry = {"provider": provider, "env": env, "scope": scope}
    if json_out:
        print(_key_json(keys_path, "added", name, entry))
        return 0
    print(row("updated", str(keys_path)))
    print(row("added", f"{name}  {provider} → ${env}"))
    print(row("value", f"stored (never printed) — use it: `key run {name} -- CMD`"))
    return 0


RUN_USAGE = "key run NAME[,NAME...] -- CMD..."


def cmd_key_run(names_raw: str, cmd: list[str], keys_file: str, secrets_file: str) -> int:
    """Inject the named values into a child env and exec CMD — the values' only exit
    from the store. Never prints one; the child's own exit code passes through
    untranslated, and a failed exec is 127 (the `env(1)` convention)."""
    names = list(dict.fromkeys(n.strip() for n in names_raw.split(",") if n.strip()))
    if not cmd or not names:
        print(f"usage: {RUN_USAGE}", file=sys.stderr)
        return 2
    catalog, keys_path, error = _open_keys(keys_file)
    if error is not None:
        return 1
    if catalog is None:
        print(f"no key catalog: {keys_path}\nAdd one: `{ADD_USAGE}`.", file=sys.stderr)
        return 1
    unknown = [n for n in names if n not in catalog]
    if unknown:
        print(f"not catalogued: {', '.join(unknown)} — see `key ls`.", file=sys.stderr)
        return 1
    env_owner: dict[str, str] = {}  # env var → the selected name injecting it
    for name in names:
        var = catalog[name]["env"]
        if var is None:
            print(f"{name!r} has no usable `env` — see `key doctor`.", file=sys.stderr)
            return 1
        if var in env_owner:
            print(
                f"{env_owner[var]} and {name} both inject ${var} — pick one per run.",
                file=sys.stderr,
            )
            return 1
        env_owner[var] = name
    secrets_path = Path(secrets_file).expanduser()
    values, sec_error = load_secrets(secrets_path)
    if sec_error is not None:
        print(f"secrets file is unusable: {secrets_path}\n{sec_error}", file=sys.stderr)
        return 1
    missing = [n for n in names if n not in (values or {})]
    if missing:
        print(
            f"no stored value for: {', '.join(missing)} — catalogued but valueless.\n"
            f"Rotate one in: `key rm NAME` then `key add NAME ...` (see `key doctor`).",
            file=sys.stderr,
        )
        return 1
    child_env = {**os.environ, **{var: values[name] for var, name in env_owner.items()}}
    if os.name != "nt":
        try:
            os.execvpe(cmd[0], cmd, child_env)  # never returns on success
        except OSError as exc:
            print(f"cannot exec {cmd[0]!r}: {exc}", file=sys.stderr)
            return 127
    proc = subprocess.run(cmd, env=child_env)
    return proc.returncode


def cmd_key_rm(name: str, keys_file: str, secrets_file: str, json_out: bool) -> int:
    catalog, keys_path, error = _open_keys(keys_file)
    if error is not None:
        return 1
    secrets_path = Path(secrets_file).expanduser()
    stored, sec_error = load_secret_names(secrets_path)
    if sec_error is not None:
        print(f"secrets file is unusable: {secrets_path}\n{sec_error}", file=sys.stderr)
        return 1
    in_catalog = catalog is not None and name in catalog
    has_value = stored is not None and name in stored
    if not in_catalog and not has_value:
        print(f"{name!r} is not catalogued — see `key ls`.", file=sys.stderr)
        return 1

    if in_catalog:
        text = remove_key(keys_path.read_text(encoding="utf-8"), name)
        if text is None:
            print(
                f"couldn't find {name!r}'s block in {keys_path} — a shape this tool "
                f"doesn't manage; edit the file directly.",
                file=sys.stderr,
            )
            return 1
        keys_path.write_text(text, encoding="utf-8")
    if has_value:
        text = remove_secret(secrets_path.read_text(encoding="utf-8"), name)
        if text is None:
            print(
                f"couldn't find {name!r}'s line in {secrets_path} — a shape this tool "
                f"doesn't manage; edit the file directly.",
                file=sys.stderr,
            )
            return 1
        write_secrets(secrets_path, text)

    if json_out:
        print(_key_json(keys_path, "removed", name, None))
        return 0
    print(row("updated", str(keys_path)))
    removed = name if in_catalog else f"{name} (orphan value only)"
    print(row("removed", f"{removed}{' + stored value' if in_catalog and has_value else ''}"))
    return 0


# ── audit ───────────────────────────────────────────────────────────────────


def cmd_doctor(state_dir: Path | None, registry_file: str, json_out: bool) -> int:
    state = (state_dir or default_state_dir()).expanduser()
    registry = Path(registry_file).expanduser()
    problems = doctor(state, registry)
    if json_out:
        print(json.dumps({"state_dir": str(state), "problems": problems}, indent=2))
    elif not problems:
        print(f"lightbridge doctor: {state} — no problems.")
    else:
        print(f"lightbridge doctor: {len(problems)} problem(s) in {state}:")
        for problem in problems:
            print(f"- [{problem['kind']}] {problem['path']}: {problem['detail']}")
    return 1 if problems else 0


# ── mv ──────────────────────────────────────────────────────────────────────


def _default_ask(prompt: str) -> bool:
    """The interactive confirmation — swapped out by tests via `cmd_mv(ask=...)`."""
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _print_mv_plan(plan: dict) -> None:
    """The blast radius, shown before anything changes (and by `--dry-run`)."""
    verb = "move + repair" if plan["mode"] == "move" else "repair (already moved)"
    print(row("plan", f"{verb}: {plan['old']} → {plan['new']}"))
    print(
        row(
            "affects",
            f"{len(plan['projects'])} project(s) · {len(plan['repos'])} registry entry(ies)",
        )
    )
    for project in plan["projects"]:
        merge = "  (merge into existing state)" if project["collision"] == "state" else ""
        print(row("key", f"{project['old_key']}  →  {project['new_key']}{merge}"))
    for name, change in plan["repos"].items():
        print(row("repos", f"{name}: {change['old']} → {change['new']}"))


def cmd_mv(
    old_raw: str,
    new_raw: str,
    *,
    yes: bool,
    dry_run: bool,
    json_out: bool,
    state_dir: Path | None = None,
    registry_file: str = DEFAULT_REGISTRY,
    ask=None,
) -> int:
    state = (state_dir or default_state_dir()).expanduser()
    registry = Path(registry_file).expanduser()
    plan = plan_mv(old_raw, new_raw, state, registry)

    if plan["errors"]:
        print("\n".join(plan["errors"]), file=sys.stderr)
        return 1
    if plan["mode"] == "noop":
        if json_out:
            print(json.dumps({**plan, "applied": False}, indent=2))
        else:
            print(
                row(
                    "unchanged",
                    f"already consistent — {len(plan['settled'])} reference(s) under "
                    f"{plan['new']} are keyed to it",
                )
            )
        return 0
    if not json_out:
        _print_mv_plan(plan)
    if dry_run:
        if json_out:
            print(json.dumps({**plan, "applied": False}, indent=2))
        else:
            print(row("dry-run", "nothing changed"))
        return 0

    # The guard (design Decision 2): a human at a TTY confirms; everything else
    # needs --yes, which is reserved for explicitly human-instructed moves.
    if not yes:
        if ask is None and not sys.stdin.isatty():
            print(
                "refused — this changes the filesystem and needs confirmation, but stdin "
                "is not a TTY.\nRe-run with --yes to apply. Agents: pass --yes only when "
                "the human explicitly instructed this move.",
                file=sys.stderr,
            )
            return 1
        if not (ask or _default_ask)("proceed? [y/N] "):
            print("aborted — nothing changed.", file=sys.stderr)
            return 1

    apply_mv(plan, state, registry)

    for note in plan["claude"]:
        print(
            f"note: ~/.claude/projects/{note['old_key']} exists (Claude Code session "
            f"state; its new key would be {note['new_key']}) — not touched, migrate it "
            "deliberately if wanted.",
            file=sys.stderr,
        )

    if json_out:
        print(json.dumps({**plan, "applied": True}, indent=2))
        return 0
    print(
        row(
            "moved" if plan["mode"] == "move" else "repaired",
            f"{plan['old']} → {plan['new']}",
        )
    )
    print(
        row(
            "rekeyed",
            f"{len(plan['projects'])} project(s) · {len(plan['repos'])} registry entry(ies)",
        )
    )
    return 0
