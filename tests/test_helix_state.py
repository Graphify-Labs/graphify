import pytest

from graphify.helix import native
from graphify.helix.model import GraphBuildData, NodeData
from graphify.helix.persistence import HelixEmbeddedStore
from graphify.helix.state import (
    community_records,
    communities_from_state,
    labels_from_state,
    new_state,
)


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


def test_embedded_graph_store_disables_fresh_write_caches_and_bounds_read_caches(
    tmp_path, monkeypatch
):
    calls = []
    sentinel = object()

    def embedded(_cls, source, *, cache=None, id_lease_size=None):
        calls.append(("writer", source, cache, id_lease_size))
        return sentinel

    def embedded_reader(_cls, source, *, cache=None):
        calls.append(("reader", source, cache, None))
        return sentinel

    monkeypatch.setattr(native.helixdb.Client, "embedded", classmethod(embedded))
    monkeypatch.setattr(
        native.helixdb.Client,
        "embedded_reader",
        classmethod(embedded_reader),
    )

    assert native.open_embedded_client(tmp_path / "writer", disable_cache=True) is sentinel
    reader_path = tmp_path / "reader"
    reader_path.mkdir()
    assert native.open_embedded_client(reader_path, read_only=True) is sentinel

    assert [kind for kind, *_ in calls] == ["writer", "reader"]
    assert all(cache.vector_memory_bytes == 1 for _, _, cache, _ in calls)
    assert isinstance(calls[0][2].mode, native.helixdb.VectorMemoryOnly)
    assert isinstance(calls[1][2].mode, native.helixdb.MemoryCache)


def test_current_generation_reopens_and_retains_semantic_edge_label(tmp_path):
    path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(path) as store:
        store.save_generation(
            GraphBuildData(nodes=[NodeData("a")]),
            new_state(build={"source_schema": 5}),
        )
        verified = store.verify()
    assert verified["nodes"] == 1
