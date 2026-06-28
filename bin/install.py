#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Project these shared skills into one or more agents' skills directories.

The canonical source of truth is `plugins/<domain>/skills/<name>/SKILL.md`. This
installer discovers those skills and either symlinks or copies them into the
directory each agent reads from (skills land flat, keyed by skill name).

The set of known agents is data-driven — see `bin/targets.toml`. Each entry there
gets a matching `--<name>` flag here, and several may be combined in one run.

    uv run bin/install.py --list                       # skills + detected agents
    uv run bin/install.py --claude                     # all skills into ~/.claude/skills
    uv run bin/install.py --claude --codex --pi        # into several agents at once
    uv run bin/install.py --all                        # every agent present on this machine
    uv run bin/install.py --claude coding/example-skill  # one skill
    uv run bin/install.py --claude --domain coding     # a whole plugin/domain
    uv run bin/install.py --all --dry-run              # preview, no writes

Skills are addressed as `<domain>/<skill>`, or by the bare `<skill>` name when it
is unambiguous across domains.

Install mode defaults to `auto`: symlink on macOS/Linux (live edits, zero drift),
copy on Windows where symlinks need elevated/Developer-Mode privileges. Override
with `--mode symlink|copy`. A `--force` replace is guarded so it can never delete
the canonical source if a target happens to resolve to it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT / "plugins"
HOOKS_ROOT = REPO_ROOT / "hooks"
TARGETS_FILE = Path(__file__).resolve().parent / "targets.toml"
SNIPPET_PLACEHOLDER = "ABSOLUTE/PATH/TO/agent-stuff"


def load_targets() -> dict[str, Path]:
    """Read bin/targets.toml -> {agent name: expanded skills dir}."""
    with TARGETS_FILE.open("rb") as fh:
        data = tomllib.load(fh)
    targets: dict[str, Path] = {}
    for name, entry in data.items():
        skills = entry.get("skills") if isinstance(entry, dict) else None
        if not isinstance(skills, str) or not skills.strip():
            sys.exit(f"error: targets.toml: '{name}' is missing a string `skills` path")
        targets[name] = Path(skills).expanduser()
    if not targets:
        sys.exit("error: targets.toml defines no agents")
    return targets


def print_hook_snippets() -> int:
    """Print each hook's settings.json snippet with the absolute path filled in.

    Never edits settings — wiring a hook stays a deliberate, one-time choice.
    """
    snippets = sorted(HOOKS_ROOT.glob("*/hook.json.snippet"))
    if not snippets:
        print("No hooks found under hooks/.", file=sys.stderr)
        return 1
    print(
        "# Merge a block below into ~/.claude/settings.json (user-level, once) "
        "or a repo's\n# .claude/settings.json. Paths are resolved for this checkout.\n"
    )
    for snippet in snippets:
        hook_name = snippet.parent.name
        body = snippet.read_text(encoding="utf-8").replace(
            SNIPPET_PLACEHOLDER, str(REPO_ROOT)
        )
        print(f"# --- {hook_name} ---")
        print(body.rstrip())
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


def resolve_selection(
    tokens: list[str],
    domain: str | None,
    available: dict[str, Path],
) -> tuple[list[str], list[str]]:
    """Resolve user tokens (and an optional --domain) to canonical `<domain>/<skill>` keys.

    Returns (selected_keys, errors). A bare `<skill>` resolves only when unique.
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
        if token in available:  # already `<domain>/<skill>`
            selected.append(token)
        elif "/" in token:
            errors.append(f"unknown skill: {token}")
        else:  # bare `<skill>` name
            matches = by_bare.get(token, [])
            if not matches:
                errors.append(f"unknown skill: {token}")
            elif len(matches) > 1:
                errors.append(
                    f"ambiguous skill '{token}': use one of {', '.join(matches)}"
                )
            else:
                selected.append(matches[0])

    # De-duplicate while preserving order.
    return list(dict.fromkeys(selected)), errors


def parse_args(argv: list[str], registry: dict[str, Path]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install shared skills into one or more agents' skills directories.",
    )
    parser.add_argument(
        "skills",
        nargs="*",
        help="Skills to install as <domain>/<skill> or bare <skill> (default: all).",
    )
    parser.add_argument("--domain", help="Install every skill in this plugin/domain.")
    parser.add_argument(
        "--target", help="Install into a custom directory (cannot combine with agents)."
    )
    agent_group = parser.add_argument_group("agents (from bin/targets.toml)")
    for name, skills_dir in registry.items():
        agent_group.add_argument(
            f"--{name}", action="store_true", help=f"Target {skills_dir}"
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
        help="Print hook settings.json snippets (with paths filled in), then exit.",
    )
    return parser.parse_args(argv)


def resolve_targets(
    args: argparse.Namespace, registry: dict[str, Path]
) -> list[tuple[str, Path]]:
    """Resolve flags to a list of (label, skills_dir) install targets."""
    chosen = [name for name in registry if getattr(args, name, False)]

    if args.target and (chosen or args.all):
        sys.exit("error: --target cannot be combined with agent flags or --all")
    if args.target:
        return [("target", Path(args.target).expanduser())]

    if args.all:
        present = [(name, d) for name, d in registry.items() if is_present(d)]
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
            os.symlink(source, target, target_is_directory=True)
        else:
            shutil.copytree(source, target)

    prefix = f"would {mode}" if dry_run else mode
    print(f"{prefix} {name} -> {target}")


def main(argv: list[str]) -> int:
    registry = load_targets()
    args = parse_args(argv, registry)
    available = available_skills()

    if args.hooks:
        return print_hook_snippets()

    if args.list:
        print("Skills:")
        print("\n".join(f"  {key}" for key in sorted(available)) or "  (none)")
        print("\nAgents (from bin/targets.toml):")
        for name, d in registry.items():
            mark = "present" if is_present(d) else "not detected"
            print(f"  --{name:<8} {d}  [{mark}]")
        return 0

    if not available:
        print("No plugins/*/skills/*/SKILL.md files found.", file=sys.stderr)
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

    for label, target_dir in targets:
        print(f"# {label}: {target_dir}", file=sys.stderr)
        if not args.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
        for key in selected:
            install_one(
                available[key], target_dir, mode, force=args.force, dry_run=args.dry_run
            )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
