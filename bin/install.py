#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Project shared skills and subagents into one or more agents' directories.

The canonical sources of truth are `plugins/<domain>/skills/<name>/SKILL.md`
(skills — folders) and `plugins/<domain>/agents/<name>.md` (subagents — single
files). This installer discovers both and either symlinks or copies them into
the directories each agent reads from (flat, keyed by bare name). Subagents
only ship to targets whose `targets.toml` entry declares an `agents` dir —
targets without the key are skipped silently by design.

The set of known agents is data-driven — see `bin/targets.toml`. Each entry there
gets a matching `--<name>` flag here, and several may be combined in one run.

    uv run bin/install.py --list                       # skills + detected agents
    uv run bin/install.py --claude                     # all skills into ~/.claude/skills
    uv run bin/install.py --claude --codex --pi        # into several agents at once
    uv run bin/install.py --all                        # every agent present on this machine
    uv run bin/install.py --claude coding/example-skill  # one skill
    uv run bin/install.py --claude mech                # one subagent, same addressing
    uv run bin/install.py --claude --domain coding     # a whole plugin/domain
    uv run bin/install.py --all --dry-run              # preview, no writes

Skills and subagents share one address space: `<domain>/<name>`, or the bare
`<name>` when it is unambiguous.

Install mode defaults to `auto`: symlink on macOS/Linux (live edits, zero drift),
copy on Windows where symlinks need elevated/Developer-Mode privileges. Override
with `--mode symlink|copy`. A `--force` replace is guarded so it can never delete
the canonical source if a target happens to resolve to it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT / "plugins"
HOOKS_ROOT = REPO_ROOT / "hooks"
TARGETS_FILE = Path(__file__).resolve().parent / "targets.toml"


def load_targets() -> dict[str, dict[str, Path | None]]:
    """Read bin/targets.toml -> {agent name: {"skills": dir, "agents": dir | None}}.

    `skills` is required. `agents` is optional — its presence is what opts a
    target into receiving subagent files (no key, no subagents, no error).
    """
    with TARGETS_FILE.open("rb") as fh:
        data = tomllib.load(fh)
    targets: dict[str, dict[str, Path | None]] = {}
    for name, entry in data.items():
        skills = entry.get("skills") if isinstance(entry, dict) else None
        if not isinstance(skills, str) or not skills.strip():
            sys.exit(f"error: targets.toml: '{name}' is missing a string `skills` path")
        agents = entry.get("agents") if isinstance(entry, dict) else None
        if agents is not None and (not isinstance(agents, str) or not agents.strip()):
            sys.exit(f"error: targets.toml: '{name}' has a non-string `agents` path")
        targets[name] = {
            "skills": Path(skills).expanduser(),
            "agents": Path(agents).expanduser() if agents else None,
        }
    if not targets:
        sys.exit("error: targets.toml defines no agents")
    return targets


def render_hook(descriptor: dict, command: str, agent: str) -> dict:
    """Build one agent's registration object from a hook.toml descriptor.

    Both Claude Code and Codex share the SessionStart wire format
    `{hooks: {<event>: [{[matcher], hooks: [{type: command, command, ...}]}]}}`.
    The only per-agent difference is which optional keys are emitted: Codex shows
    `statusMessage`; Claude ignores it, so we omit it there to keep the block clean.
    """
    handler: dict = {"type": "command", "command": command}
    if agent == "codex" and isinstance(descriptor.get("statusMessage"), str):
        handler["statusMessage"] = descriptor["statusMessage"]

    group: dict = {}
    if isinstance(descriptor.get("matcher"), str):
        group["matcher"] = descriptor["matcher"]
    group["hooks"] = [handler]

    return {"hooks": {descriptor["event"]: [group]}}


def render_codex_toml(descriptor: dict, command: str) -> str:
    """Hand-emit the inline `config.toml` form of a hook (one event, one handler)."""
    event = descriptor["event"]
    lines = [f"[[hooks.{event}]]"]
    if isinstance(descriptor.get("matcher"), str):
        lines.append(f"matcher = {json.dumps(descriptor['matcher'])}")
    lines += [
        "",
        f"[[hooks.{event}.hooks]]",
        'type = "command"',
        f"command = {json.dumps(command)}",
    ]
    if isinstance(descriptor.get("statusMessage"), str):
        lines.append(f"statusMessage = {json.dumps(descriptor['statusMessage'])}")
    return "\n".join(lines)


def print_hook_snippets() -> int:
    """Render each hook's registration block for every hook-capable agent.

    The canonical source is `hooks/<name>/hook.toml`; this renders it into Claude
    Code and Codex forms with the command path resolved for this checkout. It only
    PRINTS — wiring a hook stays a deliberate, one-time choice the user makes.
    """
    descriptors = sorted(HOOKS_ROOT.glob("*/hook.toml"))
    if not descriptors:
        print("No hooks found under hooks/.", file=sys.stderr)
        return 1

    print(
        "# Hook registration blocks, paths resolved for this checkout. Nothing below is\n"
        "# written for you. Register each hook ONCE at user level (or per-repo).\n"
        "#\n"
        "# Codex: pick EXACTLY ONE of its two forms (hooks.json OR config.toml) — Codex\n"
        "# warns if both exist in one layer. Then run `/hooks` in Codex to review & trust\n"
        "# it; trust is keyed to the hook's hash, so re-trust after you edit hook.py\n"
        "# (or pass --dangerously-bypass-hook-trust while iterating).\n"
    )
    for path in descriptors:
        hook_name = path.parent.name
        descriptor = tomllib.loads(path.read_text(encoding="utf-8"))
        command = str(path.parent / descriptor["command"])

        print(f"# ===== {hook_name} =====\n")
        print("# --- Claude Code → merge into ~/.claude/settings.json ---")
        print(json.dumps(render_hook(descriptor, command, "claude"), indent=2))
        print("\n# --- Codex → write to ~/.codex/hooks.json ---")
        print(json.dumps(render_hook(descriptor, command, "codex"), indent=2))
        print("\n# --- Codex → OR merge into ~/.codex/config.toml (do not do both) ---")
        print(render_codex_toml(descriptor, command))
        print()
    return 0


def is_present(skills_dir: Path) -> bool:
    """True when this agent looks installed: the parent of its skills dir exists.

    e.g. ~/.claude/skills -> check ~/.claude. Keeps `--all` safe to run anywhere.
    """
    return skills_dir.parent.exists()


def resolve_mode(mode: str) -> str:
    """Resolve `auto` to copy on Windows, symlink elsewhere."""
    if mode != "auto":
        return mode
    return "copy" if os.name == "nt" else "symlink"


def same_real_path(left: Path, right: Path) -> bool:
    """True if both paths resolve to the same real location (guards --force)."""
    try:
        return os.path.realpath(left) == os.path.realpath(right)
    except OSError:
        return False


def available_skills() -> dict[str, Path]:
    """Map `<domain>/<skill>` -> source folder for every discovered skill."""
    found: dict[str, Path] = {}
    for skill_md in sorted(PLUGINS_ROOT.glob("*/skills/*/SKILL.md")):
        folder = skill_md.parent
        domain = folder.parent.parent.name
        found[f"{domain}/{folder.name}"] = folder
    return found


def available_subagents() -> dict[str, Path]:
    """Map `<domain>/<name>` -> source .md file for every discovered subagent."""
    found: dict[str, Path] = {}
    for agent_md in sorted(PLUGINS_ROOT.glob("*/agents/*.md")):
        domain = agent_md.parent.parent.name
        found[f"{domain}/{agent_md.stem}"] = agent_md
    return found


def resolve_selection(
    tokens: list[str],
    domain: str | None,
    available: dict[str, Path],
) -> tuple[list[str], list[str]]:
    """Resolve user tokens (and an optional --domain) to canonical `<domain>/<name>` keys.

    Works over the merged skill + subagent catalog. Returns (selected_keys,
    errors). A bare `<name>` resolves only when unique across the catalog.
    """
    selected: list[str] = []
    errors: list[str] = []

    if domain:
        in_domain = [key for key in available if key.split("/", 1)[0] == domain]
        if not in_domain:
            errors.append(f"unknown domain: {domain}")
        selected.extend(in_domain)

    by_bare: dict[str, list[str]] = {}
    for key in available:
        by_bare.setdefault(key.split("/", 1)[1], []).append(key)

    for token in tokens:
        if token in available:  # already `<domain>/<name>`
            selected.append(token)
        elif "/" in token:
            errors.append(f"unknown skill/subagent: {token}")
        else:  # bare `<name>`
            matches = by_bare.get(token, [])
            if not matches:
                errors.append(f"unknown skill/subagent: {token}")
            elif len(matches) > 1:
                errors.append(
                    f"ambiguous name '{token}': use one of {', '.join(matches)}"
                )
            else:
                selected.append(matches[0])

    # De-duplicate while preserving order.
    return list(dict.fromkeys(selected)), errors


def parse_args(argv: list[str], registry: dict[str, dict]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install shared skills and subagents into one or more agents' directories.",
    )
    parser.add_argument(
        "skills",
        nargs="*",
        help="Skills/subagents to install as <domain>/<name> or bare <name> (default: all).",
    )
    parser.add_argument("--domain", help="Install everything in this plugin/domain.")
    parser.add_argument(
        "--target", help="Install into a custom directory (cannot combine with agents)."
    )
    agent_group = parser.add_argument_group("agents (from bin/targets.toml)")
    for name, dirs in registry.items():
        agent_group.add_argument(
            f"--{name}", action="store_true", help=f"Target {dirs['skills']}"
        )
    parser.add_argument(
        "--all", action="store_true",
        help="Install into every agent present on this machine.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "symlink", "copy"],
        default="auto",
        help="auto (default): symlink on macOS/Linux, copy on Windows.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print actions without changing files."
    )
    parser.add_argument(
        "--force", action="store_true", help="Replace an existing skill at the target."
    )
    parser.add_argument(
        "--list", action="store_true", help="List available skills and agents, then exit."
    )
    parser.add_argument(
        "--hooks", action="store_true",
        help="Print hook registration blocks for Claude & Codex (paths resolved), then exit.",
    )
    return parser.parse_args(argv)


def resolve_targets(
    args: argparse.Namespace, registry: dict[str, dict]
) -> list[tuple[str, dict]]:
    """Resolve flags to a list of (label, {"skills": dir, "agents": dir|None}) targets."""
    chosen = [name for name in registry if getattr(args, name, False)]

    if args.target and (chosen or args.all):
        sys.exit("error: --target cannot be combined with agent flags or --all")
    if args.target:
        # A custom dir receives everything flat — skills and subagents alike.
        custom = Path(args.target).expanduser()
        return [("target", {"skills": custom, "agents": custom})]

    if args.all:
        present = [
            (name, dirs) for name, dirs in registry.items()
            if is_present(dirs["skills"])
        ]
        if not present:
            sys.exit(
                "error: --all found no agents on this machine "
                f"(looked for: {', '.join(registry)}). Use an explicit --<agent>."
            )
        return present

    if chosen:
        return [(name, registry[name]) for name in chosen]

    # Backward-compatible default: Claude Code.
    if "claude" in registry:
        return [("claude", registry["claude"])]
    first = next(iter(registry))
    return [(first, registry[first])]


def install_one(
    source: Path, target_dir: Path, mode: str, *, force: bool, dry_run: bool
) -> None:
    name = source.name
    target = target_dir / name

    if target.exists() or target.is_symlink():
        if not force:
            print(f"exists, skipping: {target}", file=sys.stderr)
            return
        if not target.is_symlink() and same_real_path(source, target):
            print(f"target is source, skipping: {target}", file=sys.stderr)
            return
        if dry_run:
            print(f"remove {target}")
        else:
            if target.is_symlink() or target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target)

    if not dry_run:
        if mode == "symlink":
            os.symlink(source, target, target_is_directory=source.is_dir())
        elif source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    prefix = f"would {mode}" if dry_run else mode
    print(f"{prefix} {name} -> {target}")


def use_utf8_console() -> None:
    """Keep this CLI's own output printable on a legacy Windows console.

    Windows defaults stdout to the ANSI codepage (cp1252), which cannot encode the
    arrows in the `--hooks` registration banner — printing one raised
    UnicodeEncodeError and took the whole command down. POSIX is UTF-8 already, so
    this is a no-op there.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # not a TextIOWrapper (captured/wrapped) — leave it alone
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass  # already detached or non-reconfigurable; printing is best-effort


def main(argv: list[str]) -> int:
    use_utf8_console()
    registry = load_targets()
    args = parse_args(argv, registry)
    skills = available_skills()
    subagents = available_subagents()
    # One address space; the validator forbids a skill and a subagent sharing
    # a `<domain>/<name>` key, so a plain merge is safe.
    available = {**skills, **subagents}

    if args.hooks:
        return print_hook_snippets()

    if args.list:
        print("Skills:")
        print("\n".join(f"  {key}" for key in sorted(skills)) or "  (none)")
        print("\nSubagents:")
        print("\n".join(f"  {key}" for key in sorted(subagents)) or "  (none)")
        print("\nAgents (from bin/targets.toml):")
        for name, dirs in registry.items():
            mark = "present" if is_present(dirs["skills"]) else "not detected"
            agents_note = f", agents: {dirs['agents']}" if dirs["agents"] else ""
            print(f"  --{name:<8} {dirs['skills']}{agents_note}  [{mark}]")
        return 0

    if not available:
        print(
            "No plugins/*/skills/*/SKILL.md or plugins/*/agents/*.md files found.",
            file=sys.stderr,
        )
        return 1

    mode = resolve_mode(args.mode)
    targets = resolve_targets(args, registry)

    if args.skills or args.domain:
        selected, errors = resolve_selection(args.skills, args.domain, available)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            print(f"available: {', '.join(sorted(available))}", file=sys.stderr)
            return 1
    else:
        selected = sorted(available)

    for label, dirs in targets:
        print(f"# {label}: {dirs['skills']}", file=sys.stderr)
        for key in selected:
            if key in subagents:
                dest = dirs["agents"]
                if dest is None:
                    print(
                        f"no agents dir for {label}, skipping subagent: {key}",
                        file=sys.stderr,
                    )
                    continue
            else:
                dest = dirs["skills"]
            if not args.dry_run:
                dest.mkdir(parents=True, exist_ok=True)
            install_one(
                available[key], dest, mode, force=args.force, dry_run=args.dry_run
            )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
