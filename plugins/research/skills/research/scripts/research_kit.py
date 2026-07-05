#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Deterministic machinery for the `research` skill.

Operates on a research session directory (see the skill's SKILL.md for the layout):

    merge-sources <session>    sources/*.yaml fragments -> sources.yaml ledger
                               (dedup by DOI/PMID/URL, stable global S-ids)
    check-citations <session>  report.md <-> sources.yaml <-> notes/ <-> verification.md
                               consistency gate; phase: done requires exit 0
    status <session>           token-economical phase/progress digest

Exit codes: 0 = pass, 1 = fail (offenders listed on stdout, one per line).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import yaml

FRAGMENT_ID_RE = re.compile(r"^S\d+-\d+$")
NOTE_FILE_RE = re.compile(r"^(\d+)(-.*)?$")
UNCERTAIN_RE = re.compile(r"\[uncertain (U\d+-\d+)\]")
U_ID_RE = re.compile(r"\bU\d+-\d+\b")
VERDICT_RE = re.compile(
    r"^-\s*\[(U\d+-\d+|C-\d+)\]\s+(confirmed|unsupported|contradicted)\b",
    re.MULTILINE,
)
# [S1] or [S1, S4] in the report; also catches fragment-style [S03-1] so it
# surfaces as an unresolved citation instead of passing silently.
CITE_GROUP_RE = re.compile(r"\[(S\d+(?:-\d+)?(?:\s*,\s*S\d+(?:-\d+)?)*)\]")

LEDGER_FIELDS = ("url", "title", "type", "accessed", "doi", "pmid")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a Markdown file into (YAML frontmatter dict, body)."""
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError("missing YAML frontmatter")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    return data, match.group(2)


def normalize_url(url: str) -> str:
    """Scheme-insensitive URL key: lowercase host, no trailing slash, no utm_*/fragment."""
    parts = urlsplit(str(url).strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    ]
    key = parts.netloc.lower() + parts.path.rstrip("/")
    if query:
        key += "?" + urlencode(query)
    return key


def dedup_key(entry: dict) -> str:
    """Identity of a source: DOI first, then PMID, then normalized URL."""
    doi = str(entry.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    pmid = str(entry.get("pmid") or "").strip()
    if pmid:
        return f"pmid:{pmid}"
    return "url:" + normalize_url(entry.get("url", ""))


def note_ids(session: Path) -> set[str]:
    """Zero-padded sub-question ids that already have a note file (NN.md or NN-slug.md)."""
    ids = set()
    for note in (session / "notes").glob("*.md"):
        match = NOTE_FILE_RE.match(note.stem)
        if match:
            ids.add(f"{int(match.group(1)):02d}")
    return ids


# ---------------------------------------------------------------- merge-sources


def cmd_merge_sources(session: Path) -> int:
    frag_dir = session / "sources"
    frag_files = sorted(frag_dir.glob("*.yaml")) if frag_dir.is_dir() else []

    errors: list[str] = []
    fragments: list[tuple[str, list[dict]]] = []
    for frag in frag_files:
        rel = f"sources/{frag.name}"
        try:
            data = yaml.safe_load(frag.read_text())
        except yaml.YAMLError as exc:
            errors.append(f"malformed: {rel}: invalid YAML ({exc})")
            continue
        if data is None:
            data = []
        if not isinstance(data, list):
            errors.append(f"malformed: {rel}: expected a YAML list of entries")
            continue
        entries = []
        for i, entry in enumerate(data, 1):
            if not isinstance(entry, dict):
                errors.append(f"malformed: {rel} entry {i}: not a mapping")
                continue
            if not FRAGMENT_ID_RE.match(str(entry.get("id") or "")):
                errors.append(f"malformed: {rel} entry {i}: bad or missing id (want S<NN>-<k>)")
            for field in ("url", "title"):
                if not str(entry.get(field) or "").strip():
                    errors.append(f"malformed: {rel} entry {i}: missing {field}")
            entries.append(entry)
        fragments.append((frag.name, entries))

    if errors:
        print("\n".join(errors))
        return 1

    ledger_path = session / "sources.yaml"
    ledger: list[dict] = []
    if ledger_path.is_file():
        ledger = yaml.safe_load(ledger_path.read_text()) or []
    by_key = {dedup_key(entry): entry for entry in ledger}
    next_n = max((int(str(entry["id"])[1:]) for entry in ledger), default=0) + 1

    duplicates = 0
    all_entries = [entry for _, entries in fragments for entry in entries]
    for entry in all_entries:
        frag_id = str(entry["id"])
        key = dedup_key(entry)
        if key in by_key:
            duplicates += 1
            fids = by_key[key].setdefault("fragment_ids", [])
            if frag_id not in fids:
                fids.append(frag_id)
        else:
            merged: dict = {"id": f"S{next_n}"}
            next_n += 1
            for field in LEDGER_FIELDS:
                value = entry.get(field)
                if value not in (None, ""):
                    merged[field] = value
            merged["fragment_ids"] = [frag_id]
            ledger.append(merged)
            by_key[key] = merged

    ledger.sort(key=lambda entry: int(str(entry["id"])[1:]))
    ordered = [
        {
            key: entry[key]
            for key in ("id", *LEDGER_FIELDS, "fragment_ids")
            if key in entry
        }
        for entry in ledger
    ]
    ledger_path.write_text(
        yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, width=100)
    )
    print(f"merged {len(frag_files)} fragments -> {len(ledger)} sources ({duplicates} duplicates)")
    return 0


# -------------------------------------------------------------- check-citations


def cmd_check_citations(session: Path) -> int:
    fails: list[str] = []
    report_path = session / "report.md"
    ledger_path = session / "sources.yaml"
    if not report_path.is_file():
        fails.append("FAIL presence: report.md missing")
    if not ledger_path.is_file():
        fails.append("FAIL presence: sources.yaml missing")
    if fails:
        print("\n".join(fails))
        return 1

    ledger = yaml.safe_load(ledger_path.read_text()) or []
    ledger_ids = [str(entry.get("id")) for entry in ledger]
    report = report_path.read_text()

    cited: list[str] = []
    for match in CITE_GROUP_RE.finditer(report):
        cited.extend(re.split(r"\s*,\s*", match.group(1)))

    for token in sorted(set(cited) - set(ledger_ids)):
        fails.append(f"FAIL resolve: [{token}] cited in report.md but not in sources.yaml")
    for ledger_id in ledger_ids:
        if ledger_id not in cited:
            fails.append(f"FAIL orphan: {ledger_id} in sources.yaml but never cited in report.md")

    if "[uncertain" in report:
        fails.append("FAIL leak: '[uncertain' marker present in report.md")
    for uid in sorted(set(U_ID_RE.findall(report))):
        fails.append(f"FAIL leak: {uid} present in report.md")

    markers: set[str] = set()
    notes_dir = session / "notes"
    if notes_dir.is_dir():
        for note in sorted(notes_dir.glob("*.md")):
            markers |= set(UNCERTAIN_RE.findall(note.read_text()))
    verification_path = session / "verification.md"
    if markers and not verification_path.is_file():
        fails.append(
            f"FAIL verify: verification.md missing but {len(markers)} [uncertain] markers in notes/"
        )
    elif markers:
        verdicts = {m.group(1) for m in VERDICT_RE.finditer(verification_path.read_text())}
        for uid in sorted(markers - verdicts):
            fails.append(f"FAIL verify: {uid} has no verdict in verification.md")

    if fails:
        print("\n".join(fails))
        return 1
    print(f"citations OK: {len(ledger_ids)} sources, {len(markers)} uncertain claims all verified")
    return 0


# ----------------------------------------------------------------------- status


def cmd_status(session: Path) -> int:
    plan_path = session / "plan.md"
    if not plan_path.is_file():
        print(f"error: no plan.md in {session}")
        return 1
    try:
        fm, body = parse_frontmatter(plan_path.read_text())
    except (ValueError, yaml.YAMLError) as exc:
        print(f"error: malformed plan.md frontmatter ({exc})")
        return 1

    sub_ids: list[str] = []
    section = re.search(r"^## Sub-questions\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL)
    if section:
        sub_ids = [f"{int(n):02d}" for n in re.findall(r"^\s*(\d+)\.\s", section.group(1), re.MULTILINE)]
    done = sorted(set(sub_ids) & note_ids(session))
    undone = [i for i in sub_ids if i not in done]

    n_notes = len(list((session / "notes").glob("*.md"))) if (session / "notes").is_dir() else 0
    n_frags = len(list((session / "sources").glob("*.yaml"))) if (session / "sources").is_dir() else 0
    n_ledger = 0
    if (session / "sources.yaml").is_file():
        n_ledger = len(yaml.safe_load((session / "sources.yaml").read_text()) or [])
    verification_path = session / "verification.md"
    if verification_path.is_file():
        verification = f"{len(VERDICT_RE.findall(verification_path.read_text()))} verdicts"
    else:
        verification = "absent"

    execution = fm.get("execution") or {}
    progress = fm.get("progress") or {}
    print(f"phase: {fm.get('phase', '?')}  shape: {fm.get('shape', '?')}  output: {fm.get('output', '?')}")
    print(f"topic: {fm.get('topic', '?')}")
    print(
        f"waves: {progress.get('waves_done', 0)}/{execution.get('max_waves', '?')} done  "
        f"sub-questions: {len(done)}/{len(sub_ids)} done "
        f"(undone: {' '.join(undone) if undone else 'none'})"
    )
    print(f"notes: {n_notes}  fragments: {n_frags}  ledger: {n_ledger} sources")
    print(f"verification: {verification}")
    return 0


# ------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="research_kit",
        description="Deterministic machinery for research sessions (see module docstring).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_ in (
        ("merge-sources", "merge sources/*.yaml fragments into sources.yaml"),
        ("check-citations", "gate report.md against the source ledger and verification"),
        ("status", "print a short phase/progress digest"),
    ):
        cmd = sub.add_parser(name, help=help_)
        cmd.add_argument("session", type=Path, help="research session directory")
    args = parser.parse_args(argv)

    session = args.session
    if args.command != "status" and not session.is_dir():
        print(f"error: no such session directory: {session}")
        return 1
    if args.command == "status" and not session.is_dir():
        print(f"error: no plan.md in {session}")
        return 1

    return {
        "merge-sources": cmd_merge_sources,
        "check-citations": cmd_check_citations,
        "status": cmd_status,
    }[args.command](session)


if __name__ == "__main__":
    sys.exit(main())
