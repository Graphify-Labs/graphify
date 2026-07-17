from graphify.export import attach_hyperedges
from graphify.helix.model import GraphBuildData, NodeData
from graphify.helix.persistence import HelixEmbeddedStore
from graphify.helix.state import new_state


def test_hyperedges_persist_in_native_metadata(tmp_path):
    data = GraphBuildData(nodes=[NodeData("a"), NodeData("b")])
    attach_hyperedges(data, [{"id": "flow", "nodes": ["a", "b"], "relation": "sequence"}])
    attach_hyperedges(data, [{"id": "flow", "nodes": ["a"]}])
    path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(path) as store:
        store.save_generation(data, new_state())
    with HelixEmbeddedStore(path, read_only=True) as store:
        loaded = store.load()
    assert loaded.graph.attributes["graph"]["hyperedges"] == [
        {"id": "flow", "nodes": ["a", "b"], "relation": "sequence"}
    ]
