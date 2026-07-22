import copy
import threading

import pytest

from graphify.helix.model import EdgeData, GraphBuildData, NodeData
from graphify.helix.persistence import (
    _BUFFERED_WRITE_CONCURRENCY,
    _changed_buckets,
    HelixEmbeddedStore,
    HelixGraphReader,
    _prepare_topology,
    _public_store_rebuild_message,
    _StoreLock,
)
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


@pytest.mark.parametrize("weight", [True, "1.0", float("inf"), float("nan")])
def test_invalid_native_weights_fail_before_persistence(tmp_path, weight):
    graph = GraphBuildData(
        nodes=[NodeData("a"), NodeData("b")],
        edges=[EdgeData("a", "b", {"weight": weight})],
    )
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        with pytest.raises(TypeError, match="weight must be finite numeric"):
            store.save_generation(graph, new_state())
        assert store._active_generation(required=False) is None


def test_missing_edge_endpoint_fails_before_persistence(tmp_path):
    graph = GraphBuildData(
        nodes=[NodeData("a")],
        edges=[EdgeData("a", "missing")],
    )
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        with pytest.raises(ValueError, match="references a missing node"):
            store.save_generation(graph, new_state())
        assert store._active_generation(required=False) is None


def test_topology_hashes_are_order_independent_and_bucket_local():
    first = GraphBuildData(
        kind="digraph",
        nodes=[NodeData("c"), NodeData("a"), NodeData("b")],
        edges=[EdgeData("b", "c"), EdgeData("a", "b")],
    )
    reordered = GraphBuildData(
        kind="digraph",
        nodes=list(reversed(first.nodes)),
        edges=list(reversed(first.edges)),
    )
    changed = GraphBuildData(
        kind="digraph",
        nodes=[NodeData("a"), NodeData("b", {"changed": True}), NodeData("c")],
        edges=list(reordered.edges),
    )
    prepared = _prepare_topology(first, max_nodes=10, max_edges=10)
    reordered_prepared = _prepare_topology(reordered, max_nodes=10, max_edges=10)
    changed_prepared = _prepare_topology(changed, max_nodes=10, max_edges=10)

    assert prepared.checksum == reordered_prepared.checksum
    assert prepared.node_bucket_hashes == reordered_prepared.node_bucket_hashes
    assert prepared.edge_bucket_hashes == reordered_prepared.edge_bucket_hashes
    changed_node_buckets = _changed_buckets(
        prepared.node_bucket_hashes, changed_prepared.node_bucket_hashes
    )
    assert changed_node_buckets is not None
    assert len(changed_node_buckets) == 1
    assert not _changed_buckets(prepared.edge_bucket_hashes, changed_prepared.edge_bucket_hashes)


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
    result = graph.traverse(TraversalOptions(seeds=("a",), max_depth=3, allowed_labels=("calls",)))
    assert tuple(visit.node_id for visit in result.visits) == ("a", "b")
    assert "relation" not in graph.edges()[0].attributes.get("attrs", {})


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
            proposed = staged.graph
            state = new_state(communities=community_records({0: ["a", "b"]}))
            active = store.activate_staged(staged, state)
            assert active.generation == active.state["build"]["generation"]
            assert active.generation == active.state["incremental"]["last_successful_generation"]
            assert active.graph is proposed
            with pytest.raises(RuntimeError, match="already been activated"):
                _ = staged.graph
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
    with HelixEmbeddedStore(store_path, retain_rollback=True) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("first")]), new_state())
        first = store.active_generation
        store.save_generation(GraphBuildData(nodes=[NodeData("second")]), new_state())
        second = store.active_generation
        assert store.load_generation(first).graph.contains_node("first")
        store.save_generation(GraphBuildData(nodes=[NodeData("third")]), new_state())
        assert store.load_generation(second).graph.contains_node("second")
        with pytest.raises(RuntimeError, match="metadata is missing"):
            store.load_generation(first)


def test_activation_prunes_old_generation_by_default(tmp_path):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("first")]), new_state())
        first = store.active_generation
        store.save_generation(GraphBuildData(nodes=[NodeData("second")]), new_state())
        assert store.load().graph.contains_node("second")
        with pytest.raises(RuntimeError, match="metadata is missing"):
            store.load_generation(first)
        with pytest.raises(RuntimeError, match="no rollback generation"):
            store.rollback()


def test_explicitly_retained_generation_can_be_rolled_back(tmp_path):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path, retain_rollback=True) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("first")]), new_state())
        store.save_generation(GraphBuildData(nodes=[NodeData("second")]), new_state())
        rolled_back = store.rollback()
        assert rolled_back.graph.contains_node("first")
        assert store.load().graph.contains_node("first")


def test_state_and_topology_reopen_from_the_same_generation(tmp_path):
    store_path = tmp_path / "graph.helix"
    state = new_state(
        communities=[
            {
                "id": 0,
                "members": [b"a"],
                "name": "Typed",
                "naming_source": "test",
                "signature": "sha256:test",
                "cohesion": 1.0,
                "clustering": {"algorithm": "helix-leiden"},
            }
        ],
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
    state = new_state(
        incremental={
            "files": files,
            "extractor_state": {"mode": "ast"},
            "extraction_cache": extraction_cache,
        }
    )
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("root")]), state)
    with HelixEmbeddedStore(store_path, read_only=True) as store:
        loaded = store.load()
    assert loaded.state["incremental"]["files"] == files
    assert loaded.state["incremental"]["extraction_cache"] == extraction_cache


def test_large_cache_only_replacement_uses_chunked_native_revision(tmp_path):
    files = {f"src/module_{index}.py": {"content_hash": f"content-{index}"} for index in range(130)}
    cache = {f"ast:src/module_{index}.py": {"version": 1, "nodes": []} for index in range(130)}
    state = new_state(incremental={"files": files, "extraction_cache": cache})
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("root")]), state)
        before = store.load()
        updated = copy.deepcopy(dict(before.state))
        for value in updated["incremental"]["extraction_cache"].values():
            value["version"] = 2
        store.replace_state(
            updated,
            previous_state=dict(before.state),
            snapshot=before,
        )
        after = store.load()

    assert after.generation == before.generation
    assert after.metadata["active_cache_revision"] != before.metadata["active_cache_revision"]
    assert after.metadata["active_file_revision"] == before.metadata["active_file_revision"]
    assert {
        value["version"] for value in after.state["incremental"]["extraction_cache"].values()
    } == {2}


def test_state_batch_uses_fixed_planner_safe_transactions(tmp_path):
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        records = [("section", f"key-{index}", {"value": index}, index) for index in range(4)]
        store._write_state_chunk("generation", records, "revision")
        assert len(store._read_state_rows("generation", revision="revision")) == 4


def test_state_replacement_keeps_native_topology_and_generation(tmp_path, monkeypatch):
    store_path = tmp_path / "graph.helix"
    graph = GraphBuildData(
        nodes=[NodeData("a"), NodeData("b")],
        edges=[EdgeData("a", "b", {"relation": "calls"})],
    )
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(graph, new_state(analysis={"version": 1}))
        before = store.load()
        before_edge = before.graph.edges()[0].id
        before_revision = before.metadata["active_section_revision"]
        before_cache_revision = before.metadata["active_cache_revision"]
        before_file_revision = before.metadata["active_file_revision"]

        def topology_write_is_a_bug(*_args, **_kwargs):
            raise AssertionError("state-only update attempted to rewrite topology")

        monkeypatch.setattr(store, "_stage_generation", topology_write_is_a_bug)
        store.replace_state(
            new_state(analysis={"version": 2}),
            previous_state=dict(before.state),
        )
        after = store.load()

        assert after.generation == before.generation
        assert after.graph.edges()[0].id == before_edge
        assert after.state["analysis"] == {"version": 2}
        assert after.metadata["active_section_revision"] != before_revision
        assert after.metadata["active_cache_revision"] == before_cache_revision
        assert after.metadata["active_file_revision"] == before_file_revision


def test_failed_state_pointer_flip_leaves_previous_revision_active(tmp_path, monkeypatch):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(
            GraphBuildData(nodes=[NodeData("a")]),
            new_state(analysis={"version": 1}),
        )
        previous_state = store.read_state()
        original_query = store._query

        def fail_activation(batch, **kwargs):
            request = batch.to_query_request(kwargs.get("params"), kwargs.get("values"))
            if "activate_state" in request.to_json_string():
                raise RuntimeError("simulated activation failure")
            return original_query(batch, **kwargs)

        monkeypatch.setattr(store, "_query", fail_activation)
        with pytest.raises(RuntimeError, match="simulated activation failure"):
            store.replace_state(
                new_state(analysis={"version": 2}),
                previous_state=previous_state,
            )
        monkeypatch.setattr(store, "_query", original_query)
        assert store.load().state["analysis"] == {"version": 1}


def test_reader_hot_reloads_state_revision_without_topology_activation(tmp_path):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(
            GraphBuildData(nodes=[NodeData("a")]),
            new_state(analysis={"version": 1}),
        )
    reader = HelixGraphReader(store_path)
    first = reader.get()
    with HelixEmbeddedStore(store_path) as store:
        store.replace_state(new_state(analysis={"version": 2}))
    second = reader.get()
    assert first.generation == second.generation
    assert second.state["analysis"] == {"version": 2}


def test_configured_ingestion_bounds_fail_before_activation(tmp_path):
    with HelixEmbeddedStore(tmp_path / "graph.helix", max_nodes=1) as store:
        with pytest.raises(ValueError, match="ingestion bounds"):
            store.save_generation(GraphBuildData(nodes=[NodeData("a"), NodeData("b")]), new_state())
        assert store._active_generation(required=False) is None


def test_fresh_writer_opens_native_database_on_a_background_thread(tmp_path, monkeypatch):
    from graphify.helix import persistence

    opened_on: list[int | None] = []

    class Client:
        closed = False

        def close(self):
            self.closed = True

    client = Client()

    def open_client(_path, *, read_only=False, disable_cache=False):
        assert not read_only
        assert disable_cache
        opened_on.append(threading.current_thread().ident)
        return client

    monkeypatch.setattr(persistence, "open_embedded_client", open_client)
    store = HelixEmbeddedStore(tmp_path / "graph.helix")
    assert store._open_future is not None
    store._open_future.result(timeout=1)
    assert opened_on != [threading.current_thread().ident]
    assert store._client is None
    store.close()
    assert client.closed


def test_background_open_failure_releases_writer_lock(tmp_path, monkeypatch):
    from graphify.helix import persistence

    def fail_open(_path, *, read_only=False, disable_cache=False):
        assert not read_only
        assert disable_cache
        raise RuntimeError("simulated native open failure")

    monkeypatch.setattr(persistence, "open_embedded_client", fail_open)
    path = tmp_path / "graph.helix"
    store = HelixEmbeddedStore(path)
    with pytest.raises(RuntimeError, match="simulated native open failure"):
        store._ensure_client()
    assert store._closed

    lock = _StoreLock(path / ".graphify-writer.lock", shared=False, timeout=0.1)
    lock.acquire()
    lock.release()


def test_full_write_uses_buffered_staging_and_one_durable_publication_fence(tmp_path, monkeypatch):
    graph = GraphBuildData(
        nodes=[NodeData("a"), NodeData("b")],
        edges=[EdgeData("a", "b", {"relation": "calls"})],
    )
    observed: list[bool | None] = []
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        original_query = store._query

        def observe(batch, **kwargs):
            observed.append(kwargs.get("await_durability"))
            return original_query(batch, **kwargs)

        monkeypatch.setattr(store, "_query", observe)

        def count_scan_is_a_bug(*_args, **_kwargs):
            raise AssertionError("full write performed a pre-publication count scan")

        monkeypatch.setattr(store, "_verify_generation_counts", count_scan_is_a_bug)
        store.save_generation(graph, new_state())

    explicit = [value for value in observed if value is not None]
    assert explicit.count(True) == 1
    assert explicit[-1] is True
    assert all(value is False for value in explicit[:-1])


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


def test_native_store_supports_spaces_unicode_and_deep_paths(tmp_path):
    store_path = (
        tmp_path
        / "native store with spaces"
        / "gráph-数据"
        / ("nested-" + "x" * 96)
        / "graph.helix"
    )
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("naïve-节点")]), new_state())
    with HelixEmbeddedStore(store_path, read_only=True) as store:
        assert store.load().graph.contains_node("naïve-节点")


@pytest.mark.parametrize(
    "detail",
    [
        "Migration required: writer migration must complete before opening a reader",
        "Index lifecycle unavailable for secondary: reader coordination unavailable",
    ],
)
def test_public_runtime_format_failures_require_source_rebuild(tmp_path, detail):
    message = _public_store_rebuild_message(RuntimeError(detail), tmp_path / "graph.helix")
    assert message is not None
    assert "move that graph.helix directory aside" in message
    assert "graphify update from source" in message


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


def test_snapshot_load_retries_a_changed_read_view(tmp_path, monkeypatch):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("a")]), new_state())
        original_metadata = store._metadata
        attempts = 0

        def metadata(generation, *, client=None):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("Request read view changed during execution; retry the request")
            return original_metadata(generation, client=client)

        monkeypatch.setattr(store, "_metadata", metadata)
        assert store.load().graph.contains_node("a")
        assert attempts == 2


def test_checksum_mismatch_is_rejected(tmp_path):
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(GraphBuildData(nodes=[NodeData("a")]), new_state())
        generation = store.active_generation
        traversal = (
            store._helix.g()
            .n_with_label_where(
                "GraphifyMeta",
                store._helix.SourcePredicate.eq("graphify_generation", generation),
            )
            .set_property("checksum", "sha256:corrupt")
        )
        store._query(store._helix.write_batch().var_as("corrupt", traversal).returning(["corrupt"]))
        with pytest.raises(RuntimeError, match="checksum verification"):
            store.verify()
