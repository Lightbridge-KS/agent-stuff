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
DEFAULT_GRAPH = "~/.lightbridge/graph.toml"
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


def load_registry(registry: Path) -> tuple[dict[str, str] | None, str | None]:
    """Read the personal name→path repo registry, `~/.lightbridge/repos.toml`.

    The one implementation (issue #18): `repo_links.py` path-loads this module, and
    `lb repos`/`doctor`/`mv` import it, so the registry is read one way everywhere.

    Returns (repos, error):

    * `(None, None)` — the file is absent. This machine has not opted in; callers stay
      silent, since a registry can only exist on the owner's machine.
    * `(None, reason)` — the file exists but is unusable. Two distinct causes, both worth
      surfacing: bad TOML, or **root-level keys with no `[repos]` table** — the
      hand-authoring mistake where names were written without the header. That case must
      not be reported as "nothing registered": the names are sitting in the file, plainly
      visible, and appending a `[repos]` table below them would strand them for good.
    * `({name: raw_path}, None)` — usable. `{}` when the table is missing *and* the file
      holds nothing else, which is the benign "nothing registered yet" state `repos add`
      can fix by creating the header. Values that are not non-blank strings are dropped:
      a non-path cannot be a repo path, and every caller would otherwise re-check.

    Paths are returned exactly as written — expansion and resolution belong to callers,
    so a hand-authored `~` spelling survives (`lb mv` depends on this).
    """
    if not registry.is_file():
        return None, None
    try:
        data = tomllib.loads(registry.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return None, f"unreadable ({exc})"

    repos = data.get("repos")
    if not isinstance(repos, dict):
        stranded = [key for key, value in data.items() if not isinstance(value, dict)]
        if stranded:
            names = ", ".join(sorted(stranded)[:3]) + ("…" if len(stranded) > 3 else "")
            return None, (
                f"missing a [repos] table (found {len(stranded)} root-level key(s): "
                f"{names} — indent them under a [repos] header)"
            )
        return {}, None
    return {k: v for k, v in repos.items() if isinstance(v, str) and v.strip()}, None


def load_graph(graph: Path) -> tuple[dict | None, str | None]:
    """Read the personal cross-repo graph, `~/.lightbridge/graph.toml`.

    The one implementation: `repo_links.py` and the SessionStart hook path-load this
    module, and the `lb graph` verbs import it, so the graph is read one way everywhere
    (the `load_registry` precedent, issue #18).

    Returns (graph, error):

    * `(None, None)` — the file is absent. This machine has not opted in; readers stay
      silent, like an absent registry.
    * `(None, reason)` — the file exists but is unusable (bad TOML, or `types`/`edge`
      holding a shape that is not a table / array of tables).
    * `({"types": {...}, "edges": [...], "skipped": N}, None)` — usable. Each edge is
      normalized to `{from, to, type, from_note, to_note, backlink}` with None for
      absent optionals; entries missing a non-blank `from`/`to`/`type` are dropped and
      counted in `skipped` so callers can surface the loss instead of silently thinning
      the graph. Semantic checks (undeclared types, unregistered names, bad backlink
      modes) belong to `lb graph doctor`, not here.
    """
    if not graph.is_file():
        return None, None
    try:
        data = tomllib.loads(graph.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return None, f"unreadable ({exc})"

    types = data.get("types", {})
    if not isinstance(types, dict) or not all(isinstance(v, dict) for v in types.values()):
        return None, "the [types] table is malformed (each type must be a [types.<name>] table)"
    raw_edges = data.get("edge", [])
    if not isinstance(raw_edges, list):
        return None, "`edge` must be an array of tables ([[edge]] blocks)"

    def _field(entry: dict, key: str) -> str | None:
        value = entry.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    edges: list[dict] = []
    skipped = 0
    for entry in raw_edges:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        frm, to, etype = _field(entry, "from"), _field(entry, "to"), _field(entry, "type")
        if frm is None or to is None or etype is None:
            skipped += 1
            continue
        edges.append(
            {
                "from": frm,
                "to": to,
                "type": etype,
                "from_note": _field(entry, "from_note"),
                "to_note": _field(entry, "to_note"),
                "backlink": _field(entry, "backlink"),
            }
        )
    return {"types": types, "edges": edges, "skipped": skipped}, None


def project_node(graph: dict, name: str) -> dict:
    """Select `name`'s incident edges from a loaded graph — the one projection rule.

    Lives here (data selection, not rendering) because both projection consumers need
    identical semantics: `repo_links.py`/the hook render the injected ego view, and
    `lb graph show NAME` renders the same view for inspection. Formatting stays with
    each caller.

    Returns `{"out": [...], "backlinks": [...], "mentions": [...]}`. Every entry is
    `{other, type, label, note, declared}`:

    * `out` — edges where `name` is `from`; label = the edge type, note = from_note.
    * `backlinks` — incoming edges whose effective backlink mode is `full`;
      label = the type's declared inverse, note = to_note.
    * `mentions` — incoming edges with mode `compact` (callers render these as one
      names-only line). Mode `off` incoming edges are omitted entirely.

    Effective mode: the edge's own `backlink` when it is a valid mode, else the
    type's, else `full`. An undeclared type projects visibly (label falls back to the
    type name, `declared` False, mode full) — rot should surface, not vanish.
    """
    types = graph.get("types", {})
    out: list[dict] = []
    backlinks: list[dict] = []
    mentions: list[dict] = []
    for edge in graph.get("edges", []):
        spec = types.get(edge["type"])
        declared = isinstance(spec, dict)
        if edge["from"] == name:
            out.append(
                {
                    "other": edge["to"],
                    "type": edge["type"],
                    "label": edge["type"],
                    "note": edge["from_note"],
                    "declared": declared,
                }
            )
        elif edge["to"] == name:
            mode = edge["backlink"]
            if mode not in ("full", "compact", "off"):
                mode = spec.get("backlink") if declared else None
            if mode not in ("full", "compact", "off"):
                mode = "full"
            if mode == "off":
                continue
            inverse = spec.get("inverse") if declared else None
            entry = {
                "other": edge["from"],
                "type": edge["type"],
                "label": inverse if isinstance(inverse, str) and inverse else edge["type"],
                "note": edge["to_note"],
                "declared": declared,
            }
            (backlinks if mode == "full" else mentions).append(entry)
    return {"out": out, "backlinks": backlinks, "mentions": mentions}


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
