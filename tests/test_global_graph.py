"""Tests for the global graph infrastructure (graphify/global_graph.py),
prefix/prune helpers in graphify/build.py, and the cross-repo guard in
graphify/dedup.py."""
from __future__ import annotations

import json
import pytest
import networkx as nx
from contextlib import contextmanager
from unittest.mock import patch


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_graph(nodes, edges=None):
    """Build a simple nx.Graph from node dicts."""
    G = nx.Graph()
    for n in nodes:
        nid = n["id"]
        G.add_node(nid, **{k: v for k, v in n.items() if k != "id"})
    for e in (edges or []):
        G.add_edge(
            e["source"],
            e["target"],
            **{k: v for k, v in e.items() if k not in ("source", "target")},
        )
    return G


def _graph_to_json(G, path):
    from networkx.readwrite import json_graph as jg
    try:
        data = jg.node_link_data(G, edges="links")
    except TypeError:
        data = jg.node_link_data(G)
    path.write_text(json.dumps(data), encoding="utf-8")


@contextmanager
def _global_store(global_dir):
    """Point graphify.global_graph at ``global_dir`` instead of the user's home."""
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        yield global_dir / "global-graph.json", global_dir / "global-manifest.json"


def _write_batch_units(tmp_path):
    """Three unit graphs: repoA parks a member call repoB answers, plus a shared stub.

    repoC contributes a second copy of the `logging` stub so the external-label dedup has
    something to do on a unit that is not the first one composed.
    """
    units = {}
    units["repoA"] = _make_graph(
        [{"id": "app", "label": ".run()", "source_file": "src/App.java",
          "metadata": {"unresolved_calls": [
              {"lang": "java", "receiver_type": "Greeter", "callee": "greet", "line": 7}]}},
         {"id": "logging", "label": "logging"}],
        [{"source": "app", "target": "logging", "relation": "imports"}],
    )
    units["repoB"] = _make_graph(
        [{"id": "greeter", "label": "Greeter", "source_file": "src/Greeter.java",
          "_callable_class": True},
         {"id": "greet", "label": ".greet()", "source_file": "src/Greeter.java"}],
        [{"source": "greeter", "target": "greet", "relation": "method"}],
    )
    units["repoC"] = _make_graph(
        [{"id": "worker", "label": "Worker", "source_file": "src/worker.py"},
         {"id": "logging", "label": "logging"}],
        [{"source": "worker", "target": "logging", "relation": "imports"}],
    )
    sources = []
    for tag, G in units.items():
        path = tmp_path / tag / "graph.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _graph_to_json(G, path)
        sources.append((path, tag))
    return sources


def _read_store(graph_path, manifest_path):
    """Return the stored graph and manifest in a form two runs can be compared by."""
    from networkx.readwrite import json_graph as jg
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    try:
        G = jg.node_link_graph(data, edges="links")
    except TypeError:
        G = jg.node_link_graph(data)
    nodes = {n: dict(d) for n, d in G.nodes(data=True)}
    edges = {frozenset((u, v)): dict(d) for u, v, d in G.edges(data=True)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["repos"].values():
        entry.pop("added_at", None)
    return nodes, edges, manifest


# ── build.py helpers ──────────────────────────────────────────────────────────

def test_prefix_graph_preserves_label():
    from graphify.build import prefix_graph_for_global
    G = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    H = prefix_graph_for_global(G, "repoA")
    assert "repoA::userservice" in H.nodes
    assert "userservice" not in H.nodes
    assert H.nodes["repoA::userservice"]["label"] == "UserService"


def test_prefix_graph_sets_repo_and_local_id():
    from graphify.build import prefix_graph_for_global
    G = _make_graph([{"id": "userservice", "label": "UserService"}])
    H = prefix_graph_for_global(G, "repoA")
    data = H.nodes["repoA::userservice"]
    assert data["repo"] == "repoA"
    assert data["local_id"] == "userservice"


def test_prefix_graph_rewrites_edges():
    from graphify.build import prefix_graph_for_global
    G = _make_graph(
        [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        [{"source": "a", "target": "b"}],
    )
    H = prefix_graph_for_global(G, "repo1")
    assert H.has_edge("repo1::a", "repo1::b")
    assert not H.has_edge("a", "b")


def test_prefix_graph_rewrites_edge_directional_attributes():
    """prefix_graph_for_global must update directional edge attributes (_src/_tgt)
    so they stay aligned with the prefixed node IDs (#2261)."""
    from graphify.build import prefix_graph_for_global
    G = _make_graph(
        [{"id": "rota", "label": "rota.js"}, {"id": "collections", "label": "collections.js"}],
        [{"source": "rota", "target": "collections", "relation": "imports_from", "_src": "rota", "_tgt": "collections"}],
    )
    H = prefix_graph_for_global(G, "repoA")
    assert H.has_edge("repoA::rota", "repoA::collections")
    data = H.get_edge_data("repoA::rota", "repoA::collections")
    assert data["_src"] == "repoA::rota"
    assert data["_tgt"] == "repoA::collections"


def test_prefix_graph_offsets_community_ids():
    """#3014: every input graph numbers its communities from 0, so a merge
    carrying ids across unchanged fuses community 0 of one repo with community
    0 of another into a single meta-node in the aggregated view. An offset must
    shift integer ids into a shared id space and keep the per-repo id in
    local_community."""
    from graphify.build import prefix_graph_for_global
    G = _make_graph(
        [{"id": "a", "community": 0}, {"id": "b", "community": 1}], [],
    )
    H = prefix_graph_for_global(G, "repoA", community_offset=5)
    assert H.nodes["repoA::a"]["community"] == 5
    assert H.nodes["repoA::a"]["local_community"] == 0
    assert H.nodes["repoA::b"]["community"] == 6
    assert H.nodes["repoA::b"]["local_community"] == 1


def test_prefix_graph_zero_offset_leaves_communities_untouched():
    """The default offset must be a no-op — no community rewrite, no
    local_community noise — so single-repo callers (global store, tests)
    keep their ids exactly as stored."""
    from graphify.build import prefix_graph_for_global
    G = _make_graph(
        [{"id": "a", "community": 0}, {"id": "b", "community": 1}], [],
    )
    H = prefix_graph_for_global(G, "repoA")
    assert H.nodes["repoA::a"]["community"] == 0
    assert H.nodes["repoA::b"]["community"] == 1
    assert "local_community" not in H.nodes["repoA::a"]
    assert "local_community" not in H.nodes["repoA::b"]



def test_prune_repo_removes_correct_nodes():
    from graphify.build import prune_repo_from_graph
    G = nx.Graph()
    G.add_node("repoA::userservice", repo="repoA", label="UserService")
    G.add_node("repoB::userservice", repo="repoB", label="UserService")
    G.add_node("repoA::auth", repo="repoA", label="Auth")
    removed = prune_repo_from_graph(G, "repoA")
    assert removed == 2
    assert "repoB::userservice" in G.nodes
    assert "repoA::userservice" not in G.nodes
    assert "repoA::auth" not in G.nodes


def test_prune_repo_returns_zero_if_not_present():
    from graphify.build import prune_repo_from_graph
    G = nx.Graph()
    G.add_node("repoA::x", repo="repoA")
    removed = prune_repo_from_graph(G, "repoB")
    assert removed == 0
    assert G.number_of_nodes() == 1


# ── global_graph.py ───────────────────────────────────────────────────────────

def test_global_add_creates_global_graph(tmp_path):
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        result = global_add(src_graph, "repoA")

    assert result["skipped"] is False
    assert result["nodes_added"] > 0
    manifest_path = global_dir / "global-manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert "repoA" in manifest["repos"]


def test_global_add_skip_on_unchanged_hash(tmp_path):
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        global_add(src_graph, "repoA")
        result2 = global_add(src_graph, "repoA")

    assert result2["skipped"] is True


def test_global_add_two_repos_no_collision(tmp_path):
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    G1 = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    G2 = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    _graph_to_json(G1, g1)
    _graph_to_json(G2, g2)

    global_dir = tmp_path / ".graphify"
    global_graph_path = global_dir / "global-graph.json"
    global_manifest_path = global_dir / "global-manifest.json"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_graph_path), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_manifest_path):
        from graphify.global_graph import global_add, _load_global_graph
        global_add(g1, "repoA")
        global_add(g2, "repoB")
        G = _load_global_graph()

    assert "repoA::userservice" in G.nodes
    assert "repoB::userservice" in G.nodes
    assert G.number_of_nodes() == 2  # no silent merge


def test_global_remove(tmp_path):
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add, global_remove
        global_add(src_graph, "repoA")
        removed = global_remove("repoA")

    assert removed > 0
    # manifest should no longer list repoA - need to re-patch for list call
    global_dir2 = global_dir  # same dir
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir2), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir2 / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir2 / "global-manifest.json"):
        from graphify.global_graph import global_list
        repos = global_list()
    assert "repoA" not in repos


def test_global_remove_unknown_tag_raises(tmp_path):
    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_remove
        with pytest.raises(KeyError):
            global_remove("nonexistent")


def test_global_add_collision_warning(tmp_path, capsys):
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "x.py"}])
    _graph_to_json(G, g1)
    _graph_to_json(G, g2)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        global_add(g1, "myrepo")
        global_add(g2, "myrepo")  # different source path, same tag

    captured = capsys.readouterr()
    assert "warning" in captured.err.lower() or "warning" in captured.out.lower()


# ── dedup guard ───────────────────────────────────────────────────────────────

def test_dedup_raises_on_cross_repo_nodes():
    from graphify.dedup import deduplicate_entities
    nodes = [
        {"id": "repoA::userservice", "label": "UserService", "repo": "repoA"},
        {"id": "repoB::userservice", "label": "UserService", "repo": "repoB"},
    ]
    with pytest.raises(ValueError, match="multiple repos"):
        deduplicate_entities(nodes, [], communities={})


def test_dedup_ok_with_single_repo():
    from graphify.dedup import deduplicate_entities
    nodes = [
        {"id": "repoA::userservice", "label": "UserService", "repo": "repoA"},
        {"id": "repoA::auth", "label": "Auth", "repo": "repoA"},
    ]
    result_nodes, result_edges = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2  # no false merge


def test_dedup_ok_with_no_repo_attr():
    from graphify.dedup import deduplicate_entities
    nodes = [
        {"id": "userservice", "label": "UserService"},
        {"id": "auth", "label": "Auth"},
    ]
    result_nodes, result_edges = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


# ── merge-graphs prefix ───────────────────────────────────────────────────────

def test_merge_graphs_prefixes_ids(tmp_path):
    """merge-graphs should prefix node IDs with repo name to avoid silent collision."""
    from graphify.build import prefix_graph_for_global
    from networkx.readwrite import json_graph as jg

    # Two graphs with same node ID
    G1 = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    G2 = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])

    repo1 = tmp_path / "repo1" / "graphify-out"
    repo2 = tmp_path / "repo2" / "graphify-out"
    repo1.mkdir(parents=True)
    repo2.mkdir(parents=True)

    g1_path = repo1 / "graph.json"
    g2_path = repo2 / "graph.json"
    _graph_to_json(G1, g1_path)
    _graph_to_json(G2, g2_path)

    # Simulate what merge-graphs now does (prefix before compose)
    graphs = []
    graph_paths = [g1_path, g2_path]
    for gp in graph_paths:
        data = json.loads(gp.read_text())
        if "links" not in data and "edges" in data:
            data = dict(data, links=data["edges"])
        try:
            G = jg.node_link_graph(data, edges="links")
        except TypeError:
            G = jg.node_link_graph(data)
        repo_tag = gp.parent.parent.name
        graphs.append(prefix_graph_for_global(G, repo_tag))

    merged = nx.Graph()
    for G in graphs:
        merged = nx.compose(merged, G)

    assert "repo1::userservice" in merged.nodes
    assert "repo2::userservice" in merged.nodes
    assert merged.number_of_nodes() == 2  # no silent collapse


def test_global_add_rewires_edges_to_deduplicated_externals(tmp_path):
    """Edges incident to an external node that gets deduplicated against an
    already-present external must be rewired to the existing node, not dropped."""
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    GA = _make_graph(
        [
            {"id": "moda", "label": "ModA", "source_file": "src/a.py"},
            {"id": "requests", "label": "requests"},
        ],
        [{"source": "moda", "target": "requests", "relation": "imports"}],
    )
    GB = _make_graph(
        [
            {"id": "modb", "label": "ModB", "source_file": "src/b.py"},
            {"id": "requests", "label": "requests"},
        ],
        [{"source": "modb", "target": "requests", "relation": "imports"}],
    )
    _graph_to_json(GA, g1)
    _graph_to_json(GB, g2)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add, _load_global_graph
        global_add(g1, "repoA")
        global_add(g2, "repoB")
        G = _load_global_graph()

    # repoB's external "requests" was deduplicated against repoA's
    assert "repoA::requests" in G.nodes
    assert "repoB::requests" not in G.nodes
    # repoA's edge is untouched
    assert G.has_edge("repoA::moda", "repoA::requests")
    # repoB's edge must be rewired to the existing external node, not dropped
    assert G.has_edge("repoB::modb", "repoA::requests")
    assert G.edges["repoB::modb", "repoA::requests"]["relation"] == "imports"


def test_global_add_rejects_oversized_source_graph(monkeypatch, tmp_path):
    """#F4: global_add must refuse to read a source graph.json that
    exceeds the size cap, rather than json.loads-ing it into memory."""
    import pytest

    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "src/x.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        with pytest.raises(ValueError, match="exceeds"):
            global_add(src_graph, "repoA")


# ── global_add_many ───────────────────────────────────────────────────────────

def test_global_add_many_matches_one_add_per_unit(tmp_path):
    """The acceptance criterion for the batch path: same inputs, same artifact.

    Sequential adds round-trip the global graph through JSON between every two units and
    run the cross-repo pass after each; the batch does neither. Nodes, node attributes,
    edges, edge attributes and the manifest all have to come out the same anyway.
    """
    from graphify.global_graph import global_add, global_add_many

    seq_sources = _write_batch_units(tmp_path / "seq")
    with _global_store(tmp_path / "seq-store") as (graph_path, manifest_path):
        for source_path, repo_tag in seq_sources:
            global_add(source_path, repo_tag)
        sequential = _read_store(graph_path, manifest_path)

    batch_sources = _write_batch_units(tmp_path / "batch")
    with _global_store(tmp_path / "batch-store") as (graph_path, manifest_path):
        global_add_many(batch_sources)
        batched = _read_store(graph_path, manifest_path)

    # The manifest records each source's absolute path, which differs by design here.
    for _, _, manifest in (sequential, batched):
        for entry in manifest["repos"].values():
            entry.pop("source_path", None)
    assert batched[0] == sequential[0]
    assert batched[1] == sequential[1]
    assert batched[2] == sequential[2]
    # The fixture exists to exercise the pass, so a run that resolves nothing proves nothing.
    assert any(d.get("_cross_repo_call") for d in batched[1].values()), batched[1]


def test_global_add_many_reports_per_unit_and_batch_level_counts(tmp_path):
    from graphify.global_graph import global_add_many

    sources = _write_batch_units(tmp_path)
    with _global_store(tmp_path / "store"):
        batch = global_add_many(sources)

    assert [r["repo_tag"] for r in batch["results"]] == ["repoA", "repoB", "repoC"]
    assert all(r["skipped"] is False for r in batch["results"])
    assert all(r["nodes_added"] > 0 for r in batch["results"])
    assert batch["cross_repo_calls"] == 1
    # A per-unit number would have to attribute the pass's output to one of the two repos
    # that produced it, so the count stays at the batch level.
    assert all("cross_repo_calls" not in r for r in batch["results"])


def test_global_add_many_dedups_a_later_units_external_against_an_earlier_one(tmp_path):
    """A stub of the same label composed by an earlier unit in the same batch has to be
    the one a later unit's edges attach to, exactly as when the two units arrive as two
    separate adds."""
    from graphify.global_graph import _load_global_graph, global_add_many

    sources = _write_batch_units(tmp_path)
    with _global_store(tmp_path / "store"):
        global_add_many(sources)
        G = _load_global_graph()

    assert "repoC::logging" not in G.nodes
    assert G.has_edge("repoC::worker", "repoA::logging")


def test_global_add_many_keeps_a_skipped_unit_in_position(tmp_path):
    from graphify.global_graph import _load_global_graph, global_add_many

    sources = _write_batch_units(tmp_path)
    with _global_store(tmp_path / "store"):
        global_add_many(sources[:1])
        before = {frozenset(e) for e in _load_global_graph().edges()}
        batch = global_add_many(sources)
        after = {frozenset(e) for e in _load_global_graph().edges()}

    assert [r["skipped"] for r in batch["results"]] == [True, False, False]
    assert batch["results"][0]["nodes_added"] == 0
    assert batch["results"][0]["nodes_removed"] == 0
    # A skipped unit must not be pruned and re-composed: its edges survive untouched.
    assert before <= after


def test_global_add_many_runs_the_cross_repo_pass_once(tmp_path):
    from graphify.global_graph import global_add_many

    sources = _write_batch_units(tmp_path)
    with _global_store(tmp_path / "store"):
        with patch("graphify.cross_repo_calls.link_cross_repo_member_calls",
                   return_value=7) as spy:
            batch = global_add_many(sources)

    assert spy.call_count == 1
    assert batch["cross_repo_calls"] == 7


def test_global_add_many_leaves_the_store_untouched_when_nothing_changed(tmp_path):
    """An unchanged batch must not read or rewrite the global graph. Loading it to discover
    there is nothing to do costs a full deserialize plus a full write of the same bytes."""
    from graphify.global_graph import global_add_many

    sources = _write_batch_units(tmp_path)
    with _global_store(tmp_path / "store") as (graph_path, _):
        global_add_many(sources)
        before = graph_path.stat().st_mtime_ns
        with patch("graphify.global_graph._load_global_graph") as load:
            batch = global_add_many(sources)

    assert load.call_count == 0
    assert graph_path.stat().st_mtime_ns == before
    assert [r["skipped"] for r in batch["results"]] == [True, True, True]
    assert batch["cross_repo_calls"] == 0


def test_global_add_many_rejects_one_tag_naming_two_sources(tmp_path):
    """Two sources under one tag would have the second prune the first, so the batch
    reports a graph half of which is missing. Refuse the input instead."""
    from graphify.global_graph import global_add_many

    sources = _write_batch_units(tmp_path)
    clashing = [sources[0], (sources[1][0], sources[0][1])]
    with _global_store(tmp_path / "store") as (graph_path, _):
        with pytest.raises(ValueError, match="two sources in one batch"):
            global_add_many(clashing)
    assert not graph_path.exists()


def test_global_add_many_reports_a_missing_source_the_way_one_add_does(tmp_path):
    """Hashing the source would raise on its own, with the OS message for a missing file.
    The batch is still the caller's own input, so it gets `global_add`'s wording."""
    from graphify.global_graph import global_add_many

    sources = _write_batch_units(tmp_path)
    with _global_store(tmp_path / "store") as (graph_path, manifest_path):
        with patch("graphify.build.prefix_graph_for_global") as compose:
            with pytest.raises(FileNotFoundError, match="graph not found"):
                global_add_many([*sources, (tmp_path / "absent" / "graph.json", "repoD")])

    assert compose.call_count == 0
    assert not graph_path.exists()
    assert not manifest_path.exists()


def test_global_add_many_checks_every_size_cap_before_composing_any(monkeypatch, tmp_path):
    """The batch writes only at the end, so a unit rejected late throws away every unit
    composed before it. The cap is a stat, so it can be paid for the whole batch up front."""
    from graphify.global_graph import global_add_many

    sources = _write_batch_units(tmp_path)
    oversized = tmp_path / "repoD" / "graph.json"
    oversized.parent.mkdir(parents=True, exist_ok=True)
    _graph_to_json(_make_graph([{"id": "d", "label": "D" * 4096, "source_file": "d.py"}]),
                   oversized)
    cap = max(p.stat().st_size for p, _ in sources) + 1
    assert oversized.stat().st_size > cap
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", cap)

    with _global_store(tmp_path / "store"):
        with patch("graphify.build.prefix_graph_for_global") as compose:
            with pytest.raises(ValueError, match="exceeds"):
                global_add_many([*sources, (oversized, "repoD")])

    assert compose.call_count == 0
