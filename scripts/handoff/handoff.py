#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Cross-repo handoff inbox: list what a repo has been sent, and acknowledge it.

A **same-repo** handoff is *pulled* — the user says "resume", and pickup runs because
someone asked. A **cross-repo** handoff is *pushed*: repo A writes it into repo B's
project-key because A changed something B depends on. Nothing prompts B to look. Without
an inbox it is a letter with no postman, and a `breaking: true` flag nobody reads is worth
nothing.

This is the deterministic core. `hooks/handoff-inject` is the thin wiring that surfaces the
unread ones at SessionStart; the agent (or a human) can also drive this by hand:

    handoff.py                 # list unread cross-repo handoffs for this repo
    handoff.py --all           # ...including ones already acknowledged
    handoff.py --ack <file>    # mark one read (accepts a bare filename or a path)
    handoff.py --ack-all
    handoff.py --json          # machine-readable, for an agent

Cross-repo is detected by the `from:` block in the handoff's frontmatter — its presence IS
the signal (handoff skill, v2026-07-11). Same-repo handoffs are deliberately ignored here:
they are pulled on demand, and injecting them every session would fight the harness's own
context management and could resurrect a plan the session already moved past.

State lives in `<handoffs>/.acked` — one filename per line. It is durable on purpose: an
agent merely *seeing* a notice once is not an acknowledgement, and a notice that re-fires
forever is a notice that gets tuned out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_STATE_DIR = "~/.lightbridge/projects"
STATE_DIR_ENV = "LIGHTBRIDGE_STATE_DIR"  # override; exists so the hook is testable in isolation
ACK_FILE = ".acked"


def default_state_dir() -> Path:
    return Path(os.environ.get(STATE_DIR_ENV) or DEFAULT_STATE_DIR).expanduser()


def project_key(path: Path) -> str:
    """Absolute path → project-key, the same encoding `~/.claude/projects` uses."""
    text = str(path.resolve())
    if len(text) > 1 and text[1] == ":":  # Windows drive letter
        text = text[0] + text[2:]
    return text.replace(os.sep, "-").replace("/", "-")


def handoffs_dir(cwd: Path, state_dir: Path) -> Path:
    return state_dir / project_key(cwd) / "handoffs"


def parse_frontmatter(text: str) -> dict:
    """
    Minimal YAML-ish frontmatter reader — enough for the handoff schema, no dependency.

    Understands top-level `key: value` and the one nested block the schema defines (`from:`).
    Anything it cannot parse is skipped rather than raised: a malformed handoff should not
    take a session down.
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


def read_acked(directory: Path) -> set[str]:
    try:
        raw = (directory / ACK_FILE).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {line.strip() for line in raw.splitlines() if line.strip()}


def write_acked(directory: Path, names: set[str]) -> None:
    (directory / ACK_FILE).write_text("\n".join(sorted(names)) + "\n", encoding="utf-8")


def collect(cwd: Path, state_dir: Path) -> list[dict]:
    """Every cross-repo handoff addressed to `cwd`, oldest first. Same-repo ones are skipped."""
    directory = handoffs_dir(cwd, state_dir)
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
        if not isinstance(origin, dict) or not origin:
            continue  # same-repo handoff — pulled, not pushed. Not our business.

        found.append(
            {
                "file": path.name,
                "path": str(path),
                "created": meta.get("created", ""),
                "focus": meta.get("focus", ""),
                "from_repo": origin.get("repo", "?"),
                "from_git": origin.get("git", ""),
                "breaking": str(origin.get("breaking", "")).lower() == "true",
                "acked": path.name in acked,
            }
        )

    return found


def render(items: list[dict]) -> str:
    """Compact, scannable, breaking-first. This lands in an agent's context — earn the tokens."""
    breaking = [i for i in items if i["breaking"]]
    plural = "s" if len(items) != 1 else ""
    head = f"Unread cross-repo handoff{plural} addressed to this repo: {len(items)}"
    if breaking:
        head += f"  ({len(breaking)} BREAKING)"

    lines = [head]
    for item in sorted(items, key=lambda i: (not i["breaking"], i["created"])):
        mark = "!! BREAKING" if item["breaking"] else "  "
        origin = item["from_repo"]
        if item["from_git"]:
            origin += f" ({item['from_git']})"
        lines.append(f"{mark} from {origin} · {item['created']}")
        if item["focus"]:
            lines.append(f"     {item['focus']}")
        lines.append(f"     {item['path']}")

    lines.append("")
    lines.append(
        "These were PUSHED here by another repo — nobody asked for them, so read before "
        "assuming context. Start with `## Impact here`; a BREAKING one means this repo needs "
        "a code or ops change to stay correct. Acknowledge with `handoff.py --ack <file>` so "
        "it stops being announced."
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cross-repo handoff inbox for the current repo.",
        epilog="Exit: 0 ok · 1 nothing to ack · 2 usage.",
    )
    parser.add_argument("--cwd", type=Path, default=None, help="Repo to check (default: cwd).")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=default_state_dir(),
        help=f"Lightbridge project state dir (default: ${STATE_DIR_ENV} or {DEFAULT_STATE_DIR}).",
    )
    parser.add_argument("--all", action="store_true", help="Include acknowledged handoffs.")
    parser.add_argument("--json", action="store_true", help="Emit a result object on stdout.")
    parser.add_argument("--ack", metavar="FILE", help="Mark one handoff as read.")
    parser.add_argument("--ack-all", action="store_true", help="Mark every one as read.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    cwd = (args.cwd or Path.cwd()).resolve()
    directory = handoffs_dir(cwd, args.state_dir)
    items = collect(cwd, args.state_dir)

    if args.ack or args.ack_all:
        if not items:
            print("No cross-repo handoffs for this repo.", file=sys.stderr)
            return 1
        acked = read_acked(directory)
        if args.ack_all:
            targets = {i["file"] for i in items}
        else:
            name = Path(args.ack).name
            if name not in {i["file"] for i in items}:
                print(f"Not a handoff for this repo: {name}", file=sys.stderr)
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
        print("No unread cross-repo handoffs for this repo.", file=sys.stderr)
        return 0

    print(render(shown))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
