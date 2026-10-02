"""TTY-gated styling for `lb`'s human output — colour for a person, plain bytes for the rest.

One predicate, `styled()`, decides both surfaces: whether `--help` renders as rich panels
(the entrypoint passes `rich_markup_mode="rich"` or None) and whether `paint()` emits ANSI.
An agent's shell, a pipe, a file, and CI are not a TTY, so they get exactly the plain text
they got before styling existed; colour is purely additive — strip the escapes from styled
output and the plain output is what remains (a test locks that). See ADR 0005.

Precedence, first match wins:

    NO_COLOR  (set, non-empty)          → plain   — https://no-color.org
    FORCE_COLOR (set, non-empty, ≠ "0") → styled  — e.g. `FORCE_COLOR=1 lb status | less -R`
    stdout is a TTY, TERM ≠ "dumb"      → styled  (on Windows: only in a VT-capable terminal)
    otherwise                           → plain

CLI-side and stdlib-pure, like every sibling; hooks never load it — their stdout is a
JSON contract that must never carry escapes.
"""

from __future__ import annotations

import os
import sys
from typing import Literal

Tone = Literal["label", "ok", "warn", "bad", "dim"]

# SGR codes: cyan labels; green / yellow / bold-red for good / attention / broken.
_SGR: dict[str, str] = {
    "label": "36",
    "ok": "32",
    "warn": "33",
    "bad": "1;31",
    "dim": "2",
}


def styled() -> bool:
    """Whether stdout gets colour and rich help — evaluated per call, never cached, so a
    test's `redirect_stdout` (or an env change) is honoured immediately."""
    if os.environ.get("NO_COLOR"):
        return False
    force = os.environ.get("FORCE_COLOR")
    if force and force != "0":
        return True
    isatty = getattr(sys.stdout, "isatty", None)
    if not (isatty and isatty()) or os.environ.get("TERM") == "dumb":
        return False
    # A legacy Windows console prints raw escapes; Windows Terminal (WT_SESSION) and the
    # terminals that set TERM / TERM_PROGRAM (Git Bash, VS Code) interpret them.
    if os.name == "nt":
        return any(os.environ.get(v) for v in ("WT_SESSION", "TERM", "TERM_PROGRAM"))
    return True


def paint(text: str, tone: Tone) -> str:
    """`text` in `tone`'s colour when `styled()`, else `text` unchanged.

    Pad before painting (`paint(f"{label:<9}", ...)`): the escapes are zero-width on
    screen but not to `str.format`, so padding a painted string misaligns columns.
    """
    if not styled():
        return text
    return f"\033[{_SGR[tone]}m{text}\033[0m"
