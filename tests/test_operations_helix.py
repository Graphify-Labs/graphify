from graphify import operations
from graphify.helix.persistence import load_graph
from graphify.helix.state import community_records, new_state
from tests.native_helpers import make_loaded


def test_recluster_updates_state_without_rewriting_topology(tmp_path, monkeypatch):
    state = new_state(
        communities=community_records({0: ["a", "b"]}, labels={0: "Existing"})
    )
    loaded = make_loaded(
        tmp_path,
        nodes=[{"id": "a"}, {"id": "b"}],
        edges=[{"source": "a", "target": "b", "relation": "calls"}],
        state=state,
    )
    generation = loaded.generation
    edge_id = loaded.graph.edges()[0].id
    monkeypatch.setattr(operations, "cluster", lambda _graph: {0: ["a", "b"]})
    monkeypatch.setattr(operations, "score_all", lambda _graph, _communities: {0: 1.0})

    assert operations.recluster(loaded.store_path) == {0: ["a", "b"]}

    updated = load_graph(loaded.store_path)
    assert updated.generation == generation
    assert updated.graph.edges()[0].id == edge_id
    assert updated.state["communities"][0]["cohesion"] == 1.0
