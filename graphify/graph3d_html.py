"""Interactive 3D force-directed HTML view of graph.json.

A WebGL counterpart to ``graphify tree``: where the 2D ``graph.html`` (vis-network,
``exporters/html.py``) draws an undirected force layout with no arrowheads, this
renders the graph as a rotatable 3D force graph and *draws the edge direction*
(``source -> target``) as arrows — so ``calls`` / ``imports`` / ``inherits`` read
directionally, which the flat view cannot show.

Self-contained single HTML file. Loads the ``3d-force-graph`` library (MIT) from a
CDN, matching how ``tree_html`` loads D3 from ``d3js.org``. Graph data is embedded
inline (no fetch, so it opens over ``file://`` without a CORS shim).
"""
from __future__ import annotations

import html as _html
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from graphify.exporters.base import COMMUNITY_COLORS

# 3d-force-graph bundles three.js; pinned major matches the tree viewer's CDN habit.
_CDN = "https://unpkg.com/3d-force-graph@1"


def build_graph3d_data(
    graph: Dict[str, Any], labels: Optional[Dict[int, str]] = None
) -> Dict[str, Any]:
    """Shape graph.json into ``{nodes, links}`` for 3d-force-graph.

    Node size scales with degree; ``community`` drives the color; ``community_name``
    is taken from the labels sidecar (or the node) and falls back to ``Community N``.
    Links keep ``relation`` and ``confidence`` so the tooltip can name the edge and
    the renderer can dim ``INFERRED`` edges. Dangling links (an endpoint absent from
    ``nodes``) are dropped so the force engine never fabricates ghost nodes.
    """
    labels = labels or {}
    raw_links: List[Dict[str, Any]] = list(graph.get("links") or graph.get("edges") or [])

    degree: Counter = Counter()
    for e in raw_links:
        degree[e.get("source")] += 1
        degree[e.get("target")] += 1

    node_ids = {n["id"] for n in graph.get("nodes", [])}
    nodes: List[Dict[str, Any]] = []
    for n in graph.get("nodes", []):
        cid = n.get("community")
        cname = n.get("community_name") or labels.get(cid) or (
            f"Community {cid}" if cid is not None else "unknown"
        )
        nodes.append({
            "id": n["id"],
            "label": n.get("label") or n["id"],
            "community": cid,
            "community_name": cname,
            "source_file": n.get("source_file") or "",
            "source_location": n.get("source_location") or "",
            "degree": degree.get(n["id"], 0),
        })

    links = [{
        "source": e["source"],
        "target": e["target"],
        "relation": e.get("relation") or "",
        "confidence": e.get("confidence") or "",
    } for e in raw_links if e.get("source") in node_ids and e.get("target") in node_ids]

    return {"nodes": nodes, "links": links}


def emit_html(data: Dict[str, Any], *, title: str, header: str) -> str:
    # ensure_ascii + escaping `</` keeps embedded JSON from breaking out of the
    # <script> tag; every value that later lands in innerHTML is run through the
    # JS esc() helper below, so a hostile node label (e.g. from a scraped doc)
    # cannot inject markup into the local report (cf. exporters/html.py, #1838).
    data_json = json.dumps(data, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
    palette_json = json.dumps(COMMUNITY_COLORS)
    return (
        _HTML_TEMPLATE
        .replace("%%TITLE%%", _html.escape(title))
        .replace("%%HEADER%%", _html.escape(header))
        .replace("%%PALETTE%%", palette_json)
        .replace("%%DATA%%", data_json)
    )


def write_graph3d_html(
    graph_path: Path,
    output_path: Path,
    *,
    project_label: Optional[str] = None,
) -> Path:
    from graphify.security import check_graph_file_size_cap

    check_graph_file_size_cap(graph_path)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))

    labels: Dict[int, str] = {}
    labels_path = graph_path.parent / ".graphify_labels.json"
    if labels_path.is_file():
        try:
            labels = {
                int(k): v
                for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items()
                if isinstance(v, str)
            }
        except Exception:
            labels = {}

    data = build_graph3d_data(graph, labels)
    name = project_label or "Knowledge Graph"
    html = emit_html(
        data,
        title=f"{name} — graphify 3D viewer",
        header=f"{name} — {len(data['nodes'])} nodes / {len(data['links'])} edges",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>%%TITLE%%</title>
<style>
  body{margin:0;background:#0b0d17;color:#cdd3e0;font:13px/1.4 system-ui,sans-serif;overflow:hidden}
  #g{width:100vw;height:100vh}
  #hud{position:fixed;top:0;left:0;padding:10px 14px;z-index:5;pointer-events:none}
  #hud h1{margin:0 0 4px;font-size:15px;color:#fff}
  #hud small{opacity:.7}
  #info{position:fixed;top:10px;right:10px;width:280px;background:#141726ee;
        border:1px solid #2a2f45;border-radius:8px;padding:12px;z-index:5;max-height:80vh;overflow:auto}
  #info b{color:#8ab4ff}
  #search{position:fixed;bottom:14px;left:14px;z-index:5;padding:7px 10px;border-radius:6px;
          border:1px solid #2a2f45;background:#141726;color:#cdd3e0;width:240px}
  .rel{color:#e0b070}
</style>
<script src="%%CDN%%"></script>
</head><body>
<div id="hud"><h1>%%HEADER%%</h1>
  <small>Drag: rotate &middot; Wheel: zoom &middot; Click node: focus &middot; Arrows = direction (source&rarr;target)</small></div>
<div id="info">Click a node to inspect it.</div>
<input id="search" placeholder="Search node... (Enter)">
<div id="g"></div>
<script>
const DATA = %%DATA%%;
const PALETTE = %%PALETTE%%;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
const col = c => c==null ? '#8892a6' : PALETTE[((c%PALETTE.length)+PALETTE.length)%PALETTE.length];
const byId = new Map(DATA.nodes.map(n=>[n.id,n]));
const G = ForceGraph3D()(document.getElementById('g'))
  .graphData(DATA).backgroundColor('#0b0d17').nodeId('id')
  .nodeVal(n => Math.max(1, Math.sqrt(n.degree))).nodeRelSize(3)
  .nodeColor(n => col(n.community))
  .nodeLabel(n => `<div style="background:#141726;padding:6px 8px;border-radius:6px;border:1px solid #2a2f45">`
     + `<b>${esc(n.label)}</b><br><span style="opacity:.7">${esc(n.community_name)}</span><br>`
     + `<span style="opacity:.5;font-size:11px">${esc(n.source_file)}${n.source_location?':'+esc(n.source_location):''}</span><br>`
     + `<span style="opacity:.5;font-size:11px">${n.degree} connections</span></div>`)
  .linkColor(l => l.confidence==='INFERRED' ? 'rgba(224,176,112,0.22)' : 'rgba(140,150,200,0.30)')
  .linkOpacity(0.35).linkWidth(0)
  .linkDirectionalArrowLength(3.2).linkDirectionalArrowRelPos(1)
  .linkLabel(l => `<span class="rel">${esc(l.relation)}</span> ${esc(l.confidence)}`)
  .cooldownTime(15000)
  .onNodeClick(n => {
     const r = 1 + 90/Math.hypot(n.x||1,n.y||1,n.z||1);
     G.cameraPosition({x:n.x*r,y:n.y*r,z:n.z*r}, n, 1200);
     const out=[];
     DATA.links.forEach(l => {
        const s=l.source.id||l.source, t=l.target.id||l.target;
        if(s===n.id) out.push(`&rarr; <span class="rel">${esc(l.relation)}</span> ${esc((byId.get(t)||{}).label||t)}`);
        if(t===n.id) out.push(`&larr; <span class="rel">${esc(l.relation)}</span> ${esc((byId.get(s)||{}).label||s)}`);
     });
     document.getElementById('info').innerHTML =
        `<b>${esc(n.label)}</b><br><small>${esc(n.community_name)}</small>`
        + `<br><small style="opacity:.6">${esc(n.source_file)}${n.source_location?':'+esc(n.source_location):''}</small>`
        + `<hr style="border-color:#2a2f45">${out.slice(0,60).join('<br>')||'(no relations)'}`
        + (out.length>60?`<br>&hellip; +${out.length-60} more`:'');
  });
document.getElementById('search').addEventListener('keydown', e => {
  if(e.key!=='Enter') return;
  const q=e.target.value.toLowerCase();
  const hit=DATA.nodes.find(n => (n.label||'').toLowerCase().includes(q));
  if(hit){const r=1+90/Math.hypot(hit.x||1,hit.y||1,hit.z||1);
    G.cameraPosition({x:hit.x*r,y:hit.y*r,z:hit.z*r}, hit, 1200);}
});
</script></body></html>""".replace("%%CDN%%", _CDN)
