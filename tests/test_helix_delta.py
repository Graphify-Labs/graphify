import threading

import pytest

from graphify.helix.model import EdgeData, GraphBuildData, NodeData
from graphify.helix.persistence import (
    _BUFFERED_WRITE_CONCURRENCY,
    _STAGED_EDGE_WRITE_CHUNK_SIZE,
    _WRITE_CHUNK_SIZE,
    HelixEmbeddedStore,
)
from graphify.helix.state import new_state


def _graph(size: int) -> GraphBuildData:
    return GraphBuildData(
        kind="digraph",
        nodes=[NodeData(f"n{index}", {"value": index}) for index in range(size)],
        edges=[
            EdgeData(
                f"n{index}",
                f"n{(index + 1) % size}",
                {"relation": "next", "value": index},
            )
            for index in range(size)
        ],
    )


def test_small_delta_adds_updates_and_deletes_topology_in_place(tmp_path, monkeypatch):
    initial = _graph(200)
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(initial, new_state())
        generation = store.active_generation

        nodes = list(initial.nodes[:-1])
        nodes[7] = NodeData("n7", {"value": 700})
        nodes.append(NodeData("new", {"value": 999}))
        edges = list(initial.edges[:198])
        edges[13] = EdgeData("n13", "n14", {"relation": "changed"})
        edges[20] = EdgeData("n20", "n22", {"relation": "moved"})
        edges.extend(
            [
                EdgeData("n198", "new", {"relation": "next"}),
                EdgeData("new", "n0", {"relation": "next"}),
            ]
        )
        store.save_generation(
            GraphBuildData(kind="digraph", nodes=nodes, edges=edges),
            new_state(),
        )
        loaded = store.load()

        assert loaded.generation == generation
        assert loaded.graph.node("n7").attributes["attrs"]["value"] == 700
        assert loaded.graph.contains_node("new")
        assert not loaded.graph.contains_node("n199")
        changed = loaded.graph.edges_between("n13", "n14", direction="out")
        moved = loaded.graph.edges_between("n20", "n22", direction="out")
        assert loaded.graph.edge(changed[0]).label == "changed"
        assert loaded.graph.edge(moved[0]).label == "moved"
        assert loaded.graph.edge_count == 200


def test_identical_generation_save_is_a_noop(tmp_path, monkeypatch):
    graph = _graph(20)
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(graph, new_state())
        before = store.load()

        def publish_is_a_bug(*_args, **_kwargs):
            raise AssertionError("no-op save attempted delta publication")

        monkeypatch.setattr(store, "_publish_delta", publish_is_a_bug)
        store.save_generation(graph, new_state())
        after = store.load()

        assert after.generation == before.generation
        assert after.metadata["topology_revision"] == before.metadata["topology_revision"]
        assert (
            after.metadata["active_section_revision"] == before.metadata["active_section_revision"]
        )


def test_delta_threshold_and_rollback_retention_fall_back_to_generations(tmp_path, monkeypatch):
    initial = GraphBuildData(nodes=[NodeData(f"n{index}", {"value": index}) for index in range(20)])
    with HelixEmbeddedStore(tmp_path / "threshold.helix") as store:
        store.save_generation(initial, new_state())
        before = store.active_generation
        changed = list(initial.nodes)
        for index in range(3):
            changed[index] = NodeData(f"n{index}", {"value": index + 100})
        store.save_generation(GraphBuildData(nodes=changed), new_state())
        assert store.active_generation != before

    with HelixEmbeddedStore(tmp_path / "rollback.helix", retain_rollback=True) as store:
        store.save_generation(initial, new_state())
        before = store.active_generation
        changed = list(initial.nodes)
        changed[0] = NodeData("n0", {"value": 100})
        store.save_generation(GraphBuildData(nodes=changed), new_state())
        assert store.active_generation != before
        assert store.rollback().generation == before


def test_failed_delta_transaction_keeps_old_topology_and_state(tmp_path, monkeypatch):
    initial = _graph(100)
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(initial, new_state(analysis={"version": 1}))
        generation = store.active_generation
        original_query = store._query

        def fail_publication(batch, **kwargs):
            request = batch.to_query_request(kwargs.get("params"), kwargs.get("values"))
            if "publish_delta" in request.to_json_string():
                raise RuntimeError("simulated delta failure")
            return original_query(batch, **kwargs)

        monkeypatch.setattr(store, "_query", fail_publication)
        changed = _graph(100)
        changed.nodes[1] = NodeData("n1", {"value": 101})
        with pytest.raises(RuntimeError, match="simulated delta failure"):
            store.save_generation(changed, new_state(analysis={"version": 2}))
        monkeypatch.setattr(store, "_query", original_query)
        loaded = store.load()

        assert loaded.generation == generation
        assert loaded.graph.node("n1").attributes["attrs"]["value"] == 1
        assert loaded.state["analysis"] == {"version": 1}


def test_failed_state_staging_removes_invisible_revision_rows(tmp_path, monkeypatch):
    graph = _graph(100)
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(graph, new_state())
        generation = store.active_generation
        before_rows = store._read_rows(generation)[3]
        original_write = store._write_state_records
        calls = 0

        def fail_second_category(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated state staging failure")
            return original_write(*args, **kwargs)

        monkeypatch.setattr(store, "_write_state_records", fail_second_category)
        state = new_state(
            analysis={"version": 2},
            communities=[{"id": 1, "members": ["n1"]}],
        )
        with pytest.raises(RuntimeError, match="simulated state staging failure"):
            store.save_generation(graph, state)
        monkeypatch.setattr(store, "_write_state_records", original_write)

        assert len(store._read_rows(generation)[3]) == len(before_rows)
        assert store.load().state["analysis"] == {}


def test_lost_delta_response_recognizes_committed_publication(tmp_path, monkeypatch):
    graph = _graph(100)
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(graph, new_state(analysis={"version": 1}))
        original_query = store._query
        response_lost = False

        def lose_publication_response(batch, **kwargs):
            nonlocal response_lost
            request = batch.to_query_request(kwargs.get("params"), kwargs.get("values"))
            if "publish_delta" in request.to_json_string() and not response_lost:
                response_lost = True
                original_query(batch, **kwargs)
                raise RuntimeError("simulated lost response")
            return original_query(batch, **kwargs)

        monkeypatch.setattr(store, "_query", lose_publication_response)
        changed = _graph(100)
        changed.nodes[2] = NodeData("n2", {"value": 202})
        store.save_generation(changed, new_state(analysis={"version": 2}))

        loaded = store.load()
        assert response_lost
        assert loaded.graph.node("n2").attributes["attrs"]["value"] == 202
        assert loaded.state["analysis"] == {"version": 2}


def test_state_only_delta_preserves_topology_revision(tmp_path):
    graph = _graph(100)
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(graph, new_state(analysis={"version": 1}))
        before = store.load()

        store.save_generation(graph, new_state(analysis={"version": 2}))
        after = store.load()

        assert after.generation == before.generation
        assert after.metadata["topology_revision"] == before.metadata["topology_revision"]
        assert after.state["analysis"] == {"version": 2}


def test_old_and_new_loaded_graphs_keep_coherent_reader_snapshots(tmp_path, monkeypatch):
    initial = _graph(100)
    initial.nodes[0] = NodeData("n0", {"label": "old token"})
    store_path = tmp_path / "graph.helix"
    with HelixEmbeddedStore(store_path) as writer:
        writer.save_generation(initial, new_state(analysis={"version": 1}))
        with HelixEmbeddedStore(store_path, read_only=True) as reader:
            old = reader.load()
            changed = _graph(100)
            changed.nodes[0] = NodeData("n0", {"label": "new token"})
            writer.save_generation(changed, new_state(analysis={"version": 2}))
            with HelixEmbeddedStore(store_path, read_only=True) as reopened:
                new = reopened.load()

            assert old.generation == new.generation
            assert old.state["analysis"] == {"version": 1}
            assert new.state["analysis"] == {"version": 2}
            assert old.graph.node("n0").attributes["attrs"]["label"] == "old token"
            assert new.graph.node("n0").attributes["attrs"]["label"] == "new token"
            assert old.query is not None
            assert new.query is not None
            assert "n0" in old.query.candidate_ids(["old token"])
            assert "n0" not in old.query.candidate_ids(["new token"])
            assert "n0" in new.query.candidate_ids(["new token"])


def test_clustered_delta_analyzes_native_builder_graph_before_publication(tmp_path, monkeypatch):
    initial = _graph(100)
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(initial, new_state())
        generation = store.active_generation
        original_validate = store._validate_proposed_native_graph
        proposals = []

        def validate(prepared):
            proposal = original_validate(prepared)
            proposals.append(proposal)
            return proposal

        monkeypatch.setattr(store, "_validate_proposed_native_graph", validate)

        def full_stage_is_a_bug(*_args, **_kwargs):
            raise AssertionError("small clustered delta staged a full generation")

        monkeypatch.setattr(store, "_save_prepared_graph", full_stage_is_a_bug)
        changed = _graph(100)
        changed.nodes[4] = NodeData("n4", {"value": 404})
        with store.staged_graph(changed) as staged:
            assert staged.graph is proposals[0]
            activated = store.activate_staged(staged, new_state())

        assert activated.generation == generation
        assert activated.graph is proposals[0]
        assert activated.graph.node("n4").attributes["attrs"]["value"] == 404


def test_direct_delta_validates_proposed_native_graph_before_publication(tmp_path, monkeypatch):
    initial = _graph(100)
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(initial, new_state())
        original_validate = store._validate_proposed_native_graph
        validations = 0

        def validate(prepared):
            nonlocal validations
            validations += 1
            return original_validate(prepared)

        monkeypatch.setattr(store, "_validate_proposed_native_graph", validate)
        changed = _graph(100)
        changed.nodes[4] = NodeData("n4", {"value": 404})
        store.save_generation(changed, new_state())

        assert validations == 1
        assert store.load().graph.node("n4").attributes["attrs"]["value"] == 404


def test_unchanged_clustered_topology_reuses_active_native_graph(tmp_path, monkeypatch):
    graph = _graph(100)
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(graph, new_state())
        generation = store.active_generation

        def full_stage_is_a_bug(*_args, **_kwargs):
            raise AssertionError("unchanged topology staged a full generation")

        monkeypatch.setattr(store, "_save_prepared_graph", full_stage_is_a_bug)
        with store.staged_graph(graph) as staged:
            assert staged.graph.node_count == 100
            activated = store.activate_staged(staged, new_state(analysis={"version": 2}))

        assert activated.generation == generation
        assert activated.state["analysis"] == {"version": 2}


def test_full_writer_keeps_parameter_pages_bounded_and_groups_edge_shapes(tmp_path, monkeypatch):
    nodes = [NodeData(f"n{index}") for index in range(1_001)]
    edges = [
        EdgeData(
            "n0",
            "n1",
            {"relation": "calls" if index % 2 else "imports"},
            key=index,
        )
        for index in range(2_001)
    ]
    observed: list[int] = []
    active = 0
    max_active = 0
    lock = threading.Lock()
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        original_query = store._query

        def observe(batch, **kwargs):
            nonlocal active, max_active
            values = kwargs.get("values")
            if isinstance(values, dict) and isinstance(values.get("rows"), list):
                with lock:
                    observed.append(len(values["rows"]))
                    active += 1
                    max_active = max(max_active, active)
                try:
                    return original_query(batch, **kwargs)
                finally:
                    with lock:
                        active -= 1
            return original_query(batch, **kwargs)

        monkeypatch.setattr(store, "_query", observe)
        store.save_generation(
            GraphBuildData(kind="multidigraph", nodes=nodes, edges=edges),
            new_state(),
        )

    assert observed
    assert max(observed) <= _WRITE_CHUNK_SIZE
    assert observed.count(_WRITE_CHUNK_SIZE) >= 1
    assert observed.count(_STAGED_EDGE_WRITE_CHUNK_SIZE) >= 2
    assert 1 in observed
    assert 1 < max_active <= _BUFFERED_WRITE_CONCURRENCY


def test_multigraph_duplicate_stable_edge_identity_is_rejected(tmp_path):
    graph = GraphBuildData(
        kind="multigraph",
        nodes=[NodeData("a"), NodeData("b")],
        edges=[
            EdgeData("a", "b", key="same"),
            EdgeData("b", "a", key="same"),
        ],
    )
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        with pytest.raises(ValueError, match="duplicate graph edge identity"):
            store.save_generation(graph, new_state())


def test_multigraph_parallel_edges_without_explicit_keys_get_stable_ordinals(tmp_path):
    graph = GraphBuildData(
        kind="multidigraph",
        nodes=[NodeData("a"), NodeData("b")],
        edges=[
            EdgeData("a", "b", {"relation": "first"}),
            EdgeData("a", "b", {"relation": "second"}),
        ],
    )
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(graph, new_state())
        loaded = store.load()

    assert loaded.graph.edge_count == 2
    assert {edge.label for edge in loaded.graph.edges()} == {"first", "second"}


def test_undirected_multigraph_delta_preserves_parallel_and_self_loop_identities(
    tmp_path, monkeypatch
):
    nodes = [NodeData(1), NodeData("two"), *[NodeData(f"n{index}") for index in range(2, 100)]]
    filler_edges = [
        EdgeData(f"n{index}", f"n{index + 1}", {"relation": "next"}, key=index)
        for index in range(2, 99)
    ]
    initial = GraphBuildData(
        kind="multigraph",
        nodes=nodes,
        edges=[
            EdgeData(1, 1, {"relation": "self"}, key="loop"),
            EdgeData(1, "two", {"relation": "first"}, key=("parallel", 1)),
            EdgeData("two", 1, {"relation": "second"}, key=("parallel", 2)),
            *filler_edges,
        ],
    )
    with HelixEmbeddedStore(tmp_path / "graph.helix") as store:
        store.save_generation(initial, new_state())
        generation = store.active_generation
        changed = GraphBuildData(
            kind="multigraph",
            nodes=nodes,
            edges=[
                EdgeData(1, 1, {"relation": "changed-self"}, key="loop"),
                EdgeData(1, "two", {"relation": "second"}, key=("parallel", 2)),
                EdgeData("two", 1, {"relation": "third"}, key=("parallel", 3)),
                *filler_edges,
            ],
        )

        store.save_generation(changed, new_state())
        loaded = store.load()

        assert loaded.generation == generation
        assert loaded.graph.edge_count == 100
        labels = {edge.graphify_key: edge.label for edge in loaded.graph.edges()}
        assert labels["loop"] == "changed-self"
        assert labels[("parallel", 2)] == "second"
        assert labels[("parallel", 3)] == "third"
        assert ("parallel", 1) not in labels
