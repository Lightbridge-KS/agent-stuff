"""Project configuration, its offline dashboard, and project-tree audit commands."""

from __future__ import annotations

import json
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
from lb_fleet import receipt_path
from lb_keys import DEFAULT_KEYS, load_keys
from lb_resolve import (
    DEFAULT_FLEET,
    DEFAULT_GRAPH,
    config_path,
    default_state_dir,
    legacy_config,
    legacy_warning,
    load_config,
    load_fleet,
    load_graph,
    project_key,
    repo_root,
)
from lb_style import paint, row


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
        k
        for k, v in (config or {}).items()
        if k not in SECTIONS and isinstance(v, dict)
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
        print(
            row(
                "config", f"{path}  {paint('(absent — create it with `init`)', 'warn')}"
            )
        )
    else:
        print(row("config", str(path)))
        if sections:
            for name, enabled in sections.items():
                verdict = (
                    paint("enabled", "ok") if enabled else paint("DISABLED", "warn")
                )
                print(row("sections", f"{name}  {verdict}"))
        else:
            print(row("sections", "(none — nothing is enabled yet)"))
        for name in unknown:
            print(
                row(
                    "sections",
                    f"[{name}]  {paint('(unknown — not in the catalog)', 'warn')}",
                )
            )
    print(
        row(
            "state",
            f"handoffs {state['handoffs']} + {state['inbox']} inbox — handoff.py",
        )
    )
    print(row("state", f"plans {state['plans']} — plan_store.py"))
    print(row("state", f"asks {state['asks']} — ask-form / ask-form-qmd"))
    print(
        row(
            "registry",
            f"{registry}  ({'present' if registry.is_file() else 'absent'} — repo_links.py)",
        )
    )
    if graph_error is not None:
        print(
            row(
                "graph",
                f"{graph_path}  {paint(f'(UNREADABLE: {graph_error})', 'bad')}",
                "bad",
            )
        )
    elif graph is None:
        print(
            row(
                "graph",
                f"{graph_path}  {paint('(absent — seed it with `graph init`)', 'dim')}",
            )
        )
    else:
        print(
            row(
                "graph",
                f"{graph_path}  ({len(graph['edges'])} edges, {len(graph['types'])} types "
                f"— repo_links.py)",
            )
        )
    if keys_error is not None:
        print(
            row(
                "keys",
                f"{keys_path}  {paint(f'(UNREADABLE: {keys_error})', 'bad')}",
                "bad",
            )
        )
    elif key_catalog is None:
        print(
            row(
                "keys",
                f"{keys_path}  {paint('(absent — add one with `key add`)', 'dim')}",
            )
        )
    else:
        print(row("keys", f"{keys_path}  ({len(key_catalog)} key(s) — lb key)"))
    if fleet_error is not None:
        print(
            row(
                "fleet",
                f"{fleet_path}  {paint(f'(UNREADABLE: {fleet_error})', 'bad')}",
                "bad",
            )
        )
    elif fleet is None:
        print(
            row(
                "fleet",
                f"{fleet_path}  {paint('(absent — not a hub; seed one with `fleet init`)', 'dim')}",
            )
        )
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
        print(
            f"lightbridge doctor: {paint(f'{len(problems)} problem(s)', 'bad')} in {state}:"
        )
        for problem in problems:
            kind = paint(f"[{problem['kind']}]", "warn")
            print(f"- {kind} {problem['path']}: {problem['detail']}")
    return 1 if problems else 0
