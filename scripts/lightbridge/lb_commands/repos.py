"""Registry commands and the shared registry-opening diagnostic used by graph linking."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lb_registry import REGISTRY_HEADER, REPO_NAME, append_repo, remove_repo
from lb_resolve import load_registry
from lb_style import paint, row


def open_registry(registry_file: str) -> tuple[dict[str, str] | None, Path, str | None]:
    """The shared repos preamble: expanded path + parsed registry (or its error)."""
    registry = Path(registry_file).expanduser()
    repos, error = load_registry(registry)
    if error is not None:
        print(f"registry is unusable: {registry}\n{error}", file=sys.stderr)
    return repos, registry, error


# ── registry ────────────────────────────────────────────────────────────────


def cmd_repos_list(registry_file: str, json_out: bool) -> int:
    repos, registry, error = open_registry(registry_file)
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
            ""
            if Path(raw).expanduser().is_dir()
            else "   " + paint("← MISSING on this machine", "bad")
        )
        print(f"{name:<{width}}  {raw}{missing}")
    return 0


def cmd_repos_add(name: str, path_raw: str, registry_file: str, json_out: bool) -> int:
    repos, registry, error = open_registry(registry_file)
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
        registry.write_text(
            append_repo(REGISTRY_HEADER, name, path_raw), encoding="utf-8"
        )
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
    repos, registry, error = open_registry(registry_file)
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
            json.dumps(
                {"registry": str(registry), "name": name, "changed": True}, indent=2
            )
        )
        return 0
    print(row("updated", str(registry)))
    print(row("removed", name))
    return 0
