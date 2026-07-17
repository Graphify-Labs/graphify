from graphify.helix.state import community_records, new_state
from graphify.impact import analyze_impact
from tests.native_helpers import make_loaded


def test_impact_uses_native_multi_seed_traversal_and_durable_communities(tmp_path):
    state = new_state(communities=community_records({0: ["a", "b"], 1: ["c"]}))
    loaded = make_loaded(
        tmp_path,
        nodes=[
            {"id": "a", "source_file": "src/a.py"},
            {"id": "b", "source_file": "src/b.py"},
            {"id": "c", "source_file": "src/c.py"},
        ],
        edges=[
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "b", "target": "c", "relation": "calls"},
        ],
        state=state,
    )
    result = analyze_impact(loaded, ["src/a.py"], depth=2)
    assert result["seed_nodes"] == ["a"]
    assert result["impacted_nodes"] == ["a", "b", "c"]
    assert result["impacted_communities"] == [0, 1]
