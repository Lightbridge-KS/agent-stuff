#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resolve a project's declared cross-repo links to verified local paths.

Multi-repo work needs the agent to know its neighborhood: where the upstream
counterpart, the live test service, or the OSS reference clone lives on THIS
machine. Two user-level layers — nothing ever lives inside the repo:

  1. Per-project, logical — `~/.lightbridge/projects/<project-key>/config.toml`
     (resolved by `scripts/lightbridge`) declares links by NAME only:

         [repo-links]              # presence of this section = opt in
         enabled = true            # optional; default true. Must precede the links.
         [[repo-links.link]]
         name = "example-service"  # required; resolved via the personal registry
         role = "upstream"         # optional; free-form relationship
         note = "Why this repo matters when working here"  # optional

  2. Per-machine — `~/.lightbridge/repos.toml` maps names to paths:

         [repos]
         example-service = "~/work/example-service"

Each declared link is resolved through the registry, tilde-expanded, and
verified to exist on disk — dead names and stale paths surface as WARNING
lines instead of rotting silently.

    repo-links                       # human map for the repo at CWD
    repo-links --start path/to/repo  # resolve another repo's links
    repo-links --json                # machine-readable (for hooks/tooling)
    repo-links --check               # audit mode: exit 1 if anything is unresolved
    repo-links --registry alt.toml   # nonstandard registry location

Exit codes: 0 on success (warnings included); 1 under --check when any link is
unresolved; 2 when there is nothing to read (no config, no [repo-links] section,
or the section is disabled).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tomllib
from pathlib import Path

LIGHTBRIDGE = Path(__file__).resolve().parents[1] / "lightbridge" / "lightbridge.py"
DEFAULT_REGISTRY = "~/.lightbridge/repos.toml"
REMINDER = (
    "When a task involves a linked repo, work with it at the absolute path above."
)


def load_lightbridge():
    """Import the lightbridge resolver from its file path (single source of truth)."""
    spec = importlib.util.spec_from_file_location("lightbridge", LIGHTBRIDGE)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _as_str(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return None


def parse_links(section: dict) -> tuple[list[dict], list[str]]:
    """Extract valid link dicts from a `[repo-links]` section.

    Returns (links, warnings). Each link is {name, role, note} with role/note
    None when absent. Malformed entries are skipped with a warning; duplicate
    names keep the first occurrence.
    """
    raw = section.get("link")
    if not isinstance(raw, list):
        return [], []

    links: list[dict] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            warnings.append(f"link #{index}: not a table — skipped")
            continue
        name = _as_str(entry.get("name"))
        if name is None:
            warnings.append(f"link #{index}: missing required key 'name' — skipped")
            continue
        if name in seen:
            warnings.append(f"link #{index}: duplicate name '{name}' — first wins")
            continue
        seen.add(name)
        links.append(
            {"name": name, "role": _as_str(entry.get("role")), "note": _as_str(entry.get("note"))}
        )
    return links, warnings


def load_registry(path: Path) -> tuple[dict | None, str | None]:
    """Read the personal name→path registry.

    Returns (registry, error): (None, None) when the file is absent — the
    machine has not opted in, callers stay silent; (None, reason) when the file
    exists but is unusable — that can only happen on the owner's machine, so
    the reason is worth surfacing; ({name: raw_path}, None) otherwise.
    """
    if not path.is_file():
        return None, None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return None, f"unreadable ({exc})"
    repos = data.get("repos")
    if not isinstance(repos, dict):
        return None, "missing a [repos] table"
    return repos, None


def find_aliases(registry: dict, relevant: set[str] | None = None) -> list[str]:
    """
    Names that resolve to the SAME repo — an identity split, and invisible without this check.

    Both names resolve, so nothing ever errors; the registry just quietly says one repo is two.
    That breaks any cross-referencing keyed on the name: a `[repo-links]` link declared in one
    repo as `rmos-inhouse` will not match a handoff whose `from.repo` says `ramaai-inhouse-rmos`,
    even though they are the same clone. An alias is a registry smell, not a resolver error, so
    the resolver has to be told to look for it.

    `relevant` scopes the report to alias groups touching the names a repo actually declares —
    a global registry wart should not nag every unrelated session.
    """
    by_path: dict[str, list[str]] = {}
    for name, raw in registry.items():
        if not isinstance(raw, str):
            continue
        try:
            resolved = str(Path(raw).expanduser().resolve())
        except OSError:
            continue
        by_path.setdefault(resolved, []).append(name)

    warnings: list[str] = []
    for path, names in sorted(by_path.items()):
        if len(names) < 2:
            continue
        if relevant is not None and not relevant.intersection(names):
            continue
        warnings.append(
            f"registry aliases: {', '.join(sorted(names))} all resolve to {path} — "
            f"pick one canonical name; the rest split that repo's identity"
        )
    return warnings


def resolve_links(
    links: list[dict], registry: dict, registry_display: str = DEFAULT_REGISTRY
) -> list[dict]:
    """Resolve each link's name through the registry and verify the path.

    Adds to each link: `path` (tilde-expanded string, or None), `status`
    (ok | unregistered | relative-path | missing | not-a-dir), and `detail`
    (human reason when status != ok). Paths are expanded but NOT resolve()d —
    a symlinked path renders as the user wrote it; is_dir() follows symlinks.
    """
    resolved: list[dict] = []
    for link in links:
        record = dict(link)
        raw = registry.get(link["name"])
        if not isinstance(raw, str) or not raw.strip():
            record.update(
                path=None,
                status="unregistered",
                detail=f"not registered in {registry_display} "
                "(add it there, or fix the name in the project's lightbridge config)",
            )
            resolved.append(record)
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            record.update(
                path=str(path),
                status="relative-path",
                detail=f"registered path '{raw}' is not absolute",
            )
        elif not path.exists():
            record.update(
                path=str(path),
                status="missing",
                detail=f"registered path {path} does not exist (stale registry entry?)",
            )
        elif not path.is_dir():
            record.update(
                path=str(path),
                status="not-a-dir",
                detail=f"registered path {path} is not a directory",
            )
        else:
            record.update(path=str(path), status="ok", detail=None)
        resolved.append(record)
    return resolved


def render_human(
    resolved: list[dict],
    config_warnings: list[str] | None = None,
    registry_error: str | None = None,
    registry_display: str = DEFAULT_REGISTRY,
) -> str:
    """Render the linked-repos map: one line per link, WARNING lines for rot.

    A registry-wide error collapses the map to a single warning line — the
    per-link state is unknowable without a readable registry.
    """
    header = "Linked repos (.lightbridge [repo-links]):"
    if registry_error is not None:
        count = len(resolved)
        noun = "link" if count == 1 else "links"
        return (
            f"{header} WARNING — {registry_display} is {registry_error}; "
            f"{count} declared {noun} not resolved."
        )

    lines = [header]
    for link in resolved:
        if link["status"] == "ok":
            line = f"- {link['name']} → {link['path']}"
            if link["role"]:
                line += f" ({link['role']})"
            if link["note"]:
                line += f" — {link['note']}"
        else:
            line = f"- {link['name']}: WARNING — {link['detail']}"
        lines.append(line)
    for warning in config_warnings or []:
        lines.append(f"- WARNING — {warning}")
    if any(link["status"] == "ok" for link in resolved):
        lines.append("")
        lines.append(REMINDER)
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="repo-links",
        description="Resolve a repo's declared cross-repo links to verified local paths.",
    )
    parser.add_argument(
        "--start",
        default=".",
        help="Directory whose project root (git toplevel) is resolved to the "
        "user-level lightbridge config (default: CWD).",
    )
    parser.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY,
        help=f"Personal name→path registry (default: {DEFAULT_REGISTRY}).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human text."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Audit mode: exit 1 when a declared link is unresolved, or the registry "
        "gives one repo two names.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    start = Path(args.start).expanduser().resolve()

    lb = load_lightbridge()
    if lb is None:
        print(f"repo-links: resolver not found at {LIGHTBRIDGE}.", file=sys.stderr)
        return 2

    config, config_path, error = lb.load_config(start)
    legacy = lb.legacy_config(start)
    if legacy is not None:
        print(lb.legacy_warning(legacy), file=sys.stderr)
    if error is not None:
        print(f"repo-links: {config_path} is unreadable: {error}", file=sys.stderr)
        return 2
    if config is None:
        print(
            f"repo-links: no lightbridge config for this project (expected at "
            f"{config_path}). Bootstrap one — see the lightbridge-config skill.",
            file=sys.stderr,
        )
        return 2

    section = config.get("repo-links")
    if not isinstance(section, dict) or section.get("enabled", True) is False:
        print(
            f"repo-links: no enabled [repo-links] section in {config_path}. "
            "Add one — see the lightbridge-config skill.",
            file=sys.stderr,
        )
        return 2

    links, config_warnings = parse_links(section)
    registry_path = Path(args.registry).expanduser()
    registry, registry_error = load_registry(registry_path)

    if registry is None and registry_error is None:
        resolved: list[dict] = [
            {**link, "path": None, "status": "unregistered", "detail": f"no registry at {registry_path}"}
            for link in links
        ]
    elif registry is None:
        resolved = [
            {**link, "path": None, "status": "unregistered", "detail": f"registry {registry_error}"}
            for link in links
        ]
    else:
        resolved = resolve_links(links, registry, registry_display=args.registry)
        # An alias resolves fine, so it never shows up as a broken link — it has to be looked
        # for. Folded into the warning stream so the SessionStart hook surfaces it too.
        config_warnings = config_warnings + find_aliases(
            registry, relevant={link["name"] for link in links}
        )

    if args.json:
        print(
            json.dumps(
                {
                    "config": str(config_path),
                    "registry": str(registry_path),
                    "registry_found": registry is not None or registry_error is not None,
                    "registry_error": registry_error,
                    "links": resolved,
                    "warnings": config_warnings,
                },
                indent=2,
            )
        )
    elif registry is None and registry_error is None:
        print(
            f"repo-links: {len(links)} link(s) declared, but no registry at "
            f"{registry_path} — create it to resolve them ([repos] table, name = path)."
        )
    else:
        print(
            render_human(
                resolved, config_warnings, registry_error, registry_display=args.registry
            )
        )

    if args.check and (
        any(link["status"] != "ok" for link in resolved) or config_warnings
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
