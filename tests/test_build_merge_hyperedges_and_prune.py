from graphify.build import build_from_json, build_merge
from graphify.helix.persistence import HelixEmbeddedStore
from graphify.helix.state import new_state


def test_unchanged_hyperedges_are_carried_forward(tmp_path):
    path = tmp_path / "graph.helix"
    initial = build_from_json({
        "nodes": [{"id": "a", "source_file": "a.py"}, {"id": "b", "source_file": "b.py"}],
        "edges": [],
        "hyperedges": [{"id": "flow", "nodes": ["b"], "source_file": "b.py"}],
    })
    with HelixEmbeddedStore(path) as store:
        store.save_generation(initial, new_state())
    merged = build_merge(
        [{"nodes": [{"id": "a", "source_file": "a.py"}], "edges": []}],
        graph_path=path,
        dedup=False,
    )
    assert merged.attributes["hyperedges"][0]["id"] == "flow"
