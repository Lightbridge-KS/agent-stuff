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

    lightbridge init                 # create this project's config (refuses to clobber)
    lightbridge init --sections docs-index,research
    lightbridge add repo-links       # append a section to an existing config
    lightbridge sections             # what can go in a config, and who reads it
    lightbridge path                 # this project's config path (+ exists?)
    lightbridge path --start DIR     # another project's
    lightbridge doctor               # audit the whole tree; exit 1 on problems
    lightbridge doctor --json

Link it onto PATH as `lightbridge` (and `lb`) — see this tool's README.

Exit codes: 0 ok (incl. an idempotent no-op); 1 refused (`doctor` found problems,
`init` would clobber, `add` found no config); 2 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

__version__ = "0.1.0"

DEFAULT_STATE_DIR = "~/.lightbridge/projects"
STATE_DIR_ENV = "LIGHTBRIDGE_STATE_DIR"  # override; exists so readers are testable in isolation
CONFIG_NAME = "config.toml"
DEFAULT_REGISTRY = "~/.lightbridge/repos.toml"
LEGACY_CONFIG_REL = Path(".lightbridge") / CONFIG_NAME  # pre-2026-07 per-repo location

CONFIG_HEADER = """\
# ~/.lightbridge/projects/<project-key>/config.toml — personal workflow config.
# User-level, per-project — NEVER inside the repo ("local scope": the repo stays clean).
# Written by `lightbridge init`; `lightbridge sections` lists what else can go here.
# Opt-in by SECTION presence: a feature is on iff its [section] exists; set
# enabled = false to disable one without deleting it.
# Full spec: the lightbridge-config skill (references/catalog.md).
"""

# The emittable template for every known section. Prose (what each key *means*, the
# defaults, the semantics) stays canonical in the skill's references/catalog.md — this
# holds only what `init`/`add` write. tests/test_lightbridge.py asserts the two agree,
# so a section documented in one and missing from the other is a red test, not a drift.
SECTIONS: dict[str, dict[str, str]] = {
    "docs-index": {
        "purpose": "inject this repo's docs map into context at SessionStart",
        "reader": "hooks/docs-index-inject",
        "block": """\
[docs-index]
enabled = true                     # optional; default true
dir = "docs"                       # docs directory, relative to repo root
exclude = ["archive", "research"]  # subdir names to skip
include = ["CONTEXT.md", "CONTEXT-MAP.md"]  # extra root-level files (default); [] to suppress
""",
    },
    "research": {
        "purpose": "per-project defaults for deep-research sessions",
        "reader": "plugins/research → the research skill (read at plan time)",
        "block": """\
[research]
enabled = true                     # optional; default true
dir = "docs/research"              # parent dir for session folders
output = "markdown"                # markdown | quarto (.bib + @key cites, HTML render)
backends = ["websearch"]           # preference order; probed at plan time when omitted
searcher_model = "sonnet"          # searcher tier; "inherit" to match the session model
verifier_model = "sonnet"          # verifier tier; "inherit" to match the session model
corpus = []                        # local corpus dirs (reserved)
""",
    },
    "plans": {
        "purpose": "file every approved plan mode plan; optionally auto-approve the gate",
        "reader": "hooks/plan-capture + hooks/plan-gate (via scripts/plan-store)",
        "block": """\
[plans]
enabled = true                     # optional; default true
auto_approve = false               # true = skip Claude Code's plan-approval dialog.
                                   # Costs you plan iteration, the post-approval mode
                                   # choice, and the last checkpoint before writes.
                                   # Read hooks/plan-gate/README.md before enabling.
""",
    },
    "repo-links": {
        "purpose": "declare logical links to sibling repos, injected at SessionStart",
        "reader": "hooks/repo-links-inject (resolved via ~/.lightbridge/repos.toml)",
        # `enabled` MUST precede the first [[repo-links.link]] — TOML would otherwise
        # attach it to the last array-of-tables entry rather than to the section.
        "block": """\
[repo-links]
enabled = true                     # optional; default true. Must precede the first link.

[[repo-links.link]]
name = "example-service"           # required; logical name, resolved via ~/.lightbridge/repos.toml
role = "upstream"                  # optional; free-form (upstream, oss-reference, live-test-service, …)
note = "Why this repo matters when working here"  # optional
""",
    },
}


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


# ── bootstrap ───────────────────────────────────────────────────────────────


def detect_sections(root: Path) -> list[str]:
    """Sections a repo's layout obviously wants. Never a guess — only what's on disk."""
    return ["docs-index"] if (root / "docs").is_dir() else []


def present_sections(config: dict) -> set[str]:
    """Known sections already in a parsed config (unknown top-level tables are ignored)."""
    return set(config) & set(SECTIONS)


def render_config(root: Path, names: list[str]) -> str:
    """A whole config file: header, the `root` staleness marker, then each section."""
    parts = [CONFIG_HEADER, f'root = "{root}"\n']
    parts += [SECTIONS[name]["block"] for name in names]
    return "\n".join(parts)


def append_sections(existing: str, names: list[str]) -> str:
    """`existing` plus each section appended at EOF — never rewriting what's there.

    Safe because every block opens with a table header, which ends whatever table the
    file was in.
    """
    text = existing if existing.endswith("\n") else existing + "\n"
    return text + "".join("\n" + SECTIONS[name]["block"] for name in names)


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
            "root": str(root),
            "key": project_key(root),
            "config": str(path),
            "created": created,
            "sections_added": added,
            "sections_skipped": skipped,
            "detected": detected,
        },
        indent=2,
    )


def describe(name: str) -> str:
    return f"{name}  (read by: {SECTIONS[name]['reader']})"


def row(label: str, value: str) -> str:
    """One `label   value` line — every bootstrap label fits the same column."""
    return f"{label:<9} {value}"


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


def section_list(raw: str) -> list[str]:
    """`--sections a,b` → ["a", "b"]; an unknown name is a usage error naming the valid set."""
    names = [name.strip() for name in raw.split(",") if name.strip()]
    unknown = [name for name in names if name not in SECTIONS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown section(s): {', '.join(unknown)} — "
            f"known: {', '.join(sorted(SECTIONS))}"
        )
    return names


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).stem,  # `lb` when invoked through the short PATH shim
        description="Create, resolve, and audit user-level .lightbridge project config.",
        epilog="Exit: 0 ok · 1 refused (doctor problems, init would clobber, add has no "
        "config) · 2 usage.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create this project's config (never clobbers).")
    p_init.add_argument(
        "--sections",
        type=section_list,
        default=None,
        help="Comma-separated sections to write. Omitted: detected from the repo layout.",
    )
    p_init.add_argument(
        "--start",
        default=".",
        help="Directory whose project root is resolved (default: CWD).",
    )
    p_init.add_argument(
        "--dry-run", action="store_true", help="Print the config; write nothing."
    )
    p_init.add_argument("--json", action="store_true", help="Emit JSON.")

    p_add = sub.add_parser("add", help="Append section(s) to an existing config.")
    p_add.add_argument(
        "sections",
        nargs="+",
        choices=sorted(SECTIONS),
        metavar="SECTION",
        help=f"Section(s) to add: {', '.join(sorted(SECTIONS))}.",
    )
    p_add.add_argument(
        "--start",
        default=".",
        help="Directory whose project root is resolved (default: CWD).",
    )
    p_add.add_argument(
        "--dry-run", action="store_true", help="Print what would be appended; write nothing."
    )
    p_add.add_argument("--json", action="store_true", help="Emit JSON.")

    p_sections = sub.add_parser("sections", help="List the known config sections.")
    p_sections.add_argument("--json", action="store_true", help="Emit JSON.")

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


def cmd_sections(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(SECTIONS, indent=2))
        return 0
    width = max(len(name) for name in SECTIONS)
    for name, meta in SECTIONS.items():
        print(f"{name:<{width}}  {meta['purpose']}")
        print(f"{'':<{width}}  → read by {meta['reader']}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    start = Path(args.start).expanduser().resolve()
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
    names = args.sections if args.sections is not None else detected
    text = render_config(root, names)

    if args.dry_run:
        print(text, end="")
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    if args.json:
        print(
            bootstrap_json(
                root, path, created=True, added=names, skipped=[], detected=detected
            )
        )
        return 0

    print(row("created", str(path)))
    print(row("root", str(root)))
    if names:
        why = "  ← detected" if args.sections is None else ""
        for name in names:
            print(row("sections", f"{describe(name)}{why}"))
    else:
        print(row("sections", "(none — `root` only; nothing is enabled yet)"))
    remaining = [name for name in SECTIONS if name not in names]
    if remaining:
        print(row("next", f"add {' '.join(remaining)}"))
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    start = Path(args.start).expanduser().resolve()
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
    added = [name for name in args.sections if name not in present]
    skipped = [name for name in args.sections if name in present]

    if args.dry_run:
        print("".join(SECTIONS[name]["block"] for name in added), end="")
        return 0

    if added:
        path.write_text(
            append_sections(path.read_text(encoding="utf-8"), added), encoding="utf-8"
        )

    if args.json:
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


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.command == "sections":
        return cmd_sections(args)

    if args.command == "init":
        return cmd_init(args)

    if args.command == "add":
        return cmd_add(args)

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
            status = "exists" if path.is_file() else "absent — create it with `init`"
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
