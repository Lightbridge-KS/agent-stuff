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
    plan_store.py backfill [--dry-run]         # recover past plans from CC's transcripts

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

__version__ = "0.1.0"

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
        # Name the project. "No plans for this project" cannot be told apart from
        # "you are standing in the wrong directory" — and the wrong directory is the
        # likelier cause, since the store is keyed on the git root of cwd.
        raise LookupError(f"no plans filed for {repo_root(cwd)}")
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


def opted_in(cwd: Path, state_dir: Path | None = None) -> dict | None:
    """The project's `[plans]` section, or None when it hasn't opted in.

    Opt-in is by SECTION PRESENCE — the one rule of the whole .lightbridge tree.
    """
    config, _path, error = load_config(cwd, state_dir)
    if error or not config:
        return None
    section = config.get(SECTION)
    if not isinstance(section, dict) or section.get("enabled", True) is False:
        return None
    return section


def write_plan(
    cwd: Path,
    body: str,
    meta: dict[str, str],
    when: datetime,
    state_dir: Path | None = None,
) -> Path:
    """Write one plan into the project's store. The single place a plan file is created.

    Shared by live capture and backfill so the artifact contract cannot drift between
    the two — a plan recovered from a transcript is the same shape as one filed live.
    """
    slug = slugify(plan_title(body) or Path(meta.get("source", "")).stem)
    directory = plans_dir(cwd, state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = when.strftime("%Y-%m-%d_%H%M")
    target = directory / f"{stamp}_{slug}.md"
    suffix = 2
    while target.exists():  # same minute, same title — don't clobber
        target = directory / f"{stamp}_{slug}-{suffix}.md"
        suffix += 1
    target.write_text(render(meta, body), encoding="utf-8")
    return target


def capture(payload: dict, state_dir: Path | None = None) -> Path | None:
    """File an approved plan. Returns its path, or None when the project hasn't opted in.

    Fails open: any missing piece means "not our business", never an exception into a hook.
    """
    cwd = Path(payload.get("cwd") or ".").expanduser()
    section = opted_in(cwd, state_dir)
    if section is None:
        return None

    body = approved_text(payload)
    if not body:
        return None

    root = repo_root(cwd)
    now = datetime.now()
    source = (payload.get("tool_input") or {}).get("planFilePath") or ""

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
    return write_plan(cwd, body, meta, now, state_dir)


# ── backfill ────────────────────────────────────────────────────────────────
#
# Every plan Claude Code ever drafted is still in ~/.claude/plans/ — but flat, randomly
# named, and project-blind, so the history is unusable. The transcripts under
# ~/.claude/projects/*/*.jsonl can put it back together: each ExitPlanMode tool_use
# record carries `cwd`, `sessionId`, `timestamp`, and `planFilePath`, and the matching
# tool_result says whether the human approved it.
#
# The `cwd` field is what makes this tractable. The two key encodings DIFFER — Claude
# Code writes `-Users-kittipos-my-config-agent-stuff` (underscores → dashes) while
# lightbridge writes `-Users-kittipos-my_config-agent-stuff` (underscores preserved) —
# so decoding a transcript's DIRECTORY NAME back to a path is lossy and wrong. Reading
# `cwd` out of the record sidesteps the whole problem: it is the real absolute path.

CLAUDE_PROJECTS = Path("~/.claude/projects").expanduser()
APPROVED_MARKER = "User has approved your plan"


def _tool_results(record: dict) -> dict[str, str]:
    """tool_use_id → result text, for the user-side records that carry tool results."""
    content = (record.get("message") or {}).get("content")
    if not isinstance(content, list):
        return {}
    results = {}
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "tool_result":
            continue
        tuid = item.get("tool_use_id")
        raw = item.get("content")
        if isinstance(raw, list):  # content can be a list of blocks
            raw = " ".join(b.get("text", "") for b in raw if isinstance(b, dict))
        if isinstance(tuid, str) and isinstance(raw, str):
            results[tuid] = raw
    return results


def scan_transcripts(projects_dir: Path = CLAUDE_PROJECTS) -> list[dict]:
    """Every APPROVED ExitPlanMode call across all Claude Code transcripts.

    Approval is read from the tool_result — the same signal the live hook relies on
    (`PostToolUse` fires iff the tool executed). A plan that was rejected, or one whose
    call never produced a result, is not history worth keeping.
    """
    found: list[dict] = []
    if not projects_dir.is_dir():
        return found

    for transcript in sorted(projects_dir.glob("*/*.jsonl")):
        calls: dict[str, dict] = {}
        results: dict[str, str] = {}
        try:
            with transcript.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # a torn line must not sink the whole transcript
                    if not isinstance(record, dict):
                        continue
                    results.update(_tool_results(record))
                    content = (record.get("message") or {}).get("content")
                    if not isinstance(content, list):
                        continue
                    for item in content:
                        if (
                            not isinstance(item, dict)
                            or item.get("type") != "tool_use"
                            or item.get("name") != "ExitPlanMode"
                        ):
                            continue
                        tuid = item.get("id")
                        source = (item.get("input") or {}).get("planFilePath")
                        if not isinstance(tuid, str) or not isinstance(source, str):
                            continue
                        calls[tuid] = {
                            "cwd": record.get("cwd") or "",
                            "session": record.get("sessionId") or "unknown",
                            "timestamp": record.get("timestamp") or "",
                            "source": source,
                            "draft": (item.get("input") or {}).get("plan") or "",
                        }
        except OSError:
            continue

        for tuid, call in calls.items():
            if APPROVED_MARKER in results.get(tuid, ""):
                found.append(call)
    return found


def _parse_ts(text: str) -> datetime | None:
    """Transcript timestamps are UTC ISO-8601 (`…Z`); file them in LOCAL time."""
    try:
        return (
            datetime.fromisoformat(text.replace("Z", "+00:00"))
            .astimezone()
            .replace(tzinfo=None)
        )
    except (ValueError, TypeError):
        return None


def backfill(
    state_dir: Path | None = None,
    dry_run: bool = False,
    projects_dir: Path = CLAUDE_PROJECTS,
) -> dict:
    """Recover approved plans from Claude Code's transcripts into the lightbridge store.

    Honors opt-in: a project without `[plans]` is SKIPPED, not silently created — the
    one rule of the tree holds even for a bulk import. Skipped projects are reported
    with their plan count so the user can decide where `lb add plans` is worth running.

    Idempotent: a plan whose `source:` is already filed is never filed twice.
    """
    filed: list[Path] = []
    skipped: dict[str, int] = {}   # project root → plans waiting on `lb add plans`
    gone_project: list[str] = []   # the repo itself was moved/renamed/deleted
    gone_content = 0               # plan file deleted AND no draft survived in the transcript
    already = 0

    # Latest approval wins: a plan iterated and re-approved in one session shows up
    # several times against the SAME planFilePath, and the file holds the final text.
    latest: dict[str, dict] = {}
    for call in scan_transcripts(projects_dir):
        prior = latest.get(call["source"])
        if prior is None or call["timestamp"] > prior["timestamp"]:
            latest[call["source"]] = call

    for source, call in sorted(latest.items(), key=lambda kv: kv[1]["timestamp"]):
        cwd = Path(call["cwd"]) if call["cwd"] else None
        if cwd is None or not cwd.exists():
            # The plan survives in ~/.claude/plans; we just have no live project to key
            # it to. Name it rather than folding it into an "unrecoverable" count — a
            # moved repo is a fixable cause, a deleted one is not, and only the user knows.
            gone_project.append(call["cwd"] or "(unknown)")
            continue

        root = repo_root(cwd)
        if opted_in(cwd, state_dir) is None:
            skipped[str(root)] = skipped.get(str(root), 0) + 1
            continue

        try:
            body = Path(source).expanduser().read_text(encoding="utf-8").strip()
        except OSError:
            body = ""
        if not body:
            body = call["draft"].strip()  # the transcript kept a copy; better than losing it
        if not body:
            gone_content += 1
            continue

        # Idempotent on `source:` — re-running backfill must never duplicate.
        existing = {
            parse_frontmatter(p.read_text(encoding="utf-8"))[0].get("source")
            for p in plan_files(cwd, state_dir)
        }
        if source in existing:
            already += 1
            continue

        when = _parse_ts(call["timestamp"]) or datetime.now()
        meta = {
            "project": str(root),
            "created": when.strftime("%Y-%m-%dT%H:%M"),
            "harness": "claude-code",
            # The sha at approval time is not recoverable from the transcript. Say so
            # rather than stamping today's sha, which would be a lie about the past.
            "git": "unknown (backfilled)",
            "status": "approved",
            # Backfilled plans all predate `plan-gate`, so no gate could have bypassed them.
            "approval": "human",
            "source": source,
            "session": call["session"],
            "backfilled": "true",
        }
        if dry_run:
            filed.append(plans_dir(cwd, state_dir) / f"{when:%Y-%m-%d_%H%M}_(dry-run).md")
            continue
        filed.append(write_plan(cwd, body, meta, when, state_dir))

    return {
        "filed": filed,
        "skipped": skipped,
        "gone_project": gone_project,
        "gone_content": gone_content,
        "already": already,
        "approved_total": len(latest),
    }


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
        # Always name the project — see the note in resolve().
        print(f"No plans filed for {repo_root(Path.cwd())}")
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


def cmd_backfill(args: argparse.Namespace) -> int:
    result = backfill(args.state_dir, dry_run=args.dry_run)
    verb = "would file" if args.dry_run else "filed"

    for path in result["filed"]:
        print(f"{verb}  {path}")

    print(
        f"\n{len(result['filed'])} {verb}"
        f" · {result['already']} already filed"
        f" (of {result['approved_total']} approved plans across all transcripts)"
    )

    # Never a silent cap: say exactly what was left behind, and how to claim it.
    if result["skipped"]:
        total = sum(result["skipped"].values())
        print(f"\n{total} skipped — these projects have not opted in:")
        for root, count in sorted(result["skipped"].items(), key=lambda kv: -kv[1]):
            print(f"  {count:>3}  {root}")
        print("\n  Opt one in, then re-run backfill (it is idempotent):")
        print("    cd <project> && lb add plans")

    if result["gone_project"]:
        print(f"\n{len(result['gone_project'])} skipped — project directory no longer exists:")
        for cwd in sorted(set(result["gone_project"])):
            print(f"       {cwd}")
        print("  (the plans survive in ~/.claude/plans; re-run backfill if you restore a repo)")

    if result["gone_content"]:
        print(f"\n{result['gone_content']} lost — plan file deleted and no draft in transcript")
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
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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

    p_bf = sub.add_parser(
        "backfill", help="recover approved plans from Claude Code's transcripts (all projects)"
    )
    p_bf.add_argument("--dry-run", action="store_true", help="report what would be filed")
    p_bf.set_defaults(func=cmd_backfill)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        raise SystemExit(2)
    return args


def main(argv: list[str]) -> int:
    _lb.use_utf8_console()  # CLI-only: hooks importing this module own their own stdout
    args = parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
