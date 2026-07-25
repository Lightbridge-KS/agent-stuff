"""The verb handlers — one `cmd_*` per CLI verb.

Each takes plain values (never Typer objects), prints the human or `--json` rendering, and
returns the exit code. Keeping them Typer-free is what lets the tests drive every verb
in-process as well as through the real subprocess.

Exit codes: 0 ok (incl. an idempotent no-op); 1 refused (`doctor` found problems or the
config/section/registry entry a verb needs is absent, would clobber, or is unreadable);
2 usage (raised by the parser in `lightbridge.py`, not here).
"""

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
from lb_mv import apply_mv, plan_mv
from lb_registry import REGISTRY_HEADER, REPO_NAME, append_repo, remove_repo
from lb_resolve import (
    DEFAULT_REGISTRY,
    config_path,
    load_registry,
    default_state_dir,
    legacy_config,
    legacy_warning,
    load_config,
    project_key,
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


def cmd_status(start_dir: str, registry_file: str, json_out: bool) -> int:
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
