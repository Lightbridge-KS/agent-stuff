"""Shared visualization data and self-contained Mermaid/HTML rendering."""

from __future__ import annotations

import json
from pathlib import Path

from .document import effective_mode


def node_group(raw_path: str | None) -> str:
    """A node's display group for the viz: its registered path's parent directory."""
    if not raw_path:
        return "unregistered"
    return Path(raw_path).expanduser().parent.name or "/"


def _viz_data(
    graph: dict, registry: dict[str, str] | None
) -> tuple[list[dict], list[dict]]:
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
        lines.append(
            f"  {nid[link['source']]} {arrow}|{link['type']}| {nid[link['target']]}"
        )
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
