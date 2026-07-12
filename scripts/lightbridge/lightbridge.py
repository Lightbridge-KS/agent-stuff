#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resolve a project's .lightbridge config — the "local scope" model.

Personal workflow config never lives inside a repo (collaborators would see it,
or every repo would need a gitignore entry). Instead each project's config sits
in the user-level lightbridge tree, keyed by the project's root path — the same
mechanism Claude Code uses for local-scoped MCP servers:

    ~/.lightbridge/projects/<project-key>/
    ├── config.toml     ← this tool resolves it
    └── handoffs/       ← sibling state (the handoff tool)

Resolution rule (the ONLY implementation — hooks and scripts import this module
rather than reimplementing it):

    repo_root   = `git rev-parse --show-toplevel` of the start dir (fallback: the
                  start dir itself, for non-git projects)
    project-key = repo_root with path separators replaced by `-`
                  (the `~/.claude/projects` encoding; Windows drops the drive colon)
    config      = <state-dir>/<project-key>/config.toml

Every config carries a top-level `root = "/abs/path"` key: the key encoding is
lossy and a moved repo silently orphans its config, so `doctor` needs the
original path to detect staleness. Readers ignore `root`.

    lightbridge path                 # this project's config path (+ exists?)
    lightbridge path --start DIR     # another project's
    lightbridge doctor               # audit the whole tree; exit 1 on problems
    lightbridge doctor --json

Exit codes: 0 ok; 1 under `doctor` when any problem is found; 2 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

DEFAULT_STATE_DIR = "~/.lightbridge/projects"
STATE_DIR_ENV = "LIGHTBRIDGE_STATE_DIR"  # override; exists so readers are testable in isolation
CONFIG_NAME = "config.toml"
DEFAULT_REGISTRY = "~/.lightbridge/repos.toml"
LEGACY_CONFIG_REL = Path(".lightbridge") / CONFIG_NAME  # pre-2026-07 per-repo location


def default_state_dir() -> Path:
    return Path(os.environ.get(STATE_DIR_ENV) or DEFAULT_STATE_DIR).expanduser()


def project_key(path: Path) -> str:
    """Absolute path → project-key, the same encoding `~/.claude/projects` uses."""
    text = str(path.resolve())
    if len(text) > 1 and text[1] == ":":  # Windows drive letter
        text = text[0] + text[2:]
    return text.replace(os.sep, "-").replace("/", "-")


def repo_root(start: Path) -> Path:
    """Project root: git toplevel of `start`; `start` itself when not in a git repo."""
    start = start.expanduser().resolve()
    try:
        proc = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return start
    if proc.returncode != 0 or not proc.stdout.strip():
        return start
    return Path(proc.stdout.strip()).resolve()


def config_path(start: Path, state_dir: Path | None = None) -> Path:
    """Where `start`'s project config lives — whether or not the file exists."""
    state = state_dir or default_state_dir()
    return state / project_key(repo_root(start)) / CONFIG_NAME


def load_config(
    start: Path, state_dir: Path | None = None
) -> tuple[dict | None, Path, str | None]:
    """Read `start`'s project config.

    Returns (config, path, error): (dict, path, None) on success;
    (None, path, None) when the file is absent — the project has not opted in;
    (None, path, reason) when it exists but is unreadable.
    """
    path = config_path(start, state_dir)
    if not path.is_file():
        return None, path, None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")), path, None
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return None, path, str(exc)


def legacy_config(start: Path) -> Path | None:
    """A stray pre-migration `<repo>/.lightbridge/config.toml`, if one exists."""
    candidate = repo_root(start) / LEGACY_CONFIG_REL
    return candidate if candidate.is_file() else None


def legacy_warning(legacy: Path) -> str:
    """The one deprecation line every reader emits — identical text everywhere."""
    return (
        f"WARNING — per-repo lightbridge config is no longer read: {legacy}. "
        f"Migrate it to `lightbridge path` and delete the .lightbridge/ folder."
    )


# ── doctor ──────────────────────────────────────────────────────────────────


def _registry_paths(registry: Path) -> list[Path]:
    """Existing repo paths from the personal registry; empty when absent/unreadable."""
    if not registry.is_file():
        return []
    try:
        data = tomllib.loads(registry.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    repos = data.get("repos")
    if not isinstance(repos, dict):
        return []
    paths = []
    for raw in repos.values():
        if isinstance(raw, str) and raw.strip():
            path = Path(raw).expanduser()
            if path.is_dir():
                paths.append(path)
    return paths


def doctor(state_dir: Path, registry: Path) -> list[dict]:
    """Audit the projects tree. Each problem: {kind, path, detail}."""
    problems: list[dict] = []

    for config in sorted(state_dir.glob(f"*/{CONFIG_NAME}")):
        try:
            data = tomllib.loads(config.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            problems.append(
                {"kind": "unreadable", "path": str(config), "detail": str(exc)}
            )
            continue
        root = data.get("root")
        if not isinstance(root, str) or not root.strip():
            problems.append(
                {
                    "kind": "missing-root",
                    "path": str(config),
                    "detail": "no top-level `root` key — staleness undetectable; add root = \"/abs/path\"",
                }
            )
            continue
        root_path = Path(root).expanduser()
        if not root_path.is_dir():
            problems.append(
                {
                    "kind": "stale",
                    "path": str(config),
                    "detail": f"root {root_path} no longer exists — repo moved or deleted; "
                    "re-key the folder or remove it",
                }
            )
            continue
        if project_key(root_path) != config.parent.name:
            problems.append(
                {
                    "kind": "key-mismatch",
                    "path": str(config),
                    "detail": f"folder key {config.parent.name!r} != key of root "
                    f"({project_key(root_path)!r}) — re-key the folder",
                }
            )

    for repo in _registry_paths(registry):
        legacy = repo / LEGACY_CONFIG_REL
        if legacy.is_file():
            problems.append(
                {
                    "kind": "legacy",
                    "path": str(legacy),
                    "detail": "per-repo config is no longer read — migrate to "
                    f"{state_dir / project_key(repo) / CONFIG_NAME} and delete .lightbridge/",
                }
            )

    return problems


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lightbridge",
        description="Resolve and audit user-level .lightbridge project config.",
        epilog="Exit: 0 ok · 1 doctor found problems · 2 usage.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_path = sub.add_parser("path", help="Print this project's config path.")
    p_path.add_argument(
        "--start",
        default=".",
        help="Directory whose project root is resolved (default: CWD).",
    )
    p_path.add_argument("--json", action="store_true", help="Emit JSON.")

    p_doctor = sub.add_parser("doctor", help="Audit the projects tree for rot.")
    p_doctor.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help=f"Projects state dir (default: ${STATE_DIR_ENV} or {DEFAULT_STATE_DIR}).",
    )
    p_doctor.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY,
        help=f"Personal repo registry, scanned for legacy per-repo configs "
        f"(default: {DEFAULT_REGISTRY}).",
    )
    p_doctor.add_argument("--json", action="store_true", help="Emit JSON.")

    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.command == "path":
        start = Path(args.start).expanduser().resolve()
        root = repo_root(start)
        path = config_path(start)
        legacy = legacy_config(start)
        if args.json:
            print(
                json.dumps(
                    {
                        "root": str(root),
                        "key": project_key(root),
                        "config": str(path),
                        "exists": path.is_file(),
                        "legacy": str(legacy) if legacy else None,
                    },
                    indent=2,
                )
            )
        else:
            status = "exists" if path.is_file() else (
                "absent — bootstrap: see the lightbridge-config skill"
            )
            print(f"{path}  ({status})")
            if legacy:
                print(legacy_warning(legacy), file=sys.stderr)
        return 0

    # doctor
    state_dir = (args.state_dir or default_state_dir()).expanduser()
    registry = Path(args.registry).expanduser()
    problems = doctor(state_dir, registry)
    if args.json:
        print(json.dumps({"state_dir": str(state_dir), "problems": problems}, indent=2))
    elif not problems:
        print(f"lightbridge doctor: {state_dir} — no problems.")
    else:
        print(f"lightbridge doctor: {len(problems)} problem(s) in {state_dir}:")
        for problem in problems:
            print(f"- [{problem['kind']}] {problem['path']}: {problem['detail']}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
