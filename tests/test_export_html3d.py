"""Tests for the 3D (WebGL) graph renderer behind `--viz 3d`."""
import hashlib
import json
import re
import tempfile
from pathlib import Path

import networkx as nx
import pytest

from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_html
from graphify.exporters.html import VIZ_MODES, _resolve_viz_mode
from graphify.exporters.html3d import (
    FORCE_GRAPH_ASSET_SHA384,
    FORCE_GRAPH_VERSION,
    _SCRIPT_3D,
    _force_graph_source,
)

FIXTURES = Path(__file__).parent / "fixtures"


def make_graph():
    return build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))


def render(mode=None, **kwargs):
    G = kwargs.pop("G", None) or make_graph()
    communities = kwargs.pop("communities", None) or cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), mode=mode, **kwargs)
        return out.read_text(encoding="utf-8")


def test_viz_3d_embeds_a_pinned_force_graph_bundle_for_offline_use():
    """The exported page must not need a CDN or network access."""
    content = render("3d")
    assert f"Version {FORCE_GRAPH_VERSION} 3d-force-graph" in content
    assert "https://unpkg.com/3d-force-graph@" not in content
    assert "<script src=" not in content
    assert "ForceGraph3D" in content


def test_vendored_force_graph_bundle_matches_the_reviewed_release():
    source = _force_graph_source()
    assert len(source) > 1_000_000
    assert hashlib.sha384(source.encode()).hexdigest() == FORCE_GRAPH_ASSET_SHA384


def test_viz_3d_does_not_pull_in_visjs():
    content = render("3d")
    assert "vis-network" not in content
    assert "ForceGraph3D(" in content


def test_default_mode_is_unchanged_2d():
    """Adding the 3D renderer must not change what existing callers get."""
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        default_out, explicit_out = Path(tmp) / "a.html", Path(tmp) / "b.html"
        to_html(G, communities, str(default_out))
        to_html(G, communities, str(explicit_out), mode="2d")
        # The output path is echoed in the <title>, so normalize it out.
        default = default_out.read_text(encoding="utf-8").replace("a.html", "X.html")
        explicit = explicit_out.read_text(encoding="utf-8").replace("b.html", "X.html")
    assert "vis-network" in default
    assert "3d-force-graph" not in default
    assert default == explicit


def test_viz_3d_carries_the_same_node_and_edge_data():
    content = render("3d")
    assert "RAW_NODES" in content
    assert "RAW_EDGES" in content
    assert "LEGEND" in content
    # The placeholders in the script template must all have been substituted.
    assert "/*__NODES__*/null" not in content
    assert "/*__EDGES__*/null" not in content
    assert "/*__LEGEND__*/null" not in content
    assert "/*__HYPEREDGES__*/null" not in content


def test_viz_3d_neighbor_links_have_no_inline_onclick_xss():
    """#1838 applies to the 3D panel too: a node id containing a double quote
    must not be able to break out of an inline handler. Same escaped data
    attribute + single delegated listener as the 2D renderer."""
    content = render("3d")
    assert 'onclick="selectNode(' not in content
    assert 'onclick="focusNode(' not in content
    assert 'data-nid="${esc(nid)}"' in content
    assert "closest('.neighbor-link')" in content


def test_viz_3d_exposes_navigation_controls():
    content = render("3d")
    for control in ("btn-reset", "btn-freeze", "focus-depth", "cb-labels"):
        assert f'id="{control}"' in content, control
    # k-hop focus and the keyboard shortcuts are what make it navigable.
    assert "recomputeFocus" in content
    assert "graph2ScreenCoords" in content


def test_viz_3d_focus_is_a_single_control():
    """A Focus on/off button plus a separate depth dropdown read as two settings
    with an unexplained relationship. The depth select *is* the switch: 0 shows
    the whole graph, anything higher isolates that many hops."""
    content = render("3d")
    assert 'id="btn-focus"' not in content
    assert '<option value="0" selected>whole graph</option>' in content
    for depth in range(1, 7):
        assert f'<option value="{depth}">selection + {depth} hop' in content, depth
    assert "let focusDepth = 0" in content
    assert "if (focusDepth < 1 || selectedId === null) return;" in content


def test_viz_3d_legend_shortcuts_survive_the_removed_focus_button():
    """F and L act on the community under the cursor: F isolates it, L isolates
    it and names it. A focused <select> swallows letter keys as native option
    typeahead, which silently ate the shortcut and stepped the depth dropdown
    instead, so it is suppressed and the select blurs after use."""
    content = render("3d")
    assert "hoveredCommunity = c.cid" in content
    assert "if (hoveredCommunity !== null) isolateCommunity(hoveredCommunity);" in content
    assert "if (hoveredCommunity !== null) setLabels(isolateCommunity(hoveredCommunity));" in content
    # Typeahead suppression + blur, the two halves of the swallowed-key fix.
    assert "e.target instanceof HTMLSelectElement) e.preventDefault();" in content
    assert "depthSel.blur();" in content
    # Isolating is a toggle, and it drives the checkbox UI rather than only the set.
    assert "function isCommunityIsolated(cid)" in content
    assert "function setCommunityHidden(cid, hidden)" in content


def test_viz_3d_names_are_off_by_default():
    """Names are opt-in — 1500 sprites in a rotating volume is noise. The hover
    tooltip must still name the node whether or not the overlay is on."""
    content = render("3d")
    assert "let showLabels = false;" in content
    assert '<input type="checkbox" class="view-cb" id="cb-labels">' in content
    assert 'id="cb-labels" checked' not in content
    # nodeLabel drives the hover tooltip and is never gated on showLabels.
    assert ".nodeLabel(n => '<div class=\"gtip\">' + n.tip + '</div>')" in content


def test_viz_3d_does_not_double_escape_tooltips():
    G = nx.Graph()
    G.add_node("a", label="A & B < C", file_type="py")
    content = render("3d", G=G, communities={0: ["a"]})
    assert '"title": "A &amp; B &lt; C"' in content
    assert "String(n.title || n.label).split('\\n').join('<br>')" in content
    assert "String(n.title || n.label).split('\\n').map(esc)" not in content


def test_viz_3d_does_not_animate_hidden_labels():
    content = render("3d")
    assert "let labelFrame = null;" in content
    assert "labelFrame = requestAnimationFrame(drawLabels);" in content
    assert "cancelAnimationFrame(labelFrame);" in content
    assert "\nrequestAnimationFrame(drawLabels);\n" not in content


def test_viz_3d_explains_how_to_recover_when_webgl_is_unavailable():
    content = render("3d")
    assert "function supportsWebGL()" in content
    assert 'id="webgl-error"' in content
    assert "graphify export html --viz 2d" in content
    assert "if (!supportsWebGL())" in content


def test_viz_3d_starts_pre_expanded_and_bounded():
    """The stock d3-force-3d setup erupts from a point over ~10s and lets
    disconnected components coast outward forever. Warmup ticks move the
    simulation before the first frame; the gravity force and the capped
    repulsion range keep the result compact."""
    content = render("3d")
    assert ".warmupTicks(WARMUP_TICKS)" in content
    assert "gravityForce" in content
    assert "charge.distanceMax(CHARGE_MAX_DISTANCE)" in content


def test_viz_3d_layout_constants_stay_in_their_working_range():
    """These four numbers were tuned against a 1.6k-node graph in a browser, and
    each has a failure mode outside its range: gravity above ~0.08 packs the
    graph into a featureless ball, and a repulsion cap far past the graph radius
    makes the warmup ticks expensive enough to freeze the tab on load."""
    content = render("3d")
    values = {}
    for name in (
        "GRAVITY_STRENGTH",
        "CHARGE_MAX_DISTANCE",
        "CHARGE_STRENGTH",
        "WARMUP_TICKS",
    ):
        match = re.search(rf"const {name} = (-?[\d.]+);", content)
        assert match is not None
        values[name] = float(match.group(1))
    assert 0 < values["GRAVITY_STRENGTH"] <= 0.08
    assert 200 <= values["CHARGE_MAX_DISTANCE"] <= 450
    assert values["CHARGE_STRENGTH"] < 0
    assert 0 < values["WARMUP_TICKS"] <= 200


def test_viz_3d_frames_once_at_startup_without_zoom_to_fit():
    """The camera must be placed once, early, and then left alone. zoomToFit()
    animates even when asked for a zero-duration transition, so using it here
    reads as the view drifting or lurching out from under the user; and framing
    off a timer runs before the warmup ticks land, measuring a radius of zero
    and parking the camera inside the graph."""
    content = render("3d")
    calls = [ln for ln in _SCRIPT_3D.splitlines()
             if "zoomToFit" in ln and not ln.strip().startswith("//")]
    assert not calls, calls
    # Framed from the first tick that has real positions, exactly once.
    assert "if (framed || layoutRadius() < 1) return;" in content
    assert "graph.onEngineTick(" in content
    # Placement is direct, with no transition.
    assert "graph.cameraPosition({ x: 0, y: 0, z: dist }, { x: 0, y: 0, z: 0 }, 0);" in content


def test_viz_3d_never_calls_refresh():
    """graph.refresh() snaps the camera back to its default, silently undoing
    every fly-to. Accessor re-assignment (restyle) is the supported way to make
    the renderer re-evaluate visibility and colour."""
    content = render("3d")
    calls = [ln for ln in content.splitlines()
             if "graph.refresh()" in ln and not ln.strip().startswith("//")]
    assert not calls, calls
    assert "function restyle()" in content


def test_viz_3d_hyperedges_become_a_star_expansion():
    """3D has no hull shading, so each hyperedge is rendered as a hub node
    linked to its members. The toggle only appears when there are any."""
    G = make_graph()
    members = list(G.nodes())[:3]
    G.graph["hyperedges"] = [{"id": "h1", "label": "shared pipeline", "nodes": members}]
    content = render("3d", G=G)
    assert '"shared pipeline"' in content
    assert "__hyperedge_" in content
    assert 'id="btn-hyper"' in content

    G.graph["hyperedges"] = []
    assert 'id="btn-hyper"' not in render("3d", G=G)


def test_viz_3d_survives_a_node_id_with_quotes_and_script_tags():
    G = nx.Graph()
    G.add_node('a"b', label='</script><img src=x onerror=alert(1)>', file_type="py")
    G.add_node("c", label="plain", file_type="py")
    G.add_edge('a"b', "c", relation="calls", confidence="EXTRACTED")
    content = render("3d", G=G, communities={0: ['a"b', "c"]})
    # The embedded JSON must not be able to close the script tag early.
    assert "</script><img" not in content
    assert "<\\/script>" in content


def test_over_limit_aggregation_keeps_the_requested_mode():
    """The community-aggregation fallback re-enters to_html; it must not drop
    back to the 2D renderer when the caller asked for 3D."""
    G = make_graph()
    communities = cluster(G)
    if len(communities) < 2:
        pytest.skip("fixture collapses to a single community")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), node_limit=1, mode="3d")
        content = out.read_text(encoding="utf-8")
    assert "3d-force-graph" in content
    assert "vis-network" not in content


@pytest.mark.parametrize("raw,expected", [
    (None, "2d"), ("", "2d"), ("2d", "2d"), ("3d", "3d"),
    ("3D", "3d"), (" 3d ", "3d"), ("webgl", "2d"), ("nonsense", "2d"),
])
def test_resolve_viz_mode(raw, expected):
    assert _resolve_viz_mode(raw) == expected


def test_viz_mode_env_var(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_VIZ_MODE", "3d")
    assert "3d-force-graph" in render()
    # An explicit argument still wins over the environment.
    assert "vis-network" in render("2d")
    monkeypatch.setenv("GRAPHIFY_VIZ_MODE", "bogus")
    assert "vis-network" in render()


def test_cli_viz_modes_match_the_exporter():
    """cli.py hardcodes the accepted values to keep networkx off the startup
    path; the two lists must not drift."""
    from graphify.cli import _VIZ_MODES
    assert tuple(_VIZ_MODES) == tuple(VIZ_MODES)
