"""html — moved verbatim from graphify/export.py."""
from __future__ import annotations

from graphify.exporters.base import COMMUNITY_COLORS  # noqa: E402,F401
from pathlib import Path
import html as _html
from graphify.analyze import _node_community_map
from graphify.paths import write_text_atomic
import json
import networkx as nx
from graphify.security import sanitize_label


MAX_NODES_FOR_VIZ = 5_000
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
  :root {
    --bg: #0f0f1a; --panel: #1a1a2e; --border: #2a2a4e; --input-border: #3a3a5e;
    --text: #e0e0e0; --text-2: #aaa; --text-3: #ccc; --muted: #555; --count: #666;
    --neighbor-border: #333; --node-label: #ffffff;
  }
  [data-theme="light"] {
    --bg: #ffffff; --panel: #f8f9fa; --border: #d9dee5; --input-border: #c3cad4;
    --text: #222222; --text-2: #666666; --text-3: #333333; --muted: #888888; --count: #777777;
    --neighbor-border: #ccc; --node-label: #222222;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; display: flex; height: 100vh; overflow: hidden; }
  #graph { flex: 1; }
  #sidebar { width: 280px; background: var(--panel); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  #search-wrap { padding: 12px; border-bottom: 1px solid var(--border); }
  #search { width: 100%; background: var(--bg); border: 1px solid var(--input-border); color: var(--text); padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
  #search:focus { border-color: #4E79A7; }
  #search-results { max-height: 140px; overflow-y: auto; padding: 4px 12px; border-bottom: 1px solid var(--border); display: none; }
  .search-item { padding: 4px 6px; cursor: pointer; border-radius: 4px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .search-item:hover { background: var(--border); }
  #info-panel { padding: 14px; border-bottom: 1px solid var(--border); min-height: 140px; }
  #info-panel h3 { font-size: 13px; color: var(--text-2); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
  #info-content { font-size: 13px; color: var(--text-3); line-height: 1.6; }
  #info-content .field { margin-bottom: 5px; }
  #info-content .field b { color: var(--text); }
  #info-content .empty { color: var(--muted); font-style: italic; }
  .neighbor-link { display: block; padding: 2px 6px; margin: 2px 0; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid var(--neighbor-border); }
  .neighbor-link:hover { background: var(--border); }
  #neighbors-list { max-height: 160px; overflow-y: auto; margin-top: 4px; }
  #legend-wrap { flex: 1; overflow-y: auto; padding: 12px; }
  #legend-wrap h3 { font-size: 13px; color: var(--text-2); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
  .legend-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; border-radius: 4px; font-size: 12px; }
  .legend-item:hover { background: var(--border); padding-left: 4px; }
  .legend-item.dimmed { opacity: 0.35; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .legend-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-count { color: var(--count); font-size: 11px; }
  #stats { padding: 10px 14px; border-top: 1px solid var(--border); font-size: 11px; color: var(--muted); }
  #legend-controls { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding: 4px 0; }
  #legend-controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: var(--text-2); user-select: none; }
  #legend-controls label:hover { color: var(--text); }
  .legend-cb, #select-all-cb { appearance: none; -webkit-appearance: none; width: 14px; height: 14px; border: 1.5px solid var(--input-border); border-radius: 3px; background: var(--bg); cursor: pointer; position: relative; flex-shrink: 0; }
  .legend-cb:checked, #select-all-cb:checked { background: #4E79A7; border-color: #4E79A7; }
  .legend-cb:checked::after, #select-all-cb:checked::after { content: ''; position: absolute; left: 3.5px; top: 1px; width: 4px; height: 7px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
  #select-all-cb:indeterminate { background: #4E79A7; border-color: #4E79A7; }
  #select-all-cb:indeterminate::after { content: ''; position: absolute; left: 2px; top: 5px; width: 8px; height: 2px; background: #fff; border: none; transform: none; }
  #theme-wrap { display: flex; gap: 4px; padding: 8px 12px; border-bottom: 1px solid var(--border); }
  #theme-wrap button { flex: 1; background: var(--bg); color: var(--text-2); border: 1px solid var(--input-border); border-radius: 4px; padding: 3px 0; font-size: 11px; cursor: pointer; }
  #theme-wrap button:hover { color: var(--text); }
  #theme-wrap button[aria-pressed="true"] { background: #4E79A7; border-color: #4E79A7; color: #fff; }
</style>"""

def _hyperedge_script(hyperedges_json: str) -> str:
    return f"""<script>
// Render hyperedges as shaded regions
const hyperedges = {hyperedges_json};
// afterDrawing passes ctx already transformed to network coordinate space.
// Draw node positions raw — no manual pan/zoom/DPR math needed.

// Andrew's monotone chain. Returns the hull in counter-clockwise order, which
// is what the perimeter must be traced in. Collinear and duplicate points
// collapse to the extremes, so degenerate member sets render as a segment
// rather than a zero-area crossed path.
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
network.on('afterDrawing', function(ctx) {{
    hyperedges.forEach(h => {{
        // Legend toggles only set `hidden` on nodes; getPositions() still
        // returns them, so skip hidden members or their hull lingers.
        const positions = h.nodes
            .filter(nid => {{ const n = nodesDS.get(nid); return n && n.hidden !== true; }})
            .map(nid => network.getPositions([nid])[nid])
            .filter(p => p !== undefined);
        if (positions.length < 2) return;
        ctx.save();
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = '#6366f1';
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.beginPath();
        // Centroid and expanded hull in network coordinates.
        // The perimeter must follow hull order, not h.nodes order: tracing the
        // raw member order self-intersects whenever the layout does not happen
        // to place members in angular order, filling as crossed wedges.
        const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length;
        const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length;
        const hull = convexHull(positions);
        const expanded = hull.map(p => ({{
            x: cx + (p.x - cx) * 1.15,
            y: cy + (p.y - cy) * 1.15
        }}));
        ctx.moveTo(expanded[0].x, expanded[0].y);
        expanded.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        ctx.closePath();
        ctx.fill();
        ctx.globalAlpha = 0.4;
        ctx.stroke();
        // Label
        ctx.globalAlpha = 0.8;
        ctx.fillStyle = '#4f46e5';
        ctx.font = 'bold 11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(h.label, cx, cy - 5);
        ctx.restore();
    }});
}});
</script>"""

def _html_script(nodes_json: str, edges_json: str, legend_json: str) -> str:
    return f"""<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND = {legend_json};

// HTML-escape helper — prevents XSS when injecting graph data into innerHTML
function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

// Build vis datasets
const nodesDS = new vis.DataSet(RAW_NODES.map((n, i) => ({{
  id: n.id, label: n.label, color: n.color, size: n.size,
  font: n.font, title: n.title,
  // Fermat/golden-angle spiral seed positions (#3699): spreading nodes out
  // before physics runs keeps avoidOverlap from computing near-zero-distance
  // repulsion that blows the BarnesHut recursion into a stack overflow on large
  // graphs. `i` is the map index — physics still settles small graphs identically.
  x: 30 * Math.sqrt(i) * Math.cos(i * 2.4),
  y: 30 * Math.sqrt(i) * Math.sin(i * 2.4),
  community: n.community, community_name: n.community_name,
  source_file: n.source_file, file_type: n.file_type, degree: n.degree,
  member_count: n.member_count,
}})));

const edgesDS = new vis.DataSet(RAW_EDGES.map((e, i) => ({{
  id: i, from: e.from, to: e.to,
  label: '',
  title: e.title,
  dashes: e.dashes,
  width: e.width,
  color: e.color,
  arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
}})));

const container = document.getElementById('graph');
const network = new vis.Network(container, {{ nodes: nodesDS, edges: edgesDS }}, {{
  physics: {{
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -60,
      centralGravity: 0.005,
      springLength: 120,
      springConstant: 0.08,
      damping: 0.4,
      avoidOverlap: 0.8,
    }},
    stabilization: {{ iterations: 200, fit: true }},
  }},
  interaction: {{
    hover: true,
    tooltipDelay: 100,
    hideEdgesOnDrag: true,
    navigationButtons: false,
    keyboard: false,
  }},
  nodes: {{ shape: 'dot', borderWidth: 1.5 }},
  edges: {{ smooth: {{ type: 'continuous', roundness: 0.2 }}, selectionWidth: 3 }},
}});

// Theme toggle (#3894): Light / Dark / System, persisted in localStorage.
const THEME_KEY = 'graphify-theme';
const themeMQ = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
let themeLabelColor = '#ffffff';  // matches the per-node font color set in Python
function themePref() {{
  let p = null;
  try {{ p = localStorage.getItem(THEME_KEY); }} catch (e) {{}}
  return (p === 'light' || p === 'dark' || p === 'system') ? p : null;
}}
function applyTheme(pref) {{
  const t = pref === 'light' ? 'light' : (pref === 'system' && themeMQ && themeMQ.matches) ? 'light' : 'dark';
  const root = document.documentElement;
  if (!root) return;
  root.setAttribute('data-theme', t);
  document.querySelectorAll('[data-theme-choice]').forEach(b => {{
    b.setAttribute('aria-pressed', String(b.dataset.themeChoice === (pref || 'dark')));
  }});
  const labelColor = getComputedStyle(root).getPropertyValue('--node-label').trim();
  if (labelColor && labelColor !== themeLabelColor) {{
    themeLabelColor = labelColor;
    nodesDS.update(nodesDS.get().map(n => ({{ id: n.id, font: Object.assign({{}}, n.font, {{ color: labelColor }}) }})));
  }}
}}
document.querySelectorAll('[data-theme-choice]').forEach(b => {{
  b.addEventListener('click', () => {{
    const pref = b.dataset.themeChoice;
    try {{ localStorage.setItem(THEME_KEY, pref); }} catch (e) {{}}
    applyTheme(pref);
  }});
}});
if (themeMQ) {{
  const onSchemeChange = () => {{ if (themePref() === 'system') applyTheme('system'); }};
  if (themeMQ.addEventListener) themeMQ.addEventListener('change', onSchemeChange);
  else if (themeMQ.addListener) themeMQ.addListener(onSchemeChange);
}}
applyTheme(themePref());

network.once('stabilizationIterationsDone', () => {{
  network.setOptions({{ physics: {{ enabled: false }} }});
}});

function showInfo(nodeId) {{
  const n = nodesDS.get(nodeId);
  if (!n) return;
  const neighborIds = network.getConnectedNodes(nodeId);
  const neighborItems = neighborIds.map(nid => {{
    const nb = nodesDS.get(nid);
    const color = nb ? nb.color.background : '#555';
    return `<span class="neighbor-link" style="border-left-color:${{esc(color)}}" data-nid="${{esc(nid)}}">${{esc(nb ? nb.label : nid)}}</span>`;
  }}).join('');
  const isMetaNode = !n.file_type && !n.source_file;
  let html = `<div class="field"><b>${{esc(n.label)}}</b></div>`;
  if (!isMetaNode) {{
    html += `<div class="field">Type: ${{esc(n.file_type || 'unknown')}}</div>`;
  }}
  html += `<div class="field">Community: ${{esc(n.community_name || '')}}</div>`;
  if (!isMetaNode) {{
    html += `<div class="field">Source: ${{esc(n.source_file || '-')}}</div>`;
  }} else if (n.member_count !== undefined && n.member_count !== null) {{
    html += `<div class="field">Members: ${{esc(n.member_count)}}</div>`;
  }}
  html += `<div class="field">Degree: ${{n.degree}}</div>`;
  if (neighborIds.length) {{
    html += `<div class="field" style="margin-top:8px;color:var(--text-2);font-size:11px">Neighbors (${{neighborIds.length}})</div><div id="neighbors-list">${{neighborItems}}</div>`;
  }}
  document.getElementById('info-content').innerHTML = html;
}}

function focusNode(nodeId) {{
  network.focus(nodeId, {{ scale: 1.4, animation: true }});
  network.selectNodes([nodeId]);
  showInfo(nodeId);
}}

// Neighbor links use a data attribute + one delegated listener rather than an
// inline onclick. A node id/label sourced from a document or a scraped URL
// (graphify add) can contain a double-quote; dropping the stringified id
// unescaped into a quoted onclick both broke every link and allowed a hostile
// source to inject an event handler into the local report (stored XSS, #1838).
// esc() on data-nid keeps the value inside the attribute; the listener reads it
// back verbatim. Bound to document so it survives the innerHTML rebuild that
// recreates #neighbors-list on each showInfo().
document.addEventListener('click', e => {{
  const el = e.target.closest('.neighbor-link');
  if (el && el.dataset.nid !== undefined) focusNode(el.dataset.nid);
}});

// Sidebar tooltips reuse vis-network's .vis-tooltip style and 100ms tooltipDelay.
// Names get one only when CSS ellipsis truncates them (the full text is still in
// the DOM); counts always get one, to say what the number is. Text is set with
// textContent only (labels are untrusted). Delegated on document so rows rebuilt
// later (search results, showInfo()) are covered.
const sidebarTip = document.createElement('div');
sidebarTip.className = 'vis-tooltip';
sidebarTip.style.cssText = 'white-space: normal; max-width: 360px; overflow-wrap: break-word;';
document.body.appendChild(sidebarTip);
let sidebarTipTimer = null;
let sidebarTipEl = null;    // element whose text the tooltip shows
let sidebarTipZone = null;  // element the pointer must leave to hide it
function hideSidebarTip() {{
  clearTimeout(sidebarTipTimer);
  sidebarTip.style.visibility = 'hidden';
  sidebarTip.textContent = '';
  sidebarTipEl = sidebarTipZone = null;
}}
document.addEventListener('mouseover', e => {{
  const zone = e.target.closest && e.target.closest('.legend-count, .legend-item, .search-item, .neighbor-link');
  // Anywhere on a legend row except its count (dot, checkbox, gaps, padding)
  // stands for the row's name, so moving within the row never re-triggers it.
  const el = zone && zone.classList.contains('legend-item') ? zone.querySelector('.legend-label') : zone;
  if (!el || el === sidebarTipEl) return;
  hideSidebarTip();
  const isCount = el.classList.contains('legend-count');
  if (!isCount && el.scrollWidth <= el.clientWidth) return;
  const text = isCount ? `${{el.textContent}} ${{el.textContent === '1' ? 'node' : 'nodes'}}` : el.textContent;
  sidebarTipEl = el;
  sidebarTipZone = zone;
  const x = e.clientX, y = e.clientY;
  sidebarTipTimer = setTimeout(() => {{
    sidebarTip.textContent = text;
    sidebarTip.style.left = sidebarTip.style.top = '0px';  // measure at full max-width
    sidebarTip.style.visibility = 'visible';
    const w = sidebarTip.offsetWidth, h = sidebarTip.offsetHeight;
    sidebarTip.style.left = Math.max(4, Math.min(x + 12, window.innerWidth - w - 4)) + 'px';
    sidebarTip.style.top = (y + 16 + h > window.innerHeight ? Math.max(4, y - h - 8) : y + 16) + 'px';
  }}, 100);
}});
document.addEventListener('mouseout', e => {{
  if (sidebarTipZone && !sidebarTipZone.contains(e.relatedTarget)) hideSidebarTip();
}});
// A click rebuilds or hides the row (showInfo(), search pick) without a mouseout.
document.addEventListener('mousedown', hideSidebarTip);

// Track hovered node — hover detection is more reliable than click params
let hoveredNodeId = null;
network.on('hoverNode', params => {{
  hoveredNodeId = params.node;
  container.style.cursor = 'pointer';
}});
network.on('blurNode', () => {{
  hoveredNodeId = null;
  container.style.cursor = 'default';
}});
container.addEventListener('click', () => {{
  if (hoveredNodeId !== null) {{
    showInfo(hoveredNodeId);
    network.selectNodes([hoveredNodeId]);
  }}
}});
network.on('click', params => {{
  if (params.nodes.length > 0) {{
    showInfo(params.nodes[0]);
  }} else if (hoveredNodeId === null) {{
    document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>';
  }}
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
    el.style.borderLeft = `3px solid ${{n.color.background}}`;
    el.style.paddingLeft = '8px';
    el.onclick = () => {{
      network.focus(n.id, {{ scale: 1.5, animation: true }});
      network.selectNodes([n.id]);
      showInfo(n.id);
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

const hiddenCommunities = new Set();

const selectAllCb = document.getElementById('select-all-cb');

function updateSelectAllState() {{
  const total = LEGEND.length;
  const hidden = hiddenCommunities.size;
  selectAllCb.checked = hidden === 0;
  selectAllCb.indeterminate = hidden > 0 && hidden < total;
}}

function toggleAllCommunities(hide) {{
  document.querySelectorAll('.legend-item').forEach(item => {{
    hide ? item.classList.add('dimmed') : item.classList.remove('dimmed');
  }});
  document.querySelectorAll('.legend-cb').forEach(cb => {{
    cb.checked = !hide;
  }});
  LEGEND.forEach(c => {{
    if (hide) hiddenCommunities.add(c.cid); else hiddenCommunities.delete(c.cid);
  }});
  const updates = RAW_NODES.map(n => ({{ id: n.id, hidden: hide }}));
  nodesDS.update(updates);
  updateSelectAllState();
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
    if (cb.checked) {{
      hiddenCommunities.delete(c.cid);
      item.classList.remove('dimmed');
    }} else {{
      hiddenCommunities.add(c.cid);
      item.classList.add('dimmed');
    }}
    const updates = RAW_NODES
      .filter(n => n.community === c.cid)
      .map(n => ({{ id: n.id, hidden: !cb.checked }}));
    nodesDS.update(updates);
    updateSelectAllState();
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


# ---------------------------------------------------------------------------
# 3D viewer (default). Same RAW_NODES / RAW_EDGES / LEGEND data as the 2D page,
# rendered with 3d-force-graph (three.js) plus a floating node card that shows
# each node's kind, signature, source comment and grouped relationships.
# ---------------------------------------------------------------------------

# Bumping the version MUST update both the URL and the hash (verified against
# unpkg and jsdelivr copies of the published npm file).
_FORCE_GRAPH_3D_URL = "https://unpkg.com/3d-force-graph@1.73.4/dist/3d-force-graph.min.js"
_FORCE_GRAPH_3D_SRI = "sha384-GNPicn8pBA2/PGSyPTpxIlPurgLUYcNYJ2zskIq782dE9+gp5E32WSyuxZqA7J+u"

VIZ_MODES = ("3d", "2d")


def _viz_mode(mode: str | None) -> str:
    """Resolve the renderer: explicit *mode*, else GRAPHIFY_VIZ_MODE, else 3d."""
    import os
    raw = (mode or os.environ.get("GRAPHIFY_VIZ_MODE") or "3d").strip().lower()
    return raw if raw in VIZ_MODES else "3d"


def _html3d_styles() -> str:
    # Shared chrome (theme variables, sidebar, legend, search) comes from the 2D
    # stylesheet so both viewers look alike and theme the same way.
    base = _html_styles().replace("</style>", "")
    return base + """  #graph-wrap { flex: 1; position: relative; min-width: 0; }
  #graph { position: absolute; inset: 0; }
  #toolbar { position: absolute; top: 12px; left: 12px; z-index: 5; display: flex; gap: 6px; }
  #toolbar button { background: var(--panel); color: var(--text-2); border: 1px solid var(--input-border); border-radius: 6px; padding: 5px 10px; font-size: 12px; cursor: pointer; }
  #toolbar button:hover { color: var(--text); }
  #toolbar button[aria-pressed="true"] { background: #4E79A7; border-color: #4E79A7; color: #fff; }
  #viewer-error { position: absolute; inset: 0; display: none; align-items: center; justify-content: center; padding: 24px; text-align: center; color: var(--text-2); font-size: 14px; line-height: 1.6; }
  .g3-sidebar-tip { position: fixed; visibility: hidden; z-index: 100; white-space: normal; max-width: 360px; overflow-wrap: break-word; background: var(--panel); color: var(--text); border: 1px solid var(--border); border-radius: 4px; padding: 5px 8px; font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); pointer-events: none; }
  .scene-tooltip { background: rgba(20,20,35,0.92); padding: 6px 9px; border-radius: 6px; color: #eee !important; font-size: 12px; }
  .kind-chip { display: inline-block; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; padding: 1px 6px; border-radius: 8px; background: var(--border); color: var(--text-2); vertical-align: middle; }
  #info-content .desc { margin: 6px 0 8px; color: var(--text); line-height: 1.5; }
  #info-content .desc.auto { color: var(--text-2); font-size: 12px; }
  #info-content .sig { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; margin: 6px 0 8px; white-space: pre-wrap; word-break: break-word; color: var(--text-3); }
  #info-content .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
  #info-content .lesson { font-size: 11px; margin: 4px 0; padding-left: 6px; border-left: 3px solid var(--muted); color: var(--text-2); }
  #neighbors-list { margin-top: 4px; max-height: none; overflow: visible; }
  .rel-head { margin-top: 8px; color: var(--text-2); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
  #node-card { position: absolute; z-index: 6; left: 0; top: 0; width: max-content; max-width: 320px; max-height: 55%;
    overflow-y: auto; padding: 10px 12px; border-radius: 10px; font-size: 12px;
    background: rgba(22, 22, 40, 0.68); border: 1px solid rgba(255,255,255,0.10);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    box-shadow: 0 6px 24px rgba(0,0,0,0.35);
    opacity: 0; transform: translateY(4px); transition: opacity .18s ease, transform .18s ease;
    pointer-events: none; }
  [data-theme="light"] #node-card { background: rgba(255,255,255,0.78); border-color: rgba(0,0,0,0.10); box-shadow: 0 6px 24px rgba(0,0,0,0.12); }
  #node-card.show { opacity: 1; transform: none; }
  #node-card.pinned { pointer-events: auto; }
  #node-card .card-close { position: sticky; top: 0; float: right; margin: -4px -4px 0 6px; background: none; border: none;
    color: var(--text-2); font-size: 16px; line-height: 1; cursor: pointer; padding: 2px 4px; border-radius: 4px; }
  #node-card .card-close:hover { color: var(--text); background: var(--border); }
  #node-card #info-content { font-size: 12px; line-height: 1.5; color: var(--text-3); }
  #node-card .desc { margin: 4px 0 6px; }
  #node-card .sig { margin: 4px 0 6px; background: rgba(0,0,0,0.18); }
  [data-theme="light"] #node-card .sig { background: rgba(0,0,0,0.04); }
  #node-card .field { margin-bottom: 2px; }
  #node-card .meta { color: var(--text-2); font-size: 11px; }
</style>"""


def _html3d_data_script(nodes_json: str, edges_json: str, legend_json: str,
                        hyperedges_json: str, node_info_json: str) -> str:
    return f"""<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND = {legend_json};
const HYPEREDGES = {hyperedges_json};
const NODE_INFO = {node_info_json};
</script>"""


# Plain string (not an f-string): no data is interpolated into the viewer code.
_HTML3D_SCRIPT = r"""<script>
// HTML-escape helper: every graph-derived string goes through esc() before
// reaching innerHTML (labels, comments and paths come from source files).
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ---- Graph data -------------------------------------------------------------
const nodeById = new Map();
const NODES = RAW_NODES.map(n => {
  const node = {
    id: n.id, label: n.label, color: n.color.background, size: n.size, title: n.title,
    community: n.community, community_name: n.community_name,
    source_file: n.source_file, file_type: n.file_type, degree: n.degree,
    member_count: n.member_count,
    // Work-memory overlay: annotated nodes carry a "Lesson: ..." line after the
    // label in their title, and a status colour as their border.
    lesson: String(n.title || '').split('\n').slice(1).join(' '),
    ring: n.color.border !== n.color.background ? n.color.border : null,
  };
  nodeById.set(n.id, node);
  return node;
});
const LINKS = RAW_EDGES
  .filter(e => nodeById.has(e.from) && nodeById.has(e.to))
  .map(e => ({ source: e.from, target: e.to, relation: e.label, title: e.title,
               width: e.width, confidence: e.confidence }));

const neighbors = new Map(NODES.map(n => [n.id, new Set()]));
const relOut = new Map(NODES.map(n => [n.id, []]));
const relIn = new Map(NODES.map(n => [n.id, []]));
LINKS.forEach(l => {
  neighbors.get(l.source).add(l.target); neighbors.get(l.target).add(l.source);
  relOut.get(l.source).push([l.relation, l.target]);
  relIn.get(l.target).push([l.relation, l.source]);
});
// How each relation reads from the selected node's side: [outgoing, incoming]
const REL_TEXT = {
  calls: ['Calls', 'Called by'],
  references: ['Uses', 'Used by'],
  uses: ['Uses', 'Used by'],
  contains: ['Contains', 'Defined in'],
  method: ['Methods', 'Method of'],
  imports: ['Imports', 'Imported by'],
  imports_from: ['Imports', 'Imported by'],
  case_of: ['Variants', 'Variant of'],
  defines: ['Defines', 'Defined in'],
  implements: ['Implements', 'Implemented by'],
  inherits: ['Inherits from', 'Inherited by'],
  extends: ['Extends', 'Extended by'],
  depends_on: ['Depends on', 'Depended on by'],
  shares_data_with: ['Shares data with', 'Shares data with'],
  rationale_for: ['Explains', 'Explained by'],
  conceptually_related_to: ['Related to', 'Related to'],
  semantically_similar_to: ['Similar to', 'Similar to'],
};
const REL_ORDER = ['Defined in', 'Method of', 'Variant of', 'Explained by', 'Methods', 'Variants', 'Contains',
  'Calls', 'Called by', 'Uses', 'Used by', 'Imports', 'Imported by'];

// Hyperedges (shaded regions in 2D) are listed as "Group:" on member cards.
const hyperMember = new Map();
HYPEREDGES.forEach(h => (h.nodes || []).forEach(id => {
  if (!hyperMember.has(id)) hyperMember.set(id, []);
  hyperMember.get(id).push(h);
}));

const INFO = NODE_INFO || {};
const hiddenCommunities = new Set();
let selectedId = null;
const highlightNodes = new Set();
const highlightLinks = new Set();

function isDark() { return document.documentElement.getAttribute('data-theme') !== 'light'; }
function endId(x) { return typeof x === 'object' ? x.id : x; }
function linkKey(l) { return endId(l.source) + '\u0000' + endId(l.target); }
function endNode(x) { return typeof x === 'object' ? x : nodeById.get(x); }
function firstSentence(t, max) {
  const m = String(t).match(/^.*?[.!?](\s|$)/);
  let s = (m ? m[0] : String(t)).trim();
  if (s.length > max) s = s.slice(0, max - 1) + '…';
  return s;
}

// ---- 3D scene ---------------------------------------------------------------
const container = document.getElementById('graph');
const Graph = (typeof ForceGraph3D === 'function') ? ForceGraph3D({ controlType: 'orbit' })(container) : null;
if (!Graph) {
  const err = document.getElementById('viewer-error');
  err.textContent = 'The 3D viewer could not load (it needs WebGL and an internet connection for ' +
    'the 3d-force-graph library). Re-render with GRAPHIFY_VIZ_MODE=2d for the flat viewer.';
  err.style.display = 'flex';
} else {
  Graph
    .graphData({ nodes: NODES, links: LINKS })
    .nodeId('id')
    .nodeLabel(() => '')
    .nodeVal(n => Math.max(1, n.size / 3))
    .nodeRelSize(4)
    .nodeResolution(16)
    .nodeOpacity(0.95)
    .nodeColor(n => {
      if (highlightNodes.size && !highlightNodes.has(n.id)) return isDark() ? '#2a2a40' : '#d4d8de';
      if (n.id === selectedId) return isDark() ? '#ffffff' : '#111111';
      return n.color;
    })
    .nodeVisibility(n => !hiddenCommunities.has(n.community))
    .linkVisibility(l => {
      const s = endNode(l.source), t = endNode(l.target);
      return !hiddenCommunities.has(s.community) && !hiddenCommunities.has(t.community);
    })
    .linkLabel(l => esc(l.title || l.relation || ''))
    .linkColor(l => {
      if (highlightLinks.has(linkKey(l))) return isDark() ? '#ffd166' : '#d97706';
      return isDark() ? '#8890b0' : '#7a8494';
    })
    .linkOpacity(0.25)
    .linkWidth(l => highlightLinks.has(linkKey(l)) ? 1.5 : (l.confidence === 'EXTRACTED' ? 0.3 : 0))
    .linkDirectionalArrowLength(l => highlightLinks.has(linkKey(l)) ? 4 : 2)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalParticles(l => highlightLinks.has(linkKey(l)) ? 3 : 0)
    .linkDirectionalParticleWidth(1.8)
    .linkDirectionalParticleSpeed(0.006)
    .warmupTicks(60)
    .cooldownTicks(300)
    .onNodeHover(n => {
      container.style.cursor = n ? 'pointer' : 'default';
      if (selectedId !== null) return;          // a pinned card stays put
      if (n) openCard(n.id, false); else closeCard();
    })
    .onNodeClick(n => focusNode(n.id))
    .onBackgroundClick(() => clearSelection());

  // Same-community links are shorter than cross-community ones so clusters separate.
  Graph.d3Force('charge').strength(-40);
  Graph.d3Force('link').distance(l => endNode(l.source).community === endNode(l.target).community ? 25 : 70);

  let fittedOnce = false;
  Graph.onEngineStop(() => {
    if (!fittedOnce) { fittedOnce = true; Graph.zoomToFit(800, 40, n => !hiddenCommunities.has(n.community)); }
  });
  const resize = () => Graph.width(container.clientWidth).height(container.clientHeight);
  window.addEventListener('resize', resize);
  resize();
}

function refreshStyles() {
  if (!Graph) return;
  Graph.nodeColor(Graph.nodeColor())
       .linkColor(Graph.linkColor())
       .linkWidth(Graph.linkWidth())
       .linkDirectionalArrowLength(Graph.linkDirectionalArrowLength())
       .linkDirectionalParticles(Graph.linkDirectionalParticles());
}

function setHighlight(nodeId) {
  highlightNodes.clear();
  highlightLinks.clear();
  if (nodeId !== null) {
    highlightNodes.add(nodeId);
    neighbors.get(nodeId).forEach(nid => highlightNodes.add(nid));
    LINKS.forEach(l => {
      if (endId(l.source) === nodeId || endId(l.target) === nodeId) highlightLinks.add(linkKey(l));
    });
  }
  refreshStyles();
}

function clearSelection() {
  selectedId = null;
  setHighlight(null);
  closeCard();
}

// ---- Theme toggle: Light / Dark / System, persisted in localStorage ----------
const THEME_KEY = 'graphify-theme';
const themeMQ = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
function themePref() {
  let p = null;
  try { p = localStorage.getItem(THEME_KEY); } catch (e) {}
  return (p === 'light' || p === 'dark' || p === 'system') ? p : null;
}
function applyTheme(pref) {
  const t = pref === 'light' ? 'light' : (pref === 'system' && themeMQ && themeMQ.matches) ? 'light' : 'dark';
  const root = document.documentElement;
  if (!root) return;
  root.setAttribute('data-theme', t);
  document.querySelectorAll('[data-theme-choice]').forEach(b => {
    b.setAttribute('aria-pressed', String(b.dataset.themeChoice === (pref || 'dark')));
  });
  if (Graph) Graph.backgroundColor(getComputedStyle(root).getPropertyValue('--bg').trim() || '#0f0f1a');
  refreshStyles();
}
document.querySelectorAll('[data-theme-choice]').forEach(b => {
  b.addEventListener('click', () => {
    const pref = b.dataset.themeChoice;
    try { localStorage.setItem(THEME_KEY, pref); } catch (e) {}
    applyTheme(pref);
  });
});
if (themeMQ) {
  const onSchemeChange = () => { if (themePref() === 'system') applyTheme('system'); };
  if (themeMQ.addEventListener) themeMQ.addEventListener('change', onSchemeChange);
  else if (themeMQ.addListener) themeMQ.addListener(onSchemeChange);
}
applyTheme(themePref());

// ---- Node card contents -------------------------------------------------------
function relationGroups(nodeId) {
  const g = new Map();
  const add = (title, id) => { if (!g.has(title)) g.set(title, new Set()); g.get(title).add(id); };
  const pretty = r => String(r || 'related').replace(/_/g, ' ');
  relOut.get(nodeId).forEach(([r, id]) => add((REL_TEXT[r] || [pretty(r)])[0], id));
  relIn.get(nodeId).forEach(([r, id]) => add((REL_TEXT[r] || [, pretty(r) + ' (from)'])[1], id));
  const rank = t => { const i = REL_ORDER.indexOf(t); return i < 0 ? 99 : i; };
  return [...g.entries()].sort((a, b) => rank(a[0]) - rank(b[0])).map(([t, ids]) => [t, [...ids]]);
}

// Plain-language fallback when the source has no comment for this node.
function autoSummary(nodeId, inf) {
  const n = nodeById.get(nodeId);
  if (n.member_count != null && !n.source_file) {
    return `A community of ${n.member_count} nodes. Links show how many edges cross to other communities.`;
  }
  const kind = (inf.k || 'node').toLowerCase();
  const groups = new Map(relationGroups(nodeId));
  const names = t => (groups.get(t) || []).map(id => (nodeById.get(id) || {}).label).filter(Boolean);
  const list = (arr, max) => arr.slice(0, max).join(', ') + (arr.length > max ? ` and ${arr.length - max} more` : '');
  const parts = [];
  const owner = names('Method of')[0] || names('Variant of')[0];
  const file = inf.l ? inf.l.split(':')[0].split('/').pop() : '';
  if (kind.startsWith('external')) {
    const users = names('Used by').concat(names('Imported by'), names('Called by'));
    parts.push('Comes from outside this project (standard library or a dependency).');
    if (users.length) parts.push(`Used here by ${list(users, 4)}.`);
    return parts.join(' ');
  }
  const article = /^[aeiou]/.test(kind) ? 'An' : 'A';
  parts.push(owner ? `${article} ${kind} of ${owner}${file ? ' in ' + file : ''}.`
                   : `${article} ${kind}${file ? ' in ' + file : ''}.`);
  const calls = names('Calls'), callers = names('Called by'), users = names('Used by'), uses = names('Uses');
  if (calls.length) parts.push(`It calls ${list(calls, 4)}.`);
  if (uses.length) parts.push(`It uses ${list(uses, 4)}.`);
  if (callers.length) parts.push(`Called from ${list(callers, 4)}.`);
  if (users.length) parts.push(`Used by ${list(users, 4)}.`);
  const methods = names('Methods'), variants = names('Variants');
  if (methods.length) parts.push(`Has ${methods.length} method${methods.length > 1 ? 's' : ''}: ${list(methods, 5)}.`);
  if (variants.length) parts.push(`Variants: ${list(variants, 6)}.`);
  parts.push('(No comment in the source; summary built from the code graph.)');
  return parts.join(' ');
}

function showInfo(nodeId, full = true) {
  const n = nodeById.get(nodeId);
  if (!n) return;
  const inf = INFO[nodeId] || {};
  let html = full ? `<button class="card-close" type="button" title="Close (Esc)" aria-label="Close">×</button>` : '';
  html += `<div class="field"><b>${esc(n.label)}</b>` +
          (inf.k ? ` <span class="kind-chip">${esc(inf.k)}</span>` : '') + `</div>`;
  if (inf.d) html += `<div class="desc">${esc(full ? inf.d : firstSentence(inf.d, 220))}</div>`;
  if (inf.s) html += `<pre class="sig">${esc(inf.s)}</pre>`;
  if (!inf.d) html += `<div class="desc auto">${esc(autoSummary(nodeId, inf))}</div>`;
  if (n.lesson) {
    html += `<div class="lesson" style="border-left-color:${esc(n.ring || '#9ca3af')}">${esc(n.lesson)}</div>`;
  }
  const src = inf.l || n.source_file;
  if (src) html += `<div class="field meta mono">${esc(src)}</div>`;
  if (!full) {
    html += `<div class="field meta">${esc(n.community_name || '')} · click for details</div>`;
  } else {
    html += `<div class="field meta">${esc(n.community_name || '')} · degree ${esc(n.degree)}` +
            (n.member_count != null && !src ? ` · ${esc(n.member_count)} members` : '') + `</div>`;
    if (hyperMember.has(nodeId)) {
      html += `<div class="field meta">Group: ${hyperMember.get(nodeId).map(h => esc(h.label || h.relation || h.id || '')).join('; ')}</div>`;
    }
    const groups = relationGroups(nodeId);
    if (groups.length) {
      html += `<div id="neighbors-list">` + groups.map(([title, ids]) =>
        `<div class="rel-head">${esc(title)} (${ids.length})</div>` + ids.map(nid => {
          const nb = nodeById.get(nid);
          return `<span class="neighbor-link" style="border-left-color:${esc(nb ? nb.color : '#555')}" data-nid="${esc(nid)}">${esc(nb ? nb.label : nid)}</span>`;
        }).join('')).join('') + `</div>`;
    }
  }
  document.getElementById('info-content').innerHTML = html;
}

// ---- Floating card: follows its node on screen --------------------------------
const card = document.getElementById('node-card');
const wrap = document.getElementById('graph-wrap');
let cardNodeId = null, cardRaf = null;

function openCard(nodeId, pinned) {
  cardNodeId = nodeId;
  showInfo(nodeId, pinned);
  card.classList.toggle('pinned', pinned);
  card.scrollTop = 0;
  positionCard();
  card.classList.add('show');
  if (!cardRaf) cardRaf = requestAnimationFrame(trackCard);
}
function closeCard() {
  card.classList.remove('show', 'pinned');
  cancelAnimationFrame(cardRaf); cardRaf = null;
}
function trackCard() {
  positionCard();
  cardRaf = card.classList.contains('show') ? requestAnimationFrame(trackCard) : null;
}
function positionCard() {
  const n = cardNodeId !== null && nodeById.get(cardNodeId);
  if (!Graph || !n || n.x === undefined) return;
  // Hide the card while its node is behind the camera.
  const e = Graph.camera().matrixWorldInverse.elements;
  const behind = e[2] * n.x + e[6] * n.y + e[10] * n.z + e[14] > 0;
  card.style.visibility = behind ? 'hidden' : 'visible';
  if (behind) return;
  const p = Graph.graph2ScreenCoords(n.x, n.y, n.z);
  const W = wrap.clientWidth, H = wrap.clientHeight;
  const w = card.offsetWidth, h = card.offsetHeight, gap = 18;
  let x = p.x + gap, y = p.y - h / 2;
  if (x + w > W - 8) x = p.x - gap - w;                  // flip to the left side
  x = Math.max(8, Math.min(x, W - w - 8));
  y = Math.max(8, Math.min(y, H - h - 8));
  card.style.left = x + 'px';
  card.style.top = y + 'px';
}
card.addEventListener('click', e => { if (e.target.closest('.card-close')) clearSelection(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && card.classList.contains('show')) clearSelection(); });

// Fly the camera to a node and highlight it with its neighbourhood.
function focusNode(nodeId) {
  const n = nodeById.get(nodeId);
  if (!n || hiddenCommunities.has(n.community)) return;
  selectedId = nodeId;
  setHighlight(nodeId);
  openCard(nodeId, true);
  if (!Graph) return;
  const x = n.x || 0, y = n.y || 0, z = n.z || 0;
  const dist = 120;
  const r = Math.hypot(x, y, z);
  const ratio = r > 0 ? 1 + dist / r : 1;
  const camPos = r > 0 ? { x: x * ratio, y: y * ratio, z: z * ratio } : { x: 0, y: 0, z: dist };
  Graph.cameraPosition(camPos, { x, y, z }, 1200);
}

// Neighbour links: escaped data attribute + one delegated listener, never an
// inline onclick (labels and ids are untrusted, #1838).
document.addEventListener('click', e => {
  const el = e.target.closest('.neighbor-link');
  if (el && el.dataset.nid !== undefined) focusNode(el.dataset.nid);
});

// ---- Sidebar tooltips (truncated names, and node counts) ---------------------
const sidebarTip = document.createElement('div');
sidebarTip.className = 'g3-sidebar-tip';
document.body.appendChild(sidebarTip);
let sidebarTipTimer = null, sidebarTipEl = null, sidebarTipZone = null;
function hideSidebarTip() {
  clearTimeout(sidebarTipTimer);
  sidebarTip.style.visibility = 'hidden';
  sidebarTip.textContent = '';
  sidebarTipEl = sidebarTipZone = null;
}
document.addEventListener('mouseover', e => {
  const zone = e.target.closest && e.target.closest('.legend-count, .legend-item, .search-item, .neighbor-link');
  const el = zone && zone.classList.contains('legend-item') ? zone.querySelector('.legend-label') : zone;
  if (!el || el === sidebarTipEl) return;
  hideSidebarTip();
  const isCount = el.classList.contains('legend-count');
  if (!isCount && el.scrollWidth <= el.clientWidth) return;
  const text = isCount ? `${el.textContent} ${el.textContent === '1' ? 'node' : 'nodes'}` : el.textContent;
  sidebarTipEl = el; sidebarTipZone = zone;
  const x = e.clientX, y = e.clientY;
  sidebarTipTimer = setTimeout(() => {
    sidebarTip.textContent = text;
    sidebarTip.style.left = sidebarTip.style.top = '0px';
    sidebarTip.style.visibility = 'visible';
    const w = sidebarTip.offsetWidth, h = sidebarTip.offsetHeight;
    sidebarTip.style.left = Math.max(4, Math.min(x + 12, window.innerWidth - w - 4)) + 'px';
    sidebarTip.style.top = (y + 16 + h > window.innerHeight ? Math.max(4, y - h - 8) : y + 16) + 'px';
  }, 100);
});
document.addEventListener('mouseout', e => {
  if (sidebarTipZone && !sidebarTipZone.contains(e.relatedTarget)) hideSidebarTip();
});
document.addEventListener('mousedown', hideSidebarTip);

// ---- Search -------------------------------------------------------------------
const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) { searchResults.style.display = 'none'; return; }
  const matches = RAW_NODES.filter(n => n.label.toLowerCase().includes(q)).slice(0, 20);
  if (!matches.length) { searchResults.style.display = 'none'; return; }
  searchResults.style.display = 'block';
  matches.forEach(n => {
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.label;
    el.style.borderLeft = `3px solid ${n.color.background}`;
    el.style.paddingLeft = '8px';
    el.onclick = () => {
      focusNode(n.id);
      searchResults.style.display = 'none';
      searchInput.value = '';
    };
    searchResults.appendChild(el);
  });
});
document.addEventListener('click', e => {
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
});

// ---- Community legend / visibility ------------------------------------------
const selectAllCb = document.getElementById('select-all-cb');
function updateSelectAllState() {
  const total = LEGEND.length, hidden = hiddenCommunities.size;
  selectAllCb.checked = hidden === 0;
  selectAllCb.indeterminate = hidden > 0 && hidden < total;
}
function refreshVisibility() {
  if (selectedId === null && cardNodeId !== null && hiddenCommunities.has(nodeById.get(cardNodeId).community)) closeCard();
  if (selectedId !== null && hiddenCommunities.has(nodeById.get(selectedId).community)) clearSelection();
  if (Graph) Graph.nodeVisibility(Graph.nodeVisibility()).linkVisibility(Graph.linkVisibility());
}
function toggleAllCommunities(hide) {
  document.querySelectorAll('.legend-item').forEach(item => item.classList.toggle('dimmed', hide));
  document.querySelectorAll('.legend-cb').forEach(cb => { cb.checked = !hide; });
  LEGEND.forEach(c => { if (hide) hiddenCommunities.add(c.cid); else hiddenCommunities.delete(c.cid); });
  refreshVisibility();
  updateSelectAllState();
}

const legendEl = document.getElementById('legend');
LEGEND.forEach(c => {
  const item = document.createElement('div');
  item.className = 'legend-item';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'legend-cb';
  cb.checked = true;
  cb.addEventListener('change', (e) => {
    e.stopPropagation();
    if (cb.checked) { hiddenCommunities.delete(c.cid); item.classList.remove('dimmed'); }
    else { hiddenCommunities.add(c.cid); item.classList.add('dimmed'); }
    refreshVisibility();
    updateSelectAllState();
  });
  // c.label is already HTML-escaped once in Python; c.color comes from the fixed palette.
  item.innerHTML = `<div class="legend-dot" style="background:${esc(c.color)}"></div>
    <span class="legend-label">${c.label}</span>
    <span class="legend-count">${esc(c.count)}</span>`;
  item.prepend(cb);
  item.onclick = (e) => {
    if (e.target === cb) return;
    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event('change'));
  };
  legendEl.appendChild(item);
});

// ---- Toolbar: reset view / auto-rotate ----------------------------------------
let rotating = false, rotAngle = 0, rotTimer = null;
document.getElementById('btn-fit').onclick = () => {
  if (Graph) Graph.zoomToFit(800, 40, n => !hiddenCommunities.has(n.community));
};
document.getElementById('btn-rotate').onclick = (e) => {
  if (!Graph) return;
  rotating = !rotating;
  e.currentTarget.setAttribute('aria-pressed', String(rotating));
  if (rotating) {
    const p = Graph.cameraPosition();
    const dist = Math.hypot(p.x, p.z) || 600;
    rotAngle = Math.atan2(p.x, p.z);
    rotTimer = setInterval(() => {
      rotAngle += Math.PI / 600;
      Graph.cameraPosition({ x: dist * Math.sin(rotAngle), z: dist * Math.cos(rotAngle) });
    }, 16);
  } else {
    clearInterval(rotTimer);
  }
};
</script>"""


def _html3d_body(stats: str) -> str:
    return f"""<div id="graph-wrap">
  <div id="graph"></div>
  <div id="viewer-error" role="alert"></div>
  <div id="node-card" aria-live="polite"><div id="info-content"></div></div>
  <div id="toolbar">
    <button type="button" id="btn-fit">Reset view</button>
    <button type="button" id="btn-rotate" aria-pressed="false">Auto-rotate</button>
  </div>
</div>
<div id="sidebar">
  <div id="theme-wrap" role="group" aria-label="Theme">
    <button type="button" data-theme-choice="light">Light</button>
    <button type="button" data-theme-choice="dark">Dark</button>
    <button type="button" data-theme-choice="system">System</button>
  </div>
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="legend-wrap">
    <h3>Communities</h3>
    <div id="legend-controls">
      <label><input type="checkbox" id="select-all-cb" checked onchange="toggleAllCommunities(!this.checked)">Select All</label>
    </div>
    <div id="legend"></div>
  </div>
  <div id="stats">{stats}</div>
</div>"""


_THEME_INIT_SCRIPT = """<script id="graphify-theme-init">
// Apply the saved theme before first paint (#3894). No saved choice keeps the
// historical dark look; "system" follows prefers-color-scheme.
(function () {
  var pref = null;
  try { pref = localStorage.getItem('graphify-theme'); } catch (e) {}
  var t = pref === 'light' ? 'light'
    : pref === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light'
    : 'dark';
  document.documentElement.setAttribute('data-theme', t);
})();
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
    mode: str | None = None,
    source_root: "str | Path | None" = None,
) -> bool:
    """Generate an interactive HTML visualization of the graph.

    *mode* picks the renderer: ``"3d"`` (default) is a three.js force graph
    (3d-force-graph) with a floating node card showing each node's kind,
    signature, source comment and grouped relationships; ``"2d"`` is the flat
    vis-network page. When *mode* is None the ``GRAPHIFY_VIZ_MODE`` env var
    decides, falling back to 3d.

    In 3D mode node descriptions are read from the project's source files
    under *source_root* (default: the project recorded for the graph next to
    *output_path*, see :func:`graphify.paths.graph_root_for`).

    Features: node size by degree, click-to-inspect panel, search box,
    community filter, physics clustering by community, confidence-styled edges.
    Raises ValueError if graph exceeds MAX_NODES_FOR_VIZ.

    If member_counts is provided (aggregated community view), node sizes are
    based on community member counts rather than graph degree.

    If node_limit is set and the graph exceeds it, automatically builds an
    aggregated community-level meta-graph instead of raising ValueError.

    Returns True when the output was written. Returns False when an aggregated
    view would contain fewer than two communities and is intentionally skipped.
    """
    mode = _viz_mode(mode)
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
                              community_labels=community_labels, member_counts=mc,
                              mode=mode)
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

    # Build nodes list for vis.js
    vis_nodes = []
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        label = sanitize_label(data.get("label", node_id))
        deg = degree.get(node_id, 1)
        if member_counts:
            mc = member_counts.get(cid, 1)
            size = 10 + 30 * (mc / max_mc)
            font_size = 12
        else:
            size = 10 + 30 * (deg / max_deg)
            # Only show label for high-degree nodes by default; others show on hover
            font_size = 12 if deg >= max_deg * 0.15 else 0
        node = {
            "id": node_id,
            "label": label,
            "color": {"background": color, "border": color, "highlight": {"background": "#ffffff", "border": color}},
            "size": round(size, 1),
            "font": {"size": font_size, "color": "#ffffff"},
            # Tooltip `title` is a STRING, which vis-network renders via
            # Popup.setText -> `frame.innerText = t` (verified in the pinned
            # 9.1.6 bundle: the only non-Element branch is innerText, and the
            # bundle has zero `innerHTML = <var>` sinks). So raw special chars
            # are shown literally and must NOT be html-escaped here or the user
            # sees `&amp;`/`&lt;` in the tooltip (#3664/#3686). This is the
            # #1838 stored-XSS boundary: never pass an HTMLElement as `title`,
            # and do not change the vis-network pin below without re-checking
            # Popup rendering (the test_export version-pin guard enforces this).
            "title": label,
            "community": cid,
            "community_name": sanitize_label((community_labels or {}).get(cid, f"Community {cid}")),
            "source_file": sanitize_label(str(data.get("source_file") or "")),
            "file_type": data.get("file_type", ""),
            "degree": deg,
        }
        if member_counts:
            node["member_count"] = member_counts.get(cid, len(communities.get(cid, [])))
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
                # Status-colored ring via the border; stale => desaturated +
                # dashed (vis.js supports per-node `shapeProperties.borderDashes`).
                if stale:
                    ring = "#9ca3af"
                    node["shapeProperties"] = {"borderDashes": [4, 4]}
                node["borderWidth"] = 3
                node["color"] = {
                    "background": color, "border": ring,
                    "highlight": {"background": "#ffffff", "border": ring},
                }
            # Lesson line appended to the hover title.
            if status == "contested":
                lesson = f"Lesson: contested (useful {entry.get('uses', 0)} / dead-end {entry.get('neg', 0)})"
            elif status == "preferred":
                lesson = f"Lesson: preferred source ({entry.get('uses', 0)} useful, score={entry.get('score', 0)})"
            else:
                lesson = f"Lesson: {status} ({entry.get('uses', 0)} useful)"
            if stale:
                lesson += " [code changed — re-verify]"
            node["title"] = f"{label}\n{sanitize_label(lesson)}"
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
        vis_edges.append({
            "from": true_src,
            "to": true_tgt,
            "label": relation,
            "title": sanitize_label(f"{relation} [{confidence}]"),
            "dashes": confidence != "EXTRACTED",
            "width": 2 if confidence == "EXTRACTED" else 1,
            "color": {"opacity": 0.7 if confidence == "EXTRACTED" else 0.35},
            "confidence": confidence,
        })

    # Build community legend data
    legend_data = []
    for cid in sorted((community_labels or {}).keys()):
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        lbl = _html.escape(sanitize_label((community_labels or {}).get(cid, f"Community {cid}")))
        n = member_counts.get(cid, len(communities.get(cid, []))) if member_counts else len(communities.get(cid, []))
        legend_data.append({"cid": cid, "color": color, "label": lbl, "count": n})

    # Escape every `<` as < so embedded JSON cannot break out of the <script>
    # element. Escaping only `</` is not enough: an unclosed `<!--` then a later
    # `<script` in a label drive the HTML tokenizer into script-data-double-escaped
    # state, where the real `</script>` no longer closes the tag and the page goes
    # blank (#4124). `<` round-trips through JSON.parse, so labels render unchanged.
    def _js_safe(obj) -> str:
        return json.dumps(obj).replace("<", "\\u003c")

    nodes_json = _js_safe(vis_nodes)
    edges_json = _js_safe(vis_edges)
    legend_json = _js_safe(legend_data)
    hyperedges_json = _js_safe(getattr(G, "graph", {}).get("hyperedges", []))
    title = _html.escape(sanitize_label(_html_document_title(output_path)))
    stats = f"{G.number_of_nodes()} nodes &middot; {G.number_of_edges()} edges &middot; {len(communities)} communities"

    if mode == "3d":
        node_info: dict = {}
        if not member_counts:  # community meta-nodes have no source to describe
            try:
                from graphify.exporters.node_info import build_node_info
                root = source_root
                if root is None:
                    from graphify.paths import graph_root_for
                    root = graph_root_for(Path(output_path).parent / "graph.json")
                node_info = build_node_info(G, root)
            except Exception as exc:  # descriptions are a bonus, never fatal
                print(f"[graphify] node descriptions skipped: {exc}")
                node_info = {}
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify - {title}</title>
<script src="{_FORCE_GRAPH_3D_URL}"
        integrity="{_FORCE_GRAPH_3D_SRI}"
        crossorigin="anonymous"></script>
{_html3d_styles()}
{_THEME_INIT_SCRIPT}
</head>
<body>
{_html3d_body(stats)}
{_html3d_data_script(nodes_json, edges_json, legend_json, hyperedges_json, _js_safe(node_info))}
{_HTML3D_SCRIPT}
</body>
</html>"""
        write_text_atomic(output_path, html)
        return True

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify - {title}</title>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"
        integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
        crossorigin="anonymous"></script>
{_html_styles()}
{_THEME_INIT_SCRIPT}
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="theme-wrap" role="group" aria-label="Theme">
    <button type="button" data-theme-choice="light">Light</button>
    <button type="button" data-theme-choice="dark">Dark</button>
    <button type="button" data-theme-choice="system">System</button>
  </div>
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="info-panel">
    <h3>Node Info</h3>
    <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
  </div>
  <div id="legend-wrap">
    <h3>Communities</h3>
    <div id="legend-controls">
      <label><input type="checkbox" id="select-all-cb" checked onchange="toggleAllCommunities(!this.checked)">Select All</label>
    </div>
    <div id="legend"></div>
  </div>
  <div id="stats">{stats}</div>
</div>
{_html_script(nodes_json, edges_json, legend_json)}
{_hyperedge_script(hyperedges_json)}
</body>
</html>"""

    write_text_atomic(output_path, html)
    return True
