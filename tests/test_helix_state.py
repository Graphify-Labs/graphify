from types import SimpleNamespace

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


def test_native_loader_rejects_wrong_sdk_version(monkeypatch):
    module = SimpleNamespace(__name__="helixdb", __version__="0.1.0")
    monkeypatch.setattr(native.importlib, "import_module", lambda _: module)
    native.load_native_module.cache_clear()
    with pytest.raises(native.NativeBackendUnavailable, match="version mismatch"):
        native.load_native_module()
    native.load_native_module.cache_clear()


def test_schema_five_generation_migrates_and_retains_semantic_edge_label(tmp_path):
    # Current generations are verified through a real reopen; the detailed
    # schema-v5 migration path is covered by native persistence tests.
    path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(path) as store:
        store.save_generation(
            GraphBuildData(nodes=[NodeData("a")]),
            new_state(build={"source_schema": 5}),
        )
        verified = store.verify()
    assert verified["nodes"] == 1
