import threading

import pytest

from graphify.helix.model import EdgeData, GraphBuildData, NodeData
from graphify.helix.persistence import HelixEmbeddedStore, HelixGraphReader, _StoreLock
from graphify.helix.state import community_records, new_state
from tests.native_helpers import make_loaded


@pytest.mark.parametrize(
    "kind,directed,multigraph",
    [
        ("graph", False, False),
        ("digraph", True, False),
        ("multigraph", False, True),
        ("multidigraph", True, True),
    ],
)
def test_all_declared_graph_kinds_round_trip(tmp_path, kind, directed, multigraph):
    edge = {"source": "a", "target": "b", "relation": "calls"}
    if multigraph:
        edge["key"] = ("edge", 1)
    loaded = make_loaded(
        tmp_path,
        kind=kind,
        nodes=[{"id": "a"}, {"id": "b"}],
        edges=[edge],
    )
    assert loaded.graph.directed is directed
    assert loaded.graph.multigraph is multigraph
    assert loaded.graph.edges()[0].graphify_key == (("edge", 1) if multigraph else None)


def test_typed_identities_do_not_collide(tmp_path):
    identities = [None, False, 0, 1, 1.5, "1", b"1", (1, "1"), frozenset({"a", "b"})]
    loaded = make_loaded(tmp_path, nodes=[{"id": value} for value in identities])
    assert loaded.graph.node_count == len(identities)
    assert {repr(node.id) for node in loaded.graph.nodes()} == {repr(value) for value in identities}


def test_semantic_labels_drive_native_filtering(tmp_path):
    from helixdb import TraversalOptions

    graph = make_loaded(
        tmp_path,
        nodes=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        edges=[
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "b", "target": "c", "relation": "imports"},
        ],
    ).graph
    result = graph.traverse(TraversalOptions(
        seeds=("a",), max_depth=3, allowed_labels=("calls",)
    ))
    assert tuple(visit.node_id for visit in result.visits) == ("a", "b")
    assert "relation" not in graph.edges()[0].attributes["attrs"]


def test_native_algorithms_and_transforms(tmp_path):
    graph = make_loaded(
        tmp_path,
        kind="digraph",
        nodes=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        edges=[
            {"source": "a", "target": "b", "relation": "calls", "weight": 1.0},
            {"source": "b", "target": "c", "relation": "calls", "weight": 1.0},
            {"source": "c", "target": "a", "relation": "calls", "weight": 1.0},
        ],
    ).graph
    assert graph.shortest_path("a", "c", direction="out").node_ids == ("a", "b", "c")
    assert graph.betweenness_centrality()
    assert graph.edge_betweenness_centrality()
    assert graph.simple_cycles(3).cycles
    assert graph.to_undirected().leiden().communities
    assert graph.spring_layout()
    assert graph.induced_subgraph(["a", "b"]).node_count == 2
    assert graph.relabel({"a": "renamed"}).contains_node("renamed")
    assert graph.to_undirected().to_directed().directed


def test_stage_analysis_and_state_activate_same_generation(tmp_path):
    store_path = tmp_path / "graph.helix"
    build = GraphBuildData(
        nodes=[NodeData("a"), NodeData("b")],
        edges=[EdgeData("a", "b", {"relation": "calls"})],
    )
    with HelixEmbeddedStore(store_path) as store:
        with store.staged_graph(build) as staged:
            assert store._active_generation(required=False) is None
            state = new_state(communities=community_records({0: ["a", "b"]}))
            active = store.activate_staged(staged, state)
            assert active.generation == active.state["build"]["generation"]
            assert active.generation == active.state["incremental"]["last_successful_generation"]
    with HelixEmbeddedStore(store_path, read_only=True) as store:
        assert store.verify()["nodes"] == 2


def test_interrupted_stage_leaves_previous_generation_active(tmp_path):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("old")]), new_state())
        previous = store.active_generation
        with pytest.raises(RuntimeError):
            with store.staged_graph(GraphBuildData(nodes=[NodeData("new")])):
                raise RuntimeError("interrupt")
        assert store.active_generation == previous
        assert store.load().graph.contains_node("old")


def test_activation_retains_one_verified_rollback_generation(tmp_path):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("first")]), new_state())
        first = store.active_generation
        store.save_generation(GraphBuildData(nodes=[NodeData("second")]), new_state())
        second = store.active_generation
        assert store.load_generation(first).graph.contains_node("first")
        store.save_generation(GraphBuildData(nodes=[NodeData("third")]), new_state())
        assert store.load_generation(second).graph.contains_node("second")
        with pytest.raises(RuntimeError, match="metadata is missing"):
            store.load_generation(first)


def test_state_and_topology_reopen_from_the_same_generation(tmp_path):
    store_path = tmp_path / "graph.helix"
    state = new_state(
        communities=[{
            "id": 0,
            "members": [b"a"],
            "name": "Typed",
            "naming_source": "test",
            "signature": "sha256:test",
            "cohesion": 1.0,
            "clustering": {"algorithm": "helix-leiden"},
        }],
        analysis={"god_nodes": [b"a"]},
        incremental={
            "files": {
                "a.py": {
                    "content_hash": "content",
                    "semantic_hash": "semantic",
                    "extractor_state": "ast",
                }
            },
            "extractor_state": {"mode": "ast"},
        },
        learning={"scores": {b"a": {"status": "accepted", "provenance": "test"}}},
        semantic={"used": True, "model": "test"},
    )
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData(b"a")]), state)
        generation = store.active_generation
    with HelixEmbeddedStore(store_path, read_only=True) as store:
        loaded = store.load()
        assert loaded.generation == generation
        assert loaded.state["build"]["generation"] == generation
        assert loaded.state["incremental"]["last_successful_generation"] == generation
        assert loaded.state["incremental"]["files"]["a.py"]["semantic_hash"] == "semantic"
        assert loaded.state["communities"][0]["members"] == [b"a"]
        assert loaded.state["learning"]["scores"][b"a"]["status"] == "accepted"
        assert loaded.state["semantic"]["used"] is True


def test_large_incremental_state_is_written_in_planner_safe_batches(tmp_path):
    files = {
        f"src/module_{index}.py": {
            "content_hash": f"content-{index}",
            "semantic_hash": f"semantic-{index}",
            "extractor_state": {"language": "python", "cached": True},
        }
        for index in range(350)
    }
    extraction_cache = {
        f"ast:src/module_{index}.py": {
            "nodes": [{"id": f"module-{index}", "label": f"Module {index}"}],
            "edges": [],
            "hyperedges": [],
        }
        for index in range(350)
    }
    state = new_state(incremental={
        "files": files,
        "extractor_state": {"mode": "ast"},
        "extraction_cache": extraction_cache,
    })
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("root")]), state)
    with HelixEmbeddedStore(store_path, read_only=True) as store:
        loaded = store.load()
    assert loaded.state["incremental"]["files"] == files
    assert loaded.state["incremental"]["extraction_cache"] == extraction_cache


def test_state_batch_bisects_only_known_planner_failure(tmp_path, monkeypatch):
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        original_query = store._query
        attempts = 0

        def planner_once(batch):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("unsupported cascades plan")
            return original_query(batch)

        monkeypatch.setattr(store, "_query", planner_once)
        records = [("section", f"key-{index}", {"value": index}, index) for index in range(4)]
        store._write_state_chunk("generation", records)
        assert len(store._read_state_rows("generation")) == 4
        assert attempts == 4


def test_configured_ingestion_bounds_fail_before_activation(tmp_path):
    with HelixEmbeddedStore(tmp_path / "graph.helix", max_nodes=1) as store:
        with pytest.raises(ValueError, match="ingestion bounds"):
            store.save_generation(
                GraphBuildData(nodes=[NodeData("a"), NodeData("b")]), new_state()
            )
        assert store._active_generation(required=False) is None


def test_read_only_enforcement(tmp_path):
    loaded = make_loaded(tmp_path, nodes=[{"id": "a"}])
    with HelixEmbeddedStore(loaded.store_path, read_only=True) as store:
        with pytest.raises(RuntimeError):
            store.save_generation(GraphBuildData(), new_state())


def test_read_only_open_does_not_create_missing_store(tmp_path):
    missing = tmp_path / "missing.helix"
    with pytest.raises(FileNotFoundError):
        HelixEmbeddedStore(missing, read_only=True)
    assert not missing.exists()


def test_competing_writers_are_rejected(tmp_path):
    lock_path = tmp_path / "graph.helix" / ".graphify-writer.lock"
    first = _StoreLock(lock_path, shared=False, timeout=0.1)
    second = _StoreLock(lock_path, shared=False, timeout=0.1)
    first.acquire()
    try:
        with pytest.raises(TimeoutError, match="embedded Helix store lock"):
            second.acquire()
    finally:
        first.release()
        second.release()


def test_reader_hot_reloads_active_generation(tmp_path):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("a")]), new_state())
    reader = HelixGraphReader(store_path)
    first = reader.get()
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("b")]), new_state())
    second = reader.get()
    assert first.generation != second.generation
    assert second.graph.contains_node("b")


def test_concurrent_native_readers(tmp_path):
    loaded = make_loaded(tmp_path, nodes=[{"id": "a"}])
    results = []

    def read():
        with HelixEmbeddedStore(loaded.store_path, read_only=True) as store:
            results.append(store.load().graph.node_count)

    threads = [threading.Thread(target=read) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [1, 1, 1, 1]


def test_existing_reader_keeps_previous_snapshot_during_writer_activation(tmp_path):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("old")]), new_state())

    with HelixEmbeddedStore(store_path, read_only=True) as reader:
        old_snapshot = reader.load().graph
        with HelixEmbeddedStore(store_path) as writer:
            with writer.staged_graph(GraphBuildData(nodes=[NodeData("new")])) as staged:
                assert old_snapshot.contains_node("old")
                writer.activate_staged(staged, new_state())
        assert old_snapshot.contains_node("old")
        assert not old_snapshot.contains_node("new")

    with HelixEmbeddedStore(store_path, read_only=True) as reader:
        assert reader.load().graph.contains_node("new")


def test_checksum_mismatch_is_rejected(tmp_path):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("a")]), new_state())
        generation = store.active_generation
        traversal = store._helix.g().n_with_label_where(
            "GraphifyMeta",
            store._helix.SourcePredicate.eq("graphify_generation", generation),
        ).set_property("checksum", "sha256:corrupt")
        store._query(
            store._helix.write_batch().var_as("corrupt", traversal).returning(["corrupt"])
        )
        with pytest.raises(RuntimeError, match="checksum verification"):
            store.verify()
