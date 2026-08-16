"""The cross-repo graph document — `~/.lightbridge/graph.toml` — write path + semantics.

CLI-side only. The read half (`load_graph`, `project_node`, `DEFAULT_GRAPH`) lives in
`lb_resolve.py` (the frozen importer API) so `repo_links.py` and the SessionStart hook can
path-load it; this module supplies what the `lb graph` verbs additionally need: the seed
document, edge-block rendering and location, and the direction-confirming sentence.

The graph is a property graph over the repo registry's names:

    [types.<name>]      # edge A -> B: the type names what B is to A
    inverse = "..."     # what A is to B, shown in B's projected view
    backlink = "..."    # how the reverse renders in B's sessions: full | compact | off

    [[edge]]
    from = "a"
    to = "b"
    type = "<name>"
    from_note = "..."   # optional, A's viewpoint
    to_note = "..."     # optional, B's viewpoint
    backlink = "off"    # optional per-edge override

Edits follow the `lb_tomledit` invariant — lines not targeted come out byte-identical —
but `[[edge]]` blocks are graph-specific (an array of tables, which `section_span` by
design does not enter), so their span logic lives here rather than in the substrate.
"""

from __future__ import annotations

import re
import tomllib
from enum import Enum

from lb_resolve import toml_str
from lb_tomledit import terminate

GRAPH_HEADER = """\
# ~/.lightbridge/graph.toml — personal cross-repo knowledge graph (never committed).
# One edge is declared ONCE; both repos' injected ego views project from it.
# Edge A -> B: `type` names what B is to A; [types.<t>].inverse names what A is to B.
# backlink = how the reverse renders in B's sessions: full | compact | off
# (per-type default here; an edge may override with its own `backlink` key).
# Node names resolve via ~/.lightbridge/repos.toml. Spec: the repo-graph skill.
"""

# The seeded vocabulary `graph init` writes. User-owned from then on: the file, not this
# constant, is the source of truth — hand-edit it to grow the vocabulary; `graph doctor`
# validates that every edge's type is declared.
SEED_TYPES_BLOCK = """\
[types.upstream]              # B is the codebase A derives from (fork/variant lineage)
inverse = "downstream"
backlink = "full"

[types.component]             # B is a component repo of solution tracker A
inverse = "solution-tracker"
backlink = "full"

[types.sub-repo]              # B is a sub-repo committed inside workspace A
inverse = "parent-workspace"
backlink = "full"

[types.spec-source]           # B authors the specs A aggregates or mirrors
inverse = "spec-mirror"
backlink = "full"

[types.contracts]             # B holds the API contracts A conforms to
inverse = "contract-consumer"
backlink = "compact"

[types.live-test-service]     # B is the live service A tests against
inverse = "consumer"
backlink = "full"

[types.service-backend]       # B is a runtime service A calls
inverse = "service-client"
backlink = "full"

[types.deploy-tooling]        # B deploys or installs A
inverse = "deploy-target"
backlink = "full"

[types.ops-manual]            # B is the operations manual documenting A
inverse = "documented-app"
backlink = "full"

[types.tooling]               # B is dev tooling A uses
inverse = "tool-user"
backlink = "full"

[types.sibling-reference]     # A and B are peer artifacts to keep reconciled (symmetric)
inverse = "sibling-reference"
backlink = "full"

[types.subject]               # B is the system A studies or documents
inverse = "studied-by"
backlink = "compact"

[types.oss-reference]         # B is an OSS reference clone A consults
inverse = "referenced-by"
backlink = "off"
"""

SEED_TYPE_NAMES = list(tomllib.loads(SEED_TYPES_BLOCK)["types"])


class BacklinkMode(str, Enum):
    """The three render modes for an edge's reverse direction (Typer choice type)."""

    full = "full"
    compact = "compact"
    off = "off"


_EDGE_HEADER = re.compile(r"\s*\[\[edge\]\]\s*(#.*)?$")
_EDGE_KEY = re.compile(r"\s*(from|to|type|from_note|to_note|backlink)\s*=\s*(.+?)\s*$")


def _unquote(raw: str) -> str:
    """A TOML string value's text — enough for the simple values edge keys hold.

    Handles literal ('...') and basic ("...") strings including trailing comments after
    the closing quote. Names and modes never contain escapes; notes may, but notes are
    only ever *replaced* wholesale, never parsed for meaning, so unescaping the two
    sequences `toml_str` can emit is sufficient.
    """
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] in "'\"":
        quote = raw[0]
        end = raw.rfind(quote)
        if end > 0:
            body = raw[1:end]
            if quote == '"':
                body = body.replace('\\"', '"').replace("\\\\", "\\")
            return body
    return raw


def edge_spans(text: str) -> list[tuple[int, int]]:
    """Line span [start, end) of every `[[edge]]` block, in file order.

    A block runs from its `[[edge]]` header to the next line whose first non-space
    character is `[` (the next edge, a `[types.*]` table, anything) — the same end
    condition `section_span` uses, applied to the array-of-tables header it refuses
    to enter.
    """
    lines = text.splitlines(keepends=True)
    spans: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        if _EDGE_HEADER.match(line):
            end = len(lines)
            for j in range(i + 1, len(lines)):
                if lines[j].lstrip().startswith("["):
                    end = j
                    break
            spans.append((i, end))
    return spans


def edge_fields(text: str, span: tuple[int, int]) -> dict:
    """The edge keys present in one block span — `{key: value}`; absent keys omitted."""
    lines = text.splitlines(keepends=True)
    fields: dict[str, str] = {}
    for line in lines[span[0] + 1 : span[1]]:
        match = _EDGE_KEY.match(line)
        if match:
            fields[match.group(1)] = _unquote(match.group(2))
    return fields


def find_edge_spans(
    text: str, frm: str, to: str, etype: str | None = None
) -> list[tuple[int, int]]:
    """Spans of the edge blocks matching from/to (and type, when given)."""
    matches = []
    for span in edge_spans(text):
        fields = edge_fields(text, span)
        if fields.get("from") != frm or fields.get("to") != to:
            continue
        if etype is not None and fields.get("type") != etype:
            continue
        matches.append(span)
    return matches


def render_edge(edge: dict) -> str:
    """One `[[edge]]` block; optional keys are written only when present."""
    lines = ["[[edge]]\n"]
    for key in ("from", "to", "type"):
        lines.append(f"{key} = {toml_str(edge[key])}\n")
    for key in ("from_note", "to_note", "backlink"):
        if edge.get(key):
            lines.append(f"{key} = {toml_str(edge[key])}\n")
    return "".join(lines)


def append_edge(text: str, edge: dict) -> str:
    """`text` with the edge block appended at EOF — never inside an existing block."""
    text = terminate(text)
    separator = "" if text.endswith("\n\n") or not text else "\n"
    return text + separator + render_edge(edge)


def remove_span(text: str, span: tuple[int, int]) -> str:
    """`text` without the span's lines, absorbing the blank separator line above it."""
    lines = text.splitlines(keepends=True)
    start = span[0]
    if start > 0 and lines[start - 1].strip() == "":
        start -= 1
    return "".join(lines[:start] + lines[span[1] :])


def set_edge_key(text: str, span: tuple[int, int], key: str, value: str | None) -> str:
    """One key set (or removed, when value is None/empty) inside one edge block.

    A targeted line edit: an existing `key =` line is replaced in place, a new one is
    inserted after the block's last non-blank line, and every other line survives
    byte-identical.
    """
    lines = text.splitlines(keepends=True)
    pattern = re.compile(rf"\s*{key}\s*=")
    for i in range(span[0] + 1, span[1]):
        if pattern.match(lines[i]):
            if value:
                lines[i] = f"{key} = {toml_str(value)}\n"
            else:
                del lines[i]
            return "".join(lines)
    if not value:
        return text  # removing a key that isn't there — no-op
    insert_at = span[1]
    while insert_at > span[0] + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    lines.insert(insert_at, f"{key} = {toml_str(value)}\n")
    return "".join(lines)


def edge_sentence(edge: dict, types: dict) -> str:
    """The direction-confirming echo a `link` prints — catches a reversed edge on sight."""
    spec = types.get(edge["type"], {}) if isinstance(types, dict) else {}
    inverse = spec.get("inverse") or edge["type"]
    mode = edge.get("backlink") or spec.get("backlink") or "full"
    head = (
        f"{edge['from']} -[{edge['type']}]-> {edge['to']}: "
        f"{edge['to']} is {edge['from']}'s {edge['type']}"
    )
    if mode == "off":
        tail = f"{edge['to']} sessions will not show this edge (backlink off)"
    elif mode == "compact":
        tail = f"{edge['to']} sessions will mention {edge['from']} compactly as ({inverse})"
    else:
        tail = f"{edge['to']} sessions will show {edge['from']} as ({inverse})"
    return f"{head}; {tail}."
