"""Surgical line edits on TOML *text* — never a parse-and-rewrite.

One invariant governs every function here:

    **Lines this module does not target come out byte-identical.**

That is why the tool can promise that comments, key ordering, blank lines, quoting style,
and hand-authored `~`-style paths all survive an `enable`, a `repos add`, or an `mv`
re-keying. A `tomllib`-parse + re-serialize round trip would silently discard every one of
them; TOML has no comment-preserving writer in the stdlib.

The unit of work is the **section span**: a `[header]` line plus the lines up to the next
line whose first non-space character is `[`. That end condition includes `[[header.sub]]`,
which is exactly where TOML stops attaching keys to the section — so a line inserted inside
a span can never land in an array-of-tables entry.

Substrate only: this module knows nothing about `SECTIONS`, the repo registry, or project
keys. Its callers (`lb_catalog`, `lb_registry`, `lb_mv`) supply the meaning.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from lb_resolve import toml_str  # re-exported: every writer here needs it


def terminate(text: str) -> str:
    """`text` with a final newline — the precondition every line insert here assumes.

    `splitlines(keepends=True)` yields an unterminated final element for a file whose last
    line lacks a newline, so a line inserted at the end of that list joins onto the tail of
    the existing one (`a = "x"b = "y"`) — invalid TOML that only the *next* run notices.
    Empty text is left alone: appenders build their own header for that case.
    """
    return text + "\n" if text and not text.endswith("\n") else text


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
    text = terminate(text)
    start, end = section_span(text, name)
    lines = text.splitlines(keepends=True)
    word = "true" if value else "false"
    for i in range(start + 1, end):
        if re.match(r"\s*enabled\s*=", lines[i]):
            lines[i] = re.sub(r"(enabled\s*=\s*)\S+", rf"\g<1>{word}", lines[i], count=1)
            return "".join(lines)
    lines.insert(start + 1, f"enabled = {word}\n")
    return "".join(lines)


def set_root(text: str, root: Path) -> str:
    """`text` with the top-level `root =` line rewritten — a targeted line edit.

    Only lines before the first `[section]` header qualify (that is where TOML keeps
    top-level keys), so a section's own `root` key can never be hit. Every config the
    tool writes has the line (`lb_catalog.render_config`); when absent it is appended at
    EOF as a last resort — doctor's `missing-root` covers flagging that shape.
    """
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("["):
            break
        if re.match(r"\s*root\s*=", line):
            lines[i] = f"root = {toml_str(str(root))}\n"
            return "".join(lines)
    return terminate(text) + f"root = {toml_str(str(root))}\n"


# ── path rewriting (shared by mv's project and registry passes) ──────────────


def norm(path: str | Path) -> Path:
    """The comparison form every mv match uses: expanduser + resolve (non-strict)."""
    return Path(path).expanduser().resolve()


def rewrite_path(raw: str, old: Path, new: Path) -> str | None:
    """`raw` respelled under `new` when it equals or lies under `old`; None when unrelated.

    Matching is on the normalized form; the returned spelling preserves the entry's
    hand-authored style — a `~`-style path stays `~`-style while still under home.
    """
    resolved = norm(raw)
    if not resolved.is_relative_to(old):
        return None
    rel = resolved.relative_to(old)
    target = new if rel == Path(".") else new / rel
    if raw.lstrip().startswith("~"):
        home = norm("~")
        if target == home:
            return "~"
        try:
            return os.path.join("~", str(target.relative_to(home)))
        except ValueError:
            return str(target)
    return str(target)
