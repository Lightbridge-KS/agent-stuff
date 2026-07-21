#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Print a compact index of a repo's `docs/` so an agent reads the right doc first.

Walks a docs directory, reads each markdown file's YAML frontmatter, and prints one
line per doc: its path and a short summary, plus any "read when" hints. The intent
is a cheap, token-economical map an agent (or human) scans before coding — then
opens only the docs that match the task at hand.

Frontmatter contract (all optional, but a doc with none is flagged):

    ---
    summary: One line on what this doc covers.
    read_when:
      - touching the cache layer
      - changing database migrations
    ---

`summary` falls back to the standard `description` key when absent, so skill-style
frontmatter is understood too.

    docs-index                      # human index of ./docs
    docs-index --dir documentation  # a different docs dir
    docs-index --json               # machine-readable (for hooks/tooling)
    docs-index --exclude archive,research,vendor
    docs-index --include CONTEXT.md,CONTEXT-MAP.md  # extra root-level files

Exit codes: 0 on success (even if some docs lack a summary); 2 when --dir is missing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

__version__ = "0.1.0"

DEFAULT_EXCLUDES = ("archive", "research")
REMINDER = (
    'When your task matches a "Read when" hint above, read that doc before '
    "coding. Keep docs current: update the doc when behavior changes, and "
    "create one when it is missing."
)


def parse_frontmatter(text: str) -> tuple[dict | None, str | None]:
    """Return (frontmatter_dict, error). Either may be None; never raises."""
    if not text.startswith("---\n"):
        return None, "missing front matter"
    close = text.find("\n---", 4)
    if close == -1:
        return None, "unterminated front matter"
    try:
        data = yaml.safe_load(text[4:close])
    except yaml.YAMLError as exc:
        return None, f"invalid YAML: {exc}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, "front matter is not a mapping"
    return data, None


def as_str(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return None


def as_str_list(value) -> list[str]:
    """Coerce a frontmatter value into a clean list of non-empty strings."""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        text = as_str(item)
        if text:
            out.append(text)
    return out


def walk_markdown(root: Path, excludes: set[str]) -> list[Path]:
    """Sorted relative paths of *.md under root, skipping hidden and excluded dirs."""
    files: list[Path] = []

    def recurse(directory: Path) -> None:
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                if entry.name in excludes:
                    continue
                recurse(entry)
            elif entry.is_file() and entry.suffix == ".md":
                files.append(entry.relative_to(root))

    recurse(root)
    return sorted(files, key=lambda p: p.as_posix())


def extract(full_path: Path, fallback_description: bool = True) -> dict:
    """Pull {summary, read_when, error} from one doc's frontmatter.

    With `fallback_description` (default), an absent `summary` falls back to the
    standard `description` key. The hook path turns this off so website docs
    (Docusaurus/mkdocs/Quarto), which carry `description`, are never surfaced.
    """
    data, error = parse_frontmatter(full_path.read_text(encoding="utf-8"))
    if data is None:
        return {"summary": None, "read_when": [], "error": error}
    summary = as_str(data.get("summary"))
    if summary is None and fallback_description:
        summary = as_str(data.get("description"))
    read_when = as_str_list(data.get("read_when"))
    if summary is None:
        return {"summary": None, "read_when": read_when, "error": "no summary"}
    return {"summary": summary, "read_when": read_when, "error": None}


def build_index(
    docs_dir: Path, excludes: set[str], fallback_description: bool = True
) -> list[dict]:
    entries: list[dict] = []
    for rel in walk_markdown(docs_dir, excludes):
        record = extract(docs_dir / rel, fallback_description=fallback_description)
        record["path"] = rel.as_posix()
        entries.append(record)
    return entries


def index_files(
    root: Path, rel_paths: list[str], fallback_description: bool = True
) -> list[dict]:
    """Index an explicit list of files (relative to `root`), in the given order.

    For root-level docs that live *outside* the docs dir — e.g. `CONTEXT.md` /
    `CONTEXT-MAP.md` / `VISION.md`. Missing files are silently skipped, so a default list can name
    conventional files without forcing every repo to have them. Each entry's `path`
    is the relative path as given.
    """
    entries: list[dict] = []
    for rel in rel_paths:
        full = root / rel
        if not full.is_file():
            continue
        record = extract(full, fallback_description=fallback_description)
        record["path"] = rel
        entries.append(record)
    return entries


def _entry_lines(entry: dict) -> list[str]:
    """Render one index entry: `path — summary` plus a `Read when:` line, or the
    bare path with an error tag when it carries no summary."""
    if entry["summary"]:
        lines = [f"  {entry['path']} — {entry['summary']}"]
        if entry["read_when"]:
            lines.append(f"    Read when: {'; '.join(entry['read_when'])}")
        return lines
    reason = f" [{entry['error']}]" if entry["error"] else ""
    return [f"  {entry['path']}{reason}"]


def render_human(
    entries: list[dict],
    docs_dir: Path,
    omitted: int = 0,
    extra: list[dict] | None = None,
    extra_label: str = "Charter docs (repo root)",
) -> str:
    """Render the index. `omitted` > 0 adds a footer counting docs that exist
    but were dropped from the listing (hook path drops unannotated docs), so
    the map never silently reads as complete when it isn't. `extra` is a second
    group of root-level files (indexed via `index_files`), rendered under
    `extra_label` — used to surface `CONTEXT.md` / `CONTEXT-MAP.md` / `VISION.md`."""
    if not entries and not extra:
        return f"No markdown docs found under {docs_dir}."
    lines: list[str] = []
    if entries:
        lines.append(f"Docs index ({docs_dir}):")
        for e in entries:
            lines.extend(_entry_lines(e))
        if omitted > 0:
            noun = "doc" if omitted == 1 else "docs"
            lines.append(
                f"  (+ {omitted} {noun} without a summary, not listed — "
                f"run docs-index --dir {docs_dir} to see them)"
            )
    if extra:
        if lines:
            lines.append("")
        lines.append(f"{extra_label}:")
        for e in extra:
            lines.extend(_entry_lines(e))
    lines.append("")
    lines.append(REMINDER)
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="docs-index",
        description="Print a compact, read-before-coding index of a repo's docs.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--dir", default="docs", help="Docs directory to index (default: docs)."
    )
    parser.add_argument(
        "--exclude",
        default=",".join(DEFAULT_EXCLUDES),
        help=f"Comma-separated dir names to skip (default: {','.join(DEFAULT_EXCLUDES)}).",
    )
    parser.add_argument(
        "--include",
        default="",
        help="Comma-separated file paths (relative to CWD) to index in addition to "
        "--dir, e.g. CONTEXT.md,CONTEXT-MAP.md. Missing files are skipped.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human text."
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    docs_dir = Path(args.dir).expanduser()
    if not docs_dir.is_dir():
        print(
            f"docs-index: no docs directory at '{docs_dir}'. "
            "Pass --dir to point at one, or create it.",
            file=sys.stderr,
        )
        return 2

    excludes = {part.strip() for part in args.exclude.split(",") if part.strip()}
    entries = build_index(docs_dir, excludes)

    include = [part.strip() for part in args.include.split(",") if part.strip()]
    extra = index_files(Path("."), include)

    if args.json:
        print(
            json.dumps(
                {"dir": docs_dir.as_posix(), "docs": entries, "include": extra},
                indent=2,
            )
        )
    else:
        print(render_human(entries, docs_dir, extra=extra or None))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
