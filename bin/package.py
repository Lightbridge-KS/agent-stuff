#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Package each skill in this repo into an uploadable archive under `dist/`.

The canonical source of truth is `plugins/<domain>/skills/<name>/SKILL.md`. This
packager zips one self-contained archive per skill (upload targets like claude.ai
take a single skill at a time), so all-in-one bundling is intentionally not offered.

    uv run bin/package.py                 # package all -> dist/
    uv run bin/package.py dcmtk           # package one skill (bare name)
    uv run bin/package.py --domain radiology  # every skill in one plugin domain
    uv run bin/package.py --list          # list packageable skills
    uv run bin/package.py --skill         # also emit a .skill (same bytes)
    uv run bin/package.py --versioned     # name by frontmatter version
    uv run bin/package.py --dry-run       # preview, no writes

Skills are discovered by the same glob `bin/install.py` uses
(`plugins/*/skills/*/SKILL.md`) and keyed by their **bare** folder name, which is
globally unique across domains — that name is also the archive name and the single
top-level folder inside it:

    dcmtk.zip
    └── dcmtk/
        ├── SKILL.md
        └── references/...

Builds are reproducible: entries are sorted and stamped with a fixed timestamp,
so re-running produces byte-identical archives. A `.skill` file is byte-identical
to the `.zip` — only the extension differs.

Validate before packaging (`uv run bin/validate.py`); the `just package` recipe
wires that dependency for you.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT / "plugins"
DEFAULT_DIST = REPO_ROOT / "dist"

# Never ship editor/OS/build junk, even if it lands inside a skill folder.
EXCLUDE_NAMES = {".DS_Store", "__pycache__", ".git", ".ipynb_checkpoints"}

# A fixed timestamp keeps archives byte-stable across runs (ZIP epoch = 1980).
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)


def available_skills() -> dict[str, Path]:
    """Map bare skill name -> source folder for every discovered skill.

    Mirrors `bin/install.py`'s discovery glob. Bare folder names are globally
    unique across domains (installs land flat by that name), so the bare name is
    a safe archive name and dict key.
    """
    found: dict[str, Path] = {}
    for skill_md in sorted(PLUGINS_ROOT.glob("*/skills/*/SKILL.md")):
        folder = skill_md.parent
        found[folder.name] = folder
    return found


def skills_in_domain(domain: str) -> list[str]:
    """Bare names of every skill under plugins/<domain>/skills/."""
    return sorted(
        skill_md.parent.name
        for skill_md in PLUGINS_ROOT.glob(f"{domain}/skills/*/SKILL.md")
    )


def read_version(skill_dir: Path) -> str | None:
    """Best-effort read of `metadata.version` from SKILL.md frontmatter (no deps)."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    close = text.find("\n---", 4)
    if close == -1:
        return None
    match = re.search(
        r'^\s*version:\s*["\']?([^"\'\n]+?)["\']?\s*$',
        text[4:close],
        re.MULTILINE,
    )
    return match.group(1).strip() if match else None


def collect_entries(skill_dir: Path, name: str) -> list[tuple[str, Path]]:
    """(arcname, source) pairs for every shippable file, sorted by arcname."""
    entries: list[tuple[str, Path]] = []
    for path in skill_dir.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(skill_dir)
        if any(part in EXCLUDE_NAMES for part in rel.parts) or path.suffix == ".pyc":
            continue
        entries.append((f"{name}/{rel.as_posix()}", path))
    entries.sort(key=lambda entry: entry[0])
    return entries


def display(path: Path) -> str:
    """Repo-relative path when possible, else the path as given (e.g. a custom --out)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def write_zip(target: Path, entries: list[tuple[str, Path]]) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for arcname, source in entries:
            info = zipfile.ZipInfo(arcname, date_time=FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16  # regular file, rw-r--r--
            archive.writestr(info, source.read_bytes())


def package_one(
    name: str,
    skill_dir: Path,
    out_dir: Path,
    *,
    also_skill: bool,
    versioned: bool,
    dry_run: bool,
) -> None:
    entries = collect_entries(skill_dir, name)
    version = read_version(skill_dir)

    stem = name
    if versioned:
        if version:
            stem = f"{name}-{version}"
        else:
            print(f"warning: {name} has no metadata.version; using plain name", file=sys.stderr)

    targets = [out_dir / f"{stem}.zip"]
    if also_skill:
        targets.append(out_dir / f"{stem}.skill")

    vlabel = f"v{version}" if version else "no version"
    if dry_run:
        for target in targets:
            print(f"would package {name} -> {display(target)} ({vlabel}, {len(entries)} files)")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    write_zip(targets[0], entries)
    for extra in targets[1:]:
        shutil.copyfile(targets[0], extra)  # identical bytes, different extension
    for target in targets:
        print(f"packaged {name} -> {display(target)} ({vlabel}, {len(entries)} files)")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="package.py",
        description="Package skills into uploadable archives under dist/.",
    )
    parser.add_argument("skills", nargs="*", help="Bare skill names to package (default: all).")
    parser.add_argument("--domain", help="Package every skill in this plugin domain.")
    parser.add_argument("--out", help="Output directory. Default: dist/")
    parser.add_argument("--skill", action="store_true", help="Also emit a .skill (byte-identical to the .zip).")
    parser.add_argument("--versioned", action="store_true", help="Name archives by frontmatter version.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing files.")
    parser.add_argument("--list", action="store_true", help="List packageable skills and exit.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    available = available_skills()

    if args.list:
        print("\n".join(available))
        return 0

    if not available:
        print("No plugins/*/skills/*/SKILL.md files found.", file=sys.stderr)
        return 1

    out_dir = Path(args.out).expanduser() if args.out else DEFAULT_DIST

    selected: list[str] = []
    if args.domain:
        in_domain = skills_in_domain(args.domain)
        if not in_domain:
            print(f"unknown domain: {args.domain}", file=sys.stderr)
            return 1
        selected.extend(in_domain)
    selected.extend(args.skills)
    if not selected:
        selected = list(available)

    missing = [name for name in selected if name not in available]
    if missing:
        print(f"unknown skill(s): {', '.join(missing)}", file=sys.stderr)
        print(f"available: {', '.join(available)}", file=sys.stderr)
        return 1

    # De-duplicate while preserving order (a --domain + explicit-name overlap).
    for name in dict.fromkeys(selected):
        package_one(
            name,
            available[name],
            out_dir,
            also_skill=args.skill,
            versioned=args.versioned,
            dry_run=args.dry_run,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
