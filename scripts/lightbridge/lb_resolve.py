"""Resolve a project's .lightbridge config — the "local scope" model.

**This module is the read path, and the only one hooks and sibling scripts load.**
It is path-loaded via `importlib` `exec_module` from inside `dependencies = []` PEP 723
environments, so two properties are contractual and locked by tests
(`tests/test_lightbridge.py::ResolveModuleContractTest`):

1. **stdlib imports only** — a consumer's env has nothing else installed.
2. **no sibling imports** — relative/sibling imports do not resolve under `exec_module`.

Every writer (rendering, line edits, registry mutation, doctor, mv) is CLI-only and lives
in a sibling module the entrypoint reaches by plain `import`. See
`docs/lightbridge/adr/0001-modular-lightbridge.md`.

Personal workflow config never lives inside a repo (collaborators would see it, or every
repo would need a gitignore entry). Instead each project's config sits in the user-level
lightbridge tree, keyed by the project's root path — the same mechanism Claude Code uses
for local-scoped MCP servers:

    ~/.lightbridge/projects/<project-key>/
    ├── config.toml     ← this module resolves it
    └── handoffs/       ← sibling state (the handoff tool)

Resolution rule (the ONLY implementation — hooks and scripts import this module rather
than reimplementing it):

    repo_root   = `git rev-parse --show-toplevel` of the start dir (fallback: the
                  start dir itself, for non-git projects)
    project-key = repo_root with path separators replaced by `-`
                  (the `~/.claude/projects` encoding; Windows drops the drive colon)
    config      = <state-dir>/<project-key>/config.toml

Every config carries a top-level `root = "/abs/path"` key: the key encoding is lossy and a
moved repo silently orphans its config, so `doctor` needs the original path to detect
staleness. Readers ignore `root`.
"""

from __future__ import annotations

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


def toml_str(value: str) -> str:
    """Serialize `value` as a TOML string — correct for Windows paths.

    A basic string ("...") processes escapes, so a Windows path written naively
    (`root = "C:\\Users\\me"`) makes `\\U` an invalid unicode escape and the whole
    file stops parsing. A literal string ('...') processes nothing, which is what a
    path wants, so it is the default. Fall back to an escaped basic string only for
    the values a literal cannot hold: those containing a single quote or a control
    character. POSIX paths come out identical either way.
    """
    if "'" not in value and not any(ch < " " or ch == "\x7f" for ch in value):
        return f"'{value}'"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def use_utf8_console() -> None:
    """Let a CLI's own output survive a legacy Windows console.

    Windows defaults stdout to the ANSI codepage (cp1252), which cannot encode the
    box-drawing and arrow glyphs these tools print — so `init`/`status` died on a
    UnicodeEncodeError mid-render, after having already written the config. POSIX
    is UTF-8 already, so this is a no-op there.

    **Entry-point only.** Hooks and sibling tools load this module and own their own
    stdout (a JSON contract on it), so reconfiguring at import time would reach into
    theirs. It lives here rather than in the entrypoint because `plan_store.py` and
    `repo_links.py` are entrypoints too and need the same fix.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # not a TextIOWrapper (captured/wrapped) — leave it alone
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass  # already detached or non-reconfigurable; printing is best-effort
