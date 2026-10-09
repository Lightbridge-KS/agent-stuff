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

Which skills each agent receives is data too — an optional `profiles.toml` at the
content-tree root (one block per target: `include` / `exclude` globs over
`<domain>/<name>`, or `like = "<target>"`). No file or no block means everything.
Explicit skill names on the command line bypass the profile (with a notice).

    uv run bin/install.py --list                       # skills, agents, and the profile matrix
    uv run bin/install.py --claude                     # the Claude profile into ~/.claude/skills
    uv run bin/install.py --claude --codex --pi        # into several agents at once
    uv run bin/install.py --all                        # every agent present on this machine
    uv run bin/install.py --claude coding/example-skill  # one skill (bypasses the profile)
    uv run bin/install.py --claude mech                # one subagent, same addressing
    uv run bin/install.py --claude --domain coding     # a whole plugin/domain (within the profile)
    uv run bin/install.py --all --dry-run              # preview, no writes
    uv run bin/install.py --all --force --prune        # reconcile: relink + remove de-profiled entries
    uv run bin/install.py --check                      # read-only audit; exit 1 when a registry diverges
    uv run bin/install.py --root ../agent-stuff-private --codex   # a second content-only tree

Skills and subagents share one address space: `<domain>/<name>`, or the bare
`<name>` when it is unambiguous.

Install mode defaults to `auto`: symlink on macOS/Linux (live edits, zero drift),
copy on Windows where symlinks need elevated/Developer-Mode privileges. Override
with `--mode symlink|copy`. A `--force` replace is guarded so it can never delete
the canonical source if a target happens to resolve to it.

Ownership: `--prune` and `--check` only ever touch or report entries this content
tree owns — a symlink whose real path is under `<root>/plugins/`, or (copy mode) a
real entry named in this tree's catalog whose frontmatter `name` matches. Vendored
links, other trees, adopted copies, and harness-owned dirs are foreign and ignored.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT / "plugins"
HOOKS_ROOT = REPO_ROOT / "hooks"
TARGETS_FILE = Path(__file__).resolve().parent / "targets.toml"
PROFILES_FILE = "profiles.toml"

PROFILE_KEYS = {"include", "exclude", "like"}
FRONTMATTER_NAME = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)


def load_targets() -> dict[str, dict[str, Path | None]]:
    """Read bin/targets.toml -> {agent name: {"skills": dir, "agents": dir | None}}.

    `skills` is required. `agents` is optional — its presence is what opts a
    target into receiving subagent files (no key, no subagents, no error).
    """
    with TARGETS_FILE.open("rb") as fh:
        data = tomllib.load(fh)
    targets: dict[str, dict[str, Path | None]] = {}
    for name, entry in data.items():
        if name == "root":
            sys.exit("error: targets.toml: 'root' is reserved (collides with --root)")
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


# ── profiles ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Profile:
    """One target's selection: `<domain>/<name>` globs; exclude beats include."""

    include: tuple[str, ...] = ("*",)
    exclude: tuple[str, ...] = ()

    def selects(self, key: str) -> bool:
        return any(fnmatch.fnmatchcase(key, pat) for pat in self.include) and not any(
            fnmatch.fnmatchcase(key, pat) for pat in self.exclude
        )


DEFAULT_PROFILE = Profile()


def load_profiles(
    root: Path,
    target_names: list[str],
    catalog_keys: set[str] | None = None,
) -> tuple[dict[str, Profile], list[str]]:
    """Read `<root>/profiles.toml` -> ({target: Profile}, errors).

    Absent file -> ({}, []): every target gets everything. The validator and the
    installer share this one loader, so a profile that fails here fails both.
    With `catalog_keys`, every pattern in a non-`like` block must match at least
    one skill — a dead pattern is an error, not a silent no-op.
    """
    path = root / PROFILES_FILE
    if not path.is_file():
        return {}, []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return {}, [f"{PROFILES_FILE}: invalid TOML: {exc}"]

    known = ", ".join(target_names)
    errors: list[str] = []
    blocks: dict[str, dict] = {}
    for name, block in data.items():
        if name not in target_names:
            errors.append(
                f"{PROFILES_FILE}: unknown target '{name}' (known: {known})"
            )
            continue
        if not isinstance(block, dict):
            errors.append(f"{PROFILES_FILE}: [{name}] must be a table")
            continue
        unknown = sorted(set(block) - PROFILE_KEYS)
        if unknown:
            errors.append(
                f"{PROFILES_FILE}: [{name}] unknown key(s): {', '.join(unknown)} "
                "(allowed: include, exclude, like)"
            )
        if "like" in block and ({"include", "exclude"} & set(block)):
            errors.append(
                f"{PROFILES_FILE}: [{name}] 'like' cannot be combined with include/exclude"
            )
        for key in ("include", "exclude"):
            value = block.get(key)
            if value is not None and not (
                isinstance(value, list)
                and all(isinstance(item, str) and item.strip() for item in value)
            ):
                errors.append(
                    f"{PROFILES_FILE}: [{name}] {key} must be a list of non-empty strings"
                )
        like = block.get("like")
        if like is not None and (not isinstance(like, str) or like not in target_names):
            errors.append(
                f"{PROFILES_FILE}: [{name}] like must name a known target (known: {known})"
            )
        blocks[name] = block
    if errors:
        return {}, errors

    if catalog_keys is not None:
        for name, block in blocks.items():
            if "like" in block:
                continue
            for pat in list(block.get("include", [])) + list(block.get("exclude", [])):
                if not any(fnmatch.fnmatchcase(key, pat) for key in catalog_keys):
                    errors.append(
                        f"{PROFILES_FILE}: [{name}] pattern '{pat}' matches no skill"
                    )
        if errors:
            return {}, errors

    profiles: dict[str, Profile] = {}

    def resolve(name: str, chain: list[str]) -> Profile:
        if name in profiles:
            return profiles[name]
        block = blocks.get(name)
        if block is None:  # `like` → a target with no block: everything
            return DEFAULT_PROFILE
        if name in chain:
            errors.append(
                f"{PROFILES_FILE}: 'like' cycle: {' -> '.join(chain + [name])}"
            )
            return DEFAULT_PROFILE
        if "like" in block:
            profile = resolve(block["like"], chain + [name])
        else:
            profile = Profile(
                tuple(block.get("include", ["*"])), tuple(block.get("exclude", []))
            )
        profiles[name] = profile
        return profile

    for name in blocks:
        resolve(name, [])
    if errors:
        return {}, errors
    return profiles, []


def select_for_target(
    target: str, keys: list[str], profiles: dict[str, Profile]
) -> list[str]:
    """The `<domain>/<name>` keys a target receives under its profile (default: all)."""
    profile = profiles.get(target, DEFAULT_PROFILE)
    return [key for key in keys if profile.selects(key)]


# ── ownership ────────────────────────────────────────────────────────────────


def is_under(path: Path, root: Path) -> bool:
    """True when `path` resolves (as far as it can) to somewhere under `root`.

    Works for dangling symlinks too: realpath resolves the parent chain lexically,
    so a link into a renamed skill folder still counts as this tree's.
    """
    real = os.path.realpath(path)
    real_root = os.path.realpath(root)
    return real == real_root or real.startswith(real_root + os.sep)


def frontmatter_name(path: Path) -> str | None:
    """The `name:` of a markdown file's leading `---` block, or None. No YAML dep."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    close = text.find("\n---", 3)
    block = text[3:close] if close != -1 else ""
    match = FRONTMATTER_NAME.search(block)
    return match.group(1).strip().strip("'\"") if match else None


def owned_entries(
    target_dir: Path, plugins_root: Path, catalog_names: set[str]
) -> dict[str, Path]:
    """Entries in `target_dir` that this content tree may prune or report.

    A symlink is owned when its real path is under `plugins_root`. A real dir or
    `.md` file (copy mode) is owned when its name is in `catalog_names` and its
    frontmatter `name` matches — the one place ownership rests on the
    no-name-collision convention rather than on a path. Everything else is
    foreign and never touched.
    """
    if not target_dir.is_dir():
        return {}
    owned: dict[str, Path] = {}
    for entry in sorted(target_dir.iterdir()):
        if entry.is_symlink():
            if is_under(entry, plugins_root):
                owned[entry.name] = entry
        elif entry.name not in catalog_names:
            continue
        elif entry.is_dir():
            if frontmatter_name(entry / "SKILL.md") == entry.name:
                owned[entry.name] = entry
        elif entry.is_file() and entry.suffix == ".md":
            if frontmatter_name(entry) == entry.stem:
                owned[entry.name] = entry
    return owned


def prune_dir(
    target_dir: Path,
    plugins_root: Path,
    wanted_names: set[str],
    catalog_names: set[str],
    *,
    dry_run: bool,
) -> list[str]:
    """Remove owned entries that are not wanted. Returns the pruned entry names."""
    pruned: list[str] = []
    for name, entry in owned_entries(target_dir, plugins_root, catalog_names).items():
        if name in wanted_names:
            continue
        if dry_run:
            print(f"would prune {entry}")
        else:
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
            else:
                shutil.rmtree(entry)
            print(f"prune {entry}")
        pruned.append(name)
    return pruned


def check_dir(
    target_dir: Path,
    plugins_root: Path,
    wanted: dict[str, str],
    catalog_names: set[str],
) -> list[tuple[str, str]]:
    """Compare a registry dir with what the profile wants. Returns (kind, display).

    kinds: missing (wanted, absent) · foreign (wanted, but the name is taken by an
    entry this tree does not own) · broken (owned symlink, dangling) · stray
    (owned, not wanted). `wanted` maps entry name -> display key.
    """
    owned = owned_entries(target_dir, plugins_root, catalog_names)
    findings: list[tuple[str, str]] = []
    for name, key in sorted(wanted.items()):
        entry = target_dir / name
        if name in owned:
            if not entry.exists():
                findings.append(("broken", key))
        elif entry.exists() or entry.is_symlink():
            findings.append(("foreign", key))
        else:
            findings.append(("missing", key))
    for name in sorted(owned):
        if name not in wanted:
            findings.append(("stray", name))
    return findings


# ── hooks ────────────────────────────────────────────────────────────────────


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


# ── catalog + targets ────────────────────────────────────────────────────────


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


def available_skills(plugins_root: Path = PLUGINS_ROOT) -> dict[str, Path]:
    """Map `<domain>/<skill>` -> source folder for every discovered skill."""
    found: dict[str, Path] = {}
    for skill_md in sorted(plugins_root.glob("*/skills/*/SKILL.md")):
        folder = skill_md.parent
        domain = folder.parent.parent.name
        found[f"{domain}/{folder.name}"] = folder
    return found


def available_subagents(plugins_root: Path = PLUGINS_ROOT) -> dict[str, Path]:
    """Map `<domain>/<name>` -> source .md file for every discovered subagent."""
    found: dict[str, Path] = {}
    for agent_md in sorted(plugins_root.glob("*/agents/*.md")):
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
        help="Skills/subagents to install as <domain>/<name> or bare <name> "
        "(default: the target's profile). Explicit names bypass the profile.",
    )
    parser.add_argument("--domain", help="Install everything in this plugin/domain.")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        metavar="DIR",
        help="Content tree to install from (default: this repo). Serves a second "
        "content-only tree with the same plugins/ shape (e.g. agent-stuff-private). "
        "Its profiles.toml, if any, is read from there.",
    )
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
        "--prune", action="store_true",
        help="Remove entries this tree owns that the profile no longer selects.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Read-only: report missing/stray/broken entries per target; exit 1 if any. "
        "Without agent flags, checks every agent present.",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available skills, agents, and the profile matrix, then exit.",
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

    if args.all or (args.check and not chosen):
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


def print_matrix(
    skills: dict[str, Path], registry: dict[str, dict], profiles: dict[str, Profile]
) -> None:
    """Skill × target grid: `x` = the target's profile selects it, `.` = it does not."""
    names = list(registry)
    width = max((len(key) for key in skills), default=5)
    print("\nProfile matrix (x = installed by --all; targets not detected are marked):")
    header = "  " + "skill".ljust(width) + "  " + "  ".join(names)
    print(header)
    for key in sorted(skills):
        cells = []
        for name in names:
            mark = "x" if profiles.get(name, DEFAULT_PROFILE).selects(key) else "."
            cells.append(mark.center(len(name)))
        print("  " + key.ljust(width) + "  " + "  ".join(cells))
    undetected = [name for name, dirs in registry.items() if not is_present(dirs["skills"])]
    if undetected:
        print(f"  (not detected on this machine: {', '.join(undetected)})")


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
    root = args.root.expanduser().resolve()
    plugins_root = root / "plugins"
    skills = available_skills(plugins_root)
    subagents = available_subagents(plugins_root)
    # One address space; the validator forbids a skill and a subagent sharing
    # a `<domain>/<name>` key, so a plain merge is safe.
    available = {**skills, **subagents}

    if args.hooks:
        return print_hook_snippets()

    profiles, profile_errors = load_profiles(root, list(registry), set(skills))
    if profile_errors:
        print("\n".join(profile_errors), file=sys.stderr)
        return 1

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
        if skills:
            print_matrix(skills, registry, profiles)
        return 0

    if not available:
        print(
            f"No plugins/*/skills/*/SKILL.md or plugins/*/agents/*.md files found "
            f"under {plugins_root.parent}.",
            file=sys.stderr,
        )
        return 1

    if args.check and (args.prune or args.force or args.skills or args.domain):
        sys.exit("error: --check is read-only; it cannot combine with --prune, --force, or skill names")

    mode = resolve_mode(args.mode)
    targets = resolve_targets(args, registry)

    explicit: list[str] = []
    token_keys: set[str] = set()
    if args.skills or args.domain:
        explicit, errors = resolve_selection(args.skills, args.domain, available)
        token_keys = set(resolve_selection(args.skills, None, available)[0])
        if errors:
            print("\n".join(errors), file=sys.stderr)
            print(f"available: {', '.join(sorted(available))}", file=sys.stderr)
            return 1

    # Entry names this tree could ever place in a registry (copy-mode ownership).
    catalog_names = {key.split("/", 1)[1] for key in skills} | {
        f"{key.split('/', 1)[1]}.md" for key in subagents
    }

    diverged = False
    for label, dirs in targets:
        print(f"# {label}: {dirs['skills']}", file=sys.stderr)
        profile_keys = set(select_for_target(label, sorted(skills), profiles))
        if explicit:
            # Explicit names bypass the profile; --domain alone stays within it.
            selected = [
                key for key in explicit
                if key in subagents or key in profile_keys or key in token_keys
            ]
            for key in explicit:
                if key in subagents or key in profile_keys:
                    continue
                if key in token_keys:
                    print(f"note: {key} is outside the {label} profile", file=sys.stderr)
                else:
                    print(f"note: {key} excluded by the {label} profile", file=sys.stderr)
        else:
            selected = sorted(profile_keys) + sorted(subagents)

        # What each destination dir should hold: entry name -> display key.
        wanted: dict[Path, dict[str, str]] = {}
        for key in selected:
            source = available[key]
            dest = dirs["agents"] if key in subagents else dirs["skills"]
            if dest is None:
                if not args.check:
                    print(
                        f"no agents dir for {label}, skipping subagent: {key}",
                        file=sys.stderr,
                    )
                continue
            wanted.setdefault(dest, {})[source.name] = key

        dests = list(dict.fromkeys(
            d for d in (dirs["skills"], dirs["agents"]) if d is not None
        ))

        if args.check:
            for dest in dests:
                findings = check_dir(dest, plugins_root, wanted.get(dest, {}), catalog_names)
                for kind, display in findings:
                    diverged = True
                    print(f"{label:<8} {kind:<8} {display}")
            continue

        for key in selected:
            source = available[key]
            dest = dirs["agents"] if key in subagents else dirs["skills"]
            if dest is None:
                continue
            if not args.dry_run:
                dest.mkdir(parents=True, exist_ok=True)
            install_one(source, dest, mode, force=args.force, dry_run=args.dry_run)

        if args.prune:
            for dest in dests:
                prune_dir(
                    dest, plugins_root, set(wanted.get(dest, {})), catalog_names,
                    dry_run=args.dry_run,
                )

    if args.check:
        if diverged:
            print(
                "registries diverge from the profile — reconcile with "
                "`install.py --all --force --prune`",
                file=sys.stderr,
            )
            return 1
        print("registries match the profile", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
