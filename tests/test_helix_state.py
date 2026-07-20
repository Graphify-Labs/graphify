import pytest

from graphify.helix import native
from graphify.helix.model import GraphBuildData, NodeData
from graphify.helix.persistence import HelixEmbeddedStore
from graphify.helix.state import community_records, communities_from_state, labels_from_state, new_state


def test_community_state_round_trip():
    records = community_records({0: ["a", "b"]}, labels={0: "Auth"}, cohesion={0: 0.5})
    state = new_state(communities=records)
    assert communities_from_state(state) == {0: ["a", "b"]}
    assert labels_from_state(state) == {0: "Auth"}
    assert records[0]["clustering"]["algorithm"] == "helix-leiden"


def test_native_validator_rejects_wrong_sdk_version(monkeypatch):
    original_version = native.importlib.metadata.version

    def version(distribution):
        return "0.1.0" if distribution == "helix-db" else original_version(distribution)

    monkeypatch.setattr(native.importlib.metadata, "version", version)
    native.validate_native_backend.cache_clear()
    with pytest.raises(native.NativeBackendUnavailable, match="version mismatch"):
        native.validate_native_backend()
    native.validate_native_backend.cache_clear()


def test_current_generation_reopens_and_retains_semantic_edge_label(tmp_path):
    path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(path) as store:
        store.save_generation(
            GraphBuildData(nodes=[NodeData("a")]),
            new_state(build={"source_schema": 5}),
        )
        verified = store.verify()
    assert verified["nodes"] == 1
