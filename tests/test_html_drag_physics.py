"""graph.html re-enables physics while a node is dragged."""
import networkx as nx

from graphify.export import to_html


def _script(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="Alpha", source_file="a.py", file_type="code")
    G.add_node("b", label="Beta", source_file="b.py", file_type="code")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    out = tmp_path / "graph.html"
    to_html(G, {0: ["a", "b"]}, str(out), community_labels={0: "Core"})
    html = out.read_text(encoding="utf-8")
    start = html.index("network.once('stabilizationIterationsDone'")
    return html[start:html.index("function showInfo", start)]


def test_initial_layout_still_freezes_after_stabilization(tmp_path):
    js = _script(tmp_path)
    assert (
        "network.once('stabilizationIterationsDone', () => {\n"
        "  network.setOptions({ physics: { enabled: false } });\n"
        "});"
    ) in js


def test_node_drag_enables_physics_and_view_pan_does_not(tmp_path):
    js = _script(tmp_path)
    drag_start = js[js.index("network.on('dragStart'"):js.index("network.on('dragEnd'")]
    # dragStart also fires for view pans, with params.nodes empty.
    assert "if (!params.nodes.length) return;" in drag_start
    assert drag_start.index("return;") < drag_start.index("enabled: true")


def test_physics_turns_off_on_settle_unless_a_node_is_held(tmp_path):
    js = _script(tmp_path)
    assert "network.on('dragEnd', () => { draggingNode = false; });" in js
    assert (
        "network.on('stabilized', () => {\n"
        "  if (!draggingNode) network.setOptions({ physics: { enabled: false } });\n"
        "});"
    ) in js
