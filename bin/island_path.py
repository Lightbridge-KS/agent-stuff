#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resolve island names to workspace paths — the registry shim for skills-island.

An *island* is a workspace folder that holds many git repos but is not itself a
repo (e.g. `~/my_book`). Its `.claude/skills/` can never be committed anywhere,
so the canonical skills live in the `skills-island` content tree and are
symlinked back in. This script owns the one thing that tree cannot commit: where
each island sits on THIS machine.

    ~/.lightbridge/islands.toml        never committed, per-machine
    root = "~/my_config/skills-island"
    [islands]
    my-book = { path = "~/my_book", harnesses = ["claude", "agents"] }

Harness names index `bin/targets.toml`: `claude` -> `~/.claude/skills` -> the
island-relative `.claude/skills`. Add a harness there and islands can use it.

    island_path.py path my-book       # /Users/kittipos/my_book
    island_path.py targets my-book    # one skills dir per line, for a shell loop
    island_path.py root               # where the skills-island tree lives
    island_path.py list               # every island, with link health

Resolution only. Installing is `install.py --root <tree> --domain <island>
--target <dir>`; this script supplies the `<dir>`s.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

REGISTRY = Path("~/.lightbridge/islands.toml").expanduser()
TARGETS_FILE = Path(__file__).resolve().parent / "targets.toml"


def load_registry() -> dict:
    if not REGISTRY.exists():
        sys.exit(
            f"error: no island registry at {REGISTRY}\n"
            "  create it with:\n"
            '    root = "~/my_config/skills-island"\n'
            "    [islands]\n"
            '    my-book = {{ path = "~/my_book", harnesses = ["claude"] }}'
        )
    with REGISTRY.open("rb") as fh:
        return tomllib.load(fh)


def harness_subdirs() -> dict[str, Path]:
    """targets.toml -> {harness: island-relative skills dir}.

    A target is usable for islands only if its skills dir is under `~/` — that
    prefix is exactly what gets swapped for the island's own root.
    """
    with TARGETS_FILE.open("rb") as fh:
        data = tomllib.load(fh)
    out: dict[str, Path] = {}
    for name, entry in data.items():
        skills = entry.get("skills", "")
        if isinstance(skills, str) and skills.startswith("~/"):
            out[name] = Path(skills[2:])
    return out


def get_island(reg: dict, name: str) -> dict:
    islands = reg.get("islands", {})
    if name not in islands:
        known = ", ".join(sorted(islands)) or "(none)"
        sys.exit(f"error: unknown island '{name}' — registered: {known}")
    entry = islands[name]
    if isinstance(entry, str):  # shorthand: name = "~/path"
        entry = {"path": entry}
    if "path" not in entry:
        sys.exit(f"error: island '{name}' has no `path`")
    return entry


def island_targets(name: str, entry: dict) -> list[Path]:
    root = Path(entry["path"]).expanduser()
    subdirs = harness_subdirs()
    wanted = entry.get("harnesses") or ["claude"]
    targets = []
    for h in wanted:
        if h not in subdirs:
            sys.exit(
                f"error: island '{name}' wants harness '{h}', which is not a "
                f"`~/`-rooted entry in targets.toml — known: {', '.join(sorted(subdirs))}"
            )
        targets.append(root / subdirs[h])
    return targets


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd in ("path", "targets"):
        s = sub.add_parser(cmd)
        s.add_argument("island")
    sub.add_parser("root")
    sub.add_parser("list")
    args = p.parse_args()

    reg = load_registry()

    if args.cmd == "root":
        root = reg.get("root")
        if not root:
            sys.exit(f"error: {REGISTRY} has no top-level `root`")
        print(Path(root).expanduser())
        return

    if args.cmd == "list":
        islands = reg.get("islands", {})
        if not islands:
            print("(no islands registered)")
            return
        for name in sorted(islands):
            entry = get_island(reg, name)
            root = Path(entry["path"]).expanduser()
            mark = "ok     " if root.is_dir() else "MISSING"
            print(f"{mark} {name:<16} {root}")
            for t in island_targets(name, entry):
                links = sorted(t.glob("*")) if t.is_dir() else []
                broken = [x.name for x in links if not x.exists()]
                state = f"{len(links)} link(s)" if t.is_dir() else "absent"
                if broken:
                    state += f", BROKEN: {', '.join(broken)}"
                print(f"          {t}  [{state}]")
        return

    entry = get_island(reg, args.island)
    if args.cmd == "path":
        print(Path(entry["path"]).expanduser())
    else:
        for t in island_targets(args.island, entry):
            print(t)


if __name__ == "__main__":
    main()
