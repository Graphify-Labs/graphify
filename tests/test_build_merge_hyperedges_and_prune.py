from graphify.build import build_from_extraction, build_merge
def test_unchanged_hyperedges_are_carried_forward(tmp_path):
    path = tmp_path / "graph.helix"
    initial = build_from_extraction({
        "nodes": [{"id": "a", "source_file": "a.py"}, {"id": "b", "source_file": "b.py"}],
        "edges": [],
        "hyperedges": [{"id": "flow", "nodes": ["b"], "source_file": "b.py"}],
    })
    merged = build_merge(
        [{"nodes": [{"id": "a", "source_file": "a.py"}], "edges": []}],
        graph_path=path,
        base_graph=initial,
        dedup=False,
    )
    assert merged.attributes["hyperedges"][0]["id"] == "flow"
