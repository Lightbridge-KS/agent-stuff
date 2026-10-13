"""CLI graph operations and visualization, exported as their implementation objects.

Graph readers and projection remain in standalone lb_resolve for path-loaded consumers.
"""

from .document import (
    BACKLINK_MODES,
    GRAPH_HEADER,
    SEED_TYPES_BLOCK,
    SEED_TYPE_NAMES,
    BacklinkMode,
    BacklinkSetting,
    edge_spans,
    edge_fields,
    find_edge_spans,
    render_edge,
    append_edge,
    remove_span,
    set_edge_key,
    effective_mode,
    audit,
    edge_sentence,
)
from .visualization import (
    node_group,
    mermaid_text,
    html_text,
    HTML_TEMPLATE,
)

__all__ = [
    "BACKLINK_MODES",
    "GRAPH_HEADER",
    "SEED_TYPES_BLOCK",
    "SEED_TYPE_NAMES",
    "BacklinkMode",
    "BacklinkSetting",
    "edge_spans",
    "edge_fields",
    "find_edge_spans",
    "render_edge",
    "append_edge",
    "remove_span",
    "set_edge_key",
    "effective_mode",
    "audit",
    "edge_sentence",
    "node_group",
    "mermaid_text",
    "html_text",
    "HTML_TEMPLATE",
]
