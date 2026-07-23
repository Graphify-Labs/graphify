import graphify.__main__ as mainmod
import pytest
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


def test_cluster_only_project_path_persists_analysis_in_native_state(
    tmp_path, monkeypatch
):
    """``cluster-only <project>`` refreshes native state beside the store."""
    out = tmp_path / "graphify-out"
    out.mkdir()
    make_loaded(
        out,
        nodes=[
            {"id": "a", "label": "A", "source_file": "a.py"},
            {"id": "b", "label": "B", "source_file": "b.py"},
        ],
        edges=[{"source": "a", "target": "b", "relation": "calls"}],
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "cluster-only", str(tmp_path)]
    )

    mainmod.main()

    loaded = load_graph(out / "graph.helix")
    assert loaded.state["communities"]
    assert set(loaded.state["analysis"]) >= {
        "god_nodes",
        "surprises",
        "suggested_questions",
        "community_summaries",
    }
    assert not (out / ".graphify_analysis.json").exists()


def test_cluster_only_missing_native_store_fails_without_creating_output(
    tmp_path, monkeypatch
):
    """A missing native store fails clearly instead of synthesizing output."""
    project = tmp_path / "missing-project"
    project.mkdir()
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "cluster-only", str(project)]
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 1
    assert not (project / "graphify-out").exists()


def test_cluster_only_explicit_store_does_not_pollute_cwd(tmp_path, monkeypatch):
    """An explicit native store is updated in place without CWD output."""
    project = tmp_path / "project"
    out = project / "graphify-out"
    out.mkdir(parents=True)
    loaded = make_loaded(
        out,
        nodes=[{"id": "a"}, {"id": "b"}],
        edges=[{"source": "a", "target": "b", "relation": "calls"}],
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "cluster-only", ".", "--store", str(loaded.store_path)],
    )

    mainmod.main()

    assert load_graph(loaded.store_path).state["communities"]
    assert not (elsewhere / "graphify-out").exists()


def test_cluster_only_remaps_labels_to_previous_cids(tmp_path, monkeypatch):
    """Reclustering keeps labels attached by node overlap, not new raw IDs."""
    state = new_state(
        communities=community_records(
            {4242: ["a", "b"], 9999: ["c", "d"]},
            labels={4242: "First Group", 9999: "Second Group"},
        )
    )
    loaded = make_loaded(
        tmp_path,
        nodes=[{"id": node} for node in "abcd"],
        edges=[
            {"source": "a", "target": "b", "relation": "related"},
            {"source": "c", "target": "d", "relation": "related"},
        ],
        state=state,
    )
    monkeypatch.setattr(
        operations,
        "cluster",
        lambda _graph: {0: ["c", "d"], 1: ["a", "b"]},
    )
    monkeypatch.setattr(
        operations,
        "score_all",
        lambda _graph, communities: {community_id: 1.0 for community_id in communities},
    )

    operations.recluster(loaded.store_path)

    records = {
        record["id"]: record for record in load_graph(loaded.store_path).state["communities"]
    }
    assert records[4242]["members"] == ["a", "b"]
    assert records[4242]["name"] == "First Group"
    assert records[9999]["members"] == ["c", "d"]
    assert records[9999]["name"] == "Second Group"
