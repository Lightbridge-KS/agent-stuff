#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.27"]
# ///
"""skill-vendor — keep Vendored agent skills in sync with their installed binaries.

The invariant (docs/skill-vendor/design.md): **the skill bytes served to harness
registries are the ones known-good for the installed binary.** What varies per entry
is where "known-good" comes from — the manifest's key shape selects the mode:

    source = "install-tree"          co-shipped: skill inside the install unit;
                                     correct by construction
    source = "repo"  + tag           first-party detached: skill in the binary's repo,
                                     pinned to the tag rendered from `<binary> --version`
    source = "repo"  + ref           third-party detached: skill repo has its own
                                     history; pinned ref + user attestation
                                     (`verified-against` / `verified-on`)

Manifest: `~/.lightbridge/skill-vendors.toml` — hand-edited, machine-specific, never
committed. `attest` is the only machine writer. Worktrees live under
`~/.lightbridge/skill-vendors/worktrees/<name>`; registry entries are symlinks into
them (or straight into the install tree for co-shipped).

    skill-vendor list                # inventory: name, mode, versions, status
    skill-vendor doctor              # read-only skew + integrity report (incl. registry scan)
    skill-vendor sync                # converge: fetch tags, move worktrees, relink registries
    skill-vendor sync crabbox        # one entry
    skill-vendor attest sometool     # stamp verified-against/-on (third-party only)

Link it onto PATH as `skill-vendor` — see this tool's README.

Exit codes: 0 clean · 1 skew (drift needing action: run sync, or re-verify + attest;
also registry-invariant violations awaiting the drain) · 2 broken (missing binary/tag/
skill dir/symlink, unreadable manifest, usage). Never falls back silently: a pin that
cannot resolve leaves existing symlinks untouched.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# `lb_resolve.py` is lightbridge's frozen path-load API (stdlib-only, no sibling
# imports — see docs/lightbridge/adr/0001-modular-lightbridge.md). It is the ONLY
# lightbridge module sibling tools may load.
_LB_RESOLVE = Path(__file__).resolve().parents[1] / "lightbridge" / "lb_resolve.py"
_spec = importlib.util.spec_from_file_location("lb_resolve_sv", _LB_RESOLVE)
_lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lb)
toml_str = _lb.toml_str
use_utf8_console = _lb.use_utf8_console

__version__ = "0.1.0"

HOME_ENV = "SKILL_VENDOR_HOME"  # override; exists so the tool is testable in isolation
DEFAULT_HOME = "~/.lightbridge"
MANIFEST_NAME = "skill-vendors.toml"
DEFAULT_REGISTRIES = ["~/.claude/skills", "~/.codex/skills"]
SEMVER = re.compile(r"\d+\.\d+\.\d+")

OK, SKEW, BROKEN = 0, 1, 2
SEVERITY_WORD = {OK: "ok", SKEW: "skew", BROKEN: "broken"}

SAMPLE_ENTRY = """\
[defaults]
registries = ["~/.claude/skills", "~/.codex/skills"]

[mytool]                      # entry key = skill dir name in registries
binary      = "mytool"
source      = "repo"          # or "install-tree" + skill-path for co-shipped
repo        = "~/OSS/mytool"
tag         = "v{version}"    # first-party; use `ref` + attest for third-party
skill-paths = ["skills/mytool"]
"""


def default_home() -> Path:
    return Path(os.environ.get(HOME_ENV) or DEFAULT_HOME).expanduser()


# ── manifest ─────────────────────────────────────────────────────────────────


@dataclass
class Entry:
    """One vendored skill, as declared in the manifest."""

    name: str
    binary: str
    source: str  # "install-tree" | "repo"
    mode: str  # "co-shipped" | "first-party" | "third-party"
    registries: list[Path]
    skill_path: str | None = None  # co-shipped: absolute path into the install tree
    repo: str | None = None
    tag: str | None = None  # first-party: template over the installed version
    ref: str | None = None  # third-party: pinned skill-repo rev
    verified_against: str | None = None
    verified_on: str | None = None
    skill_paths: list[str] = field(default_factory=list)  # repo modes: probe in order
    version_cmd: str | None = None  # default: "<binary> --version"


def parse_entry(name: str, raw: dict, registries: list[Path]) -> tuple[Entry | None, list[str]]:
    """Validate one manifest table into an Entry; mode is selected by key shape."""
    problems: list[str] = []
    source = raw.get("source")
    tag, ref = raw.get("tag"), raw.get("ref")

    if source == "install-tree":
        mode = "co-shipped"
        if not raw.get("skill-path"):
            problems.append(f"[{name}] install-tree needs `skill-path`")
        if raw.get("repo") or tag or ref:
            problems.append(f"[{name}] install-tree takes no `repo`/`tag`/`ref`")
    elif source == "repo":
        mode = "first-party" if tag else "third-party"
        if not raw.get("repo"):
            problems.append(f"[{name}] repo source needs `repo`")
        if not raw.get("skill-paths"):
            problems.append(f"[{name}] repo source needs `skill-paths`")
        if bool(tag) == bool(ref):
            problems.append(f"[{name}] exactly one of `tag` (first-party) or `ref` (third-party)")
    else:
        problems.append(f"[{name}] `source` must be \"repo\" or \"install-tree\"")
        mode = "?"

    if not raw.get("binary"):
        problems.append(f"[{name}] needs `binary`")
    if problems:
        return None, problems

    verified_on = raw.get("verified-on")
    entry_registries = [Path(r).expanduser() for r in raw.get("registries", [])] or registries
    return (
        Entry(
            name=name,
            binary=raw["binary"],
            source=source,
            mode=mode,
            registries=entry_registries,
            skill_path=raw.get("skill-path"),
            repo=raw.get("repo"),
            tag=tag,
            ref=ref,
            verified_against=raw.get("verified-against"),
            verified_on=str(verified_on) if verified_on is not None else None,
            skill_paths=list(raw.get("skill-paths", [])),
            version_cmd=raw.get("version-cmd"),
        ),
        [],
    )


def load_manifest(home: Path) -> tuple[list[Entry], list[Path], list[str]]:
    """Read the manifest → (entries, default registries, fatal problems).

    A missing manifest is fatal-with-guidance: v1 is hand-edited, so the error names
    the exact path and shows a minimal entry to copy.
    """
    path = home / MANIFEST_NAME
    if not path.is_file():
        return [], [], [f"no manifest at {path} — create it by hand; a minimal entry:\n\n{SAMPLE_ENTRY}"]
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return [], [], [f"unreadable manifest {path}: {exc}"]

    defaults = data.get("defaults", {})
    registries = [Path(r).expanduser() for r in defaults.get("registries", DEFAULT_REGISTRIES)]

    entries: list[Entry] = []
    problems: list[str] = []
    for name, raw in data.items():
        if name == "defaults" or not isinstance(raw, dict):
            continue
        entry, entry_problems = parse_entry(name, raw, registries)
        problems.extend(entry_problems)
        if entry:
            entries.append(entry)
    return entries, registries, problems


# ── shell + git helpers ──────────────────────────────────────────────────────


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run a command, capturing stdout+stderr; (127, reason) when the binary is absent."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=120
        )
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def installed_version(entry: Entry) -> tuple[str | None, str | None]:
    """The installed binary's version — first semver in the version command's output."""
    cmd = shlex.split(entry.version_cmd) if entry.version_cmd else [entry.binary, "--version"]
    rc, out = run(cmd)
    if rc == 127:
        return None, f"binary `{entry.binary}` not on PATH"
    if rc != 0:
        return None, f"`{' '.join(cmd)}` failed: {out.splitlines()[0] if out else rc}"
    match = SEMVER.search(out)
    if not match:
        return None, f"no version found in `{' '.join(cmd)}` output: {out[:80]!r}"
    return match.group(0), None


def rev_commit(repo: Path, rev: str) -> str | None:
    """The commit a rev resolves to in `repo`; None when the rev does not exist."""
    rc, out = run(["git", "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"], cwd=repo)
    return out if rc == 0 and out else None


def worktree_dir(entry: Entry, home: Path) -> Path:
    return home / "skill-vendors" / "worktrees" / entry.name


def pinned_rev(entry: Entry, version: str) -> str:
    """The rev the entry pins to: rendered tag (first-party) or literal ref (third-party)."""
    return entry.tag.replace("{version}", version) if entry.tag else entry.ref


def skill_dir(entry: Entry, base: Path) -> Path | None:
    """First `skill-paths` candidate under `base` that holds a SKILL.md."""
    for rel in entry.skill_paths:
        candidate = base / rel
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


# ── assessment (shared by doctor / list / sync) ──────────────────────────────


@dataclass
class Report:
    """One entry's assessed state; `notes` name the next move, worst first."""

    name: str
    mode: str
    severity: int = OK
    binary_version: str | None = None
    pinned: str | None = None
    target: Path | None = None  # the dir registry symlinks must point at
    notes: list[str] = field(default_factory=list)

    def flag(self, severity: int, note: str) -> None:
        self.severity = max(self.severity, severity)
        self.notes.append(note)

    def as_json(self) -> dict:
        return {
            "name": self.name,
            "mode": self.mode,
            "status": SEVERITY_WORD[self.severity],
            "binary_version": self.binary_version,
            "pinned": self.pinned,
            "notes": self.notes,
        }


def assess(entry: Entry, home: Path) -> Report:
    """Read-only assessment of one entry — doctor's per-entry logic.

    The one question, asked per mode: does the installed binary version match the
    version the skill is bound to? Skew (1) = drift with a named fix; broken (2) =
    an engine-managed piece is wrong or unusable.
    """
    report = Report(name=entry.name, mode=entry.mode)
    version, problem = installed_version(entry)
    if problem:
        report.flag(BROKEN, problem)
        return report
    report.binary_version = version

    if entry.mode == "co-shipped":
        target = Path(entry.skill_path).expanduser()
        report.pinned = version  # by construction
        if not (target / "SKILL.md").is_file():
            report.flag(BROKEN, f"install-tree skill missing: {target}")
            return report
        report.target = target
    else:
        rev = pinned_rev(entry, version)
        report.pinned = rev
        repo = Path(entry.repo).expanduser()
        if not repo.is_dir():
            report.flag(BROKEN, f"repo not found: {repo}")
            return report
        expected = rev_commit(repo, rev)
        if expected is None:
            report.flag(BROKEN, f"rev `{rev}` not in {repo} — release published? `git fetch --tags`?")
            return report
        wt = worktree_dir(entry, home)
        if not wt.is_dir():
            report.flag(BROKEN, f"no worktree at {wt} — run `skill-vendor sync {entry.name}`")
            return report
        rc, head = run(["git", "rev-parse", "HEAD"], cwd=wt)
        if rc != 0:
            report.flag(BROKEN, f"worktree unreadable at {wt}: {head}")
            return report
        if head != expected:
            report.flag(SKEW, f"worktree at {head[:12]}, pin is `{rev}` — run `skill-vendor sync {entry.name}`")
        target = skill_dir(entry, wt)
        if target is None:
            report.flag(BROKEN, f"no SKILL.md under {wt} at any of {entry.skill_paths}")
            return report
        report.target = target
        if entry.mode == "third-party":
            if entry.verified_against is None:
                report.flag(SKEW, f"never attested — verify against {version}, then `skill-vendor attest {entry.name}`")
            elif entry.verified_against != version:
                report.flag(
                    SKEW,
                    f"verified against {entry.verified_against}, binary is {version} — "
                    f"re-verify, then `skill-vendor attest {entry.name}`",
                )

    for registry in entry.registries:
        link = registry / entry.name
        if not link.is_symlink():
            what = "real path (refusing to manage)" if link.exists() else "missing"
            report.flag(BROKEN, f"registry link {what}: {link} — run `skill-vendor sync {entry.name}`")
        elif link.resolve() != report.target.resolve():
            report.flag(BROKEN, f"registry link points elsewhere: {link} → {link.resolve()}")
    return report


def scan_registries(registries: list[Path], managed: set[str]) -> list[tuple[int, str]]:
    """The registry invariant: registries are symlink-only proxies.

    Real directories and dangling symlinks are **skew** (policy drift awaiting the
    Adopted-shelf drain — AGENTS.qmd *Skill vendors*), not broken: they do not affect
    vendored serving. Foreign symlinks that resolve (Authored, Adopted homes) pass
    silently — they are not this engine's business.
    """
    findings: list[tuple[int, str]] = []
    for registry in registries:
        if not registry.is_dir():
            findings.append((SKEW, f"registry missing: {registry}"))
            continue
        for child in sorted(registry.iterdir()):
            if child.name.startswith(".") or child.name in managed:
                continue  # hidden housekeeping; managed entries are assessed per entry
            if child.is_symlink():
                if not child.exists():
                    findings.append((SKEW, f"dangling symlink: {child}"))
            elif child.is_dir():
                findings.append((SKEW, f"real directory (unvendored drift): {child}"))
    return findings


# ── verbs ────────────────────────────────────────────────────────────────────


def relink(entry: Entry, target: Path, report: Report) -> None:
    """Point every registry entry at `target` — replacing links only, never real paths."""
    for registry in entry.registries:
        if not registry.is_dir():
            report.flag(BROKEN, f"registry missing: {registry}")
            continue
        link = registry / entry.name
        if link.exists() and not link.is_symlink():
            report.flag(BROKEN, f"refusing to replace a real path: {link}")
            continue
        if link.is_symlink():
            if link.resolve() == target.resolve():
                continue
            link.unlink()
        link.symlink_to(target)
        report.notes.append(f"linked {link} → {target}")


def converge(entry: Entry, home: Path) -> Report:
    """Sync one entry: resolve version → resolve pin → worktree → relink.

    Failure honesty: any unresolvable step reports broken and leaves existing
    symlinks untouched — never a silent fallback to a repo's `main`.
    """
    report = Report(name=entry.name, mode=entry.mode)
    version, problem = installed_version(entry)
    if problem:
        report.flag(BROKEN, problem)
        return report
    report.binary_version = version

    if entry.mode == "co-shipped":
        target = Path(entry.skill_path).expanduser()
        report.pinned = version
        if not (target / "SKILL.md").is_file():
            report.flag(BROKEN, f"install-tree skill missing: {target}")
            return report
    else:
        rev = pinned_rev(entry, version)
        report.pinned = rev
        repo = Path(entry.repo).expanduser()
        if not repo.is_dir():
            report.flag(BROKEN, f"repo not found: {repo}")
            return report
        if entry.mode == "first-party":
            rc, out = run(["git", "fetch", "--tags", "--quiet"], cwd=repo)
            if rc != 0:  # offline is not fatal — local tags may already suffice
                report.notes.append(f"fetch --tags failed (offline?): {out.splitlines()[0] if out else rc}")
        expected = rev_commit(repo, rev)
        if expected is None:
            report.flag(BROKEN, f"rev `{rev}` not in {repo} — release published? symlinks left untouched")
            return report
        wt = worktree_dir(entry, home)
        if wt.is_dir():
            rc, head = run(["git", "rev-parse", "HEAD"], cwd=wt)
            if rc != 0:
                report.flag(BROKEN, f"worktree unreadable at {wt}: {head}")
                return report
            if head != expected:
                rc, out = run(["git", "checkout", "--detach", expected], cwd=wt)
                if rc != 0:
                    report.flag(BROKEN, f"checkout `{rev}` failed in {wt}: {out.splitlines()[-1]}")
                    return report
                report.notes.append(f"worktree moved to {rev}")
        else:
            wt.parent.mkdir(parents=True, exist_ok=True)
            run(["git", "worktree", "prune"], cwd=repo)  # clear any stale registration
            rc, out = run(["git", "worktree", "add", "--detach", str(wt), expected], cwd=repo)
            if rc != 0:
                report.flag(BROKEN, f"worktree add failed: {out.splitlines()[-1] if out else rc}")
                return report
            report.notes.append(f"worktree created at {rev}")
        target = skill_dir(entry, wt)
        if target is None:
            report.flag(BROKEN, f"no SKILL.md under {wt} at any of {entry.skill_paths} — symlinks left untouched")
            return report

    report.target = target
    relink(entry, target, report)
    return report


def select(entries: list[Entry], names: list[str]) -> tuple[list[Entry], list[str]]:
    """The entries matching `names` (all when empty) + problems for unknown names."""
    if not names:
        return entries, []
    by_name = {e.name: e for e in entries}
    unknown = [n for n in names if n not in by_name]
    return [by_name[n] for n in names if n in by_name], [f"no manifest entry `{n}`" for n in unknown]


def emit(reports: list[Report], registry_findings: list[tuple[int, str]], as_json: bool) -> int:
    """Print the assessment; exit code = worst severity found."""
    worst = max(
        [r.severity for r in reports] + [s for s, _ in registry_findings] + [OK]
    )
    if as_json:
        print(
            json.dumps(
                {
                    "entries": [r.as_json() for r in reports],
                    "registry": [
                        {"status": SEVERITY_WORD[s], "note": n} for s, n in registry_findings
                    ],
                    "status": SEVERITY_WORD[worst],
                },
                indent=2,
            )
        )
        return worst
    for r in reports:
        mark = {OK: "ok", SKEW: "SKEW", BROKEN: "BROKEN"}[r.severity]
        pinned = r.pinned or "?"
        print(f"{r.name:<12} {r.mode:<12} binary {r.binary_version or '?':<9} pin {pinned:<10} {mark}")
        for note in r.notes:
            print(f"    {note}")
    for severity, note in registry_findings:
        print(f"registry     {SEVERITY_WORD[severity].upper():<6} {note}")
    return worst


def cmd_status(names: list[str], home: Path, as_json: bool, exit_semantics: bool) -> int:
    """`doctor` (exit_semantics=True) and `list` (always 0) share one assessment pass."""
    entries, registries, problems = load_manifest(home)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return BROKEN
    selected, unknown = select(entries, names)
    if unknown:
        print("\n".join(unknown), file=sys.stderr)
        return BROKEN
    reports = [assess(e, home) for e in selected]
    findings = scan_registries(registries, {e.name for e in entries}) if not names else []
    code = emit(reports, findings, as_json)
    return code if exit_semantics else OK


def cmd_sync(names: list[str], home: Path, as_json: bool) -> int:
    entries, _, problems = load_manifest(home)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return BROKEN
    selected, unknown = select(entries, names)
    if unknown:
        print("\n".join(unknown), file=sys.stderr)
        return BROKEN
    reports = [converge(e, home) for e in selected]
    return emit(reports, [], as_json)


def cmd_attest(name: str, home: Path) -> int:
    """Stamp `verified-against` (installed version) + `verified-on` (today) for `name`.

    Third-party only: first-party pins derive from the tag, co-shipped from the install
    unit — an attestation there would claim knowledge the mode already guarantees.
    Targeted line edits: untargeted manifest lines come out byte-identical.
    """
    entries, _, problems = load_manifest(home)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return BROKEN
    entry = next((e for e in entries if e.name == name), None)
    if entry is None:
        print(f"no manifest entry `{name}`", file=sys.stderr)
        return BROKEN
    if entry.mode != "third-party":
        print(f"`{name}` is {entry.mode} — attest applies only to third-party entries", file=sys.stderr)
        return BROKEN
    version, problem = installed_version(entry)
    if problem:
        print(problem, file=sys.stderr)
        return BROKEN

    path = home / MANIFEST_NAME
    text = path.read_text(encoding="utf-8")
    text = set_key(text, name, "verified-against", toml_str(version))
    text = set_key(text, name, "verified-on", date.today().isoformat())
    path.write_text(text, encoding="utf-8")
    print(f"{name}: verified-against = {version}, verified-on = {date.today().isoformat()}")
    return OK


def set_key(text: str, section: str, key: str, rendered: str) -> str:
    """`text` with `key = <rendered>` set inside `[section]` — a targeted line edit.

    Replaces the value on an existing line (trailing comment survives); inserts at the
    section's end (before trailing blank lines) when the key is absent. Same invariant
    as lightbridge's lb_tomledit, implemented locally: `lb_resolve.py` is the only
    lightbridge module siblings may load.
    """
    lines = text.splitlines(keepends=True)
    header = re.compile(rf"\s*\[{re.escape(section)}\]\s*(#.*)?$")
    start = next(i for i, line in enumerate(lines) if header.match(line))
    end = next(
        (j for j in range(start + 1, len(lines)) if lines[j].lstrip().startswith("[")),
        len(lines),
    )
    for i in range(start + 1, end):
        if re.match(rf"\s*{re.escape(key)}\s*=", lines[i]):
            lines[i] = re.sub(rf"({re.escape(key)}\s*=\s*)\S+", rf"\g<1>{rendered}", lines[i], count=1)
            return "".join(lines)
    insert_at = end
    while insert_at > start + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    lines.insert(insert_at, f"{key} = {rendered}\n")
    return "".join(lines)


# ── entrypoint ───────────────────────────────────────────────────────────────


def main() -> None:
    # typer stays a CLI-only import (the pattern lightbridge.py documents): cmd_* and
    # the helpers above are stdlib-pure, so tests drive them in-process dependency-free.
    import typer

    use_utf8_console()
    prog = Path(sys.argv[0]).stem

    app = typer.Typer(
        help="Keep Vendored agent skills in sync with their installed binaries.",
        epilog=(
            "Exit: 0 clean · 1 skew (run sync, or re-verify + attest; registry-invariant "
            "violations) · 2 broken/usage. Manifest: ~/.lightbridge/skill-vendors.toml "
            "(hand-edited; `attest` is the only machine writer). Spec: "
            "agent-stuff docs/skill-vendor/design.md."
        ),
        rich_markup_mode=None,
        no_args_is_help=True,
    )

    def _version(value: bool) -> None:
        if value:
            print(f"{prog} {__version__}")
            raise typer.Exit(0)

    @app.callback()
    def _root(
        version: bool = typer.Option(
            False, "--version", callback=_version, is_eager=True, help="Show the version and exit."
        ),
    ) -> None:
        pass

    names_arg = typer.Argument(None, metavar="[NAME]...", help="Entries to act on (default: all).")
    json_opt = typer.Option(False, "--json", help="Emit JSON.")
    home_opt = typer.Option(
        None, "--home", metavar="DIR", help=f"Lightbridge home (default: {DEFAULT_HOME}; env {HOME_ENV})."
    )

    def resolve_home(value: Path | None) -> Path:
        return value.expanduser() if value else default_home()

    @app.command("list")
    def list_(
        names: list[str] = names_arg, as_json: bool = json_opt, home: Path = home_opt
    ) -> None:
        """Inventory: name, mode, binary version, pinned version, status. Always exit 0."""
        raise typer.Exit(cmd_status(names or [], resolve_home(home), as_json, exit_semantics=False))

    @app.command()
    def doctor(
        names: list[str] = names_arg, as_json: bool = json_opt, home: Path = home_opt
    ) -> None:
        """Read-only skew + integrity report; includes the registry-invariant scan."""
        raise typer.Exit(cmd_status(names or [], resolve_home(home), as_json, exit_semantics=True))

    @app.command()
    def sync(
        names: list[str] = names_arg, as_json: bool = json_opt, home: Path = home_opt
    ) -> None:
        """Converge entries: fetch tags, move worktrees, relink registries."""
        raise typer.Exit(cmd_sync(names or [], resolve_home(home), as_json))

    @app.command()
    def attest(
        name: str = typer.Argument(..., help="Third-party entry to attest."),
        home: Path = home_opt,
    ) -> None:
        """Record that the pinned skill was verified against the installed binary, today."""
        raise typer.Exit(cmd_attest(name, resolve_home(home)))

    app()


if __name__ == "__main__":
    main()
