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

import json
import re
import tomllib
from enum import Enum
from pathlib import Path

from lb_resolve import toml_str
from lb_tomledit import terminate

BACKLINK_MODES = ("full", "compact", "off")

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


class BacklinkSetting(str, Enum):
    """`graph set --backlink` choices: a mode, or `default` to clear the override."""

    full = "full"
    compact = "compact"
    off = "off"
    default = "default"


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


def effective_mode(edge: dict, types: dict) -> str:
    """The backlink mode that actually renders: edge override, else type, else full."""
    mode = edge.get("backlink")
    if mode not in BACKLINK_MODES:
        spec = types.get(edge["type"])
        mode = spec.get("backlink") if isinstance(spec, dict) else None
    return mode if mode in BACKLINK_MODES else "full"


def audit(graph: dict, registry: dict[str, str] | None) -> list[dict]:
    """Every rot finding in the graph, as `{kind, subject, detail}` records.

    Kinds: malformed-edge · invalid-type · undeclared-type · invalid-backlink ·
    duplicate-edge · unregistered-node · dead-path · no-registry · registry-alias.
    """
    problems: list[dict] = []
    if graph["skipped"]:
        problems.append(
            {
                "kind": "malformed-edge",
                "subject": "graph",
                "detail": f"{graph['skipped']} edge block(s) missing from/to/type — dropped "
                "from every projection",
            }
        )
    for name, spec in graph["types"].items():
        broken = []
        if not (isinstance(spec.get("inverse"), str) and spec.get("inverse").strip()):
            broken.append("no inverse")
        if spec.get("backlink") not in BACKLINK_MODES:
            broken.append(f"backlink must be one of {', '.join(BACKLINK_MODES)}")
        if broken:
            problems.append(
                {"kind": "invalid-type", "subject": name, "detail": "; ".join(broken)}
            )

    seen: dict[tuple, int] = {}
    node_names: set[str] = set()
    for edge in graph["edges"]:
        subject = f"{edge['from']} -[{edge['type']}]-> {edge['to']}"
        node_names.update((edge["from"], edge["to"]))
        if edge["type"] not in graph["types"]:
            problems.append(
                {
                    "kind": "undeclared-type",
                    "subject": subject,
                    "detail": f"type '{edge['type']}' is not in [types] — declare it, "
                    "or fix the edge",
                }
            )
        if edge["backlink"] is not None and edge["backlink"] not in BACKLINK_MODES:
            problems.append(
                {
                    "kind": "invalid-backlink",
                    "subject": subject,
                    "detail": f"backlink '{edge['backlink']}' must be one of "
                    f"{', '.join(BACKLINK_MODES)}",
                }
            )
        key = (edge["from"], edge["to"], edge["type"])
        seen[key] = seen.get(key, 0) + 1
    for (frm, to, etype), count in seen.items():
        if count > 1:
            problems.append(
                {
                    "kind": "duplicate-edge",
                    "subject": f"{frm} -[{etype}]-> {to}",
                    "detail": f"declared {count} times — `graph unlink` the extras",
                }
            )

    if registry is None:
        if node_names:
            problems.append(
                {
                    "kind": "no-registry",
                    "subject": "registry",
                    "detail": "the graph has edges but no repos.toml exists — no name "
                    "can resolve to a path",
                }
            )
        return problems
    for name in sorted(node_names):
        raw = registry.get(name)
        if not isinstance(raw, str) or not raw.strip():
            problems.append(
                {
                    "kind": "unregistered-node",
                    "subject": name,
                    "detail": f"not in repos.toml — `repos add {name} PATH`",
                }
            )
        elif not Path(raw).expanduser().is_dir():
            problems.append(
                {
                    "kind": "dead-path",
                    "subject": name,
                    "detail": f"registered path {raw} is not a directory on this machine",
                }
            )
    by_path: dict[str, list[str]] = {}
    for name, raw in registry.items():
        if isinstance(raw, str) and raw.strip():
            try:
                by_path.setdefault(str(Path(raw).expanduser().resolve()), []).append(name)
            except OSError:
                continue
    for path, names in sorted(by_path.items()):
        if len(names) > 1 and node_names.intersection(names):
            problems.append(
                {
                    "kind": "registry-alias",
                    "subject": ", ".join(sorted(names)),
                    "detail": f"all resolve to {path} — pick one canonical name; the "
                    "rest split that repo's identity",
                }
            )
    return problems


def node_group(raw_path: str | None) -> str:
    """A node's display group for the viz: its registered path's parent directory."""
    if not raw_path:
        return "unregistered"
    return Path(raw_path).expanduser().parent.name or "/"


def _viz_data(graph: dict, registry: dict[str, str] | None) -> tuple[list[dict], list[dict]]:
    """(nodes, links) for the mermaid/HTML renderers — one derivation for both."""
    edges = graph["edges"]
    types = graph["types"]
    degree: dict[str, int] = {}
    for edge in edges:
        for name in (edge["from"], edge["to"]):
            degree[name] = degree.get(name, 0) + 1
    nodes = [
        {
            "id": name,
            "path": (registry or {}).get(name),
            "group": node_group((registry or {}).get(name)),
            "degree": degree[name],
            "registered": name in (registry or {}),
        }
        for name in sorted(degree)
    ]
    links = [
        {
            "source": e["from"],
            "target": e["to"],
            "type": e["type"],
            "inverse": (types.get(e["type"]) or {}).get("inverse") or e["type"],
            "mode": effective_mode(e, types),
            "from_note": e["from_note"],
            "to_note": e["to_note"],
        }
        for e in edges
    ]
    return nodes, links


def mermaid_text(graph: dict, registry: dict[str, str] | None) -> str:
    """A flowchart of the whole graph, nodes grouped by parent directory.

    Backlink-off edges render dashed — visibly one-directional in the projection.
    """
    nodes, links = _viz_data(graph, registry)
    nid = {n["id"]: f"n{i}" for i, n in enumerate(nodes)}
    by_group: dict[str, list[str]] = {}
    for n in nodes:
        by_group.setdefault(n["group"], []).append(n["id"])
    lines = ["flowchart LR"]
    for gi, group in enumerate(sorted(by_group)):
        lines.append(f'  subgraph g{gi}["{group}"]')
        for name in sorted(by_group[group]):
            lines.append(f'    {nid[name]}["{name}"]')
        lines.append("  end")
    for link in links:
        arrow = "-.->" if link["mode"] == "off" else "-->"
        lines.append(f"  {nid[link['source']]} {arrow}|{link['type']}| {nid[link['target']]}")
    return "\n".join(lines) + "\n"


def html_text(graph: dict, registry: dict[str, str] | None) -> str:
    """The self-contained interactive viz (vanilla JS force layout, no CDN)."""
    nodes, links = _viz_data(graph, registry)
    payload = json.dumps({"nodes": nodes, "links": links}).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__DATA__", payload)


# The self-contained page `graph html` writes: Obsidian-like force layout, wheel zoom
# (cursor-centered), background-drag pan, node drag, hover tooltips (both notes),
# click-to-focus. Vanilla JS on purpose — the page must render with no network at all.
HTML_TEMPLATE = r"""<!doctype html>
<meta charset="utf-8">
<title>lightbridge repo graph</title>
<style>
  html,body{margin:0;height:100%;background:#1b1e24;color:#ccc;font:12px/1.4 -apple-system,Helvetica,sans-serif;overflow:hidden}
  svg{width:100vw;height:100vh;display:block}
  .lbl{fill:#c8ccd4;font-size:11px;pointer-events:none;text-anchor:middle}
  #tip{position:fixed;display:none;max-width:380px;background:#262b33;border:1px solid #444;
       border-radius:6px;padding:8px 10px;pointer-events:none;z-index:10;box-shadow:0 4px 14px rgba(0,0,0,.5)}
  #tip b{color:#fff} #tip .note{color:#9aa3af;margin-top:4px}
  #legend{position:fixed;top:10px;left:10px;background:#20242bcc;border:1px solid #3a3f47;
          border-radius:8px;padding:10px 12px}
  #legend .row{display:flex;align-items:center;gap:6px;margin:2px 0}
  #legend .sw{width:10px;height:10px;border-radius:50%}
  #legend .ln{width:22px;height:0;border-top:2px solid}
  h1{position:fixed;bottom:8px;right:14px;font-size:12px;font-weight:normal;color:#666;margin:0}
</style>
<svg></svg><div id="tip"></div><div id="legend"></div>
<h1>lightbridge repo graph — scroll to zoom; drag background to pan; drag nodes; hover; click node to focus, background to reset</h1>
<script>
const data = __DATA__;
const W = innerWidth, H = innerHeight;
const PALETTE = ["#4e8fd9","#2fa198","#8a63d2","#d29a3d","#5fae5f","#c65f5f","#9aa3af","#b083c9","#6aa9a0","#c9a26a"];
const groups = [...new Set(data.nodes.map(n => n.group))].sort();
const groupColor = Object.fromEntries(groups.map((g,i) => [g, PALETTE[i % PALETTE.length]]));
const nodes = data.nodes.map(n => ({...n, x: W/2 + 250*Math.cos(9*n.id.length), y: H/2 + 250*Math.sin(7*n.id.length), vx:0, vy:0}));
const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
const links = data.links.map(l => ({...l, s: byId[l.source], t: byId[l.target]}));
nodes.forEach(n => n.r = 6 + 2*Math.sqrt(n.degree||1));

const svg = document.querySelector("svg");
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs, parent){const e=document.createElementNS(NS,tag);
  for(const k in attrs)e.setAttribute(k,attrs[k]); (parent||svg).appendChild(e); return e;}
const defs = el("defs",{});
const m = el("marker",{id:"arr", viewBox:"0 -4 8 8", refX:8, refY:0, markerWidth:7, markerHeight:7, orient:"auto"},defs);
el("path",{d:"M0,-4L8,0L0,4", fill:"#5c6570"},m);
const root = el("g",{});
const gE = el("g",{},root), gN = el("g",{},root), gL = el("g",{},root);

// --- view transform: wheel zoom (cursor-centered) + background-drag pan ---
let k=1, tx=0, ty=0;
function applyView(){ root.setAttribute("transform", `translate(${tx},${ty}) scale(${k})`); }
const toWorld = ev => [(ev.clientX-tx)/k, (ev.clientY-ty)/k];
svg.addEventListener("wheel", ev => {
  ev.preventDefault();
  const f = Math.exp(-ev.deltaY*0.0015);
  const nk = Math.min(5, Math.max(0.2, k*f)), r = nk/k;
  tx = ev.clientX - (ev.clientX-tx)*r; ty = ev.clientY - (ev.clientY-ty)*r; k = nk;
  applyView();
}, {passive:false});

links.forEach(l => {
  l.line = el("line",{stroke:"#5c6570","stroke-width":l.mode==="compact"?1.2:2,
    "stroke-dasharray":l.mode==="off"?"4 4":"", "marker-end":"url(#arr)"},gE);
  l.hit = el("line",{stroke:"transparent","stroke-width":10},gE); // fat invisible hover target
});
nodes.forEach(n => {
  n.circle = el("circle",{r:n.r, fill:groupColor[n.group]||"#777", stroke:n.registered?"#111":"#e5c07b","stroke-width":n.registered?1:2},gN);
  n.label = el("text",{class:"lbl"},gL); n.label.textContent = n.id;
});

// --- force simulation (velocity + local repulsion + springs + centering) ---
let alpha = 1;
function tick(){
  for (let i=0;i<nodes.length;i++) for (let j=i+1;j<nodes.length;j++){
    const a=nodes[i], b=nodes[j];
    let dx=b.x-a.x, dy=b.y-a.y, d2=dx*dx+dy*dy||1, d=Math.sqrt(d2);
    if (d2 > 90000) continue;  // repulsion only within 300px — spreads clusters without global explosion
    const f = 7000/d2;
    dx/=d; dy/=d;
    a.vx-=f*dx; a.vy-=f*dy; b.vx+=f*dx; b.vy+=f*dy;
  }
  links.forEach(l=>{
    let dx=l.t.x-l.s.x, dy=l.t.y-l.s.y, d=Math.sqrt(dx*dx+dy*dy)||1;
    const f = 0.02*(d-190);
    dx/=d; dy/=d;
    l.s.vx+=f*dx; l.s.vy+=f*dy; l.t.vx-=f*dx; l.t.vy-=f*dy;
  });
  nodes.forEach(n=>{
    n.vx += (W/2-n.x)*0.0013; n.vy += (H/2-n.y)*0.0013;
    if(n!==dragging){ n.x+=n.vx*alpha; n.y+=n.vy*alpha; }
    n.vx*=0.85; n.vy*=0.85;
    n.x=Math.max(30,Math.min(W-30,n.x)); n.y=Math.max(30,Math.min(H-30,n.y));
  });
  links.forEach(l=>{
    // trim line to node radius so arrowheads sit on the circle edge
    let dx=l.t.x-l.s.x, dy=l.t.y-l.s.y, d=Math.sqrt(dx*dx+dy*dy)||1;
    const sx=l.s.x+dx/d*l.s.r, sy=l.s.y+dy/d*l.s.r, tx2=l.t.x-dx/d*(l.t.r+2), ty2=l.t.y-dy/d*(l.t.r+2);
    for (const ln of [l.line,l.hit]){ ln.setAttribute("x1",sx);ln.setAttribute("y1",sy);ln.setAttribute("x2",tx2);ln.setAttribute("y2",ty2); }
  });
  nodes.forEach(n=>{
    n.circle.setAttribute("cx",n.x); n.circle.setAttribute("cy",n.y);
    n.label.setAttribute("x",n.x); n.label.setAttribute("y",n.y+n.r+13);
  });
  alpha = Math.max(alpha*0.995, 0.06);
  requestAnimationFrame(tick);
}

// --- drag nodes / pan background / click-to-focus (click = press+release without movement) ---
let dragging = null, panning = false, downNode = null, downX = 0, downY = 0;
svg.addEventListener("pointerdown", ev => {
  const [wx,wy] = toWorld(ev);
  downNode = nodes.find(n => (n.x-wx)**2 + (n.y-wy)**2 < (n.r+4)**2) || null;
  downX = ev.clientX; downY = ev.clientY;
  if(downNode){ dragging=downNode; alpha=0.6; } else { panning=true; }
  svg.setPointerCapture(ev.pointerId);
});
svg.addEventListener("pointermove", ev => {
  if(dragging){ const [wx,wy]=toWorld(ev); dragging.x=wx; dragging.y=wy; alpha=Math.max(alpha,0.3); }
  else if(panning){ tx+=ev.movementX; ty+=ev.movementY; applyView(); }
});
svg.addEventListener("pointerup", ev => {
  const moved = Math.abs(ev.clientX-downX)+Math.abs(ev.clientY-downY) > 3;
  if(!moved) downNode ? focus(downNode) : resetFocus();
  dragging=null; panning=false; downNode=null;
});

// --- tooltip ---
const tip = document.getElementById("tip");
function showTip(html, ev){ tip.innerHTML=html; tip.style.display="block";
  tip.style.left=Math.min(ev.clientX+14,W-400)+"px"; tip.style.top=(ev.clientY+14)+"px"; }
nodes.forEach(n => {
  n.circle.addEventListener("pointermove", ev => showTip(
    `<b>${n.id}</b> <span style="color:${groupColor[n.group]}">(${n.group})</span><br>${n.path||"?"}`+
    (n.registered?"":"<div class='note'>⚠ not in repos.toml</div>"), ev));
  n.circle.addEventListener("pointerleave", () => tip.style.display="none");
});
links.forEach(l => {
  l.hit.addEventListener("pointermove", ev => showTip(
    `<b>${l.source}</b> —[${l.type}]→ <b>${l.target}</b><br>`+
    `inverse: ${l.inverse} · backlink ${l.mode}`+
    (l.from_note?`<div class="note">↳ from ${l.source}: ${l.from_note}</div>`:"")+
    (l.to_note?`<div class="note">↳ from ${l.target}: ${l.to_note}</div>`:""), ev));
  l.hit.addEventListener("pointerleave", () => tip.style.display="none");
});

// --- focus / reset ---
function focus(n){
  const keep = new Set([n.id]);
  links.forEach(l => { if(l.source===n.id||l.target===n.id){ keep.add(l.source); keep.add(l.target); } });
  nodes.forEach(m2 => { const on = keep.has(m2.id); m2.circle.style.opacity = on?1:0.12; m2.label.style.opacity = on?1:0.1; });
  links.forEach(l => l.line.style.opacity = (l.source===n.id||l.target===n.id)?1:0.06);
}
function resetFocus(){
  nodes.forEach(m2 => { m2.circle.style.opacity=1; m2.label.style.opacity=1; });
  links.forEach(l => l.line.style.opacity=1);
}

// --- legend ---
const legend = document.getElementById("legend");
legend.innerHTML = groups
  .map(g => `<div class="row"><span class="sw" style="background:${groupColor[g]}"></span>${g}</div>`).join("")+
  `<div class="row" style="margin-top:6px"><span class="ln" style="border-color:#5c6570"></span>backlink full</div>`+
  `<div class="row"><span class="ln" style="border-color:#5c6570;border-top-width:1px"></span>backlink compact</div>`+
  `<div class="row"><span class="ln" style="border-color:#5c6570;border-top-style:dashed"></span>backlink off</div>`+
  `<div class="row"><span class="sw" style="background:#555;border:2px solid #e5c07b"></span>not in repos.toml</div>`;
tick();
</script>
"""


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
