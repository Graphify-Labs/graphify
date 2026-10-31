"""Perf levers in the HTML exporter (#perf).

Dense graphs defer arrowheads to hover, take over the edge pass and lean the node
draw during a drag/zoom gesture, and every graph caches its stabilized layout so a
re-open skips the on-load solver. Levers must be invisible below the density
thresholds and must not drop direction/confidence/connectivity. Edges are never
hidden: `hideEdgesOnDrag`/`hideEdgesOnZoom` looked like the graph was falling apart
while moving it, so the gesture work keeps every edge and every node drawn.

Measured (rsl 1886 nodes / 3876 edges, interleaved same-machine A/B, 3 rounds): borders
off the nodes + the batched edge pass took a node drag 40.4 -> 82.9 fps, pan 39.1 -> 78.9
fps and zoom 15.2 -> 80.4 fps, with stalled frames (>33ms) falling from 13-91/90 to 0-1/90.
The paired ratio has come out anywhere between x1.7 and x5.8 across runs because this host
drifts ~3x between rounds (the same shipped file measured 15.0 fps and 43.7 fps in
consecutive rounds of a single run), so the paired ratio is the durable number, never the
absolute fps. Neither lever touches the stored data or the resting draw: the batch is
removed on release and the frame after it is identical to the frame before it (5762
ctx.stroke(), 3876 quadratic curves, same colour set), and the lean writes widths onto the
node instances rather than calling network.setOptions, which would add a ~200ms
synchronous redraw at dragStart/dragEnd.

The batch draws the same curve vis draws at rest, not a straight line: a frame-by-frame
pixel diff against the resting frame changes 1.1-1.8% of painted pixels with the curve
versus 82-100% with straight lines, and the via point it computes agrees with vis's own
getViaNode() for all 3876 edges.
"""
from __future__ import annotations

import re
from pathlib import Path

import networkx as nx

from graphify.exporters.html import (
    ARROW_DEFER_EDGE_THRESHOLD,
    LEAN_GESTURE_NODE_THRESHOLD,
    to_html,
)
from graphify.exporters.base import COMMUNITY_COLORS


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.1 relative luminance."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _render(tmp_path: Path, n: int, k: int) -> tuple[str, int]:
    """A graph with ~n*k/2 edges: nodes 0..n-1, each wired to the next k."""
    G = nx.Graph()
    for i in range(n):
        G.add_node(f"n{i}", label=f"node{i}", community=i % 5)
    for i in range(n):
        for j in range(i + 1, min(n, i + k)):
            G.add_edge(f"n{i}", f"n{j}", relation="calls", confidence="EXTRACTED")
    comms: dict[int, list[str]] = {}
    for i in range(n):
        comms.setdefault(i % 5, []).append(f"n{i}")
    out = tmp_path / "graph.html"
    to_html(G, comms, str(out), node_limit=10**9)
    return out.read_text(encoding="utf-8"), G.number_of_edges()


def test_sparse_graph_keeps_eager_arrowheads(tmp_path):
    html, edges = _render(tmp_path, 20, 1)
    assert edges <= ARROW_DEFER_EDGE_THRESHOLD
    assert "arrows: { to: { enabled: true, scaleFactor: 0.5 } }," in html
    assert "const _arrowOn" not in html


def test_dense_graph_defers_arrowheads_to_hover(tmp_path):
    html, edges = _render(tmp_path, 120, 25)
    assert edges > ARROW_DEFER_EDGE_THRESHOLD
    assert "arrows: { to: { enabled: false } }," in html
    assert "const _arrowOn" in html
    for ev in ("hoverEdge", "blurEdge", "hoverNode", "blurNode"):
        assert f"network.on('{ev}'" in html
    # The edge or node under the pointer still highlights. Hover stays on; what
    # stays off the hover path is the fan-out that gave every edge of a node its
    # arrowhead (that was the dense-cluster stall). Dimming is click-only.
    assert "hover: true" in html
    assert "network.on('hoverNode', function (p) { _hoverNode = p.node; });" in html
    assert "hoverWidth: 1" in html


def test_direction_survives_arrow_deferral(tmp_path):
    """Deferral must not touch stored direction: every edge keeps its from/to."""
    html, edges = _render(tmp_path, 120, 25)
    arcs = re.findall(r'"from": "([^"]+)", "to": "([^"]+)"', html)
    assert len(arcs) == edges
    assert len(set(arcs)) == edges


def test_dashes_and_confidence_survive(tmp_path):
    html, edges = _render(tmp_path, 120, 25)
    assert html.count('"dashes":') == edges


def test_layout_cache_emitted_for_every_graph(tmp_path):
    for n, k in ((20, 1), (120, 25)):
        html, _ = _render(tmp_path, n, k)
        assert "function _savePositions()" in html
        assert "graphify-pos:" in html
        assert "localStorage.setItem(POSK" in html


def test_stabilization_handler_is_valid_js(tmp_path):
    """`716c421e` shipped the handler as "…() => {\\n  network…", so the emitted page
    contained a literal backslash-n and the whole main <script> died on a parse error:
    no graph at all. The handler must carry no escape sequence."""
    html, _ = _render(tmp_path, 20, 1)
    assert "\\\\n" not in html
    assert ("network.once('stabilizationIterationsDone', () => { "
            "network.setOptions({ physics: { enabled: false } }); "
            "_savePositions(); });") in html


def test_offline_vis_fallback_present(tmp_path):
    """The CDN script must fall back to a sibling vis-network.min.js so a graph
    still renders offline when that file is dropped next to it (L1: blocking the
    CDN otherwise leaves a blank page - `vis is not defined`)."""
    html, _ = _render(tmp_path, 20, 1)
    assert "unpkg.com/vis-network@9.1.6" in html
    assert "vis-network.min.js" in html
    assert "onerror=" in html


# --- the node disc without the border stroke (#perf L22) ---------------------
# vis draws a node as a fill plus a border stroke whose world width is
# min(nodeWidth, 1.5/scale); on rsl those 1886 hairline strokes are the single biggest
# cost of a resting frame (86 ms with them, 29 ms without). The border colour is the
# fill colour, so the same disc is drawn with one fill and a size grown by exactly the
# width the border would have added. Hovered and selected nodes keep a real border,
# because theirs is white.

def test_node_disc_is_drawn_without_the_border_stroke(tmp_path):
    """vis's border is min(nodeWidth, 1.5/scale) world units. While that is capped at the
    node's own width the disc is exactly twice the fill radius, so one fill reproduces it;
    once the zoom makes the border thinner than the node, vis's own border is used. The
    switch is a MODE change, applied once per node per crossing - not a size recomputed on
    every zoom frame, which rewrote 1886 sizes per frame and made the dots shimmer."""
    html, _ = _render(tmp_path, 900, 3)
    assert "if (_BORDER_FULL / (scale || 1) < base) {" in html
    assert "size = base * 2; bw = 0;" in html
    assert "size = base; bw = _BORDER_FULL;" in html
    assert "if (!force && n.__nbSize === size && n.__nbBw === bw && n.baseSize === size) return;" in html
    assert "n.options.size = size;" in html
    assert "n.options.borderWidth = bw;" in html


def test_hovered_and_selected_nodes_keep_their_white_border(tmp_path):
    """The border of a hovered or selected node is white and therefore visible: it must
    not be dropped with the rest."""
    html, _ = _render(tmp_path, 900, 3)
    assert "if (_nbHover[id] || _nbSel[id]) {" in html
    assert "size = base; bw = _BORDER_FULL;" in html
    for ev in ("hoverNode", "blurNode", "selectNode", "deselectNode"):
        assert "network.on('%s'" % ev in html


def test_node_disc_follows_the_zoom_but_not_the_solver(tmp_path):
    """The border it replaces was a screen-constant width, so the size follows the scale.
    The solver must still see the sizes the exporter shipped, or the layout would differ
    from the unbaked picture."""
    html, _ = _render(tmp_path, 900, 3)
    assert "network.on('beforeDrawing', function () {" in html
    assert "if (network.physics && network.physics.options.enabled) return;" in html
    assert "network.on('stabilizationIterationsDone', function () { _nbApply(true); _nbLock = true; });" in html
    assert "if (!_nbLock) { _nbApply(false); _nbLock = true; }" in html
    # A drag updates the DataSet, and vis setValueRange then writes the constructed
    # radius back onto every node. The paint puts the resting disc back; it does
    # not recompute the size from the scale.
    assert "function _nbRestore()" in html
    assert "n.baseSize = n.__nbRestSize;" in html


def test_gestures_do_not_resize_the_disc(tmp_path):
    """The lean used to shrink the disc for the length of a gesture because the small
    discs raster faster. That is exactly what made the nodes visibly shrink every time
    the graph moved or zoomed, so the size is now the same in a gesture as at rest; the
    lean only suppresses the hover paint."""
    html, _ = _render(tmp_path, 900, 3)
    block = html.split("function _nbApplyNode")[1].split("function _nbApply")[0]
    assert "_lean" not in block
    assert "size = base * 2; bw = 0;" in block


def test_dense_graph_has_no_gesture_lean_left(tmp_path):
    """There is nothing to lean any more: the disc is drawn with one fill in every state
    (L22/L30) and the hover dim is gone (L32). The lean's timer used to fire a FULL extra
    redraw plus a forced rewrite of all 1886 nodes after every zoom step - twelve extra
    complete frames per wheel gesture, which is what made a dense zoom feel clumsy."""
    html, _ = _render(tmp_path, 900, 3)
    assert "function _setLean(on, redraw)" not in html
    assert "_setLean(" not in html
    assert "_zoomTimer" not in html
    assert "_draggingNow" not in html
    # the disc is still drawn without a border stroke
    assert "_BORDER_FULL = 1.5" in html
    assert "size = base * 2; bw = 0;" in html


def test_node_sizes_are_written_on_the_instances_not_global_setoptions(tmp_path):
    """network.setOptions re-applies the global borderWidth but also costs a full
    synchronous redraw (~200ms on a 2290-node aggregate, 670ms+ at 9142 nodes). The shipped
    path mutates the node instances instead."""
    html, _ = _render(tmp_path, 900, 3)
    assert "n.options.size = size;" in html
    assert "n.options.borderWidth = bw;" in html
    # the node instances are written directly, never through a global setOptions
    assert "network.setOptions({ nodes: { borderWidth" not in html


def test_zoom_has_no_restore_timer(tmp_path):
    """The zoom used to leave a 180 ms timer behind that restored the lean, and that
    timer fired a full extra redraw. Nothing needs restoring any more."""
    html, _ = _render(tmp_path, 900, 3)
    assert "_zoomTimer" not in html
    assert "setTimeout(function () { if (!raf) lean(false, true); }, 90);" not in html


def _without_js_comments(html: str) -> str:
    """Comment lines aside, so an assertion about emitted options is not satisfied or
    broken by prose that merely names them."""
    return "\n".join(ln for ln in html.splitlines() if not ln.lstrip().startswith("//"))


def test_edges_stay_visible_during_gestures(tmp_path):
    """Edges must never vanish while panning or zooming (user-visible regression from
    hideEdgesOnDrag/hideEdgesOnZoom): the graph has to look the same in motion as at
    rest. Smoothness comes from drawing them cheaper, never from not drawing them."""
    for n, k in ((20, 1), (900, 3)):
        html, _ = _render(tmp_path, n, k)
        code = _without_js_comments(html)
        assert "hideEdgesOnDrag" not in code
        assert "hideEdgesOnZoom" not in code


# --- batched edge pass (#perf) ------------------------------------------------
# One ctx.stroke() per edge per frame was ~30ms of an rsl frame and the reason a drag
# with the edges visible stayed at ~21fps. vis resolves what to draw while it draws it,
# so per-edge option writes change nothing on screen; the only lever is to take over
# edgeType.drawLine for the gesture and stroke each (colour, dash, width) group once.

def test_dense_graph_batches_the_edge_pass(tmp_path):
    html, _ = _render(tmp_path, 900, 3)
    assert "const _EDGE_BATCH = (function ()" in html
    # the pass replaces drawLine per edge and strokes once per group
    assert "et.drawLine = function (ctx, values, sel, hov, via)" in html
    assert "if (_drawn) return;" in html
    assert "g.strokeStyle = grp.col;" in html
    assert "g.beginPath();" in html
    assert "_groups.push(grp)" in html


def test_edge_batch_groups_by_colour_and_width_and_leaves_dashes_to_vis(tmp_path):
    """Grouping by anything less than what vis varies per edge would silently repaint
    edges: a single-colour batch measured x1.2 faster but dumped every edge in one
    colour. Dashed edges are excluded from the batch instead of grouped - confidence
    texture has to come out exactly as vis draws it."""
    html, _ = _render(tmp_path, 900, 3)
    assert "const key = col + '|' + baseW;" in html
    # resolved exactly the way the draw path resolves them
    assert "col = e.edgeType.getColor(_ctx, t);" in html
    assert "t = e.getFormattingValues();" in html
    assert "if (_dashOf(t)) { e.edgeType.__leanDash = true; continue; }" in html
    assert "this.__leanDash" in html
    # the pattern itself is still recognised as the one vis uses
    assert "return d === true ? [5, 5] : d;" in html


def test_edge_batch_reads_live_endpoints_each_frame(tmp_path):
    """edgeType.fromPoint IS the node object, so the batch must read it per frame. A
    batch built once at dragStart would freeze the endpoints and break exactly the node
    drag it is supposed to help."""
    html, _ = _render(tmp_path, 900, 3)
    assert "g.moveTo(et.fromPoint.x, et.fromPoint.y);" in html
    assert "g.lineTo(et.toPoint.x, et.toPoint.y);" in html
    # no cached coordinate array
    assert not re.search(r"pts\.push\(", html)


def test_edge_batch_width_is_rederived_per_frame(tmp_path):
    """vis draws edges at max(width, 0.3/scale) and the floor moves with the zoom, so the
    width cannot be baked in at gesture start."""
    html, _ = _render(tmp_path, 900, 3)
    assert "const floor = 0.3 / _scale();" in html
    assert "g.lineWidth = Math.max(grp.baseW, floor);" in html


def test_edge_batch_drops_curves_that_miss_the_screen(tmp_path):
    """Zoomed in, one path per colour covers the whole graph and the rasterizer walks
    every off-screen curve. Edges whose control-point box misses the canvas are left
    out, and once most edges miss, the ones that remain are stroked one each so a miss
    is a small path. The fit view still batches, because there almost every edge hits."""
    html, _ = _render(tmp_path, 900, 3)
    assert "function _onScreen(et, m, pad, w, h) {" in html
    assert "const perEdge = total > 0 && shown * 2 < total;" in html
    assert "if (!canCull || _onScreen(et, m, pad, w, h)) { mask[j] = 1; shown++; }" in html


def test_edge_batch_draws_the_resting_curve(tmp_path):
    """Straight lines are cheaper but they are a visibly different graph in motion: the
    frame-by-frame pixel diff against the resting frame changed 82-100% of painted pixels
    with straight lines and 1.1-1.8% with the curve vis actually draws."""
    html, _ = _render(tmp_path, 900, 3)
    assert "function _curveTo(g, et) {" in html
    assert "_curveTo(g, et);" in html
    assert "g.quadraticCurveTo(vx, vy, et.toPoint.x, et.toPoint.y);" in html
    # anything that is not a continuous smooth edge is still a straight line
    assert ("if (!o || o.enabled === false || o.type !== 'continuous') "
            "{ g.lineTo(et.toPoint.x, et.toPoint.y); return; }") in html
    # the via point is vis's own arithmetic: roundness * dominant extent, signed toward
    # `to`, then clamped into the segment's box
    assert "let a = (C <= I) ? e * I : e * C;" in html
    assert "if (C <= I) vx = (fx <= tx) ? (tx < vx ? tx : vx) : (tx > vx ? tx : vx);" in html


def test_edge_batch_uninstalls_and_always_has_a_fallback(tmp_path):
    """The patch can be undone, and the batch is reset per frame via vis's own
    afterDrawing event."""
    html, _ = _render(tmp_path, 900, 3)
    assert "delete et.drawLine;" in html
    assert "delete et.__leanBatch;" in html
    assert "network.on('afterDrawing', function () { _EDGE_BATCH.frame(); });" in html
    # a throwing batch falls back to vis's own draw instead of a blank canvas
    assert "if (_errors > 2) { _uninstall(); }" in html
    assert "orig.call(this, ctx, values, sel, hov, via);" in html
    # the batch is installed at rest, so nothing has to drive it per gesture
    assert "_EDGE_BATCH.set(on);" not in html
    assert "_EDGE_BATCH.setRest(_REST_EDGE_BATCH);" in html


def test_dense_graph_keeps_the_edge_batch_at_rest(tmp_path):
    """L12: on a dense graph (arrowheads deferred) the batched pass is installed for the
    whole session, and the gesture flag cannot uninstall it."""
    html, _ = _render(tmp_path, 900, 3)
    assert "const _REST_EDGE_BATCH = true;" in html
    assert "_EDGE_BATCH.setRest(_REST_EDGE_BATCH);" in html
    assert "if (_rest) return;" in html
    # a data change (legend toggle, arrow reveal, theme) invalidates the cached groups
    assert "nodesDS.on('*', function () { _EDGE_BATCH.dirty(); });" in html
    assert "edgesDS.on('*', function () { _EDGE_BATCH.dirty(); });" in html
    assert "if (_dirty && _installed) { _dirty = false; _build(); _patch(); }" in html


def test_rest_batch_hands_selected_and_arrowed_edges_back_to_vis(tmp_path):
    """Capability guard: the batch draws a plain line, so anything that needs a highlight
    or an arrowhead must go through vis's own drawLine."""
    html, _ = _render(tmp_path, 900, 3)
    assert "if (sel || hov || this.__leanDash || _arrowed(this)) { orig.call(this, ctx, values, sel, hov, via); return; }" in html
    assert "function _arrowed(et) {" in html
    assert "a.to && a.to.enabled === true" in html
    # dashed edges (confidence) are not batched either: vis draws them, exactly as at rest
    assert "if (_dashOf(t)) { e.edgeType.__leanDash = true; continue; }" in html
    # and re-applied after vis replaces an edgeType on a data change
    assert "et.__leanBatch = orig;" in html
    assert "_patch();" in html


def test_rest_batch_skips_edges_of_hidden_nodes(tmp_path):
    """vis draws an edge only when the edge and both endpoints are visible. Legend
    filtering hides nodes, so the cached batch has to apply the same rule or it keeps
    drawing the orphan edges of a filtered community."""
    html, _ = _render(tmp_path, 900, 3)
    assert "e.from && e.from.options" in html
    assert "(e.options && e.options.hidden) || (fo && fo.hidden) || (to && to.hidden)" in html


def test_big_sparse_graph_keeps_vis_drawing_edges_at_rest(tmp_path):
    """A big-but-sparse graph shows arrowheads at rest, so the batch cannot draw its edges
    and the rest install stays off (the gesture batch still exists)."""
    html, edges = _render(tmp_path, LEAN_GESTURE_NODE_THRESHOLD + 100, 1)
    assert edges < ARROW_DEFER_EDGE_THRESHOLD
    assert "const _REST_EDGE_BATCH = false;" in html
    assert "const _EDGE_BATCH = (function ()" in html


def test_big_sparse_graph_gets_no_arrow_deferral(tmp_path):
    """A big-but-sparse graph keeps the eager arrowheads (and gets the disc treatment,
    which is size-gated, not edge-gated)."""
    html, edges = _render(tmp_path, LEAN_GESTURE_NODE_THRESHOLD + 100, 1)
    assert edges <= ARROW_DEFER_EDGE_THRESHOLD
    assert "arrows: { to: { enabled: true, scaleFactor: 0.5 } }," in html
    assert "const _arrowOn" not in html
    assert "size = base * 2; bw = 0;" in html


def test_sparse_small_graph_gets_none_of_the_gesture_levers(tmp_path):
    """Byte-level promise: a small graph is untouched by any of this."""
    html, _ = _render(tmp_path, 20, 1)
    for marker in ("function _setLean(on, redraw)", "hideEdgesOnZoom", "const _arrowOn",
                   "const _EDGE_BATCH", "_syncArrows", "dragStart"):
        assert marker not in html
    assert "nodes: { shape: 'dot', borderWidth: 1.5 }," in html


# --- interaction feel (#perf L13) ---------------------------------------------
# The reported "zoom freezes the graph and the colours go dim" came from two separate
# bugs in a prototype: per-event wheel zoom (24 long tasks / 2369ms over one battery)
# and a click-to-focus that set node opacity and never put it back (1858 nodes left
# dimmed after a single click). Both are shipped here as: an eased cursor-anchored
# zoom that redraws once per frame, and a hover-only focus that always restores.

def test_selection_keeps_the_community_colour(tmp_path):
    """A selected or hovered node must keep its community colour and gain a white
    ring instead. The old highlight repainted the fill #ffffff, so clicking a dense
    cluster washed it out."""
    html, _ = _render(tmp_path, 120, 25)
    assert '"background": "#ffffff"' not in html
    pairs = re.findall(
        r'"color": \{"background": "(#[0-9A-Fa-f]{6})", "border": "#[0-9A-Fa-f]{6}", '
        r'"highlight": \{"background": "(#[0-9A-Fa-f]{6})", "border": "#ffffff"\}, '
        r'"hover": \{"background": "(#[0-9A-Fa-f]{6})", "border": "#ffffff"\}\}',
        html,
    )
    assert pairs, "no node emitted the new highlight/hover colour dict"
    for bg, hi_bg, hov_bg in pairs:
        assert hi_bg == bg
        assert hov_bg == bg


def test_large_graph_gets_the_frame_coalesced_zoom(tmp_path):
    """vis zooms once per wheel event, so a trackpad fires a full redraw dozens of times a
    frame. The shipped path accumulates a target scale and applies it one per animation
    frame, holding the world point under the cursor fixed. It used to EASE toward the
    target over ~40 ms, which read as lag next to vis's instant jump, so it lands on the
    target in the frame it is applied."""
    html, _ = _render(tmp_path, 900, 3)
    assert "targetScale = Math.max(MIN_S, Math.min(MAX_S, targetScale * Math.exp(-e.deltaY * unit)));" in html
    assert "raf = requestAnimationFrame(zoomStep);" in html
    assert "var next = targetScale;" in html
    assert "network.moveTo({" in html
    # vis's own wheel handler must never also see the event, or every delta redraws
    assert "{ passive: false, capture: true }" in html
    assert "e.stopPropagation();" in html
    # the anchor is the cursor, converted to world space before the scale changes
    assert "var wp = network.DOMtoCanvas({ x: anchor.x, y: anchor.y });" in html


def test_hover_never_dims_anything(tmp_path):
    """Hover must leave the picture whole: the user does not want the graph to dim while
    the pointer moves, and during a zoom nodes slide under the cursor - every hover event
    used to repaint the whole graph. Dimming is the click focus's job."""
    html, _ = _render(tmp_path, 900, 3)
    block = _ux_block(html)
    assert "scheduleHover" not in block
    assert "flushHover" not in block
    assert "network.on('hoverNode', function (p) { scheduleHover" not in block
    # the click focus is still there, and still a delta paint on the instances
    assert "function setClick(id)" in block
    assert "function clearClick()" in block
    assert "nc.background = o.bg; nc.border = o.bd;" in block
    assert "nc.background = d; nc.border = d;" in block
    assert "nodesDS.update" not in html.split("// ---- 2. click focus")[1].split("// ---- 3.")[0]


def _ux_block(html: str) -> str:
    """Just the L13 interaction block, so a marker that the base template already
    ships (the info-panel click handler, the cursor hoverNode) cannot satisfy an
    assertion about this block."""
    start = html.index("interaction feel (#perf L13)")
    return html[start:html.index("</script>", start)]


def test_every_community_gets_a_row_in_the_families_panel(tmp_path):
    """The panel used to be built from the community *labels*, so a graph without labels
    got an empty list and there was no way to filter by family at all."""
    html, _ = _render(tmp_path, 120, 25)
    m = re.search(r"const LEGEND = (\[.*?\]);", html, re.S)
    assert m, "the page must carry the family list"
    legend = m.group(1)
    assert legend.count('"cid"') == 5, legend[:200]
    assert '"count"' in legend and '"label"' in legend
    # a family without a label is named after the file most of its members come from
    assert '"colourIndex"' in legend


def test_families_panel_filters_and_isolates(tmp_path):
    """The user asked for filtering by family and by colour; the panel is the answer."""
    html, _ = _render(tmp_path, 900, 3)
    assert 'id="family-filter"' in html
    assert 'id="colour-strip"' in html
    assert "function isolateCommunity(cid)" in html
    assert "function showColour(index)" in html
    assert "function visibleFamilies()" in html
    assert "familyFilterEl.addEventListener('input', renderFamilies);" in html
    # a bulk change is spread over frames instead of blocking the main thread once
    assert "const perFrame = Math.max(1, Math.ceil(changed.length / 4));" in html
    assert "requestAnimationFrame(step);" in html


def test_filter_only_updates_the_families_that_changed(tmp_path):
    """A DataSet update for 1886 nodes measured 149.6 ms, and 'show all' used to pay it
    even when nothing was hidden."""
    html, _ = _render(tmp_path, 900, 3)
    assert "function applyHidden(next)" in html
    assert "for (const cid of next) if (!appliedHidden.has(cid)) changed.push(cid);" in html
    assert "if (!changed.length)" in html


def test_community_colouring_is_the_shipped_one(tmp_path):
    """Palette index = community id modulo the palette size, exactly what the shipped
    viewer does. An adjacency-aware greedy colouring was tried and reverted: it hands
    every non-adjacent community the lowest free index, so whole regions collapse onto
    one colour and the picture loses the variety the families are read by. The
    classification is part of the look, not a perf lever."""
    html, _ = _render(tmp_path, 120, 25)
    m = re.search(r"const COMMUNITY_COLOUR = (\{.*?\});", html, re.S)
    assert m, "the page must carry the community -> palette index map"
    mapping = m.group(1)
    for cid in range(5):
        assert f'"{cid}": {cid % 10}' in mapping, mapping
    assert "_community_color_map" not in html


def test_community_palette_is_the_same_in_both_themes(tmp_path):
    """A darkened light-theme palette was tried and rejected: on white the original
    colours are the ones that look right (the user's call). What differs per theme is the
    edge colour, the selection ring and the dimming amount, not the nodes."""
    from graphify.exporters.base import COMMUNITY_COLORS

    html, _ = _render(tmp_path, 900, 3)
    for c in COMMUNITY_COLORS:
        assert '"%s"' % c in html
    assert "const PALETTE = [" in html
    assert "PAL_LIGHT" not in html
    # the per-theme values are still there
    assert "--dim: 0.55" in html and "--dim: 0.42" in html
    assert "--node-ring: #ffffff" in html and "--node-ring: #1f2430" in html
    assert "--edge-opacity: 0.7" in html and "--edge-opacity: 0.92" in html


def test_theme_switch_recolours_the_instances_not_the_dataset(tmp_path):
    """A theme switch has to feel instant: one DataSet update for 1886 nodes measured
    149.6 ms, so the colours are written onto the instances and the batch is told to
    rebuild its groups."""
    html, _ = _render(tmp_path, 900, 3)
    assert "function retint()" in html
    assert "c.background = col;" in html
    assert "c.highlight.border = tk.ring;" in html
    assert "e.options.color = { color: tk.edge, opacity:" in html
    assert "_EDGE_BATCH.dirty()" in html
    # the legend swatches and the search / neighbour colours follow the palette
    assert "palColor(c.cid)" in html
    assert "palColor(nb.community)" in html
    assert "palColor(n.community)" in html
    # a data change (the legend filter) must not put the dark palette back
    assert "nodesDS.on('*', function () { retint(); });" in html


def test_dimming_follows_the_theme(tmp_path):
    """55% toward the background buries a node on white and leaves it loud on black, so
    the blend amount is a theme value."""
    html, _ = _render(tmp_path, 900, 3)
    assert "function dimAmount()" in html
    assert "getPropertyValue('--dim')" in html
    assert "d = mix(hex, dimAmount());" in html
    # and the focus block re-captures its base colours when the theme moves them
    assert "document.addEventListener('graphify-theme', function () {" in html
    assert "captureBase();" in html


def test_click_focus_dims_what_is_not_connected(tmp_path):
    """L24: the user asked for it explicitly - click a node and the nodes that are not
    connected to it dim down, and they stay that way until you click away. The focus set
    is the node plus its 1-hop neighbours, the same set the hover focus uses."""
    html, _ = _render(tmp_path, 900, 3)
    block = _ux_block(html)
    assert "network.on('click', function (p) {" in block
    assert "setClick(p.nodes[0]);" in block
    assert "else clearClick();" in block
    assert "function neighbourhood(id)" in block
    assert "network.getConnectedNodes(id)" in block
    # Escape and a second click on the same node clear it
    assert "if (e.key === 'Escape') clearClick();" in block
    assert "if (clickOn && clickNode === id) { clearClick(); return; }" in block
    # hover does not compete with it any more: nothing on hover repaints
    assert "scheduleHover" not in block


def test_click_focus_never_uses_opacity(tmp_path):
    """The dim is a colour blend on the node instances, never `opacity` (vis ignores
    opacity on the draw) and never a DataSet update (1886 nodes measured 149.6 ms)."""
    html, _ = _render(tmp_path, 900, 3)
    block = _ux_block(html)
    assert "opacity" not in block
    assert "nodesDS.update" not in block
    assert "nc.background = d; nc.border = d;" in block


def test_zoom_is_clamped_around_the_fit(tmp_path):
    """Unbounded wheel zoom let labels grow without limit; the range is derived after
    the fit on first use, because a baked build fits after this script runs."""
    html, _ = _render(tmp_path, 900, 3)
    assert "MIN_S = Math.max(0.004, fitScale / 6);" in html
    # vis's own wheel handler clamps to [1e-5, 10]; the old fit*12 ceiling was ~1.0 on
    # rsl, a tenth of what the shipped viewer allows
    assert "MAX_S = 10;" in html
    assert "if (fitScale === null) {" in html


def test_hud_loop_only_runs_while_the_hud_is_on(tmp_path):
    """The HUD's rAF loop used to run for the life of the page even with the HUD hidden:
    0 draws but 432 rAF wake-ups in 3 s of silence (probe_idle.mjs). A reading page must be
    quiet, so the loop starts on H and stops on H."""
    html, _ = _render(tmp_path, 900, 3)
    block = _ux_block(html)
    assert "if (!hudOn) { loopId = 0; return; }" in block
    assert "if (!loopId) loopId = requestAnimationFrame(loop);" in block
    assert "cancelAnimationFrame(loopId); loopId = 0;" in block
    # the infinite form is gone
    assert "  requestAnimationFrame(loop);\n  })(t0);" not in block
    assert "(function loop(t) {" not in block


def test_interaction_block_is_absent_on_small_graphs(tmp_path):
    """A small graph stays byte-identical: no eased zoom, no hover focus, no HUD."""
    html, _ = _render(tmp_path, 20, 1)
    assert "interaction feel (#perf L13)" not in html
    for marker in ("zoomStep", "dimOf", "fitScale", "targetScale"):
        assert marker not in html


def test_dense_arrow_reveal_never_touches_the_dataset(tmp_path):
    """The reveal used to run one batched edgesDS.update() per hover. Even batched, that
    makes vis recompute _updateVisibleIndices + _updateValueRange over all nodes and all
    edges AND invalidates the batched edge pass, which then re-reads the formatting values
    of all 3876 edges: a 100-200 ms stall on a hover in a dense cluster. The arrow flag is
    written onto the edge instance instead, and the batch skips arrowed edges at draw
    time."""
    html, _ = _render(tmp_path, 900, 3)
    assert "function _syncArrows()" in html
    assert "function _setArrow(id, on)" in html
    assert "e.options.arrows.to.enabled = on;" in html
    assert "edgesDS.update" not in html.split("const _arrowOn")[1].split("network.on('hoverNode'")[0]
    assert "if (_arrowed(et)) continue;" in html
    # suppressed while dragging, resynced once on release
    assert "if (!_dragging) _syncArrows();" in html

def test_desync_canvas_patch_is_emitted(tmp_path):
    """L37: the graph canvas must be created with desynchronized: true."""
    html, _ = _render(tmp_path, 20, 1)
    assert "HTMLCanvasElement.prototype.getContext" in html
    assert "desynchronized: true" in html
    patch_idx = html.find("HTMLCanvasElement.prototype.getContext")
    vis_idx = html.find("unpkg.com/vis-network")
    assert patch_idx != -1 and vis_idx != -1 and patch_idx < vis_idx
    html2, _ = _render(tmp_path, 900, 3)
    assert "desynchronized: true" in html2