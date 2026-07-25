"""The section catalog: what may go in a config, and how a config document is assembled.

Prose (what each key *means*, the defaults, the semantics) stays canonical in the
`lightbridge-config` skill's `references/catalog.md` — this module holds only what
`init`/`add` write. `tests/test_lightbridge.py` asserts the two agree, so a section
documented in one and missing from the other is a red test, not a drift.

CLI-side: the entrypoint reaches this by plain `import`. Hooks never need it — knowing
*which* sections exist is a write-path and dashboard concern, not a read-path one.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from lb_resolve import toml_str

CONFIG_HEADER = """\
# ~/.lightbridge/projects/<project-key>/config.toml — personal workflow config.
# User-level, per-project — NEVER inside the repo ("local scope": the repo stays clean).
# Written by `lightbridge init`; `lightbridge sections` lists what else can go here.
# Opt-in by SECTION presence: a feature is on iff its [section] exists; set
# enabled = false to disable one without deleting it.
# Full spec: the lightbridge-config skill (references/catalog.md).
"""

SECTIONS: dict[str, dict[str, str]] = {
    "docs-index": {
        "purpose": "inject this repo's docs map into context at SessionStart",
        "reader": "hooks/docs-index-inject",
        "block": """\
[docs-index]
enabled = true                     # optional; default true
dir = "docs"                       # docs directory, relative to repo root
exclude = ["archive", "research"]  # subdir names to skip
include = ["CONTEXT.md", "CONTEXT-MAP.md"]  # extra root-level files (default); [] to suppress
""",
    },
    "research": {
        "purpose": "per-project defaults for deep-research sessions",
        "reader": "plugins/research → the research skill (read at plan time)",
        "block": """\
[research]
enabled = true                     # optional; default true
dir = "docs/research"              # parent dir for session folders
output = "markdown"                # markdown | quarto (.bib + @key cites, HTML render)
backends = ["websearch"]           # preference order; probed at plan time when omitted
searcher_model = "sonnet"          # searcher tier; "inherit" to match the session model
verifier_model = "sonnet"          # verifier tier; "inherit" to match the session model
corpus = []                        # local corpus dirs (reserved)
""",
    },
    "plans": {
        "purpose": "file every approved plan mode plan; optionally auto-approve the gate",
        "reader": "hooks/plan-capture + hooks/plan-gate (via scripts/plan-store)",
        "block": """\
[plans]
enabled = true                     # optional; default true
auto_approve = false               # true = skip Claude Code's plan-approval dialog.
                                   # Costs you plan iteration, the post-approval mode
                                   # choice, and the last checkpoint before writes.
                                   # Read hooks/plan-gate/README.md before enabling.
""",
    },
    "repo-links": {
        "purpose": "declare logical links to sibling repos, injected at SessionStart",
        "reader": "hooks/repo-links-inject (resolved via ~/.lightbridge/repos.toml)",
        # `enabled` MUST precede the first [[repo-links.link]] — TOML would otherwise
        # attach it to the last array-of-tables entry rather than to the section.
        "block": """\
[repo-links]
enabled = true                     # optional; default true. Must precede the first link.

[[repo-links.link]]
name = "example-service"           # required; logical name, resolved via ~/.lightbridge/repos.toml
role = "upstream"                  # optional; free-form (upstream, oss-reference, live-test-service, …)
note = "Why this repo matters when working here"  # optional
""",
    },
}


# CLI-parsing concern only (handlers take plain strings): the choice type Typer
# validates section names against — usage error (exit 2) naming the valid set,
# plus shell completion of the values. Members mirror SECTIONS; the assert below
# turns any drift into an import-time failure every test run hits.
class SectionName(str, Enum):
    docs_index = "docs-index"
    plans = "plans"
    repo_links = "repo-links"
    research = "research"


assert {member.value for member in SectionName} == set(SECTIONS)


def detect_sections(root: Path) -> list[str]:
    """Sections a repo's layout obviously wants. Never a guess — only what's on disk."""
    return ["docs-index"] if (root / "docs").is_dir() else []


def present_sections(config: dict) -> set[str]:
    """Known sections already in a parsed config (unknown top-level tables are ignored)."""
    return set(config) & set(SECTIONS)


def render_config(root: Path, names: list[str]) -> str:
    """A whole config file: header, the `root` staleness marker, then each section."""
    parts = [CONFIG_HEADER, f"root = {toml_str(str(root))}\n"]
    parts += [SECTIONS[name]["block"] for name in names]
    return "\n".join(parts)


def append_sections(existing: str, names: list[str]) -> str:
    """`existing` plus each section appended at EOF — never rewriting what's there.

    Safe because every block opens with a table header, which ends whatever table the
    file was in.
    """
    text = existing if existing.endswith("\n") else existing + "\n"
    return text + "".join("\n" + SECTIONS[name]["block"] for name in names)


def describe(name: str) -> str:
    return f"{name}  (read by: {SECTIONS[name]['reader']})"
