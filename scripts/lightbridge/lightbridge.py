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

    lightbridge status               # one-shot dashboard: config, sections, sibling state
    lightbridge init                 # create this project's config (refuses to clobber)
    lightbridge init docs-index research
    lightbridge add repo-links       # append a section to an existing config
    lightbridge show                 # print the stored config; `show SECTION` for one block
    lightbridge enable research      # flip a section's `enabled` in place (or `disable`)
    lightbridge sections             # what can go in a config, and who reads it
    lightbridge path                 # this project's config path (+ exists?)
    lightbridge path --start DIR     # another project's
    lightbridge repos list           # manage ~/.lightbridge/repos.toml (add NAME PATH · rm NAME)
    lightbridge doctor               # audit the whole tree; exit 1 on problems
    lightbridge doctor --json

Link it onto PATH as `lightbridge` (and `lb`) — see this tool's README.

Exit codes: 0 ok (incl. an idempotent no-op); 1 refused (`doctor` found problems or the
config/section/registry entry a verb needs is absent, would clobber, or is unreadable);
2 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

__version__ = "0.2.0"

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


def section_span(text: str, name: str) -> tuple[int, int] | None:
    """Line span [start, end) of the `[name]` block — header included, sub-tables not.

    The block ends at the next line whose first non-space char is `[`, which includes
    `[[name.sub]]` — exactly where TOML stops attaching keys to the section, so a line
    inserted inside the span can never land in an array-of-tables entry.
    """
    lines = text.splitlines(keepends=True)
    header = re.compile(rf"\s*\[{re.escape(name)}\]\s*(#.*)?$")
    for i, line in enumerate(lines):
        if header.match(line):
            for j in range(i + 1, len(lines)):
                if lines[j].lstrip().startswith("["):
                    return i, j
            return i, len(lines)
    return None


def slice_section(text: str, name: str) -> str | None:
    """The `[name]` block verbatim, comments included; None when the header is absent."""
    span = section_span(text, name)
    if span is None:
        return None
    lines = text.splitlines(keepends=True)
    return "".join(lines[span[0] : span[1]])


def set_enabled(text: str, name: str, value: bool) -> str:
    """`text` with `enabled = <value>` set inside `[name]` — a targeted line edit.

    Replaces the value on an existing `enabled =` line (its trailing comment survives);
    inserts one right after the header when the section never had the key. Never a TOML
    rewrite, so comments and layout elsewhere are untouched. Caller guarantees the
    section exists.
    """
    start, end = section_span(text, name)
    lines = text.splitlines(keepends=True)
    word = "true" if value else "false"
    for i in range(start + 1, end):
        if re.match(r"\s*enabled\s*=", lines[i]):
            lines[i] = re.sub(r"(enabled\s*=\s*)\S+", rf"\g<1>{word}", lines[i], count=1)
            return "".join(lines)
    lines.insert(start + 1, f"enabled = {word}\n")
    return "".join(lines)


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


# ── registry (~/.lightbridge/repos.toml) ────────────────────────────────────

REGISTRY_HEADER = """\
# ~/.lightbridge/repos.toml — personal name → path repo registry. PER MACHINE, never
# committed anywhere; its presence is this machine's opt-in for [repo-links] resolution.
# Managed by `lightbridge repos add|rm|list`; read by repo_links.py and `lightbridge doctor`.
[repos]
"""

_REPO_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")  # a bare TOML key


def load_registry(registry: Path) -> tuple[dict[str, str] | None, str | None]:
    """The registry's `[repos]` name→path map.

    Returns (repos, error): (dict, None) on success — `{}` when the table is missing or
    empty; (None, None) when the file is absent; (None, reason) when it is unreadable.
    """
    if not registry.is_file():
        return None, None
    try:
        data = tomllib.loads(registry.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return None, str(exc)
    repos = data.get("repos")
    if not isinstance(repos, dict):
        return {}, None
    return {k: v for k, v in repos.items() if isinstance(v, str) and v.strip()}, None


def append_repo(text: str, name: str, path: str) -> str:
    """`text` with `name = "path"` appended inside `[repos]` — a targeted line edit.

    Lands before the block's trailing blank lines; a registry with no `[repos]` header
    gains one at EOF.
    """
    line = f'{name} = "{path}"\n'
    span = section_span(text, "repos")
    if span is None:
        base = text if text.endswith("\n") else text + "\n"
        return base + "\n[repos]\n" + line
    lines = text.splitlines(keepends=True)
    end = span[1]
    while end > span[0] + 1 and lines[end - 1].strip() == "":
        end -= 1
    lines.insert(end, line)
    return "".join(lines)


def remove_repo(text: str, name: str) -> str | None:
    """`text` without `name`'s line in `[repos]`; None when the line can't be found
    (hand-written key shape this tool doesn't manage — edit the file directly)."""
    span = section_span(text, "repos")
    if span is None:
        return None
    lines = text.splitlines(keepends=True)
    pattern = re.compile(rf'\s*(?:{re.escape(name)}|"{re.escape(name)}")\s*=')
    for i in range(span[0] + 1, span[1]):
        if pattern.match(lines[i]):
            del lines[i]
            return "".join(lines)
    return None


# ── doctor ──────────────────────────────────────────────────────────────────


def _registry_paths(registry: Path) -> list[Path]:
    """Existing repo paths from the personal registry; empty when absent/unreadable."""
    repos, _error = load_registry(registry)
    paths = []
    for raw in (repos or {}).values():
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
        prog=Path(sys.argv[0]).stem,  # `lb` when invoked through the short PATH shim
        description="Create, inspect, and audit user-level .lightbridge project config "
        "— plus the personal repo registry.",
        epilog="Exit: 0 ok · 1 refused (doctor problems, would clobber, missing "
        "config/section/name, unreadable file) · 2 usage. "
        "Siblings (own their state, not wrapped here): plan_store.py (plans/), "
        "handoff.py (handoffs/), repo_links.py ([repo-links] resolution), "
        "docs-index ([docs-index] rendering). Spec: the lightbridge-config skill.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser(
        "status", help="One-shot dashboard: config, sections, sibling state, registry."
    )
    p_status.add_argument(
        "--start",
        default=".",
        help="Directory whose project root is resolved (default: CWD).",
    )
    p_status.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY,
        help=f"Personal repo registry (default: {DEFAULT_REGISTRY}).",
    )
    p_status.add_argument("--json", action="store_true", help="Emit JSON.")

    p_init = sub.add_parser("init", help="Create this project's config (never clobbers).")
    p_init.add_argument(
        "sections",
        nargs="*",
        metavar="SECTION",
        # no `choices`: Python 3.11 argparse rejects zero args against choices
        # ("invalid choice: []"); cmd_init validates instead — same exit 2.
        help=f"Section(s) to write: {', '.join(sorted(SECTIONS))}. "
        "Omitted: detected from the repo layout.",
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

    p_show = sub.add_parser(
        "show", help="Print the stored config, or one section's block, verbatim."
    )
    p_show.add_argument(
        "section",
        nargs="?",
        default=None,
        metavar="SECTION",
        help="Only this section (any table present in the config).",
    )
    p_show.add_argument(
        "--start",
        default=".",
        help="Directory whose project root is resolved (default: CWD).",
    )
    p_show.add_argument("--json", action="store_true", help="Emit JSON (parsed TOML).")

    for verb, sense in (("enable", "true"), ("disable", "false")):
        p_toggle = sub.add_parser(
            verb, help=f"Set `enabled = {sense}` on a section, in place."
        )
        p_toggle.add_argument(
            "section",
            choices=sorted(SECTIONS),
            metavar="SECTION",
            help=f"Section to {verb}: {', '.join(sorted(SECTIONS))}.",
        )
        p_toggle.add_argument(
            "--start",
            default=".",
            help="Directory whose project root is resolved (default: CWD).",
        )
        p_toggle.add_argument("--json", action="store_true", help="Emit JSON.")

    p_repos = sub.add_parser(
        "repos", help="Manage the personal repo registry (never clobbers a name)."
    )
    rsub = p_repos.add_subparsers(dest="repos_command", required=True)
    r_list = rsub.add_parser("list", help="Every registered name → path; dead paths marked.")
    r_add = rsub.add_parser("add", help="Register NAME → PATH (refuses an existing name).")
    r_add.add_argument("name", help="Logical repo name (a bare TOML key).")
    r_add.add_argument("path", help="Local path, ~-relative or absolute; stored as given.")
    r_rm = rsub.add_parser("rm", help="Unregister NAME.")
    r_rm.add_argument("name", help="Registered repo name — see `repos list`.")
    for p_sub in (r_list, r_add, r_rm):
        p_sub.add_argument(
            "--registry",
            default=DEFAULT_REGISTRY,
            help=f"Registry file (default: {DEFAULT_REGISTRY}).",
        )
        p_sub.add_argument("--json", action="store_true", help="Emit JSON.")

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
    unknown = [name for name in args.sections if name not in SECTIONS]
    if unknown:  # argparse `choices` can't do this on 3.11 — see parse_args
        print(
            f"unknown section(s): {', '.join(unknown)} — "
            f"known: {', '.join(sorted(SECTIONS))}",
            file=sys.stderr,
        )
        return 2

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
    names = args.sections or detected
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
        why = "" if args.sections else "  ← detected"
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


def _refuse_missing(config: dict | None, path: Path, error: str | None) -> int | None:
    """The shared show/enable/disable refusals; None when the config is usable."""
    if error is not None:
        print(f"config is unreadable: {path}\n{error}", file=sys.stderr)
        return 1
    if config is None:
        print(f"no config for this project: {path}\nRun `init` first.", file=sys.stderr)
        return 1
    return None


def cmd_show(args: argparse.Namespace) -> int:
    start = Path(args.start).expanduser().resolve()
    config, path, error = load_config(start)

    refused = _refuse_missing(config, path, error)
    if refused is not None:
        return refused

    if args.section is None:
        if args.json:
            print(json.dumps(config, indent=2))
        else:
            print(path.read_text(encoding="utf-8"), end="")
        return 0

    if args.section not in config:
        hint = f"\nAdd it: `add {args.section}`." if args.section in SECTIONS else ""
        print(f"no [{args.section}] in this config: {path}{hint}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({args.section: config[args.section]}, indent=2))
        return 0
    block = slice_section(path.read_text(encoding="utf-8"), args.section)
    if block is None:  # keys exist but no literal [section] header (sub-tables only)
        block = json.dumps({args.section: config[args.section]}, indent=2) + "\n"
    print(block, end="")
    return 0


def cmd_toggle(args: argparse.Namespace, value: bool) -> int:
    start = Path(args.start).expanduser().resolve()
    root = repo_root(start)
    config, path, error = load_config(start)

    refused = _refuse_missing(config, path, error)
    if refused is not None:
        return refused
    if args.section not in present_sections(config):
        print(
            f"no [{args.section}] in this config: {path}\nAdd it: `add {args.section}`.",
            file=sys.stderr,
        )
        return 1

    changed = config[args.section].get("enabled", True) != value
    if changed:
        path.write_text(
            set_enabled(path.read_text(encoding="utf-8"), args.section, value),
            encoding="utf-8",
        )

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "key": project_key(root),
                    "config": str(path),
                    "section": args.section,
                    "enabled": value,
                    "changed": changed,
                },
                indent=2,
            )
        )
        return 0
    print(row("updated" if changed else "unchanged", str(path)))
    print(row("section", f"[{args.section}]  enabled = {'true' if value else 'false'}"))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    start = Path(args.start).expanduser().resolve()
    root = repo_root(start)
    config, path, error = load_config(start)
    registry = Path(args.registry).expanduser()
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

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "key": project_key(root),
                    "config": str(path),
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


def cmd_repos(args: argparse.Namespace) -> int:
    registry = Path(args.registry).expanduser()
    repos, error = load_registry(registry)

    if error is not None:
        print(f"registry is unreadable: {registry}\n{error}", file=sys.stderr)
        return 1

    if args.repos_command == "list":
        if args.json:
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

    if args.repos_command == "add":
        if not _REPO_NAME.match(args.name):
            print(
                f"invalid repo name {args.name!r} — letters, digits, '-', '_' only.",
                file=sys.stderr,
            )
            return 2
        if repos is not None and args.name in repos:
            print(
                f"{args.name!r} is already registered → {repos[args.name]}\n"
                f"`repos rm {args.name}` first, or pick another name.",
                file=sys.stderr,
            )
            return 1
        if repos is None:
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(
                append_repo(REGISTRY_HEADER, args.name, args.path), encoding="utf-8"
            )
        else:
            registry.write_text(
                append_repo(registry.read_text(encoding="utf-8"), args.name, args.path),
                encoding="utf-8",
            )
        if not Path(args.path).expanduser().is_dir():
            print(
                f"note: {args.path} does not exist on this machine (yet) — registered anyway.",
                file=sys.stderr,
            )
        if args.json:
            print(
                json.dumps(
                    {
                        "registry": str(registry),
                        "name": args.name,
                        "path": args.path,
                        "changed": True,
                    },
                    indent=2,
                )
            )
            return 0
        print(row("updated", str(registry)))
        print(row("added", f'{args.name} = "{args.path}"'))
        return 0

    # rm
    if repos is None or args.name not in repos:
        print(f"{args.name!r} is not registered — see `repos list`.", file=sys.stderr)
        return 1
    text = remove_repo(registry.read_text(encoding="utf-8"), args.name)
    if text is None:
        print(
            f"couldn't find {args.name!r}'s line in {registry} — a key shape this tool "
            f"doesn't manage; edit the file directly.",
            file=sys.stderr,
        )
        return 1
    registry.write_text(text, encoding="utf-8")
    if args.json:
        print(
            json.dumps(
                {"registry": str(registry), "name": args.name, "changed": True}, indent=2
            )
        )
        return 0
    print(row("updated", str(registry)))
    print(row("removed", args.name))
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.command == "sections":
        return cmd_sections(args)

    if args.command == "init":
        return cmd_init(args)

    if args.command == "add":
        return cmd_add(args)

    if args.command == "show":
        return cmd_show(args)

    if args.command in ("enable", "disable"):
        return cmd_toggle(args, args.command == "enable")

    if args.command == "status":
        return cmd_status(args)

    if args.command == "repos":
        return cmd_repos(args)

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
