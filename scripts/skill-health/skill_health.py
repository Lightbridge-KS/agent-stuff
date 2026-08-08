#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.27"]
# ///
"""skill-health — one scheduled sweep over the agent-surface health checks.

The skill surface spans symlink registries, content trees, and vendored binaries that
drift independently. Every one of them already has a deterministic checker; none of them
ran on a schedule. This tool is the scheduler's single entrypoint.

    skill-health                 # human summary; exit 0 green / 1 red
    skill-health --json          # machine report (what an agent reads when repairing)
    skill-health --notify-command ~/bin/notify   # exec on RED only, alert JSON on stdin

Design (docs/skill-health/design.md), in three rules:

  * **Aggregation, never reimplementation.** Each check stays owned by its engine, so
    every invariant has exactly one definition. A check that needs to see more is fixed
    in *its* tool, not here.
  * **Report-only.** No repair action, ever — `skill-vendor sync` relinks registries and
    moves worktrees, which is not something to run unattended.
  * **Deterministic.** No model is involved in noticing that something broke. Reasoning
    enters afterwards, when an agent re-runs `--json` and works from the findings.

Exit: 0 all green · 1 at least one check red · 2 usage/internal error. The per-checker
nuance (skew vs broken) survives in the JSON; the process code collapses to
did-anything-fail, because that is the only question a scheduler or notifier asks.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

__version__ = "0.1.0"

HOME_ENV = "SKILL_HEALTH_HOME"  # override; exists so the tool is testable in isolation
DEFAULT_HOME = "~/.lightbridge"
REPORT_RELPATH = ("health", "skill-health.json")

OK, RED, ERROR = 0, 1, 2

# launchd hands a job a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin), so the tools this
# one shells out to — all of them user-installed — would vanish at 10:07 on a Saturday
# while working perfectly by hand. A health checker that fails that way is worse than
# none, so resolve against the real install dirs regardless of who invoked us.
EXTRA_PATH = ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin")

# Report detail is trimmed: a notifier pushes this to a phone, and an agent pays tokens
# for it. Enough to name the offender, not enough to dump a build log.
DETAIL_LINES = 20
DETAIL_CHARS = 2000

STATUS_OK = "ok"
STATUS_RED = "red"
STATUS_SKIPPED = "skipped"  # tree absent on this machine — not a failure


def default_home() -> Path:
    return Path(os.environ.get(HOME_ENV) or DEFAULT_HOME).expanduser()


def repo_root() -> Path:
    """agent-stuff root — scripts/skill-health/skill_health.py → ../../"""
    return Path(__file__).resolve().parents[2]


def search_path() -> str:
    """PATH with the user install dirs guaranteed present. See EXTRA_PATH."""
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    for extra in EXTRA_PATH:
        resolved = str(Path(extra).expanduser())
        if resolved not in parts and Path(resolved).is_dir():
            parts.append(resolved)
    return os.pathsep.join(parts)


# ── checks ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Check:
    """One deterministic checker. `argv[0]` is resolved against `search_path()`."""

    name: str
    what: str
    argv: tuple[str, ...]
    cwd: Path | None = None
    requires: Path | None = None  # skip (not fail) when this path is absent


def build_checks(root: Path | None = None) -> list[Check]:
    """The manifest. Sibling content trees are optional — a clone of this public repo
    on another machine has neither the private castle nor the island."""
    root = root or repo_root()
    validate = str(root / "bin" / "validate.py")
    checks = [
        Check(
            name="skill-vendor",
            what="vendored skew + registry invariant",
            argv=("skill-vendor", "doctor"),
        ),
        Check(
            name="lightbridge",
            what="personal config tree (~/.lightbridge)",
            argv=("lb", "doctor"),
        ),
        Check(
            name="agent-stuff",
            what="content tree contract",
            argv=(validate,),
            cwd=root,
        ),
    ]
    for sibling in ("agent-stuff-private", "skills-island"):
        tree = root.parent / sibling
        checks.append(
            Check(
                name=sibling,
                what="content tree contract",
                argv=(validate, "--root", str(tree)),
                cwd=root,
                requires=tree,
            )
        )
    return checks


@dataclass
class Result:
    name: str
    what: str
    status: str
    exit_code: int | None = None
    detail: str = ""

    @property
    def is_red(self) -> bool:
        return self.status == STATUS_RED

    def as_json(self) -> dict:
        out = {"name": self.name, "what": self.what, "status": self.status}
        if self.exit_code is not None:
            out["exit_code"] = self.exit_code
        if self.detail:
            out["detail"] = self.detail
        return out


def trim(text: str) -> str:
    """Last DETAIL_LINES meaningful lines, capped at DETAIL_CHARS."""
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) > DETAIL_LINES:
        lines = ["…"] + lines[-DETAIL_LINES:]
    out = "\n".join(lines)
    if len(out) > DETAIL_CHARS:
        out = "…" + out[-DETAIL_CHARS:]
    return out


def run_check(check: Check) -> Result:
    if check.requires is not None and not check.requires.exists():
        return Result(check.name, check.what, STATUS_SKIPPED, detail="not on this machine")

    env = dict(os.environ, PATH=search_path())
    exe = shutil.which(check.argv[0], path=env["PATH"])
    if exe is None:
        # A missing checker is red, not skipped: the check was meant to run and did not,
        # so the surface it covers is unverified. Silence here would be a lie.
        return Result(
            check.name,
            check.what,
            STATUS_RED,
            detail=f"`{check.argv[0]}` not found on PATH — install it or fix the PATH shim",
        )

    try:
        proc = subprocess.run(
            [exe, *check.argv[1:]],
            cwd=str(check.cwd) if check.cwd else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return Result(check.name, check.what, STATUS_RED, detail="timed out after 300s")
    except OSError as exc:
        return Result(check.name, check.what, STATUS_RED, detail=f"could not run: {exc}")

    output = trim((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else ""))
    status = STATUS_OK if proc.returncode == 0 else STATUS_RED
    return Result(check.name, check.what, status, proc.returncode, output if status == STATUS_RED else "")


# ── report ───────────────────────────────────────────────────────────────────


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)
    timestamp: str = ""
    host: str = ""

    @property
    def red(self) -> list[Result]:
        return [r for r in self.results if r.is_red]

    @property
    def ran(self) -> list[Result]:
        return [r for r in self.results if r.status != STATUS_SKIPPED]

    @property
    def message(self) -> str:
        if not self.red:
            return f"skill-health: all {len(self.ran)} checks green"
        names = ", ".join(r.name for r in self.red)
        return f"skill-health: {len(self.red)} of {len(self.ran)} checks red — {names}"

    def as_alert(self, report_path: Path | None = None) -> dict:
        """Payload for --notify-command.

        Core field names mirror mac-cpu-watchdog's Alert struct
        (internal/notify/notify.go) so one notifier script can serve both tools.
        `metadata` values are strings there (map[string]string) — keep them strings.
        Severity is always `warning`: this tool is report-only, so nothing it finds is
        an emergency requiring action within the hour.
        """
        meta = {
            "checks_total": str(len(self.ran)),
            "checks_red": str(len(self.red)),
            "red": ",".join(r.name for r in self.red),
        }
        if report_path is not None:
            meta["report_path"] = str(report_path)
        return {
            "severity": "warning" if self.red else "info",
            "type": "skill_health",
            "timestamp": self.timestamp,
            "host": self.host,
            "message": self.message,
            "metadata": meta,
            "checks": [r.as_json() for r in self.results],
        }


def collect(checks: list[Check]) -> Report:
    return Report(
        results=[run_check(c) for c in checks],
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        host=socket.gethostname(),
    )


def render(report: Report) -> str:
    width = max((len(r.name) for r in report.results), default=12)
    lines = []
    for r in report.results:
        lines.append(f"{r.name:<{width}}  {r.status.upper():<7} {r.what}")
        if r.detail:
            lines.extend(f"    {ln}" for ln in r.detail.splitlines())
    lines.append("")
    lines.append(report.message)
    if report.red:
        lines.append("fix: re-run the named check directly, then `skill-health` to confirm green")
    return "\n".join(lines)


def write_report(report: Report, home: Path) -> Path:
    path = home.joinpath(*REPORT_RELPATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.as_alert(), indent=2) + "\n", encoding="utf-8")
    return path


def notify(command: str, report: Report, report_path: Path) -> str | None:
    """Exec `command` with the alert JSON on stdin. Returns an error note, or None.

    A notifier that fails must not change the health verdict — the checks already ran and
    their answer stands. The failure is surfaced on stderr and recorded, not swallowed.
    """
    env = dict(os.environ, PATH=search_path())
    exe = shutil.which(command, path=env["PATH"]) or command
    try:
        proc = subprocess.run(
            [exe],
            input=json.dumps(report.as_alert(report_path)),
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"notify-command failed: {exc}"
    if proc.returncode != 0:
        return f"notify-command exited {proc.returncode}: {trim(proc.stderr or proc.stdout)}"
    return None


def cmd_run(as_json: bool, notify_command: str | None, home: Path, root: Path | None) -> int:
    report = collect(build_checks(root))

    try:
        report_path = write_report(report, home)
    except OSError as exc:
        print(f"could not write report under {home}: {exc}", file=sys.stderr)
        return ERROR

    if as_json:
        print(json.dumps(report.as_alert(report_path), indent=2))
    else:
        print(render(report))

    if notify_command and report.red:
        problem = notify(notify_command, report, report_path)
        if problem:
            print(problem, file=sys.stderr)

    return RED if report.red else OK


def main() -> None:
    # typer stays a CLI-only import (the pattern skill_vendor.py documents): everything
    # above is stdlib-pure, so tests drive it in-process dependency-free.
    import typer

    # One verb, so no callback and no subcommands: typer flattens a single-command app
    # into a bare `skill-health [OPTIONS]`. Annotations here must resolve at module
    # scope (`from __future__ import annotations` stringifies them), which is why none
    # of them name `typer.*` — the import is local to this function.
    app = typer.Typer(
        epilog=(
            "Exit: 0 all green · 1 a check is red · 2 usage/internal error. Report: "
            "~/.lightbridge/health/skill-health.json. Spec: agent-stuff "
            "docs/skill-health/design.md."
        ),
        rich_markup_mode=None,
        add_completion=False,
    )

    def _version(value: bool) -> None:
        if value:
            print(f"{Path(sys.argv[0]).stem} {__version__}")
            raise typer.Exit(0)

    @app.command()
    def check(
        as_json: bool = typer.Option(False, "--json", help="Emit the machine report."),
        notify_command: str = typer.Option(
            None,
            "--notify-command",
            metavar="PATH",
            help="On RED only: exec with the alert JSON on stdin.",
        ),
        home: Path = typer.Option(
            None, "--home", metavar="DIR", help=f"Lightbridge home (default: {DEFAULT_HOME}; env {HOME_ENV})."
        ),
        root: Path = typer.Option(
            None, "--root", metavar="DIR", help="agent-stuff root (default: this script's repo)."
        ),
        version: bool = typer.Option(
            False, "--version", callback=_version, is_eager=True, help="Show the version and exit."
        ),
    ) -> None:
        """Run every health check once. Report-only — nothing is repaired."""
        raise typer.Exit(
            cmd_run(
                as_json,
                notify_command,
                home.expanduser() if home else default_home(),
                root.expanduser() if root else None,
            )
        )

    app()


if __name__ == "__main__":
    main()
