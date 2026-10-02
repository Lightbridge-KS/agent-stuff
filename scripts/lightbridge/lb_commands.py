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
    DEFAULT_KEYS,
    ENV_NAME,
    KEY_NAME,
    KEYS_HEADER,
    SECRETS_DENIED,
    SECRETS_HEADER,
    append_key,
    append_secret,
    audit as keys_audit,
    load_keys,
    load_secret_names,
    load_secrets,
    remove_key,
    remove_secret,
    write_secrets,
)
from lb_fleet import (
    FLEET_HEADER,
    SEED_BLOCK,
    SSH_OFFLINE,
    classify_unreachable,
    distance,
    hub_fetch,
    hub_repo_dir,
    now_iso,
    parse_report,
    receipt_path,
    render_node_script,
    repo_specs,
    run_node,
    short,
    write_receipt,
)
from lb_mv import apply_mv, plan_mv
from lb_registry import REGISTRY_HEADER, REPO_NAME, append_repo, remove_repo
from lb_style import Tone, paint
from lb_resolve import (
    DEFAULT_FLEET,
    DEFAULT_GRAPH,
    DEFAULT_REGISTRY,
    config_path,
    fleet_receipts_dir,
    load_fleet,
    load_graph,
    load_receipt,
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


def row(label: str, value: str, tone: Tone = "label") -> str:
    """One `label   value` line — every bootstrap label fits the same column.

    The label is painted (padded first, so escapes never shift the column); `tone`
    flags a line whose label alone carries the verdict (REFUSED, FAILED, applied).
    """
    return f"{paint(f'{label:<9}', tone)} {value}"


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
    start_dir: str,
    registry_file: str,
    json_out: bool,
    graph_file: str = DEFAULT_GRAPH,
    keys_file: str = DEFAULT_KEYS,
    fleet_file: str = DEFAULT_FLEET,
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
        "asks": len(list(project_dir.glob("asks/*.md"))),
    }
    graph_path = Path(graph_file).expanduser()
    graph, graph_error = load_graph(graph_path)
    # The dashboard reads only the catalog — the values file is never opened here.
    keys_path = Path(keys_file).expanduser()
    key_catalog, keys_error = load_keys(keys_path)
    # The dashboard stays bounded and offline: inventory + receipt counts, no ssh.
    fleet_path = Path(fleet_file).expanduser()
    fleet, fleet_error = load_fleet(fleet_path)
    receipts = (
        sum(1 for name in fleet["nodes"] if receipt_path(fleet_path, name).is_file())
        if fleet
        else None
    )

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
                    "keys": {
                        "present": key_catalog is not None or keys_error is not None,
                        "error": keys_error,
                        "count": len(key_catalog) if key_catalog is not None else None,
                    },
                    "fleet": {
                        "present": fleet is not None or fleet_error is not None,
                        "error": fleet_error,
                        "nodes": len(fleet["nodes"]) if fleet else None,
                        "receipts": receipts,
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
        print(row("config", f"{path}  {paint(f'(UNREADABLE: {error})', 'bad')}", "bad"))
    elif config is None:
        print(row("config", f"{path}  {paint('(absent — create it with `init`)', 'warn')}"))
    else:
        print(row("config", str(path)))
        if sections:
            for name, enabled in sections.items():
                verdict = paint("enabled", "ok") if enabled else paint("DISABLED", "warn")
                print(row("sections", f"{name}  {verdict}"))
        else:
            print(row("sections", "(none — nothing is enabled yet)"))
        for name in unknown:
            print(row("sections", f"[{name}]  {paint('(unknown — not in the catalog)', 'warn')}"))
    print(row("state", f"handoffs {state['handoffs']} + {state['inbox']} inbox — handoff.py"))
    print(row("state", f"plans {state['plans']} — plan_store.py"))
    print(row("state", f"asks {state['asks']} — ask-form / ask-form-qmd"))
    print(
        row(
            "registry",
            f"{registry}  ({'present' if registry.is_file() else 'absent'} — repo_links.py)",
        )
    )
    if graph_error is not None:
        print(row("graph", f"{graph_path}  {paint(f'(UNREADABLE: {graph_error})', 'bad')}", "bad"))
    elif graph is None:
        print(row("graph", f"{graph_path}  {paint('(absent — seed it with `graph init`)', 'dim')}"))
    else:
        print(
            row(
                "graph",
                f"{graph_path}  ({len(graph['edges'])} edges, {len(graph['types'])} types "
                f"— repo_links.py)",
            )
        )
    if keys_error is not None:
        print(row("keys", f"{keys_path}  {paint(f'(UNREADABLE: {keys_error})', 'bad')}", "bad"))
    elif key_catalog is None:
        print(row("keys", f"{keys_path}  {paint('(absent — add one with `key add`)', 'dim')}"))
    else:
        print(row("keys", f"{keys_path}  ({len(key_catalog)} key(s) — lb key)"))
    if fleet_error is not None:
        print(row("fleet", f"{fleet_path}  {paint(f'(UNREADABLE: {fleet_error})', 'bad')}", "bad"))
    elif fleet is None:
        print(row("fleet", f"{fleet_path}  {paint('(absent — not a hub; seed one with `fleet init`)', 'dim')}"))
    else:
        print(
            row(
                "fleet",
                f"{fleet_path}  ({len(fleet['nodes'])} node(s), {receipts} receipt(s) — lb fleet)",
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
        missing = (
            "" if Path(raw).expanduser().is_dir()
            else "   " + paint("← MISSING on this machine", "bad")
        )
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
        print(f"graph doctor: {graph_path} — {paint('no problems.', 'ok')}")
    else:
        print(f"graph doctor: {paint(f'{len(problems)} problem(s)', 'bad')} in {graph_path}:")
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
    if sec_error == SECRETS_DENIED:
        print(
            f"{secrets_path}: {sec_error}.\n"
            f"Agents: ask the user to approve a sandbox-disabled run — every use of a "
            f"key stays a human-approved act.",
            file=sys.stderr,
        )
        return 1
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


def cmd_key_doctor(keys_file: str, secrets_file: str, json_out: bool) -> int:
    """Audit the catalog/values pair. Absent files are the not-opted-in state, not a
    problem — an empty audit of nothing is clean."""
    keys_path = Path(keys_file).expanduser()
    secrets_path = Path(secrets_file).expanduser()
    catalog, keys_error = load_keys(keys_path)
    stored, sec_error = load_secret_names(secrets_path)
    # Absent secrets = knowledge ([] → valueless keys are findings); denied/unreadable
    # = ignorance (None → value-presence checks skipped, see below).
    if stored is None and sec_error is None:
        stored = []
    problems = keys_audit(catalog or {}, stored, secrets_path)
    if sec_error == SECRETS_DENIED:
        # The environment, not the file, is refusing — expected under an agent
        # sandbox; a note, never a problem (doctor must not cry rot in every session).
        print(f"note: {secrets_path}: {sec_error}; values unaudited.", file=sys.stderr)
    elif sec_error is not None:
        problems.insert(
            0, {"kind": "bad-secrets", "subject": str(secrets_path), "detail": sec_error}
        )
    if keys_error is not None:
        problems.insert(
            0, {"kind": "bad-keys", "subject": str(keys_path), "detail": keys_error}
        )
    if json_out:
        print(
            json.dumps(
                {"keys": str(keys_path), "secrets": str(secrets_path), "problems": problems},
                indent=2,
            )
        )
    elif not problems:
        print(f"key doctor: {keys_path} — {paint('no problems.', 'ok')}")
    else:
        print(f"key doctor: {paint(f'{len(problems)} problem(s)', 'bad')} in {keys_path}:")
        for problem in problems:
            kind = paint(f"[{problem['kind']}]", "warn")
            print(f"- {kind} {problem['subject']}: {problem['detail']}")
    return 1 if problems else 0


# ── fleet ───────────────────────────────────────────────────────────────────


def _open_fleet(fleet_file: str) -> tuple[dict | None, Path, str | None]:
    """The shared fleet preamble: expanded path + parsed inventory (or its error)."""
    fleet_path = Path(fleet_file).expanduser()
    fleet, error = load_fleet(fleet_path)
    if error is not None:
        print(f"fleet inventory is unusable: {fleet_path}\n{error}", file=sys.stderr)
    return fleet, fleet_path, error


def _require_fleet(fleet_file: str) -> tuple[dict | None, Path]:
    """Inventory or a refusal that teaches — every verb but `init` opens this way."""
    fleet, fleet_path, error = _open_fleet(fleet_file)
    if error is not None:
        return None, fleet_path
    if fleet is None:
        print(
            f"no fleet inventory: {fleet_path}\n"
            f"This machine is not a hub — seed one with `fleet init`.",
            file=sys.stderr,
        )
        return None, fleet_path
    return fleet, fleet_path


def _require_node(fleet: dict, node: str) -> bool:
    if node in fleet["nodes"]:
        return True
    known = ", ".join(fleet["nodes"]) or "(none — add a [nodes.<name>] table)"
    print(f"unknown node: {node}\nKnown: {known}", file=sys.stderr)
    return False


def _tail(text: str, lines: int = 5) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


# What each refusal/failure means and the next move — worded for the node, where the
# fix happens. `n` is the dirty-file or ahead count when one applies.
REFUSALS = {
    "not-cloned": "not cloned at {root}/{name} — clone it on the node first",
    "not-on-main": "on branch {branch} — `git switch main` on the node (push the branch first)",
    "dirty": "dirty: {n} file(s) — on the node, commit on a branch and push (or revert); never stashed here",
    "ahead": "ahead of origin/main by {n} — push the branch and open a PR; the hub pulls after merge",
    "missing-requires": "missing {files} — create the per-box file on the node (e.g. `cp .device.example .device`)",
    "fetch": "git fetch failed on the node — its GitHub key or network; tail in the receipt",
    "rev-list": "could not compare HEAD with origin/main on the node",
    "pull": "fast-forward pull failed — tail in the receipt",
    "apply": "apply exited {code} — tail in the receipt",
    "verify": "verify exited {code} — tail in the receipt",
}


# The receipt step holding a failure's output. The node files fetch and rev-list
# failures under `pull` (one git phase), so a reason is not always its own key.
STEP_OF = {"fetch": "pull", "rev-list": "pull", "pull": "pull", "apply": "apply", "verify": "verify"}


def _explain(entry: dict, root: str, name: str) -> str:
    reason = entry.get("reason") or "?"
    template = REFUSALS.get(reason, reason)
    step = entry.get(STEP_OF[reason]) if reason in STEP_OF else None
    return template.format(
        root=root,
        name=name,
        branch=entry.get("branch") or "?",
        n=len(entry.get("dirty") or []) if reason == "dirty" else entry.get("ahead") or "?",
        files=", ".join(entry.get("missing_requires") or []),
        code=(step or {}).get("exit", "?"),
    )


def _classify(entry: dict, dist: dict) -> str:
    """One word per repo for `status`: in-sync | behind | diverged | not-cloned.

    `diverged` = anything the sync gate would refuse (needs a human on the node).
    """
    if entry.get("reason") == "not-cloned":
        return "not-cloned"
    if (
        entry.get("branch") != "main"
        or entry.get("dirty")
        or entry.get("missing_requires")
        or dist.get("ahead")
    ):
        return "diverged"
    return "behind" if dist.get("behind") else "in-sync"


def _flags(entry: dict, dist: dict) -> list[str]:
    flags = []
    if entry.get("branch") not in (None, "main"):
        flags.append(f"not on main ({entry['branch']})")
    if entry.get("dirty"):
        flags.append(f"DIRTY {len(entry['dirty'])}")
    if dist.get("ahead"):
        flags.append("AHEAD (unknown to hub)" if dist.get("behind") is None else "AHEAD")
    if entry.get("missing_requires"):
        flags.append("missing " + ", ".join(entry["missing_requires"]))
    return flags


def cmd_fleet_init(fleet_file: str, dry_run: bool, json_out: bool) -> int:
    fleet_path = Path(fleet_file).expanduser()
    if fleet_path.is_file():
        print(
            f"fleet inventory already exists: {fleet_path}\n"
            f"`fleet init` never clobbers — edit the file (it is hand-authored by design).",
            file=sys.stderr,
        )
        return 1
    text = FLEET_HEADER + "\n" + SEED_BLOCK
    if dry_run:
        print(text, end="")
        return 0
    fleet_path.parent.mkdir(parents=True, exist_ok=True)
    fleet_path.write_text(text, encoding="utf-8")
    fleet, error = load_fleet(fleet_path)
    if json_out:
        print(
            json.dumps(
                {
                    "fleet": str(fleet_path),
                    "created": True,
                    "nodes": list(fleet["nodes"]) if fleet else [],
                    "repos": list(fleet["repos"]) if fleet else [],
                },
                indent=2,
            )
        )
        return 0
    print(row("created", str(fleet_path)))
    print(row("nodes", ", ".join(fleet["nodes"]) if fleet else f"(seed unusable: {error})"))
    print(row("next", "edit the [nodes.*] tables to match ~/.ssh/config, then `fleet status`"))
    return 0


def cmd_fleet_status(
    node: str | None,
    fleet_file: str,
    no_fetch: bool,
    json_out: bool,
    runner=subprocess.run,
) -> int:
    """Live: ask each node what it has, compute the distance here, compare to receipts.

    Exit 0 only when every addressed node answered and every repo is in-sync.
    """
    fleet, fleet_path = _require_fleet(fleet_file)
    if fleet is None:
        return 1
    if node is not None and not _require_node(fleet, node):
        return 1
    names = [node] if node else list(fleet["nodes"])
    hub_root = fleet["hub"]["root"]

    fetched: dict[str, str | None] = {}

    def ensure_fetched(repo: str) -> None:
        if repo in fetched:
            return
        fetched[repo] = None if no_fetch else hub_fetch(hub_repo_dir(hub_root, repo))
        if fetched[repo]:
            print(f"note: {repo}: {fetched[repo]} — distance may be stale", file=sys.stderr)

    nodes_out: dict[str, dict] = {}
    all_clean = True
    for nname in names:
        spec = fleet["nodes"][nname]
        receipt, receipt_error = load_receipt(receipt_path(fleet_path, nname))
        if receipt_error:
            print(f"note: receipt for {nname}: {receipt_error}", file=sys.stderr)
        out: dict = {
            "ssh": spec["ssh"],
            "online": None,
            "host": None,
            "error": None,
            "unreachable": None,
            "last_sync": receipt.get("timestamp") if receipt else None,
            "repos": {},
            "checks": None,
        }
        nodes_out[nname] = out
        print(f"{nname}: asking {spec['ssh']} …", file=sys.stderr)
        rc, stdout, stderr = run_node(
            spec["ssh"], render_node_script("status", spec["root"], repo_specs(fleet, nname)), runner
        )
        if rc == SSH_OFFLINE:
            kind, why = classify_unreachable(stderr)
            out.update(online=False, unreachable=kind, error=why)
            all_clean = False
            continue
        if rc == 127:
            out.update(error=stderr.strip())
            all_clean = False
            continue
        report = parse_report(stdout)
        if report is None:
            out.update(online=True, error=f"no report from node (exit {rc}): {_tail(stderr or stdout)}")
            all_clean = False
            continue
        out.update(online=True, host=report.get("host"), checks=report.get("checks"))
        synced = (receipt or {}).get("repos", {})
        for rname, entry in report["repos"].items():
            ensure_fetched(rname)
            dist = distance(hub_repo_dir(hub_root, rname), entry.get("before"))
            state = _classify(entry, dist)
            if state != "in-sync":
                all_clean = False
            out["repos"][rname] = {
                "state": state,
                "branch": entry.get("branch"),
                "head": entry.get("before"),
                "origin_main": dist["origin_main"],
                "behind": dist["behind"],
                "ahead": dist["ahead"],
                "dirty": entry.get("dirty") or [],
                "missing_requires": entry.get("missing_requires") or [],
                "last_synced": (synced.get(rname) or {}).get("after"),
                "distance_error": dist["error"],
            }

    if json_out:
        print(json.dumps({"fleet": str(fleet_path), "nodes": nodes_out}, indent=2))
        return 0 if all_clean else 1

    for nname, out in nodes_out.items():
        if out["online"] is False or out["error"]:
            # A failed name lookup is this machine's fault — the node may be fine.
            tone = "warn" if out["unreachable"] == "dns" else "bad"
            print(row("node", f"{nname}  {paint(out['error'], tone)}", tone))
            continue
        last = out["last_sync"] or "never"
        print(row("node", f"{nname}  {paint('online', 'ok')} · {out['host']} · last sync {last}"))
        for rname, repo in out["repos"].items():
            if repo["state"] == "not-cloned":
                head = paint("not cloned", "bad")
            elif repo["behind"] is None and repo["ahead"]:
                head = paint("unknown to hub", "bad")
            elif repo["behind"]:
                head = paint(f"behind {repo['behind']}", "warn")
            else:
                head = paint("in-sync", "ok")
            parts = [head, *(paint(flag, "bad") for flag in _flags(
                {"branch": repo["branch"], "dirty": repo["dirty"], "missing_requires": repo["missing_requires"]},
                {"ahead": repo["ahead"], "behind": repo["behind"]},
            ))]
            if repo["distance_error"]:
                parts.append(paint(f"({repo['distance_error']})", "warn"))
            print(row("repo", f"{rname:<22} {' · '.join(parts)}"))
        broken = (out["checks"] or {}).get("broken_symlinks")
        if broken is not None:
            print(row("checks", paint(f"broken symlinks {len(broken)}", "bad" if broken else "ok")))
    if not all_clean:
        print(row("next", "fleet sync NODE  — pulls `behind` repos; `diverged` ones are refused until fixed on the node"))
    return 0 if all_clean else 1


def cmd_fleet_sync(
    node: str,
    only: list[str],
    dry_run: bool,
    reinstall: bool,
    fleet_file: str,
    json_out: bool,
    runner=subprocess.run,
) -> int:
    """Reconcile one node to origin/main: gate → ff-only pull → apply → verify → receipt.

    Exit 0 when every addressed repo is applied or in-sync and the registries are clean.
    """
    fleet, fleet_path = _require_fleet(fleet_file)
    if fleet is None:
        return 1
    if not _require_node(fleet, node):
        return 1
    spec = fleet["nodes"][node]
    unknown = [r for r in only if r not in spec["repos"]]
    if unknown:
        print(
            f"{node} does not carry: {', '.join(unknown)}\nIts repos: {', '.join(spec['repos'])}",
            file=sys.stderr,
        )
        return 2
    specs = repo_specs(fleet, node, only or None)
    script = render_node_script("sync", spec["root"], specs, reinstall=reinstall)

    if dry_run:
        if json_out:
            print(
                json.dumps(
                    {"node": node, "ssh": spec["ssh"], "root": spec["root"], "reinstall": reinstall,
                     "repos": specs, "dry_run": True},
                    indent=2,
                )
            )
            return 0
        print(row("node", f"{node}  via ssh {spec['ssh']}  root {spec['root']}"))
        for item in specs:
            verify = f"  ·  verify: {item['verify']}" if item.get("verify") else ""
            requires = f"  ·  requires: {', '.join(item['requires'])}" if item.get("requires") else ""
            print(row("repo", f"{item['name']:<22} apply: {item['apply']}{verify}{requires}"))
        print(row("dry-run", "nothing sent — drop --dry-run to reconcile"))
        return 0

    print(f"{node}: reconciling via {spec['ssh']} …", file=sys.stderr)
    rc, stdout, stderr = run_node(spec["ssh"], script, runner)
    if rc == SSH_OFFLINE:
        _, why = classify_unreachable(stderr)
        print(f"{node} not reached via {spec['ssh']}: {why} — nothing changed.", file=sys.stderr)
        return 1
    if rc == 127:
        print(stderr.strip(), file=sys.stderr)
        return 1
    report = parse_report(stdout)
    if report is None:
        print(
            f"{node}: no report came back (exit {rc}) — the node script did not finish:\n"
            f"{_tail(stderr or stdout, 10)}",
            file=sys.stderr,
        )
        return 1

    repos = report["repos"]
    broken = (report.get("checks") or {}).get("broken_symlinks") or []
    ok = all(e.get("status") in ("applied", "in-sync") for e in repos.values()) and not broken
    receipt = {
        "node": node,
        "host": report.get("host"),
        "timestamp": now_iso(),
        "mode": "sync",
        "reinstall": reinstall,
        "ok": ok,
        "repos": repos,
        "checks": report.get("checks") or {},
    }
    path = write_receipt(fleet_path, node, receipt)

    if json_out:
        print(json.dumps({"receipt": str(path), **receipt}, indent=2))
        return 0 if ok else 1

    root = report.get("root") or spec["root"]
    for rname, entry in repos.items():
        status = entry.get("status")
        if status == "applied":
            moved = entry.get("before") != entry.get("after")
            if moved:
                print(row("applied", f"{rname:<22} {short(entry['before'])} → {short(entry['after'])}  (+{entry.get('behind') or '?'})", "ok"))
            else:
                print(row("applied", f"{rname:<22} {short(entry['after'])}  (reinstalled, no new commits)", "ok"))
        elif status == "in-sync":
            print(row("in-sync", f"{rname:<22} {short(entry.get('after'))}", "ok"))
        elif status == "refused":
            print(row("REFUSED", f"{rname:<22} {_explain(entry, root, rname)}", "bad"))
        else:
            print(row("FAILED", f"{rname:<22} {_explain(entry, root, rname)}", "bad"))
            step = entry.get(STEP_OF.get(entry.get("reason") or "", ""))
            if isinstance(step, dict) and step.get("tail"):
                print(_tail(step["tail"], 8), file=sys.stderr)
    pruned = (report.get("checks") or {}).get("pruned_symlinks") or []
    if pruned:
        print(row("pruned", f"{len(pruned)} dangling registry link(s): " + ", ".join(os.path.basename(p) for p in pruned[:5])))
    print(row("checks", paint(f"broken symlinks {len(broken)}", "bad" if broken else "ok") + (f" — {', '.join(broken[:3])}" if broken else "")))
    print(row("receipt", str(path)))
    return 0 if ok else 1


# ── audit ───────────────────────────────────────────────────────────────────


def cmd_doctor(state_dir: Path | None, registry_file: str, json_out: bool) -> int:
    state = (state_dir or default_state_dir()).expanduser()
    registry = Path(registry_file).expanduser()
    problems = doctor(state, registry)
    if json_out:
        print(json.dumps({"state_dir": str(state), "problems": problems}, indent=2))
    elif not problems:
        print(f"lightbridge doctor: {state} — {paint('no problems.', 'ok')}")
    else:
        print(f"lightbridge doctor: {paint(f'{len(problems)} problem(s)', 'bad')} in {state}:")
        for problem in problems:
            kind = paint(f"[{problem['kind']}]", "warn")
            print(f"- {kind} {problem['path']}: {problem['detail']}")
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
