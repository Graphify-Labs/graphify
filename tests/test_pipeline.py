from graphify.helix.persistence import load_graph
from graphify.watch import _rebuild_code


def test_code_pipeline_activates_helix_and_outputs(tmp_path):
    (tmp_path / "app.py").write_text("def main():\n    return 1\n")
    assert _rebuild_code(tmp_path, block_on_lock=True)
    store = tmp_path / "graphify-out" / "graph.helix"
    loaded = load_graph(store)
    assert loaded.graph.node_count >= 2
    assert (tmp_path / "graphify-out" / "GRAPH_REPORT.md").is_file()
    assert (tmp_path / "graphify-out" / "graph.html").is_file()
