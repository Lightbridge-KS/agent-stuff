#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""The plan store — durable, project-keyed, status-bearing plans.

Claude Code already writes every plan it drafts to `~/.claude/plans/<codename>.md`.
That store is a *drafting scratchpad*: flat across all repos, randomly named, no
frontmatter, no project key, no outcome. You cannot ask it "what did I approve in
this repo, and did it land?"

This store answers exactly that. It keeps only the plans a human said **yes** to
(`hooks/plan-capture` fires on `PostToolUse(ExitPlanMode)`, which runs *iff* the tool
executed — that is the approval signal), files them under the project they belong to,
and gives each one a lifecycle:

    approved → executing → landed | abandoned | superseded

Artifact contract:

    ~/.lightbridge/projects/<project-key>/plans/<YYYY-MM-DD_HHMM>_<slug>.md

Layer discipline — this is NOT `docs/progress/`. The tracker is shared, committed,
zoomed-out checkbox state that collaborators audit; it belongs in the repo. A plan is
private, zoomed-in, one-off execution detail — which is why Claude Code itself writes
it to a user-level path. This store is the ephemeral layer given a filing system, and
it links *up* to the tracker rather than replacing it.

Usage:
    plan_store.py list [--status S] [--json]   # plans for this project, newest last
    plan_store.py show [<id>]                  # a plan's full text (default: latest)
    plan_store.py status <id> <state>          # move a plan through its lifecycle
    plan_store.py capture                      # file a plan from a hook payload on stdin

`<id>` is a filename stem, any unique prefix of one, or `latest`.

Exit codes: 0 ok; 1 refused (no such plan, ambiguous id, bad state); 2 usage.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PLANS = "plans"
SECTION = "plans"

# The lifecycle. `approved` is where capture puts every plan; the rest are human calls.
STATES = ("approved", "executing", "landed", "abandoned", "superseded")

# Root/key/config resolution is owned by scripts/lightbridge — one implementation for the
# whole ~/.lightbridge tree. Loaded by path, with NO third-party imports, because several
# dep-free `uv run --script` readers (including two SessionStart hooks that must fail open
# fast) exec this module into their own interpreter.
_LIGHTBRIDGE = Path(__file__).resolve().parents[1] / "lightbridge" / "lightbridge.py"
_spec = importlib.util.spec_from_file_location("lightbridge", _LIGHTBRIDGE)
_lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lb)

STATE_DIR_ENV = _lb.STATE_DIR_ENV  # override; exists so readers are testable in isolation
default_state_dir = _lb.default_state_dir
project_key = _lb.project_key
repo_root = _lb.repo_root
load_config = _lb.load_config


# ── locating ────────────────────────────────────────────────────────────────


def plans_dir(cwd: Path, state_dir: Path | None = None) -> Path:
    """Where this project's approved plans live — whether or not any exist yet."""
    state = state_dir or default_state_dir()
    return state / project_key(repo_root(cwd)) / PLANS


def plan_files(cwd: Path, state_dir: Path | None = None) -> list[Path]:
    """Every filed plan, oldest first. Timestamp-prefixed, so lexicographic = chronological."""
    directory = plans_dir(cwd, state_dir)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.md") if p.is_file())


def resolve(cwd: Path, ident: str, state_dir: Path | None = None) -> Path:
    """`<id>` → a plan file. Accepts a full stem, a unique prefix, or `latest`.

    Raises LookupError with a message that names the next move — the caller prints it.
    """
    files = plan_files(cwd, state_dir)
    if not files:
        raise LookupError("no plans filed for this project yet")
    if ident in ("latest", ""):
        return files[-1]
    matches = [p for p in files if p.stem == ident] or [
        p for p in files if p.stem.startswith(ident)
    ]
    if not matches:
        raise LookupError(f"no plan matching {ident!r} — `plan_store.py list` to see them")
    if len(matches) > 1:
        names = ", ".join(p.stem for p in matches[:4])
        raise LookupError(f"{ident!r} is ambiguous: {names}")
    return matches[0]


# ── the artifact ────────────────────────────────────────────────────────────


def slugify(text: str, limit: int = 6) -> str:
    """A filesystem-safe, human-scannable slug from the plan's title."""
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    return "-".join(words[:limit]) or "plan"


def plan_title(body: str) -> str:
    """The plan's first heading — what a human would call it."""
    for line in body.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def git_state(root: Path) -> str:
    """`<branch> @ <short-sha>` (+ ` (dirty)`); `none` outside a repo. Never raises."""
    def git(*args: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return proc.stdout.strip() if proc.returncode == 0 else None

    sha = git("rev-parse", "--short", "HEAD")
    if sha is None:
        return "none"
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "HEAD"
    dirty = " (dirty)" if git("status", "--porcelain") else ""
    return f"{branch} @ {sha}{dirty}"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a filed plan into its flat `key: value` frontmatter and its body."""
    if not text.startswith("---\n"):
        return {}, text
    _, _, rest = text.partition("---\n")
    head, sep, body = rest.partition("\n---\n")
    if not sep:
        return {}, text
    meta = {}
    for line in head.splitlines():
        key, colon, value = line.partition(":")
        if colon:
            meta[key.strip()] = value.strip()
    return meta, body.lstrip("\n")


def render(meta: dict[str, str], body: str) -> str:
    head = "\n".join(f"{k}: {v}" for k, v in meta.items())
    return f"---\n{head}\n---\n\n{body.rstrip()}\n"


# ── capture ─────────────────────────────────────────────────────────────────


def approved_text(payload: dict) -> str:
    """The plan a human actually approved.

    `tool_input.plan` is the *draft* — Claude Code lets the user edit the plan in the
    approval dialog, and the edited version is what gets written to `planFilePath`.
    So the file wins; the draft field is only a fallback when the file is unreadable.
    """
    tool_input = payload.get("tool_input") or {}
    source = tool_input.get("planFilePath")
    if isinstance(source, str) and source:
        try:
            text = Path(source).expanduser().read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            return text
    draft = tool_input.get("plan")
    return draft.strip() if isinstance(draft, str) else ""


def capture(payload: dict, state_dir: Path | None = None) -> Path | None:
    """File an approved plan. Returns its path, or None when the project hasn't opted in.

    Fails open: any missing piece means "not our business", never an exception into a hook.
    """
    cwd = Path(payload.get("cwd") or ".").expanduser()
    config, _path, error = load_config(cwd, state_dir)
    if error or not config:
        return None
    section = config.get(SECTION)
    if not isinstance(section, dict) or section.get("enabled", True) is False:
        return None

    body = approved_text(payload)
    if not body:
        return None

    root = repo_root(cwd)
    now = datetime.now()
    tool_input = payload.get("tool_input") or {}
    source = tool_input.get("planFilePath") or ""

    # Prefer the plan's own H1; fall back to the harness codename ("robust-shore").
    slug = slugify(plan_title(body) or Path(source).stem)

    # `approval` is derived, not passed between hooks: when auto_approve is on, the gate
    # hook always bypasses the dialog, so an approval under that config IS automatic.
    # Stateless — no marker files, nothing to leak or garbage-collect.
    auto = section.get("auto_approve", False) is True

    meta = {
        "project": str(root),
        "created": now.strftime("%Y-%m-%dT%H:%M"),
        "harness": "claude-code",
        "git": git_state(root),
        "status": "approved",
        "approval": "auto" if auto else "human",
        "source": source or "unknown",
        "session": payload.get("session_id") or "unknown",
    }

    directory = plans_dir(cwd, state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{now.strftime('%Y-%m-%d_%H%M')}_{slug}.md"
    suffix = 2
    while target.exists():  # same minute, same title — don't clobber
        target = directory / f"{now.strftime('%Y-%m-%d_%H%M')}_{slug}-{suffix}.md"
        suffix += 1
    target.write_text(render(meta, body), encoding="utf-8")
    return target


# ── commands ────────────────────────────────────────────────────────────────


def cmd_capture(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return 0  # fail open: a malformed payload is not the store's problem
    target = capture(payload, args.state_dir)
    if target and not args.quiet:
        print(target)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = []
    for path in plan_files(Path.cwd(), args.state_dir):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if args.status and meta.get("status") != args.status:
            continue
        rows.append(
            {
                "id": path.stem,
                "title": plan_title(body) or path.stem,
                "status": meta.get("status", "unknown"),
                "approval": meta.get("approval", "unknown"),
                "created": meta.get("created", "unknown"),
                "path": str(path),
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("No plans filed for this project.")
        return 0
    for r in rows:
        print(f"{r['created']}  {r['status']:<10}  {r['id']}")
        print(f"{'':22}{r['title']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    try:
        path = resolve(Path.cwd(), args.id, args.state_dir)
    except LookupError as exc:
        print(f"plan-store: {exc}", file=sys.stderr)
        return 1
    print(path.read_text(encoding="utf-8"), end="")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    if args.state not in STATES:
        print(
            f"plan-store: unknown state {args.state!r} — one of: {', '.join(STATES)}",
            file=sys.stderr,
        )
        return 1
    try:
        path = resolve(Path.cwd(), args.id, args.state_dir)
    except LookupError as exc:
        print(f"plan-store: {exc}", file=sys.stderr)
        return 1
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    was = meta.get("status", "unknown")
    meta["status"] = args.state
    path.write_text(render(meta, body), encoding="utf-8")
    print(f"{path.stem}: {was} → {args.state}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="plan_store.py", description="Durable, project-keyed, approved plans."
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help=f"override the ~/.lightbridge tree (or ${STATE_DIR_ENV})",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="plans for this project, newest last")
    p_list.add_argument("--status", choices=STATES, help="only plans in this state")
    p_list.add_argument("--json", action="store_true", help="machine-readable")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="a plan's full text")
    p_show.add_argument("id", nargs="?", default="latest", help="stem, unique prefix, or `latest`")
    p_show.set_defaults(func=cmd_show)

    p_status = sub.add_parser("status", help="move a plan through its lifecycle")
    p_status.add_argument("id", help="stem, unique prefix, or `latest`")
    p_status.add_argument("state", help=f"one of: {', '.join(STATES)}")
    p_status.set_defaults(func=cmd_status)

    p_cap = sub.add_parser("capture", help="file a plan from a hook payload on stdin")
    p_cap.add_argument("--quiet", action="store_true", help="print nothing on success")
    p_cap.set_defaults(func=cmd_capture)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        raise SystemExit(2)
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
