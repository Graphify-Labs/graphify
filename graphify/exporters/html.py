"""html — moved verbatim from graphify/export.py."""
from __future__ import annotations

from graphify.exporters.base import COMMUNITY_COLORS  # noqa: E402,F401
from pathlib import Path
import html as _html
from graphify.analyze import _node_community_map
import json
import networkx as nx
from graphify.security import sanitize_label


MAX_NODES_FOR_VIZ = 5_000

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
  #graph { flex: 1; }
  #sidebar { width: 280px; background: #1a1a2e; border-left: 1px solid #2a2a4e; display: flex; flex-direction: column; overflow: hidden; }
  #search-wrap { padding: 12px; border-bottom: 1px solid #2a2a4e; }
  #search { width: 100%; background: #0f0f1a; border: 1px solid #3a3a5e; color: #e0e0e0; padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
  #search:focus { border-color: #4E79A7; }
  #search-results { max-height: 140px; overflow-y: auto; padding: 4px 12px; border-bottom: 1px solid #2a2a4e; display: none; }
  .search-item { padding: 4px 6px; cursor: pointer; border-radius: 4px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .search-item:hover { background: #2a2a4e; }
  #info-panel { padding: 14px; border-bottom: 1px solid #2a2a4e; min-height: 140px; }
  #info-panel h3 { font-size: 13px; color: #aaa; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
  #info-content { font-size: 13px; color: #ccc; line-height: 1.6; }
  #info-content .field { margin-bottom: 5px; }
  #info-content .field b { color: #e0e0e0; }
  #info-content .empty { color: #555; font-style: italic; }
  .neighbor-link { display: block; padding: 2px 6px; margin: 2px 0; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid #333; }
  .neighbor-link:hover { background: #2a2a4e; }
  #neighbors-list { max-height: 160px; overflow-y: auto; margin-top: 4px; }
  #legend-wrap { flex: 1; overflow-y: auto; padding: 12px; }
  #legend-wrap h3 { font-size: 13px; color: #aaa; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
  .legend-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; border-radius: 4px; font-size: 12px; }
  .legend-item:hover { background: #2a2a4e; padding-left: 4px; }
  .legend-item.dimmed { opacity: 0.35; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .legend-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-count { color: #666; font-size: 11px; }
  #stats { padding: 10px 14px; border-top: 1px solid #2a2a4e; font-size: 11px; color: #555; }
  #legend-controls { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding: 4px 0; }
  #legend-controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: #aaa; user-select: none; }
  #legend-controls label:hover { color: #e0e0e0; }
  .legend-cb, #select-all-cb { appearance: none; -webkit-appearance: none; width: 14px; height: 14px; border: 1.5px solid #3a3a5e; border-radius: 3px; background: #0f0f1a; cursor: pointer; position: relative; flex-shrink: 0; }
  .legend-cb:checked, #select-all-cb:checked { background: #4E79A7; border-color: #4E79A7; }
  .legend-cb:checked::after, #select-all-cb:checked::after { content: ''; position: absolute; left: 3.5px; top: 1px; width: 4px; height: 7px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
  #select-all-cb:indeterminate { background: #4E79A7; border-color: #4E79A7; }
  #select-all-cb:indeterminate::after { content: ''; position: absolute; left: 2px; top: 5px; width: 8px; height: 2px; background: #fff; border: none; transform: none; }
</style>"""

def _hyperedge_script(hyperedges_json: str) -> str:
    return f"""<script>
// Render hyperedges as shaded regions
const hyperedges = {hyperedges_json};
// afterDrawing passes ctx already transformed to network coordinate space.
// Draw node positions raw — no manual pan/zoom/DPR math needed.
network.on('afterDrawing', function(ctx) {{
    hyperedges.forEach(h => {{
        const positions = h.nodes
            .map(nid => network.getPositions([nid])[nid])
            .filter(p => p !== undefined);
        if (positions.length < 2) return;
        ctx.save();
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = '#6366f1';
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.beginPath();
        // Centroid and expanded hull in network coordinates
        const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length;
        const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length;
        const expanded = positions.map(p => ({{
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
const nodesDS = new vis.DataSet(RAW_NODES.map(n => ({{
  id: n.id, label: n.label, color: n.color, size: n.size,
  font: n.font, title: n.title,
  _community: n.community, _community_name: n.community_name,
  _source_file: n.source_file, _file_type: n.file_type, _degree: n.degree,
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
  document.getElementById('info-content').innerHTML = `
    <div class="field"><b>${{esc(n.label)}}</b></div>
    <div class="field">Type: ${{esc(n._file_type || 'unknown')}}</div>
    <div class="field">Community: ${{esc(n._community_name)}}</div>
    <div class="field">Source: ${{esc(n._source_file || '-')}}</div>
    <div class="field">Degree: ${{n._degree}}</div>
    ${{neighborIds.length ? `<div class="field" style="margin-top:8px;color:#aaa;font-size:11px">Neighbors (${{neighborIds.length}})</div><div id="neighbors-list">${{neighborItems}}</div>` : ''}}
  `;
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

def _lens_markup() -> str:
    """Toggle button + HUD + scoped styles for the Focus Lens.

    Emitted only inside the conditional lens block (not in _html_styles()) so a
    graph without the lens renders byte-identically to the pre-feature output.
    The HUD legend explains the two rectangles: dotted = capture area feeding
    the tree, solid = the display panel it is drawn in.
    """
    return """<style>
  #lens-toggle { position: fixed; left: 16px; bottom: 16px; z-index: 20; background: #1a1a2e; color: #e0e0e0; border: 1px solid #3a3a5e; border-radius: 8px; padding: 8px 14px; font-size: 13px; cursor: pointer; font-family: inherit; }
  #lens-toggle:hover { border-color: #7c6df2; }
  #lens-toggle.active { background: #7c6df2; border-color: #7c6df2; color: #fff; }
  #lens-hud { position: fixed; left: 16px; bottom: 60px; z-index: 20; width: 300px; max-width: calc(100vw - 320px); background: rgba(26,26,46,0.96); border: 1px solid #3a3a5e; border-radius: 10px; padding: 12px 14px; display: none; }
  #lens-hud.on { display: block; }
  #lens-hud .lens-title { font-size: 15px; font-weight: 600; color: #fff; margin-bottom: 3px; }
  #lens-hud .lens-info { font-size: 12px; color: #b9b2ee; margin-bottom: 8px; }
  #lens-hud .lens-legend { font-size: 11px; color: #aaa; line-height: 1.8; margin-bottom: 6px; }
  #lens-hud .lens-glyph { display: inline-block; width: 18px; height: 11px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
  #lens-hud .lens-glyph.capture { border: 1.5px dashed #9d8ff5; }
  #lens-hud .lens-glyph.panel { border: 1.5px solid #7c6df2; }
  #lens-hud .lens-keys { font-size: 11px; color: #aaa; line-height: 1.6; }
</style>
<button id="lens-toggle" aria-pressed="false">Lens</button>
<div id="lens-hud" role="region" aria-label="Focus lens">
  <div class="lens-title">Focus lens</div>
  <div class="lens-info" id="lens-info">move the lens over the graph</div>
  <div class="lens-legend"><span class="lens-glyph capture"></span>dotted box &mdash; capture area: the tree reads these nodes<br><span class="lens-glyph panel"></span>solid box &mdash; tree view of that region</div>
  <div class="lens-keys">double-click / h &mdash; hold to inspect &middot; [ ] capture size &middot; arrow keys nudge &middot; f / esc exit</div>
</div>"""

def _lens_script() -> str:
    """Client-side Focus Lens: opt-in, additive, dependency-free.

    A small dotted capture region centered on the cursor selects the nodes under
    it (live positions, legend filtering respected); a larger display panel
    re-lays-out that selection as a layered tree (longest-path levels, wrapped
    rows, capped at the most-connected 30) that updates as the mouse moves.
    Double-click or 'h' holds the lens: hover a box for the longer label +
    source tooltip, click one to inspect it in the sidebar; Esc releases, then
    exits. The layout is cached on the selection key, so gliding re-layouts
    only when the captured set changes.

    All lens text is drawn with canvas fillText (an inert sink) from the same
    sanitize_label'd labels vis renders; the HUD uses textContent and inspect
    clicks delegate to the audited showInfo() — no new XSS surface (#1838).
    """
    return """<script>
(function() {
  const toggleBtn = document.getElementById('lens-toggle');
  const hud = document.getElementById('lens-hud');
  const infoEl = document.getElementById('lens-info');

  // Capture (small, feeds the selection) vs display (big, room for the tree).
  const DW = 660, DH = 480;
  let CW = 220, CH = 150;
  const CW_MIN = 120, CW_MAX = 560, CH_MIN = 84, CH_MAX = 420;
  const TRUNC = 24, TRUNC_FULL = 70, MAX_TREE = 30;
  const FONT = (w, s) => w + ' ' + s + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';

  let on = false;
  let frozen = false;         // double-click holds the lens for reading
  let held = null;            // frozen snapshot: { ids, total, R, S }
  let hoverId = null;         // tree box under the cursor while held
  let lastBoxes = [];         // drawn tree boxes, for hit-testing while held
  let cx = null, cy = null;   // lens center in container CSS px; null => center
  let raf = 0;

  const LABELS = {}, SIZE = {}, COLOR = {}, META = {}, ID2COMM = {}, ORIG_FONT = {};
  RAW_NODES.forEach(n => {
    LABELS[n.id] = n.label || '';
    SIZE[n.id] = n.size || 0;
    COLOR[n.id] = (n.color && n.color.background) || '#7c6df2';
    META[n.id] = [n.file_type, n.source_file].filter(Boolean).join(' \\u00b7 ');
    ID2COMM[n.id] = n.community;
    ORIG_FONT[n.id] = n.font;
  });

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function currentRects(rect) {
    const mx = (cx === null) ? rect.width / 2 : cx;
    const my = (cy === null) ? rect.height / 2 : cy;
    const dw = Math.min(DW, rect.width - 8), dh = Math.min(DH, rect.height - 8);
    const R = { x: clamp(mx - dw / 2, 4, Math.max(4, rect.width - dw - 4)),
                y: clamp(my - dh / 2, 4, Math.max(4, rect.height - dh - 4)), w: dw, h: dh };
    const S = { x: mx - CW / 2, y: my - CH / 2, w: CW, h: CH };
    return { R, S };
  }

  function captureIds(S) {
    // Live position read every capture: node drags and re-stabilization are
    // honored, and legend-hidden communities are excluded to match the page's
    // own filtering model.
    const pos = network.getPositions();
    const tl = network.DOMtoCanvas({ x: S.x, y: S.y });
    const br = network.DOMtoCanvas({ x: S.x + S.w, y: S.y + S.h });
    const ids = [];
    for (const id in pos) {
      if (hiddenCommunities.has(ID2COMM[id])) continue;
      const p = pos[id];
      if (p.x >= tl.x && p.x <= br.x && p.y >= tl.y && p.y <= br.y) ids.push(id);
    }
    return ids;
  }

  function pickShown(inside) {
    // Cap to the most-connected nodes so a dense region stays a readable tree;
    // sort the final set for a stable draw order and layout-cache key.
    let ids = inside;
    if (ids.length > MAX_TREE) {
      ids = ids.slice().sort((a, b) => (SIZE[b] - SIZE[a]) || (a < b ? -1 : 1)).slice(0, MAX_TREE);
    }
    return ids.slice().sort();
  }

  // Layered layout (longest-path levels, wrapped rows) in coords relative to a
  // w x h rect, plus the induced edge list; cached on the selection + size so
  // gliding re-layouts only when the captured set changes.
  let layoutKey = '', layoutCache = null;
  function layoutTreeRel(ids, w, h) {
    const key = ids.join('|') + ':' + Math.round(w) + 'x' + Math.round(h);
    if (key === layoutKey && layoutCache) return layoutCache;
    const sel = new Set(ids);
    const induced = RAW_EDGES.filter(e => e.from !== e.to && sel.has(e.from) && sel.has(e.to));
    const level = {};
    ids.forEach(id => { level[id] = 0; });
    for (let iter = 0; iter < ids.length; iter++) {
      let changed = false;
      for (let i = 0; i < induced.length; i++) {
        const e = induced[i];
        if (level[e.to] < level[e.from] + 1) { level[e.to] = level[e.from] + 1; changed = true; }
      }
      if (!changed) break;   // bounded iterations tolerate cycles
    }
    let maxL = 0;
    ids.forEach(id => { if (level[id] > maxL) maxL = level[id]; });
    const byLevel = {};
    ids.forEach(id => { const k = Math.min(level[id], maxL); (byLevel[k] = byLevel[k] || []).push(id); });
    const levels = Object.keys(byLevel).map(Number).sort((a, b) => a - b);
    levels.forEach(k => byLevel[k].sort((a, b) => (SIZE[b] - SIZE[a]) || (a < b ? -1 : 1)));
    // ~6.6 px/char at the 11px box font, plus box padding.
    function approxW(id) { const t = LABELS[id] || id; return Math.min(t.length, TRUNC) * 6.6 + 18; }
    const padX = 16, padTop = 40, padBot = 16, gapX = 12, avail = w - 2 * padX;
    const lines = [];                     // wrap wide levels onto multiple lines
    levels.forEach(k => {
      const row = byLevel[k];
      let cur = [], lw = 0;
      row.forEach(id => {
        const bw = approxW(id);
        if (cur.length && lw + bw > avail) { lines.push(cur); cur = []; lw = 0; }
        cur.push(id); lw += bw + gapX;
      });
      if (cur.length) lines.push(cur);
    });
    const pos = {}, nL = lines.length || 1, availH = h - padTop - padBot;
    lines.forEach((line, li) => {
      const widths = line.map(approxW);
      let tot = gapX * (line.length - 1);
      widths.forEach(x => { tot += x; });
      const scale = tot > avail ? avail / tot : 1;
      let x = padX + (avail - tot * scale) / 2;
      const y = padTop + (nL <= 1 ? availH / 2 : (li + 0.5) * availH / nL);
      line.forEach((id, ci) => {
        const bw = widths[ci] * scale;
        pos[id] = { x: x + bw / 2, y: y, w: bw };
        x += bw + gapX * scale;
      });
    });
    layoutKey = key; layoutCache = { pos, induced };
    return layoutCache;
  }

  network.on('afterDrawing', function(ctx) {
    if (!on) return;
    // Swat any popup an in-flight (pre-enter) tooltipDelay timer opened.
    const tip = container.querySelector('.vis-tooltip');
    if (tip && tip.style.visibility !== 'hidden') tip.style.visibility = 'hidden';
    const dpr = window.devicePixelRatio || 1;
    const rect = container.getBoundingClientRect();
    let R, S, ids, total;
    if (frozen && held) {
      R = held.R; S = held.S; ids = held.ids; total = held.total;
    } else {
      const c = currentRects(rect);
      R = c.R; S = c.S;
      const inside = captureIds(S);
      total = inside.length;
      ids = pickShown(inside);
    }

    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const rad = 14;
    // Dim the whole view, punch out the panel.
    ctx.beginPath();
    ctx.rect(0, 0, rect.width, rect.height);
    roundRect(ctx, R.x, R.y, R.w, R.h, rad);
    ctx.fillStyle = 'rgba(9, 9, 20, 0.5)';
    ctx.fill('evenodd');
    // Panel (held state gets a brighter border).
    ctx.beginPath(); roundRect(ctx, R.x, R.y, R.w, R.h, rad);
    ctx.fillStyle = 'rgba(14, 14, 28, 0.97)'; ctx.fill();
    ctx.beginPath(); roundRect(ctx, R.x, R.y, R.w, R.h, rad);
    ctx.lineWidth = frozen ? 2.5 : 2;
    ctx.strokeStyle = frozen ? '#9d8ff5' : '#7c6df2';
    ctx.stroke();
    // Capture region (dotted) -- the area the tree is built from.
    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = frozen ? 'rgba(157, 143, 245, 0.7)' : 'rgba(124, 109, 242, 0.45)';
    ctx.lineWidth = 1;
    ctx.beginPath(); roundRect(ctx, S.x, S.y, S.w, S.h, 8); ctx.stroke();
    ctx.restore();

    const countText = (total > ids.length ? ('top ' + ids.length + ' of ' + total)
      : (ids.length + (ids.length === 1 ? ' node' : ' nodes')));
    ctx.fillStyle = frozen ? '#b9b2ee' : '#8f86d8';
    ctx.font = FONT(600, 11);
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(frozen
      ? 'HELD \\u00b7 ' + countText + ' \\u00b7 hover for details \\u00b7 click to inspect \\u00b7 double-click to release'
      : (total ? countText + ' \\u00b7 double-click to hold' : countText), R.x + 14, R.y + 18);

    lastBoxes = [];
    if (ids.length >= 1) {
      ctx.save();
      ctx.beginPath(); roundRect(ctx, R.x + 1, R.y + 1, R.w - 2, R.h - 2, rad - 1); ctx.clip();
      const lay = layoutTreeRel(ids, R.w, R.h);
      const rel = lay.pos;
      // Edges (arrows) under the boxes; the hovered node's edges are highlighted.
      for (let i = 0; i < lay.induced.length; i++) {
        const e = lay.induced[i];
        const ra = rel[e.from], rb = rel[e.to];
        if (!ra || !rb) continue;
        const hot = frozen && hoverId !== null && (e.from === hoverId || e.to === hoverId);
        ctx.strokeStyle = hot ? 'rgba(190, 180, 255, 0.95)' : 'rgba(150, 140, 225, 0.5)';
        ctx.fillStyle = ctx.strokeStyle;
        ctx.lineWidth = hot ? 2 : 1.2;
        const ax = R.x + ra.x, ay = R.y + ra.y, bx = R.x + rb.x, by = R.y + rb.y;
        const ang = Math.atan2(by - ay, bx - ax);
        const px = bx - 13 * Math.cos(ang), py = by - 13 * Math.sin(ang);
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(px, py); ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(px - 6 * Math.cos(ang - 0.4), py - 6 * Math.sin(ang - 0.4));
        ctx.lineTo(px - 6 * Math.cos(ang + 0.4), py - 6 * Math.sin(ang + 0.4));
        ctx.closePath(); ctx.fill();
      }
      // Node boxes with community-colored borders + truncated labels.
      const fs = 11;
      ctx.font = FONT(600, fs);
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i], p = rel[id];
        if (!p) continue;
        let txt = LABELS[id] || id;
        if (txt.length > TRUNC) txt = txt.slice(0, TRUNC - 1) + '\\u2026';
        const bx = R.x + p.x, by = R.y + p.y, bw = p.w, bh = fs + 9;
        const hot = frozen && hoverId === id;
        ctx.fillStyle = hot ? '#26264a' : '#1a1a2e';
        ctx.strokeStyle = COLOR[id];
        ctx.lineWidth = hot ? 2.5 : 1.5;
        ctx.beginPath(); roundRect(ctx, bx - bw / 2, by - bh / 2, bw, bh, 4);
        ctx.fill(); ctx.stroke();
        ctx.fillStyle = '#e8e8f0';
        ctx.fillText(txt, bx, by);
        lastBoxes.push({ id, x: bx - bw / 2, y: by - bh / 2, w: bw, h: bh });
      }
      // Longer-label tooltip for the hovered box while held.
      if (frozen && hoverId !== null && rel[hoverId]) {
        const p = rel[hoverId];
        let full = LABELS[hoverId] || hoverId;
        if (full.length > TRUNC_FULL) full = full.slice(0, TRUNC_FULL - 1) + '\\u2026';
        const meta = META[hoverId] || '';
        ctx.font = FONT(600, 12);
        const w1 = ctx.measureText(full).width;
        ctx.font = FONT(500, 10);
        const w2 = meta ? ctx.measureText(meta).width : 0;
        const tw = Math.min(Math.max(w1, w2) + 20, R.w - 20);
        const th = meta ? 40 : 26;
        const tx = clamp(R.x + p.x - tw / 2, R.x + 8, R.x + R.w - tw - 8);
        let ty = R.y + p.y - 14 - th;
        if (ty < R.y + 30) ty = R.y + p.y + 14;
        ctx.fillStyle = 'rgba(240, 240, 246, 0.98)';
        ctx.beginPath(); roundRect(ctx, tx, ty, tw, th, 6); ctx.fill();
        ctx.fillStyle = '#12121c';
        ctx.textAlign = 'left';
        ctx.font = FONT(600, 12);
        ctx.fillText(full, tx + 10, ty + 14, tw - 20);
        if (meta) {
          ctx.fillStyle = '#555a70';
          ctx.font = FONT(500, 10);
          ctx.fillText(meta, tx + 10, ty + 29, tw - 20);
        }
      }
      ctx.restore();
    } else {
      ctx.fillStyle = '#6a6a8a';
      ctx.font = FONT(500, 12);
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('move the lens over the graph', R.x + R.w / 2, R.y + R.h / 2);
    }
    ctx.restore();

    infoEl.textContent = frozen
      ? ('held \\u00b7 ' + countText + ' \\u00b7 double-click to release')
      : (total ? countText + ' in view \\u00b7 double-click to hold' : 'move the lens over the graph');
  });

  function schedule() { if (!raf && on) raf = requestAnimationFrame(() => { raf = 0; network.redraw(); }); }

  function onMove(e) {
    if (!on) return;
    const rect = container.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    if (frozen) {
      let hit = null;
      for (let i = 0; i < lastBoxes.length; i++) {
        const b = lastBoxes[i];
        if (px >= b.x && px <= b.x + b.w && py >= b.y && py <= b.y + b.h) { hit = b.id; break; }
      }
      if (hit !== hoverId) {
        hoverId = hit;
        container.style.cursor = hit !== null ? 'pointer' : 'default';
        schedule();
      }
      return;
    }
    cx = px; cy = py;
    schedule();
  }
  container.addEventListener('mousemove', onMove);

  function toggleHold() {
    if (!on) return;
    if (frozen) {
      frozen = false; held = null; hoverId = null;
      network.setOptions({ interaction: { dragView: true, zoomView: true } });
      container.style.cursor = 'crosshair';
      schedule();
      return;
    }
    const rect = container.getBoundingClientRect();
    const c = currentRects(rect);
    const inside = captureIds(c.S);
    if (!inside.length) return;   // nothing under the lens to hold
    held = { ids: pickShown(inside), total: inside.length, R: c.R, S: c.S };
    frozen = true;
    // A held panel should not slide around under pan/zoom.
    network.setOptions({ interaction: { dragView: false, zoomView: false } });
    container.style.cursor = 'default';
    schedule();
  }
  container.addEventListener('dblclick', e => { if (on) { e.preventDefault(); toggleHold(); } });

  // Swallow clicks that land on the panel so they never act on the dimmed graph
  // behind it (vis selection is additionally disabled while the lens is on —
  // stopping DOM propagation alone cannot stop vis's pointer pipeline). While
  // held, a click on a tree box inspects that node via the audited showInfo().
  container.addEventListener('click', e => {
    if (!on) return;
    const rect = container.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    const R = (frozen && held) ? held.R : currentRects(rect).R;
    if (px >= R.x && px <= R.x + R.w && py >= R.y && py <= R.y + R.h) {
      if (frozen && hoverId !== null) showInfo(hoverId);
      e.stopPropagation();
    }
  }, true);

  function enter() {
    on = true;
    toggleBtn.classList.add('active');
    toggleBtn.setAttribute('aria-pressed', 'true');
    hud.classList.add('on');
    container.style.cursor = 'crosshair';
    // Hide vis labels (the lens draws its own), drop hover tooltips, and turn
    // off tap-selection so clicks cannot reach invisible nodes behind the
    // panel. hoveredNodeId is the main script's hover tracker — nulled here
    // because disabling hover also silences the blurNode that would clear it.
    hoveredNodeId = null;
    network.unselectAll();
    nodesDS.update(RAW_NODES.map(n => ({ id: n.id, font: { size: 0 } })));
    // vis title popups are driven by tooltipDelay (not interaction.hover), so
    // they would keep appearing over the panel for whatever sits behind it —
    // push the delay out of reach and hide any popup that is already open.
    network.setOptions({ interaction: { hover: false, selectable: false, tooltipDelay: 3600000 } });
    const tip = container.querySelector('.vis-tooltip');
    if (tip) tip.style.visibility = 'hidden';
    schedule();
  }
  function exit() {
    frozen = false; held = null; hoverId = null;
    toggleBtn.classList.remove('active');
    toggleBtn.setAttribute('aria-pressed', 'false');
    hud.classList.remove('on');
    container.style.cursor = 'default';
    nodesDS.update(RAW_NODES.map(n => ({ id: n.id, font: ORIG_FONT[n.id] })));
    network.setOptions({ interaction: { hover: true, selectable: true, dragView: true, zoomView: true, tooltipDelay: 100 } });
    on = false;
    network.redraw();
  }
  function toggle() { on ? exit() : enter(); }
  toggleBtn.addEventListener('click', toggle);

  document.addEventListener('keydown', e => {
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;   // never eat browser chords (Cmd+F etc.)
    if (e.key === 'f' || e.key === 'F') { e.preventDefault(); toggle(); return; }
    if (!on) return;
    if (e.key === 'Escape') { frozen ? toggleHold() : exit(); return; }
    if (e.key === 'h' || e.key === 'H') { toggleHold(); return; }
    if (frozen) return;   // held: the lens is fixed until released
    if (e.key === ']') { CW = Math.min(CW_MAX, CW + 40); CH = Math.min(CH_MAX, CH + 30); schedule(); }
    else if (e.key === '[') { CW = Math.max(CW_MIN, CW - 40); CH = Math.max(CH_MIN, CH - 30); schedule(); }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const rect = container.getBoundingClientRect();
      if (cx === null) { cx = rect.width / 2; cy = rect.height / 2; }
      const step = 40;
      if (e.key === 'ArrowLeft') cx -= step;
      else if (e.key === 'ArrowRight') cx += step;
      else if (e.key === 'ArrowUp') cy -= step;
      else cy += step;
      cx = clamp(cx, 0, rect.width); cy = clamp(cy, 0, rect.height);
      schedule();
    }
  });

  // Keep the lens correct as the graph pans/zooms underneath it.
  network.on('zoom', schedule);
  network.on('dragging', schedule);
  network.on('animationFinished', schedule);
})();
</script>"""

def to_html(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    member_counts: dict[int, int] | None = None,
    node_limit: int | None = None,
    learning_overlay: dict | None = None,
) -> None:
    """Generate an interactive vis.js HTML visualization of the graph.

    Features: node size by degree, click-to-inspect panel, search box,
    community filter, physics clustering by community, confidence-styled edges.
    Raises ValueError if graph exceeds MAX_NODES_FOR_VIZ.

    If member_counts is provided (aggregated community view), node sizes are
    based on community member counts rather than graph degree.

    If node_limit is set and the graph exceeds it, automatically builds an
    aggregated community-level meta-graph instead of raising ValueError.
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
                return
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
            to_html(meta, meta_communities, output_path,
                    community_labels=community_labels, member_counts=mc)
            print(f"graph.html written (aggregated: {meta.number_of_nodes()} community nodes, {meta.number_of_edges()} cross-community edges)")
            print("Tip: run with --obsidian for full node-level detail.")
            return
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
        vis_edges.append({
            "from": true_src,
            "to": true_tgt,
            "label": relation,
            "title": _html.escape(f"{relation} [{confidence}]"),
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

    # Escape </script> sequences so embedded JSON cannot break out of the script tag
    def _js_safe(obj) -> str:
        return json.dumps(obj).replace("</", "<\\/")

    nodes_json = _js_safe(vis_nodes)
    edges_json = _js_safe(vis_edges)
    legend_json = _js_safe(legend_data)
    hyperedges_json = _js_safe(getattr(G, "graph", {}).get("hyperedges", []))
    title = _html.escape(sanitize_label(str(output_path)))
    stats = f"{G.number_of_nodes()} nodes &middot; {G.number_of_edges()} edges &middot; {len(communities)} communities"

    # Opt-in Focus Lens: a movable capture region whose contents are re-laid-out
    # as a layered tree in a display panel. Emitted only for graphs large enough
    # to benefit (>=15 nodes) with >=2 communities, at least one of which has >=2
    # members — the last clause suppresses it in the aggregated community
    # meta-graph, where every "community" is a single super-node. Gates on
    # `communities` (not community_labels) so unlabeled builds keep the lens.
    # When the gate is false, lens_block is "" and the output is byte-identical
    # to the pre-feature HTML.
    lens_block = ""
    if (
        G.number_of_nodes() >= 15
        and len(communities) >= 2
        and any(len(m) >= 2 for m in communities.values())
    ):
        lens_block = "\n" + _lens_markup() + "\n" + _lens_script()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify - {title}</title>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"
        integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
        crossorigin="anonymous"></script>
{_html_styles()}
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
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
{_hyperedge_script(hyperedges_json)}{lens_block}
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")  # nosec
