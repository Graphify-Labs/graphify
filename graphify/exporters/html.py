"""html — moved verbatim from graphify/export.py."""
from __future__ import annotations

from graphify.exporters.base import COMMUNITY_COLORS  # noqa: E402,F401
from functools import lru_cache
from pathlib import Path
import html as _html
from graphify.analyze import _node_community_map
from graphify.paths import write_text_atomic
import json
import networkx as nx
from graphify.security import sanitize_label


MAX_NODES_FOR_VIZ = 20_000
_HTML_STALE_MARKER = ".graph.html.stale"

def _viz_node_limit() -> int:
    """Return the effective viz node limit, honoring GRAPHIFY_VIZ_NODE_LIMIT env var.

    Falls back to MAX_NODES_FOR_VIZ when the env var is unset, empty, or non-integer.
    Set to 0 to disable HTML viz unconditionally (useful for CI runners).
    """
    import os
    raw = os.environ.get("GRAPHIFY_VIZ_NODE_LIMIT")
    if raw is None or not raw.strip():
        return MAX_NODES_FOR_VIZ
    try:
        return int(raw)
    except ValueError:
        return MAX_NODES_FOR_VIZ

def _html_styles() -> str:
    return """<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f0f1a; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; display: flex; height: 100vh; overflow: hidden; }
  #graph { flex: 1; min-width: 0; overflow: hidden; position: relative; }
  #sidebar { width: 280px; background: #1a1a2e; border-left: 1px solid #2a2a4e; display: flex; flex-direction: column; overflow-x: hidden; overflow-y: auto; }
  #search-wrap { padding: 12px; border-bottom: 1px solid #2a2a4e; }
  #search { width: 100%; background: #0f0f1a; border: 1px solid #3a3a5e; color: #e0e0e0; padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
  #search:focus { border-color: #4E79A7; }
  #search-results { max-height: 140px; overflow-y: auto; padding: 4px 12px; border-bottom: 1px solid #2a2a4e; display: none; }
  .search-item { padding: 4px 6px; cursor: pointer; border-radius: 4px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .search-item:hover { background: #2a2a4e; }
  /* Collapsing animates grid-template-rows 1fr -> 0fr, which interpolates in
     every current browser. A native <details> cannot be animated shut: it stops
     rendering its body the instant `open` is removed. */
  /* A panel is a flex column so its body gets a definite height to clip against:
     without that the body keeps its full content height and paints over the
     panel below it when the sidebar squeezes the panel. */
  .panel { border-bottom: 1px solid #2a2a4e; padding: 10px 12px; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
  .phead { flex: none; cursor: pointer; font-size: 13px; color: #aaa; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 8px; user-select: none; }
  .phead::before { content: '\u25B8'; font-size: 10px; display: inline-block; transition: transform 0.28s ease; }
  .panel:not(.collapsed) .phead::before { transform: rotate(90deg); }
  .phead label { margin-left: auto; text-transform: none; letter-spacing: 0; font-size: 12px; display: flex; align-items: center; gap: 5px; cursor: pointer; }
  .pbody { display: grid; grid-template-rows: minmax(0, 1fr); transition: grid-template-rows 0.28s ease; min-height: 0; }
  .panel.collapsed .pbody { grid-template-rows: minmax(0, 0fr); }
  .pinner { overflow: hidden; min-height: 0; display: flex; flex-direction: column; }
  .pinner > :first-child { margin-top: 8px; }
  #info-panel:not(.collapsed) { min-height: 140px; }
  @media (prefers-reduced-motion: reduce) {
    .phead::before, .pbody, #legend-wrap { transition: none; }
  }
  #info-content { overflow-y: auto; min-height: 0; font-size: 13px; color: #ccc; line-height: 1.6; }
  #info-content .field { margin-bottom: 5px; }
  #info-content .field b { color: #e0e0e0; }
  #info-content .empty { color: #555; font-style: italic; }
  .neighbor-link { display: block; padding: 2px 6px; margin: 2px 0; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid #333; }
  .neighbor-link:hover { background: #2a2a4e; }
  #neighbors-list { max-height: 160px; overflow-y: auto; margin-top: 4px; }
  /* flex-grow is animated too: without it the panel would jump to full height
     the instant it opens, while its contents were still sliding down. */
  #legend-wrap { flex-grow: 0; min-height: 0; transition: flex-grow 0.28s ease; }
  #legend-wrap:not(.collapsed) { flex-grow: 1; }
  #legend { overflow-y: auto; min-height: 0; }
  .legend-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; border-radius: 4px; font-size: 12px; }
  .legend-item:hover { background: #2a2a4e; padding-left: 4px; }
  .legend-item.dimmed { opacity: 0.35; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .legend-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-count { color: #666; font-size: 11px; }
  #stats { padding: 10px 14px; border-top: 1px solid #2a2a4e; font-size: 11px; color: #555; }
  #physics { flex: none; font-size: 12px; }
  .ctl { display: flex; align-items: center; gap: 6px; padding: 3px 0; font-size: 11px; color: #aaa; }
  .ctl label { width: 82px; flex-shrink: 0; }
  .ctl input[type=range] { flex: 1; min-width: 0; accent-color: #4E79A7; height: 14px; }
  .ctl:has(input:disabled) { opacity: 0.35; }
  .ctl output { width: 40px; text-align: right; color: #ccc; font-variant-numeric: tabular-nums; }
  .btns { display: flex; gap: 6px; padding-top: 6px; }
  .btn { background: #2a2a4e; border: 1px solid #3a3a5e; color: #e0e0e0; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; flex: 1; }
  .btn:hover { background: #3a3a5e; }
  .btn.active { background: #4E79A7; border-color: #4E79A7; color: #fff; }
  .presets { flex-wrap: wrap; }
  .presets .btn { flex: 1 0 45%; }
  .hint { color: #666; font-size: 10px; padding-top: 6px; line-height: 1.4; }
  #legend-controls { flex: none; display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding: 4px 0; }
  #legend-controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: #aaa; user-select: none; }
  #legend-controls label:hover { color: #e0e0e0; }
  .legend-cb, #select-all-cb { appearance: none; -webkit-appearance: none; width: 14px; height: 14px; border: 1.5px solid #3a3a5e; border-radius: 3px; background: #0f0f1a; cursor: pointer; position: relative; flex-shrink: 0; }
  .legend-cb:checked, #select-all-cb:checked { background: #4E79A7; border-color: #4E79A7; }
  .legend-cb:checked::after, #select-all-cb:checked::after { content: ''; position: absolute; left: 3.5px; top: 1px; width: 4px; height: 7px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
  #select-all-cb:indeterminate { background: #4E79A7; border-color: #4E79A7; }
  #select-all-cb:indeterminate::after { content: ''; position: absolute; left: 2px; top: 5px; width: 8px; height: 2px; background: #fff; border: none; transform: none; }
</style>"""

@lru_cache(maxsize=1)
def _vendor_js() -> str:
    return (Path(__file__).parent / "vendor" / "force-graph.min.js").read_text(encoding="utf-8")


def _html_script(nodes_json: str, edges_json: str, legend_json: str, hyperedges_json: str) -> str:
    return f"""<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND = {legend_json};
const HYPEREDGES = {hyperedges_json};

// HTML-escape helper — prevents XSS when injecting graph data into innerHTML
function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

const nodeById = new Map(RAW_NODES.map(n => [n.id, n]));
const adj = new Map();
RAW_EDGES.forEach(e => {{
  if (!adj.has(e.from)) adj.set(e.from, new Set());
  if (!adj.has(e.to)) adj.set(e.to, new Set());
  adj.get(e.from).add(e.to);
  adj.get(e.to).add(e.from);
}});
const links = RAW_EDGES.map(e => ({{ source: e.from, target: e.to, title: e.title, dashes: e.dashes, width: e.width, color: `rgba(200,200,220,${{e.opacity}})` }}));
const DIM_LINK = 'rgba(200,200,220,0.03)';
const DASH = [4, 2];

const hiddenCommunities = new Set();
let selectedId = null;
// Spotlight: selected node plus its neighbours; everything else is dimmed.
let focus = null;
let view = null;
// "forceAtlas2" mirrors the vis-network forceAtlas2Based settings the previous
// renderer shipped (gravitationalConstant -60, springLength 120, centralGravity
// 0.005, no cutoff) with the community and halo forces off, so the old look can
// be compared on the same page. d3-force has no ForceAtlas2 solver; this is
// the closest mapping of its knobs, not the algorithm.
// compact: strong centre pull, short springs; the whole graph on one screen.
// spread: weak centre pull, big repulsion, long loose springs; room to drag
// nodes apart when untangling a dense core.
const BASE = {{ linkStr: 1, damping: 0.4, cooling: 0.03 }};
const PRESETS = {{
  graphify: {{ ...BASE, charge: 40, range: 600, linkLen: 60, cohesion: 0.1, separation: 0.8, gravity: 0.03, halo: 0.05 }},
  forceAtlas2: {{ ...BASE, charge: 60, range: 3000, linkLen: 120, cohesion: 0, separation: 0, gravity: 0.01, halo: 0 }},
  compact: {{ ...BASE, charge: 80, range: 3000, linkLen: 40, cohesion: 0.1, separation: 0.3, gravity: 0.15, halo: 0 }},
  spread: {{ ...BASE, charge: 150, range: 3000, linkLen: 150, linkStr: 0.5, cohesion: 0.05, separation: 1, gravity: 0.01, halo: 0.05 }},
}};
const P = {{ ...PRESETS.graphify }};
// Fragments: every node outside the giant connected component. Nothing links
// them to the core, so the physics treats them separately (see gravityForce).
(() => {{
  const seen = new Set();
  let giant = [];
  for (const start of RAW_NODES) {{
    if (seen.has(start.id)) continue;
    const comp = [start.id]; seen.add(start.id);
    for (let i = 0; i < comp.length; i++) for (const m of adj.get(comp[i]) || []) if (!seen.has(m)) {{ seen.add(m); comp.push(m); }}
    if (comp.length > giant.length) giant = comp;
  }}
  const core = new Set(giant);
  RAW_NODES.forEach(n => {{ n.halo = !core.has(n.id); }});
}})();
const HAS_HALO = RAW_NODES.some(n => n.halo);
// Seed positions by community: each community gets its own small disc, and the
// discs are packed on a sunflower spiral, largest first. Starting the simulation
// from clusters instead of one big spiral is what keeps communities as clusters;
// from a single spiral, repulsion flings the disconnected ones into a ring.
(() => {{
  const groups = new Map();
  RAW_NODES.forEach(n => {{ if (!groups.has(n.community)) groups.set(n.community, []); groups.get(n.community).push(n); }});
  const golden = Math.PI * (3 - Math.sqrt(5));
  let area = 0;
  const rank = m => (m[0].halo ? 1e9 : 0) - m.length;
  [...groups.values()].sort((a, b) => rank(a) - rank(b)).forEach((members, i) => {{
    const r = 20 * Math.sqrt(members.length) + 30;
    area += Math.PI * (1.6 * r) ** 2;
    const d = Math.sqrt(area / Math.PI), a = i * golden;
    const cx = d * Math.cos(a), cy = d * Math.sin(a);
    members.forEach((n, j) => {{
      const rr = r * Math.sqrt((j + 0.5) / members.length), aa = j * golden;
      n.x = cx + rr * Math.cos(aa); n.y = cy + rr * Math.sin(aa);
    }});
  }});
}})();
// Edges are hidden when zoomed far out: they read as haze and cost most of the frame.
const BIG_GRAPH = RAW_EDGES.length > 5000;
const LINK_ZOOM_THRESHOLD = BIG_GRAPH ? 0.08 : 0;
let linksShown = LINK_ZOOM_THRESHOLD === 0;
let linkDetail = true;

// Andrew's monotone chain, counter-clockwise hull. Tracing member order instead
// self-intersects whenever the layout does not place members in angular order.
function convexHull(pts) {{
  const p = pts.slice().sort((a, b) => (a.x - b.x) || (a.y - b.y));
  if (p.length < 3) return p;
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const build = seq => {{
    const out = [];
    for (const q of seq) {{
      while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], q) <= 0) out.pop();
      out.push(q);
    }}
    out.pop();
    return out;
  }};
  const hull = build(p).concat(build(p.slice().reverse()));
  return hull.length >= 3 ? hull : p;
}}

function drawHyperedges(ctx, scale) {{
  HYPEREDGES.forEach(h => {{
    const positions = h.nodes.map(id => nodeById.get(id)).filter(n => n && !hiddenCommunities.has(n.community));
    if (positions.length < 2) return;
    ctx.save();
    ctx.globalAlpha = 0.12;
    ctx.fillStyle = '#6366f1';
    ctx.strokeStyle = '#6366f1';
    ctx.lineWidth = 2 / scale;
    const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length;
    const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length;
    const hull = convexHull(positions);
    const expanded = hull.map(p => ({{ x: cx + (p.x - cx) * 1.15, y: cy + (p.y - cy) * 1.15 }}));
    ctx.beginPath();
    expanded.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 0.5;
    ctx.stroke();
    if (h.label) {{
      ctx.globalAlpha = 0.8;
      ctx.fillStyle = '#c7d2fe';
      ctx.font = `${{Math.max(11, 11 / scale)}}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillText(h.label, cx, cy - 20 / scale);
    }}
    ctx.restore();
  }});
}}

const container = document.getElementById('graph');
const offscreen = n => view && (n.x < view.x0 || n.x > view.x1 || n.y < view.y0 || n.y > view.y1);
const linkDash = l => l.dashes ? DASH : null;
const fit = () => graph.zoomToFit(400, 40);
const graph = ForceGraph()(container)
  .width(container.clientWidth).height(container.clientHeight)
  .backgroundColor('#0f0f1a')
  .graphData({{ nodes: RAW_NODES, links }})
  .warmupTicks(0)
  .cooldownTime(60000)
  .d3AlphaMin(0.001)
  .d3AlphaDecay(0.03)
  .d3VelocityDecay(0.4)
  .minZoom(0.002)
  .nodeLabel(n => n.title.replace(/\\n/g, '<br>'))
  .nodeVisibility(n => !hiddenCommunities.has(n.community))
  .linkVisibility(l => linksShown && !settling && !hiddenCommunities.has(l.source.community) && !hiddenCommunities.has(l.target.community))
  .onZoom(({{ k }}) => {{
    const show = k > LINK_ZOOM_THRESHOLD;
    if (show !== linksShown) {{ linksShown = show; applyVisibility(); }}
    const detail = k > 0.5;
    if (detail !== linkDetail) {{
      linkDetail = detail;
      graph.linkDirectionalArrowLength(detail ? 4 : 0).linkLineDash(detail ? linkDash : null);
    }}
  }})
  .nodeCanvasObject((n, ctx, scale) => {{
    if (offscreen(n)) return;
    const r = n.size;
    const dim = focus && !focus.has(n.id);
    ctx.globalAlpha = dim ? 0.12 : 1;
    ctx.fillStyle = n.id === selectedId ? '#ffffff' : n.color;
    if (r * scale < 1.5 && !n.ring && n.fx === undefined) {{ ctx.fillRect(n.x - r, n.y - r, 2 * r, 2 * r); ctx.globalAlpha = 1; return; }}
    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
    ctx.fill();
    if (n.fx !== undefined && !n.ring) {{
      ctx.lineWidth = 1.5 / scale;
      ctx.strokeStyle = '#ffffff';
      ctx.stroke();
    }}
    if (n.ring) {{
      ctx.lineWidth = 3 / scale;
      ctx.strokeStyle = n.ring;
      ctx.setLineDash(n.ring_dashed ? [4 / scale, 4 / scale] : []);
      ctx.stroke();
      ctx.setLineDash([]);
    }}
    if (n.show_label || scale > 2.5) {{
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = '#ffffff';
      ctx.fillText(n.label, n.x, n.y + r + 2);
    }}
    ctx.globalAlpha = 1;
  }})
  .nodePointerAreaPaint((n, color, ctx) => {{
    if (offscreen(n)) return;
    const r = n.size + 2;
    ctx.fillStyle = color;
    ctx.fillRect(n.x - r, n.y - r, 2 * r, 2 * r);
  }})
  .linkColor(l => focus && !(focus.has(l.source.id) && focus.has(l.target.id)) ? DIM_LINK : l.color)
  .linkWidth(l => l.width)
  .linkLineDash(linkDash)
  .linkDirectionalArrowLength(4)
  .linkDirectionalArrowRelPos(1)
  .linkLabel(l => l.title)
  .onRenderFramePre((ctx, scale) => {{
    // Viewport in graph units, padded by a screen margin; nodes outside it are
    // skipped entirely so zooming in does not pay for the whole graph.
    const a = graph.screen2GraphCoords(0, 0), b = graph.screen2GraphCoords(container.clientWidth, container.clientHeight);
    const m = 40 / scale;
    view = {{ x0: a.x - m, y0: a.y - m, x1: b.x + m, y1: b.y + m }};
    drawHyperedges(ctx, scale);
  }})
  .onNodeClick(n => {{ selectedId = n.id; showInfo(n.id); }})
  .onBackgroundClick(() => {{
    selectedId = null;
    setFocus(null);
    document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>';
  }})
  // Dropping a node pins it (force-graph releases it otherwise), so you can
  // untangle by hand. Right-click hands it back to the simulation.
  .onNodeDragEnd(n => {{ n.fx = n.x; n.fy = n.y; }})
  .onNodeRightClick(n => {{ n.fx = n.fy = undefined; if (physicsCb.checked) graph.d3ReheatSimulation(); }})
  .onEngineTick(() => {{ if (autoFit && ++ticks % 25 === 0) fit(); }})
  .onEngineStop(() => {{
    settling = false;
    applyVisibility();
    if (autoFit) {{ autoFit = false; fit(); }}
  }});
let ticks = 0;
// The view follows the graph only during the first settle; after that the
// camera is the user's.
let autoFit = true;
// Edges are hidden while a big graph settles: they are most of the frame cost
// and only readable once nodes stop moving.
let settling = BIG_GRAPH;
container.addEventListener('contextmenu', e => e.preventDefault());
new ResizeObserver(() => graph.width(container.clientWidth).height(container.clientHeight)).observe(container);
function setFocus(ids) {{
  focus = ids;
  graph.linkColor(graph.linkColor());
}}
// Cluster force: every node is pulled toward its community's live centroid,
// and communities whose estimated radii overlap push each other apart. This is
// what keeps communities as separate blobs instead of one core plus a ring of
// stragglers, which is what plain repulsion produces on a graph with hundreds
// of disconnected components.
const clusterForce = (() => {{
  let nodes = [], groups = [];
  const force = alpha => {{
    for (const g of groups) {{ g.x = 0; g.y = 0; g.dx = 0; g.dy = 0; g.r2 = 0; }}
    for (const n of nodes) {{ n.__g.x += n.x; n.__g.y += n.y; }}
    for (const g of groups) {{ g.x /= g.k; g.y /= g.k; }}
    const s = P.cohesion * alpha;
    for (const n of nodes) {{
      const dx = n.__g.x - n.x, dy = n.__g.y - n.y;
      n.__g.r2 += dx * dx + dy * dy;
      n.vx += dx * s; n.vy += dy * s;
    }}
    // Radius from the members' actual spread, so tight and loose communities
    // both get the right personal space.
    for (const g of groups) g.r = 1.5 * Math.sqrt(g.r2 / g.k) + 25;
    // ponytail: O(C^2) pair scan over communities; a quadtree is the upgrade if C grows past a few thousand
    const sep = P.separation * alpha;
    if (sep > 0) for (let i = 0; i < groups.length; i++) {{
      const a = groups[i];
      for (let j = i + 1; j < groups.length; j++) {{
        const b = groups[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.hypot(dx, dy) || 1e-6, min = a.r + b.r;
        if (d >= min) continue;
        // Bounded nudge: overlaps between big clusters run to hundreds of
        // units, and one cluster can overlap dozens, so an unbounded push
        // sends the layout to infinity.
        const push = Math.min(min - d, 40) / d * sep, tot = a.k + b.k;
        dx *= push; dy *= push;
        a.dx -= dx * b.k / tot; a.dy -= dy * b.k / tot;
        b.dx += dx * a.k / tot; b.dy += dy * a.k / tot;
      }}
    }}
    for (const g of groups) {{
      const m = Math.hypot(g.dx, g.dy), cap = 40 * alpha;
      if (m > cap) {{ g.dx *= cap / m; g.dy *= cap / m; }}
    }}
    for (const n of nodes) {{ n.vx += n.__g.dx; n.vy += n.__g.dy; }}
  }};
  force.initialize = ns => {{
    nodes = ns;
    const byId = new Map();
    groups = [];
    for (const n of ns) {{
      let g = byId.get(n.community);
      if (!g) {{ g = {{ k: 0 }}; byId.set(n.community, g); groups.push(g); }}
      g.k++;
      n.__g = g;
    }}
  }};
  return force;
}})();
// Central gravity for the core, the vis-network "centralGravity" knob. With
// halo > 0, fragments get a radial spring toward a band just outside the core
// instead: pushed out if they are inside it, pulled back if they drift away,
// so they ring the core without escaping and without burying it.
const gravityForce = (() => {{
  let core = [], halo = [];
  const force = alpha => {{
    const g = P.gravity * alpha, h = P.halo * alpha;
    if (g) for (const n of core) {{ n.vx -= n.x * g; n.vy -= n.y * g; }}
    if (!halo.length) return;
    if (!h) {{ if (g) for (const n of halo) {{ n.vx -= n.x * g; n.vy -= n.y * g; }} return; }}
    let s2 = 0;
    for (const n of core) s2 += n.x * n.x + n.y * n.y;
    const R = Math.sqrt(s2 / core.length) * 1.6 + 150;
    for (const n of halo) {{
      const r = Math.hypot(n.x, n.y) || 1e-6, f = (R - r) / r * h;
      n.vx += n.x * f; n.vy += n.y * f;
    }}
  }};
  force.initialize = ns => {{
    core = ns.filter(n => !n.halo); halo = ns.filter(n => n.halo);
    if (!core.length) {{ core = ns; halo = []; }}
  }};
  return force;
}})();
const baseLinkStrength = graph.d3Force('link').strength();
function applyPhysics() {{
  graph.d3Force('link').distance(P.linkLen).strength((l, i, ls) => baseLinkStrength(l, i, ls) * P.linkStr);
  graph.d3Force('charge').strength(-P.charge).distanceMax(P.range).theta(1.2);
  graph.d3VelocityDecay(P.damping).d3AlphaDecay(P.cooling);
}}
graph.d3Force('center', null);
graph.d3Force('community', clusterForce);
graph.d3Force('gravity', gravityForce);

// Panel headers collapse their panel. Clicks on the physics on/off control
// inside the header must not also toggle the panel.
document.querySelectorAll('.phead').forEach(h => h.addEventListener('click', e => {{
  if (e.target.closest('input, label')) return;
  h.parentElement.classList.toggle('collapsed');
}}));

const physicsCb = document.getElementById('physics-cb');
// hideEdges: the initial settle, the Reheat button and switching physics on
// hide edges on big graphs for speed. A slider release keeps them visible, so
// the effect of the change is what you see, not edges vanishing.
function reheat(hideEdges = true) {{
  if (!physicsCb.checked) return;
  settling = hideEdges && BIG_GRAPH;
  applyVisibility();
  graph.cooldownTime(60000);
  graph.d3ReheatSimulation();
}}
// Sliders with nothing to act on are greyed out: repel range without
// repulsion, halo without any disconnected pieces.
function syncSliderEnabled() {{
  document.getElementById('p-range').disabled = P.charge === 0;
  document.getElementById('p-halo').disabled = !HAS_HALO;
}}
// P is the single source of truth for the panel: sliders and readouts are
// filled from it here and after every preset click, never hardcoded in markup.
function syncSlidersFromP() {{
  document.querySelectorAll('#physics input[type=range]').forEach(el => {{
    el.value = P[el.dataset.key];
    el.nextElementSibling.textContent = String(P[el.dataset.key]);
  }});
}}
function syncPanel() {{
  syncSlidersFromP();
  syncPresetHighlight();
  syncSliderEnabled();
  applyPhysics();
}}
syncPanel();
physicsCb.addEventListener('change', () => {{
  if (physicsCb.checked) reheat();
  else graph.cooldownTime(0);
}});
document.querySelectorAll('#physics input[type=range]').forEach(el => {{
  el.addEventListener('input', () => {{ P[el.dataset.key] = +el.value; syncPanel(); }});
  el.addEventListener('change', () => reheat(false));
}});
// A preset button lights up while every slider still matches it; nudging any
// slider off a preset clears the highlight.
function syncPresetHighlight() {{
  document.querySelectorAll('#physics [data-preset]').forEach(b => {{
    const preset = PRESETS[b.dataset.preset];
    b.classList.toggle('active', Object.keys(preset).every(k => P[k] === preset[k]));
  }});
}}
document.querySelectorAll('#physics [data-preset]').forEach(b => b.addEventListener('click', () => {{
  Object.assign(P, PRESETS[b.dataset.preset]);
  syncPanel();
  reheat(false);
}}));
document.getElementById('p-reheat').addEventListener('click', () => reheat());
document.getElementById('p-unpin').addEventListener('click', () => {{ RAW_NODES.forEach(n => {{ n.fx = n.fy = undefined; }}); reheat(); }});
document.getElementById('p-fit').addEventListener('click', fit);

function showInfo(nodeId) {{
  const n = nodeById.get(nodeId);
  if (!n) return;
  setFocus(new Set([nodeId, ...(adj.get(nodeId) || [])]));
  const neighborIds = [...(adj.get(nodeId) || [])];
  const neighborItems = neighborIds.map(nid => {{
    const nb = nodeById.get(nid);
    const color = nb ? nb.color : '#555';
    return `<span class="neighbor-link" style="border-left-color:${{esc(color)}}" data-nid="${{esc(nid)}}">${{esc(nb ? nb.label : nid)}}</span>`;
  }}).join('');
  document.getElementById('info-content').innerHTML = `
    <div class="field"><b>${{esc(n.label)}}</b></div>
    <div class="field">Type: ${{esc(n.file_type || 'unknown')}}</div>
    <div class="field">Community: ${{esc(n.community_name)}}</div>
    <div class="field">Source: ${{esc(n.source_file || '-')}}</div>
    <div class="field">Degree: ${{n.degree}}</div>
    ${{neighborIds.length ? `<div class="field" style="margin-top:8px;color:#aaa;font-size:11px">Neighbors (${{neighborIds.length}})</div><div id="neighbors-list">${{neighborItems}}</div>` : ''}}
  `;
}}

function focusNode(nodeId) {{
  const n = nodeById.get(nodeId);
  if (!n) return;
  selectedId = nodeId;
  graph.centerAt(n.x, n.y, 400);
  graph.zoom(3, 400);
  showInfo(nodeId);
}}

// Neighbor links carry the id in an HTML-escaped data attribute and dispatch
// through one delegated listener, never an inline onclick (stored XSS, #1838).
document.addEventListener('click', e => {{
  const el = e.target.closest('.neighbor-link');
  if (el && el.dataset.nid !== undefined) focusNode(el.dataset.nid);
}});

const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {{
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) {{ searchResults.style.display = 'none'; return; }}
  const matches = RAW_NODES.filter(n => n.label.toLowerCase().includes(q)).slice(0, 20);
  if (!matches.length) {{ searchResults.style.display = 'none'; return; }}
  searchResults.style.display = 'block';
  matches.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.label;
    el.style.borderLeft = `3px solid ${{n.color}}`;
    el.style.paddingLeft = '8px';
    el.onclick = () => {{
      focusNode(n.id);
      searchResults.style.display = 'none';
      searchInput.value = '';
    }};
    searchResults.appendChild(el);
  }});
}});
document.addEventListener('click', e => {{
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
}});

const selectAllCb = document.getElementById('select-all-cb');

function applyVisibility() {{
  graph.nodeVisibility(graph.nodeVisibility());
  selectAllCb.checked = hiddenCommunities.size === 0;
  selectAllCb.indeterminate = hiddenCommunities.size > 0 && hiddenCommunities.size < LEGEND.length;
}}

function toggleAllCommunities(hide) {{
  document.querySelectorAll('.legend-item').forEach(item => item.classList.toggle('dimmed', hide));
  document.querySelectorAll('.legend-cb').forEach(cb => {{ cb.checked = !hide; }});
  LEGEND.forEach(c => {{ hide ? hiddenCommunities.add(c.cid) : hiddenCommunities.delete(c.cid); }});
  applyVisibility();
}}

const legendEl = document.getElementById('legend');
LEGEND.forEach(c => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'legend-cb';
  cb.checked = true;
  cb.addEventListener('change', (e) => {{
    e.stopPropagation();
    cb.checked ? hiddenCommunities.delete(c.cid) : hiddenCommunities.add(c.cid);
    item.classList.toggle('dimmed', !cb.checked);
    applyVisibility();
  }});
  item.innerHTML = `<div class="legend-dot" style="background:${{c.color}}"></div>
    <span class="legend-label">${{c.label}}</span>
    <span class="legend-count">${{c.count}}</span>`;
  item.prepend(cb);
  item.onclick = (e) => {{
    if (e.target === cb) return;
    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event('change'));
  }};
  legendEl.appendChild(item);
}});
</script>"""

def _html_document_title(output_path: str) -> str:
    """Return a portable label for the graph.html <title>.

    Tracked artifacts must not embed the generator host absolute path
    (regression of #433; reported again as #2598 on Windows). Keep from the
    configured output-dir bare name (``graphify-out`` / ``GRAPHIFY_OUT``
    basename) onward — portable in every case; otherwise fall back to a
    cwd-relative label, and finally the filename only.
    """
    from graphify.paths import GRAPHIFY_OUT_NAME

    raw = str(output_path).replace("\\", "/")
    # Drop Windows drive prefix so Path parts are comparable on any OS.
    if len(raw) >= 3 and raw[1] == ":" and raw[0].isalpha() and raw[2] == "/":
        raw = raw[2:]  # "/Users/..." style after drive strip
    p = Path(raw)

    parts = list(Path(raw).parts)
    # Path("C:/Users/..") on POSIX may keep "C:" as first part — strip it.
    if parts and len(parts[0]) == 2 and parts[0][1] == ":" and parts[0][0].isalpha():
        parts = parts[1:]
    # Prefer keeping from the output-dir marker onward: portable in every
    # case, whereas a cwd-relative path still leaks host/user segments when
    # the graph is built from a directory ABOVE the project (#2598 follow-up).
    marker = GRAPHIFY_OUT_NAME
    for i, part in enumerate(parts):
        if part == marker or part.startswith("graphify-out"):
            return "/".join(parts[i:])

    # No standard out-dir marker (fully custom output path): fall back to a
    # cwd-relative label when the target is under cwd, else the bare filename.
    try:
        resolved = p if p.is_absolute() else (Path.cwd() / p)
        rel = resolved.resolve().relative_to(Path.cwd().resolve())
        label = rel.as_posix()
        if label and label != ".":
            return label
    except (ValueError, OSError, RuntimeError):
        pass

    name = p.name
    return name if name else "graph.html"

def to_html(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    member_counts: dict[int, int] | None = None,
    node_limit: int | None = None,
    learning_overlay: dict | None = None,
) -> bool:
    """Generate a self-contained interactive HTML visualization of the graph.

    Rendered by an inlined force-graph build with live d3-force physics, so the
    file opens offline and the graph self-organizes in the browser.

    Features: node size by degree, click-to-inspect panel, search box,
    community filter, hyperedge hulls, confidence-styled edges.
    Raises ValueError if graph exceeds MAX_NODES_FOR_VIZ.

    If member_counts is provided (aggregated community view), node sizes are
    based on community member counts rather than graph degree.

    If node_limit is set and the graph exceeds it, automatically builds an
    aggregated community-level meta-graph instead of raising ValueError.

    Returns True when the output was written. Returns False when an aggregated
    view would contain fewer than two communities and is intentionally skipped.
    """
    limit = node_limit if node_limit is not None else _viz_node_limit()
    if G.number_of_nodes() > limit:
        if node_limit is not None:
            # Build aggregated community meta-graph
            from collections import Counter as _Counter
            import networkx as _nx
            print(f"Graph has {G.number_of_nodes()} nodes (above {limit} limit). Building aggregated community view...")
            node_to_community = {nid: cid for cid, members in communities.items() for nid in members}
            meta = _nx.Graph()
            for cid, members in communities.items():
                meta.add_node(str(cid), label=(community_labels or {}).get(cid, f"Community {cid}"))
            edge_counts = _Counter()
            for u, v in G.edges():
                cu, cv = node_to_community.get(u), node_to_community.get(v)
                if cu is not None and cv is not None and cu != cv:
                    edge_counts[(min(cu, cv), max(cu, cv))] += 1
            for (cu, cv), w in edge_counts.items():
                meta.add_edge(str(cu), str(cv), weight=w,
                              relation=f"{w} cross-community edges", confidence="AGGREGATED")
            if meta.number_of_nodes() <= 1:
                print("Single community - aggregated view not useful. Skipping graph.html.")
                return False
            meta_communities = {cid: [str(cid)] for cid in communities}
            mc = {cid: len(members) for cid, members in communities.items()}
            # Remap hyperedges from semantic node IDs to community IDs
            raw_hyperedges = G.graph.get("hyperedges", [])
            if raw_hyperedges:
                remapped = []
                for he in raw_hyperedges:
                    he_members = he.get("nodes", [])
                    comm_ids, seen = [], set()
                    for nid in he_members:
                        c = node_to_community.get(nid)
                        if c is None:
                            continue
                        s = str(c)
                        if s in seen:
                            continue
                        seen.add(s)
                        comm_ids.append(s)
                    if len(comm_ids) < 2:
                        continue
                    remapped.append({
                        "id": he.get("id", ""),
                        "label": he.get("label") or he.get("relation", "").replace("_", " "),
                        "nodes": comm_ids,
                    })
                meta.graph["hyperedges"] = remapped
            written = to_html(meta, meta_communities, output_path,
                              community_labels=community_labels, member_counts=mc)
            if not written:
                return False
            print(f"graph.html written (aggregated: {meta.number_of_nodes()} community nodes, {meta.number_of_edges()} cross-community edges)")
            print("Tip: run with --obsidian for full node-level detail.")
            return True
        raise ValueError(
            f"Graph has {G.number_of_nodes()} nodes - too large for HTML viz "
            f"(limit: {limit}). Use --no-viz, raise GRAPHIFY_VIZ_NODE_LIMIT, "
            f"or reduce input size."
        )

    node_community = _node_community_map(communities)
    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1
    max_mc = (max(member_counts.values(), default=1) or 1) if member_counts else 1

    # Work-memory overlay (derived sidecar). When not passed explicitly, load it
    # best-effort from the sibling .graphify_learning.json next to the output
    # graph.html (which lives beside graph.json). Empty/missing => no learning
    # fields, so the un-annotated render is byte-identical to pre-feature.
    if learning_overlay is None:
        learning_overlay = {}
        try:
            from graphify.reflect import load_learning_overlay as _llo
            learning_overlay = _llo(Path(output_path))
        except Exception:
            learning_overlay = {}
    # Status -> ring color. preferred=green, contested=amber. Tentative gets no
    # ring (it's not yet trustworthy enough to highlight in the map).
    _RING = {"preferred": "#22c55e", "contested": "#f59e0b"}

    vis_nodes = []
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        label = sanitize_label(data.get("label", node_id))
        deg = degree.get(node_id, 1)
        ratio = member_counts.get(cid, 1) / max_mc if member_counts else deg / max_deg
        size = 5 + 15 * ratio
        # Only show label for high-degree nodes by default; others show on hover
        show_label = True if member_counts else deg >= max_deg * 0.15
        node = {
            "id": node_id,
            "label": label,
            "color": color,
            "size": round(size, 1),
            "show_label": show_label,
            "title": _html.escape(label),
            "community": cid,
            "community_name": sanitize_label((community_labels or {}).get(cid, f"Community {cid}")),
            "source_file": sanitize_label(str(data.get("source_file") or "")),
            "file_type": data.get("file_type", ""),
            "degree": deg,
        }
        # Conditional learning fields — only present for annotated nodes, so
        # un-annotated output keeps the exact pre-feature node dict shape.
        entry = learning_overlay.get(str(node_id)) if learning_overlay else None
        if entry:
            status = sanitize_label(str(entry.get("status", "")))
            stale = bool(entry.get("stale"))
            node["learning_status"] = status
            node["learning_stale"] = stale
            ring = _RING.get(status)
            if ring:
                # Status-colored ring via the border; stale => desaturated + dashed.
                node["ring"] = "#9ca3af" if stale else ring
                node["ring_dashed"] = stale
            # Lesson line appended to the hover title.
            if status == "contested":
                lesson = f"Lesson: contested (useful {entry.get('uses', 0)} / dead-end {entry.get('neg', 0)})"
            elif status == "preferred":
                lesson = f"Lesson: preferred source ({entry.get('uses', 0)} useful, score={entry.get('score', 0)})"
            else:
                lesson = f"Lesson: {status} ({entry.get('uses', 0)} useful)"
            if stale:
                lesson += " [code changed — re-verify]"
            node["title"] = _html.escape(label) + "\n" + _html.escape(sanitize_label(lesson))
        vis_nodes.append(node)

    # Build edges list. Restore original edge direction from _src/_tgt
    # (stashed by build.py for exactly this reason): undirected NetworkX
    # canonicalizes endpoint order, which would otherwise flip the arrow
    # for `calls` and `rationale_for` in the rendered graph (#563).
    vis_edges = []
    for u, v, data in G.edges(data=True):
        confidence = data.get("confidence", "EXTRACTED")
        relation = data.get("relation", "")
        true_src = data.get("_src", u)
        true_tgt = data.get("_tgt", v)
        # Cross-community edges are the long ones; fade them so they read as context, not haze.
        cross = node_community.get(u, 0) != node_community.get(v, 0)
        vis_edges.append({
            "from": true_src,
            "to": true_tgt,
            "label": relation,
            "title": _html.escape(f"{relation} [{confidence}]"),
            "dashes": confidence != "EXTRACTED",
            "width": 1 if confidence == "EXTRACTED" else 0.6,
            "opacity": round((0.5 if confidence == "EXTRACTED" else 0.25) * (0.4 if cross else 1.0), 2),
            "confidence": confidence,
        })

    # Build community legend data
    legend_data = []
    for cid in sorted((community_labels or {}).keys()):
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        lbl = _html.escape(sanitize_label((community_labels or {}).get(cid, f"Community {cid}")))
        n = member_counts.get(cid, len(communities.get(cid, []))) if member_counts else len(communities.get(cid, []))
        legend_data.append({"cid": cid, "color": color, "label": lbl, "count": n})

    # Escape </script> sequences so embedded JSON cannot break out of the script tag
    def _js_safe(obj) -> str:
        return json.dumps(obj).replace("</", "<\\/")

    nodes_json = _js_safe(vis_nodes)
    edges_json = _js_safe(vis_edges)
    legend_json = _js_safe(legend_data)
    hyperedges_json = _js_safe(getattr(G, "graph", {}).get("hyperedges", []))
    title = _html.escape(sanitize_label(_html_document_title(output_path)))
    stats = f"{G.number_of_nodes()} nodes &middot; {G.number_of_edges()} edges &middot; {len(communities)} communities"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify - {title}</title>
<script>{_vendor_js()}</script>
{_html_styles()}
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="info-panel" class="panel">
    <div class="phead">Node Info</div>
    <div class="pbody"><div class="pinner">
      <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
    </div></div>
  </div>
  <div id="legend-wrap" class="panel">
    <div class="phead">Communities</div>
    <div class="pbody"><div class="pinner">
    <div id="legend-controls">
      <label><input type="checkbox" id="select-all-cb" checked onchange="toggleAllCommunities(!this.checked)">Select All</label>
    </div>
    <div id="legend"></div>
    </div></div>
  </div>
  <div id="physics" class="panel">
    <div class="phead">Physics <label title="Run the simulation. Off freezes every node where it is; drags still move single nodes."><input type="checkbox" id="physics-cb" checked> on</label></div>
    <div class="pbody"><div class="pinner">
    <div class="btns presets" style="padding: 0 0 6px">
      <button class="btn" data-preset="graphify" title="This renderer's defaults: community cohesion and separation on, disconnected pieces pushed to a halo.">graphify</button>
      <button class="btn" data-preset="forceAtlas2" title="Approximates the vis-network forceAtlas2Based settings of the previous graph.html: plain repulsion and springs, no community forces, no halo. For comparison.">forceAtlas2</button>
      <button class="btn" data-preset="compact" title="Strong centre pull and short springs: the whole graph in one screen, communities packed together.">compact</button>
      <button class="btn" data-preset="spread" title="Weak centre pull, big repulsion, long loose springs: room to drag nodes apart when untangling a dense core.">spread</button>
    </div>
    <div class="ctl" title="How hard every node pushes every other node away. Higher spreads the graph out; lower packs it tighter."><label for="p-charge">repulsion</label><input type="range" id="p-charge" data-key="charge" min="0" max="300" step="5"><output></output></div>
    <div class="ctl" title="Distance beyond which repulsion is ignored. Larger is smoother but costs more per tick. Has no effect while repulsion is 0."><label for="p-range">repel range</label><input type="range" id="p-range" data-key="range" min="50" max="3000" step="50"><output></output></div>
    <div class="ctl" title="Rest length of an edge. The spring pulls linked nodes toward this distance."><label for="p-linkLen">link length</label><input type="range" id="p-linkLen" data-key="linkLen" min="5" max="300" step="5"><output></output></div>
    <div class="ctl" title="How strongly edges pull toward their rest length. 0 turns edges into decoration only."><label for="p-linkStr">link strength</label><input type="range" id="p-linkStr" data-key="linkStr" min="0" max="2" step="0.05"><output></output></div>
    <div class="ctl" title="Pull toward the centre of a node's own community. Higher makes tighter community blobs."><label for="p-cohesion">cohesion</label><input type="range" id="p-cohesion" data-key="cohesion" min="0" max="0.5" step="0.01"><output></output></div>
    <div class="ctl" title="Push between communities whose members overlap. Higher spreads communities apart from each other."><label for="p-separation">separation</label><input type="range" id="p-separation" data-key="separation" min="0" max="2" step="0.05"><output></output></div>
    <div class="ctl" title="Pull toward the centre for the main connected graph. Keeps it compact; 0 lets it sprawl."><label for="p-gravity">gravity</label><input type="range" id="p-gravity" data-key="gravity" min="0" max="0.3" step="0.01"><output></output></div>
    <div class="ctl" title="Radial spring for pieces with no edge to the main graph: pushed out to a ring past its rim. 0 gives them ordinary gravity instead."><label for="p-halo">halo</label><input type="range" id="p-halo" data-key="halo" min="0" max="0.3" step="0.01"><output></output></div>
    <div class="ctl" title="Velocity lost each tick. Higher settles faster with less overshoot; lower drifts longer."><label for="p-damping">damping</label><input type="range" id="p-damping" data-key="damping" min="0.05" max="0.95" step="0.05"><output></output></div>
    <div class="ctl" title="How fast the simulation loses energy overall. Higher stops sooner with a rougher layout."><label for="p-cooling">cooling</label><input type="range" id="p-cooling" data-key="cooling" min="0.005" max="0.2" step="0.005"><output></output></div>
    <div class="btns"><button class="btn" id="p-reheat" title="Restart the simulation at full energy with the current settings.">Reheat</button><button class="btn" id="p-unpin" title="Release every node you pinned by dragging, then reheat.">Unpin all</button><button class="btn" id="p-fit" title="Zoom and pan so the whole graph is in view.">Fit</button></div>
    <div class="hint">Drag a node to pin it where you drop it. Right-click a node to release it. Click a node to spotlight its neighbours. Halo pushes pieces with no link to the main graph out to the rim.</div>
    </div></div>
  </div>
  <div id="stats">{stats}</div>
</div>
{_html_script(nodes_json, edges_json, legend_json, hyperedges_json)}
</body>
</html>"""

    write_text_atomic(output_path, html)
    return True
