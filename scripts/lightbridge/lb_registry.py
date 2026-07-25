"""The personal repo registry document — `~/.lightbridge/repos.toml`.

A name → path map, per machine, never committed anywhere; its presence is this machine's
opt-in for `[repo-links]` resolution.

**Write path.** This module owns the three targeted line edits that mutate the registry
(`repos add`, `repos rm`, and `mv`'s path re-spelling), all built on `lb_tomledit`'s span
primitives so comments, ordering, and quoting style survive. *Reading* is
`lb_resolve.load_registry` — it has to live there because `repo_links.py` path-loads that
module, and one registry reader is the point of issue #18.
"""

from __future__ import annotations

import re
from pathlib import Path

from lb_resolve import load_registry
from lb_tomledit import rewrite_path, section_span, toml_str

REGISTRY_HEADER = """\
# ~/.lightbridge/repos.toml — personal name → path repo registry. PER MACHINE, never
# committed anywhere; its presence is this machine's opt-in for [repo-links] resolution.
# Managed by `lightbridge repos add|rm|list`; read by repo_links.py and `lightbridge doctor`.
[repos]
"""

REPO_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")  # a bare TOML key

_REPO_LINE = re.compile(
    r"""^(\s*(?:(?P<bare>[A-Za-z0-9][A-Za-z0-9_-]*)|"(?P<quoted>[^"]+)")\s*=\s*)"""
    r"""(?P<q>['"])(?P<val>.*?)(?P=q)"""
)


def registry_paths(registry: Path) -> list[Path]:
    """Existing repo paths from the personal registry; empty when absent/unreadable."""
    repos, _error = load_registry(registry)
    paths = []
    for raw in (repos or {}).values():
        path = Path(raw).expanduser()
        if path.is_dir():
            paths.append(path)
    return paths


def append_repo(text: str, name: str, path: str) -> str:
    """`text` with `name = "path"` appended inside `[repos]` — a targeted line edit.

    Lands before the block's trailing blank lines; a registry with no `[repos]` header
    gains one at EOF.
    """
    line = f"{name} = {toml_str(path)}\n"
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


def rename_registry_paths(text: str, old: Path, new: Path) -> tuple[str, dict[str, str]]:
    """Rewrite every `[repos]` path equal to or under `old` — targeted line edits.

    Returns (new_text, {name: new_path}). Each entry's quoting style, trailing
    comment, and position survive; untouched lines are byte-identical.
    """
    span = section_span(text, "repos")
    if span is None:
        return text, {}
    lines = text.splitlines(keepends=True)
    changed: dict[str, str] = {}
    for i in range(span[0] + 1, span[1]):
        match = _REPO_LINE.match(lines[i])
        if match is None:
            continue
        new_raw = rewrite_path(match.group("val"), old, new)
        if new_raw is None or new_raw == match.group("val"):
            continue
        quote = match.group("q")
        value = f"{quote}{new_raw}{quote}" if quote not in new_raw else toml_str(new_raw)
        lines[i] = lines[i][: len(match.group(1))] + value + lines[i][match.end() :]
        changed[match.group("bare") or match.group("quoted")] = new_raw
    return "".join(lines), changed
