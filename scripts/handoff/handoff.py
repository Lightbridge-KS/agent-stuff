#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Handoff storage: a pulled journal, and a pushed inbox.

A repo's handoffs split on **delivery**, not on origin:

    ~/.lightbridge/projects/<project-key>/handoffs/
    ├── 2026-07-09_2233_foundation.md        journal — PULLED. "resume" reads the tail.
    ├── 2026-07-11_0313_tracer-m2.md
    └── inbox/
        ├── .acked
        └── 2026-07-11_1739_dataset-landed.md   inbox — PUSHED. announced, needs ack.

The two are different data structures and were never one collection. The journal is a
chronological log: the newest supersedes the older, pickup reads the tail, nothing is
acknowledged. The inbox is a work queue: every item is independently live, two unread
messages from two repos do not supersede each other, and each needs an explicit ack.

Storing them together forced *every* consumer to filter — and one of them got it wrong:
"resume" took the last file in a flat directory and could hand you an unrelated cross-repo
notification instead of your own work. Splitting on delivery makes that unrepresentable.

**Delivery is not origin.** Cross-repo handoffs are the common inbox case, but not the only
one: a scheduled or background agent leaving a note for the next human session in the *same*
repo is also unsolicited, and belongs in the inbox too. Origin is recorded separately, in the
`from:` frontmatter block — provenance, not routing.

Drive it by hand, or let `hooks/handoff-inject` surface the unread ones at SessionStart:

    handoff.py                 # unread inbox items for this repo
    handoff.py --all           # ...including acknowledged ones
    handoff.py --journal       # path of the latest journal handoff (what "resume" picks up)
    handoff.py --ack <file>    # mark one read
    handoff.py --ack-all
    handoff.py --json          # machine-readable, for an agent

State lives in `<handoffs>/inbox/.acked` — one filename per line, and durable on purpose. An
agent merely *seeing* a notice is not an acknowledgement; a notice that re-fires forever is one
that gets tuned out, which is the exact failure this exists to prevent.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

INBOX = "inbox"
ACK_FILE = ".acked"

# Root/key/config resolution is owned by scripts/lightbridge — one implementation
# for the whole ~/.lightbridge tree (config, handoffs). Keys derive from the git
# toplevel (cwd fallback), so a session launched in a subdir lands on the same key.
_LIGHTBRIDGE = Path(__file__).resolve().parents[1] / "lightbridge" / "lightbridge.py"
_spec = importlib.util.spec_from_file_location("lightbridge", _LIGHTBRIDGE)
_lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lb)

DEFAULT_STATE_DIR = _lb.DEFAULT_STATE_DIR
STATE_DIR_ENV = _lb.STATE_DIR_ENV  # override; exists so the hook is testable in isolation
default_state_dir = _lb.default_state_dir
project_key = _lb.project_key
repo_root = _lb.repo_root


def handoffs_dir(cwd: Path, state_dir: Path) -> Path:
    """The journal: handoffs this repo wrote to its own future sessions."""
    return state_dir / project_key(repo_root(cwd)) / "handoffs"


def inbox_dir(cwd: Path, state_dir: Path) -> Path:
    """The inbox: handoffs pushed at this repo by someone who was not asked."""
    return handoffs_dir(cwd, state_dir) / INBOX


def parse_frontmatter(text: str) -> dict:
    """
    Minimal YAML-ish frontmatter reader — enough for the handoff schema, no dependency.

    Understands top-level `key: value` and the one nested block the schema defines (`from:`).
    Anything it cannot parse is skipped rather than raised: a malformed handoff must not take a
    session down.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}

    data: dict = {}
    block: str | None = None

    for raw in text[3:end].splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        indented = raw[:1] in (" ", "\t")
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip().strip('"').strip("'")

        if indented and block:
            data.setdefault(block, {})[key] = value
            continue

        if not value:  # `from:` — a nested block opens
            block = key
            data.setdefault(key, {})
            continue

        block = None
        data[key] = value

    return data


def _is_true(value) -> bool:
    return str(value).strip().lower() == "true"


def read_acked(directory: Path) -> set[str]:
    try:
        raw = (directory / ACK_FILE).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {line.strip() for line in raw.splitlines() if line.strip()}


def write_acked(directory: Path, names: set[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ACK_FILE).write_text("\n".join(sorted(names)) + "\n", encoding="utf-8")


def collect(cwd: Path, state_dir: Path) -> list[dict]:
    """
    Every inbox item addressed to `cwd`, oldest first.

    No filtering by origin: *everything in the inbox was pushed*, which is the whole point of
    the split. The journal is a different directory and a different question.
    """
    directory = inbox_dir(cwd, state_dir)
    if not directory.is_dir():
        return []

    acked = read_acked(directory)
    found: list[dict] = []

    for path in sorted(directory.glob("*.md")):
        try:
            meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        except OSError:
            continue

        origin = meta.get("from")
        origin = origin if isinstance(origin, dict) else {}

        found.append(
            {
                "file": path.name,
                "path": str(path),
                "created": meta.get("created", ""),
                "focus": meta.get("focus", ""),
                # Provenance. Absent => pushed from within this repo (a scheduled or background
                # agent leaving a note for the next session) — unsolicited all the same.
                "from_repo": origin.get("repo", ""),
                "from_git": origin.get("git", ""),
                # Impact on the DESTINATION — top-level, because it is not a fact about the
                # origin. (`from.breaking` is the pre-split spelling; still honoured, because
                # silently losing this flag is the exact failure class it guards against.)
                "breaking": _is_true(meta.get("breaking", origin.get("breaking", ""))),
                "acked": path.name in acked,
            }
        )

    return found


def latest_journal(cwd: Path, state_dir: Path) -> Path | None:
    """The newest journal handoff — what `resume` picks up. Never an inbox item."""
    directory = handoffs_dir(cwd, state_dir)
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("*.md"))  # non-recursive: inbox/ is a subdir, so it cannot leak
    return files[-1] if files else None


def render(items: list[dict]) -> str:
    """Compact, scannable, breaking-first. This lands in an agent's context — earn the tokens."""
    breaking = [i for i in items if i["breaking"]]
    plural = "s" if len(items) != 1 else ""
    head = f"Unread handoff{plural} in this repo's inbox: {len(items)}"
    if breaking:
        head += f"  ({len(breaking)} BREAKING)"

    lines = [head]
    for item in sorted(items, key=lambda i: (not i["breaking"], i["created"])):
        mark = "!! BREAKING" if item["breaking"] else "  "
        if item["from_repo"]:
            origin = item["from_repo"]
            if item["from_git"]:
                origin += f" ({item['from_git']})"
        else:
            origin = "this repo (background/scheduled session)"
        lines.append(f"{mark} from {origin} · {item['created']}")
        if item["focus"]:
            lines.append(f"     {item['focus']}")
        lines.append(f"     {item['path']}")

    lines.append("")
    # The receiving agent sees ONLY this text (the skill is user-invoked), and it is standing in
    # another repo — so the ack command must carry its own absolute path, and the timing rule
    # (ack after acting, never after merely reading) must travel with it.
    script = Path(__file__).resolve()
    lines.append(
        "These were PUSHED here — nobody asked for them, so read before assuming context. "
        "Start with `## Impact here`; a BREAKING one means this repo needs a code or ops change "
        "to stay correct. Once an item is acted on — or the user consciously declines it — "
        f"acknowledge it: `uv run {script} --ack <file>`. Do not ack an item you have merely "
        "read; an unacked item re-announces every session. "
        "(Your own resumable work is the journal, one level up — this is not that.)"
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Handoff storage for the current repo: a pulled journal, and a pushed inbox.",
        epilog="Exit: 0 ok · 1 nothing to ack · 2 usage.",
    )
    parser.add_argument("--cwd", type=Path, default=None, help="Repo to check (default: cwd).")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help=f"Lightbridge project state dir (default: ${STATE_DIR_ENV} or {DEFAULT_STATE_DIR}).",
    )
    parser.add_argument("--all", action="store_true", help="Include acknowledged inbox items.")
    parser.add_argument(
        "--journal",
        action="store_true",
        help="Print the latest JOURNAL handoff (what `resume` picks up), not the inbox.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a result object on stdout.")
    parser.add_argument("--ack", metavar="FILE", help="Mark one inbox item as read.")
    parser.add_argument("--ack-all", action="store_true", help="Mark every inbox item as read.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    _lb.use_utf8_console()  # CLI-only: hooks importing this module own their own stdout
    args = parse_args(argv)
    cwd = (args.cwd or Path.cwd()).resolve()
    state_dir = args.state_dir or default_state_dir()

    if args.journal:
        latest = latest_journal(cwd, state_dir)
        if latest is None:
            print("No journal handoff for this repo.", file=sys.stderr)
            return 0
        print(latest)
        return 0

    directory = inbox_dir(cwd, state_dir)
    items = collect(cwd, state_dir)

    if args.ack or args.ack_all:
        if not items:
            print("Nothing in this repo's inbox.", file=sys.stderr)
            return 1
        acked = read_acked(directory)
        if args.ack_all:
            targets = {i["file"] for i in items}
        else:
            name = Path(args.ack).name
            if name not in {i["file"] for i in items}:
                print(f"Not an inbox item for this repo: {name}", file=sys.stderr)
                return 1
            targets = {name}
        write_acked(directory, acked | targets)
        for name in sorted(targets):
            print(f"acknowledged: {name}", file=sys.stderr)
        return 0

    shown = items if args.all else [i for i in items if not i["acked"]]

    if args.json:
        print(json.dumps({"handoffs": shown, "count": len(shown)}, indent=2))
        return 0

    if not shown:
        print("Nothing unread in this repo's inbox.", file=sys.stderr)
        return 0

    print(render(shown))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
