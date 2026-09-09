"""Tests for the global graph infrastructure (graphify/global_graph.py),
prefix/prune helpers in graphify/build.py, and the cross-repo guard in
graphify/dedup.py."""
from __future__ import annotations

import json
import pytest
import networkx as nx
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


# ── batched global add (#3438) ────────────────────────────────────────────────

def _patch_global(global_dir):
    """Context managers redirecting the global store into a tmp dir."""
    import contextlib

    stack = contextlib.ExitStack()
    stack.enter_context(patch("graphify.global_graph._GLOBAL_DIR", global_dir))
    stack.enter_context(
        patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json")
    )
    stack.enter_context(
        patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json")
    )
    return stack


def _graph_fingerprint(G):
    """Order-independent snapshot of a graph, for equivalence assertions."""
    nodes = sorted(
        (n, tuple(sorted((k, repr(v)) for k, v in d.items())))
        for n, d in G.nodes(data=True)
    )
    edges = sorted(
        (tuple(sorted((u, v))), tuple(sorted((k, repr(val)) for k, val in d.items())))
        for u, v, d in G.edges(data=True)
    )
    return nodes, edges


def _write_repo_graph(tmp_path, name, external=None):
    """A one-module repo graph, optionally importing a shared external lib."""
    nodes = [{"id": f"{name}mod", "label": f"{name}Mod", "source_file": f"src/{name}.py"}]
    edges = []
    if external:
        nodes.append({"id": external, "label": external})
        edges.append({"source": f"{name}mod", "target": external, "relation": "imports"})
    path = tmp_path / f"{name}.json"
    _graph_to_json(_make_graph(nodes, edges), path)
    return path


def test_global_add_many_adds_multiple_repos(tmp_path):
    g1 = _write_repo_graph(tmp_path, "a")
    g2 = _write_repo_graph(tmp_path, "b")
    g3 = _write_repo_graph(tmp_path, "c")

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        batch = global_add_many([(g1, "repoA"), (g2, "repoB"), (g3, "repoC")])
        G = _load_global_graph()

    assert [r["repo_tag"] for r in batch["results"]] == ["repoA", "repoB", "repoC"]
    assert all(r["skipped"] is False for r in batch["results"])
    assert batch["saved"] is True
    assert {"repoA::amod", "repoB::bmod", "repoC::cmod"} <= set(G.nodes)
    manifest = json.loads((global_dir / "global-manifest.json").read_text())
    assert set(manifest["repos"]) == {"repoA", "repoB", "repoC"}


def test_global_add_many_matches_sequential_adds(tmp_path):
    """The whole point of the batch: same inputs, same resulting graph."""
    seq_dir = tmp_path / "seq"
    batch_dir = tmp_path / "batch"
    graphs = [
        (_write_repo_graph(tmp_path, "a", external="requests"), "repoA"),
        (_write_repo_graph(tmp_path, "b", external="requests"), "repoB"),
        (_write_repo_graph(tmp_path, "c", external="numpy"), "repoC"),
    ]

    with _patch_global(seq_dir):
        from graphify.global_graph import global_add, _load_global_graph
        for src, tag in graphs:
            global_add(src, tag)
        sequential = _load_global_graph()

    with _patch_global(batch_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        global_add_many(graphs)
        batched = _load_global_graph()

    assert _graph_fingerprint(batched) == _graph_fingerprint(sequential)


def test_global_add_many_dedups_externals_across_batch(tmp_path):
    """Two repos in one batch importing the same library share one external node,
    with both edges rewired onto it - as they would if added one at a time."""
    g1 = _write_repo_graph(tmp_path, "a", external="requests")
    g2 = _write_repo_graph(tmp_path, "b", external="requests")

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        global_add_many([(g1, "repoA"), (g2, "repoB")])
        G = _load_global_graph()

    assert "repoA::requests" in G.nodes
    assert "repoB::requests" not in G.nodes
    assert G.has_edge("repoA::amod", "repoA::requests")
    assert G.has_edge("repoB::bmod", "repoA::requests")


def test_global_add_many_replaces_existing_repo(tmp_path):
    """A repo already in the global graph is pruned and replaced, not duplicated."""
    global_dir = tmp_path / ".graphify"
    g1 = _write_repo_graph(tmp_path, "a")
    g2 = _write_repo_graph(tmp_path, "b")

    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        global_add_many([(g1, "repoA")])

        # repoA's graph now has a different module; re-adding must drop the old one
        revised = tmp_path / "a2.json"
        _graph_to_json(
            _make_graph([{"id": "amod2", "label": "AMod2", "source_file": "src/a2.py"}]),
            revised,
        )
        batch = global_add_many([(revised, "repoA"), (g2, "repoB")])
        G = _load_global_graph()

    assert batch["results"][0]["nodes_removed"] == 1
    assert "repoA::amod" not in G.nodes
    assert "repoA::amod2" in G.nodes
    assert "repoB::bmod" in G.nodes


def test_global_add_many_skips_unchanged_repos(tmp_path):
    """An unchanged repo is reported skipped; an all-skipped batch saves nothing."""
    g1 = _write_repo_graph(tmp_path, "a")
    g2 = _write_repo_graph(tmp_path, "b")

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many
        global_add_many([(g1, "repoA")])
        batch = global_add_many([(g1, "repoA"), (g2, "repoB")])
        again = global_add_many([(g1, "repoA"), (g2, "repoB")])

    assert batch["results"][0]["skipped"] is True
    assert batch["results"][1]["skipped"] is False
    assert all(r["skipped"] for r in again["results"])
    assert again["saved"] is False


def test_global_add_many_empty_batch(tmp_path):
    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many
        batch = global_add_many([])

    assert batch["results"] == []
    assert batch["cross_repo_calls"] == 0
    assert batch["saved"] is False
    # Nothing was written: an empty batch must not create a global store.
    assert not (global_dir / "global-graph.json").exists()


def test_global_add_many_single_item_batch(tmp_path):
    g1 = _write_repo_graph(tmp_path, "a")
    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        batch = global_add_many([(g1, "repoA")])
        G = _load_global_graph()

    assert len(batch["results"]) == 1
    assert batch["results"][0]["nodes_added"] == 1
    assert "repoA::amod" in G.nodes


def test_global_add_many_missing_source_raises_before_writing(tmp_path):
    """A bad path in the batch fails up front, leaving the global graph untouched."""
    g1 = _write_repo_graph(tmp_path, "a")
    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many
        with pytest.raises(FileNotFoundError):
            global_add_many([(g1, "repoA"), (tmp_path / "nope.json", "repoB")])

    assert not (global_dir / "global-graph.json").exists()


def test_global_add_many_records_manifest_metadata(tmp_path):
    g1 = _write_repo_graph(tmp_path, "a", external="requests")
    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many
        global_add_many([(g1, "repoA")])

    entry = json.loads((global_dir / "global-manifest.json").read_text())["repos"]["repoA"]
    assert entry["source_path"] == str(g1.resolve())
    assert entry["node_count"] == 2
    assert entry["edge_count"] == 1
    assert entry["source_hash"]
    assert entry["added_at"]


def test_global_add_many_links_cross_repo_calls_within_batch(tmp_path):
    """A call parked in one repo is answered by a type in another repo added in
    the same batch - the resolve pass runs once, after every repo is merged."""
    caller = tmp_path / "caller.json"
    callee = tmp_path / "callee.json"
    _graph_to_json(
        _make_graph([{
            "id": "main",
            "label": "main",
            "source_file": "src/Main.java",
            "metadata": {"unresolved_calls": [
                {"lang": "java", "receiver_type": "Greeter", "callee": "greet", "line": 4}
            ]},
        }]),
        caller,
    )
    _graph_to_json(
        _make_graph(
            [
                {"id": "greeter", "label": "Greeter", "source_file": "src/Greeter.java",
                 "_callable_class": True},
                {"id": "greet", "label": ".greet()", "source_file": "src/Greeter.java"},
            ],
            [{"source": "greeter", "target": "greet", "relation": "method"}],
        ),
        callee,
    )

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        batch = global_add_many([(caller, "repoA"), (callee, "repoB")])
        G = _load_global_graph()

    assert batch["cross_repo_calls"] == 1
    assert G.has_edge("repoA::main", "repoB::greet")
    # The pass reads the finished graph, so its output belongs to the batch and is
    # not divided over the units that produced it.
    assert all("cross_repo_calls" not in r for r in batch["results"])


def test_global_add_many_loads_and_saves_once_per_batch(tmp_path):
    """The performance contract: one load and one save regardless of batch size."""
    graphs = [(_write_repo_graph(tmp_path, name), f"repo{name.upper()}")
              for name in ("a", "b", "c", "d")]

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        import graphify.global_graph as gg
        with patch.object(gg, "_load_global_graph", wraps=gg._load_global_graph) as load, \
             patch.object(gg, "_save_global_graph", wraps=gg._save_global_graph) as save:
            gg.global_add_many(graphs)

    assert load.call_count == 1
    assert save.call_count == 1


def test_global_add_delegates_to_batch(tmp_path):
    """global_add keeps its single-repo return shape through the batched path."""
    g1 = _write_repo_graph(tmp_path, "a")
    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add
        result = global_add(g1, "repoA")

    assert set(result) == {"repo_tag", "nodes_added", "nodes_removed", "skipped",
                           "cross_repo_calls"}
    assert result["repo_tag"] == "repoA"
    assert result["skipped"] is False


# ── batch robustness: partial failure, duplicate tags, index behaviour ────────

def _write_bad_graph(tmp_path, name="bad.json"):
    path = tmp_path / name
    path.write_text("{ this is not valid json", encoding="utf-8")
    return path


def test_global_add_many_aborts_whole_batch_on_bad_source(tmp_path):
    """Default policy: one unreadable graph means nothing is written at all, so the
    store is never left holding some of a batch the caller believes failed."""
    g1 = _write_repo_graph(tmp_path, "a")
    g2 = _write_repo_graph(tmp_path, "b")
    bad = _write_bad_graph(tmp_path)

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many
        with pytest.raises(json.JSONDecodeError):
            global_add_many([(g1, "repoA"), (bad, "repoBad"), (g2, "repoC")])

    assert not (global_dir / "global-graph.json").exists()
    assert not (global_dir / "global-manifest.json").exists()


def test_global_add_many_abort_leaves_existing_store_untouched(tmp_path):
    """A batch that aborts must not disturb repos already in the store."""
    g1 = _write_repo_graph(tmp_path, "a")
    g2 = _write_repo_graph(tmp_path, "b")
    bad = _write_bad_graph(tmp_path)

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        global_add_many([(g1, "repoA")])
        before = (global_dir / "global-graph.json").read_bytes()
        with pytest.raises(json.JSONDecodeError):
            global_add_many([(g2, "repoB"), (bad, "repoBad")])
        after = (global_dir / "global-graph.json").read_bytes()
        G = _load_global_graph()

    assert after == before
    assert "repoB::bmod" not in G.nodes


def test_global_add_many_skip_policy_commits_the_good_units(tmp_path):
    """on_error='skip' restores what a loop of `global add` gave for free: one bad
    graph costs you that repo, not the whole batch."""
    g1 = _write_repo_graph(tmp_path, "a")
    g2 = _write_repo_graph(tmp_path, "b")
    bad = _write_bad_graph(tmp_path)

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        batch = global_add_many(
            [(g1, "repoA"), (bad, "repoBad"), (g2, "repoC")], on_error="skip"
        )
        G = _load_global_graph()

    assert batch["saved"] is True
    assert batch["results"][0]["error"] is None
    assert "JSONDecodeError" in batch["results"][1]["error"]
    assert batch["results"][2]["error"] is None
    assert "repoA::amod" in G.nodes
    assert "repoC::bmod" in G.nodes
    # The failed unit contributed nothing, to neither graph nor manifest.
    assert not any(n.startswith("repoBad::") for n in G.nodes)
    manifest = json.loads((global_dir / "global-manifest.json").read_text())
    assert "repoBad" not in manifest["repos"]


def test_global_add_many_skip_policy_matches_sequential_partial_success(tmp_path):
    """The point of the skip policy: the same inputs that a per-repo loop survives
    produce the same store through one batch."""
    seq_dir = tmp_path / "seq"
    batch_dir = tmp_path / "batch"
    g1 = _write_repo_graph(tmp_path, "a")
    g2 = _write_repo_graph(tmp_path, "b")
    bad = _write_bad_graph(tmp_path)
    units = [(g1, "repoA"), (bad, "repoBad"), (g2, "repoC")]

    with _patch_global(seq_dir):
        from graphify.global_graph import global_add, _load_global_graph
        for src, tag in units:
            try:
                global_add(src, tag)
            except json.JSONDecodeError:
                pass
        sequential = _load_global_graph()

    with _patch_global(batch_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        global_add_many(units, on_error="skip")
        batched = _load_global_graph()

    assert _graph_fingerprint(batched) == _graph_fingerprint(sequential)


def test_global_add_many_skip_policy_saves_nothing_when_all_fail(tmp_path):
    bad1 = _write_bad_graph(tmp_path, "bad1.json")
    bad2 = _write_bad_graph(tmp_path, "bad2.json")

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many
        batch = global_add_many([(bad1, "repoX"), (bad2, "repoY")], on_error="skip")

    assert batch["saved"] is False
    assert all(r["error"] for r in batch["results"])
    assert not (global_dir / "global-graph.json").exists()


def test_global_add_many_rejects_invalid_on_error_policy(tmp_path):
    g1 = _write_repo_graph(tmp_path, "a")
    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many
        with pytest.raises(ValueError, match="on_error"):
            global_add_many([(g1, "repoA")], on_error="continue")


def test_global_add_many_rejects_one_tag_naming_two_sources(tmp_path):
    """Two sources under one tag: the second prunes the first, so the batch would
    report nodes for a repo whose graph is not the one in the store."""
    g1 = _write_repo_graph(tmp_path, "a")
    g2 = _write_repo_graph(tmp_path, "b")

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many
        with pytest.raises(ValueError, match="two sources in one batch"):
            global_add_many([(g1, "repoA"), (g2, "repoA")])

    assert not (global_dir / "global-graph.json").exists()


def test_global_add_many_scans_for_externals_once_per_batch(tmp_path):
    """The external-label index is threaded through the loop, not rebuilt per unit:
    rebuilding it rescans the whole graph K times, which is the quadratic term this
    function exists to remove."""
    import graphify.global_graph as gg

    graphs = [(_write_repo_graph(tmp_path, name, external="requests"), f"repo{name.upper()}")
              for name in ("a", "b", "c", "d")]

    global_dir = tmp_path / ".graphify"
    with _patch_global(global_dir):
        with patch.object(gg, "_external_label_index",
                          wraps=gg._external_label_index) as spy:
            gg.global_add_many(graphs)

    # One scan for the batch. No unit prunes anything here (all four are new), so
    # nothing may invalidate the index mid-loop.
    assert spy.call_count == 1


def test_global_add_many_rebuilds_index_after_a_prune_removes_externals(tmp_path):
    """A prune can delete stubs the old revision of a repo owned. If the index kept
    pointing at them, a later unit's edge would be rewired onto a node that is no
    longer in the graph."""
    global_dir = tmp_path / ".graphify"
    a1 = _write_repo_graph(tmp_path, "a", external="requests")
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        global_add_many([(a1, "repoA")])

        # repoA no longer imports requests, so re-adding it prunes that stub.
        a2 = tmp_path / "a2.json"
        _graph_to_json(
            _make_graph([{"id": "amod", "label": "AMod", "source_file": "src/a.py"}]), a2
        )
        b = _write_repo_graph(tmp_path, "b", external="requests")
        global_add_many([(a2, "repoA"), (b, "repoB")])
        G = _load_global_graph()

    # repoA's stub is gone; repoB's must be a live node, and its edge must land on it.
    assert "repoA::requests" not in G.nodes
    assert "repoB::requests" in G.nodes
    assert G.has_edge("repoB::bmod", "repoB::requests")
    # No edge may reference a node that is not in the graph.
    assert all(u in G.nodes and v in G.nodes for u, v in G.edges())


# ── CLI repo-tag inference ───────────────────────────────────────────────────

@pytest.mark.parametrize("path_str, expected", [
    # The conventional layout: the grandparent names the repo.
    ("/work/myrepo/graphify-out/graph.json", "myrepo"),
    # No graphify-out in between: the grandparent still names it.
    ("/work/myrepo/graph.json", "myrepo"),
    # Output directory as grandparent: skipped, the parent names the repo.
    ("/myrepo/graphify-out/nested/graph.json", "nested"),
])
def test_infer_repo_tag_uses_directory_names(path_str, expected):
    from pathlib import PurePosixPath
    from graphify.cli import _infer_repo_tag

    assert _infer_repo_tag(PurePosixPath(path_str)) == expected


@pytest.mark.parametrize("path_str", [
    "/graph.json",            # grandparent and parent are the filesystem root
    "graph.json",             # bare relative filename
    "/graphify-out/graph.json",  # only a generic directory to draw on
])
def test_infer_repo_tag_falls_back_to_the_stem(path_str):
    """These are exactly the shapes that produced an empty tag before: the
    grandparent contributes nothing, so the file's own stem has to answer."""
    from pathlib import PurePosixPath
    from graphify.cli import _infer_repo_tag

    assert _infer_repo_tag(PurePosixPath(path_str)) == "graph"


def test_infer_repo_tag_never_returns_empty():
    """An empty tag would prune by "" and register the repo under a name no later
    add can address, so no input may produce one."""
    from pathlib import PurePosixPath
    from graphify.cli import _infer_repo_tag

    for path_str in ("/graph.json", "graph.json", "a/graph.json", "/a/b/graph.json",
                     "/graphify-out/graph.json", "out/graph.json", "./graph.json"):
        assert _infer_repo_tag(PurePosixPath(path_str)), path_str


def test_global_add_many_rejects_oversized_source_before_composing(monkeypatch, tmp_path):
    """The size cap is checked for every unit up front, so an oversized graph late
    in the batch does not first cost the merge of every unit ahead of it."""
    g1 = _write_repo_graph(tmp_path, "a")
    g2 = _write_repo_graph(tmp_path, "b")

    global_dir = tmp_path / ".graphify"
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)
    with _patch_global(global_dir):
        import graphify.global_graph as gg
        with patch.object(gg, "_load_global_graph", wraps=gg._load_global_graph) as load:
            with pytest.raises(ValueError, match="exceeds"):
                gg.global_add_many([(g1, "repoA"), (g2, "repoB")])

    # Rejected before the global graph was even read.
    assert load.call_count == 0
    assert not (global_dir / "global-graph.json").exists()


def test_global_add_many_skip_policy_survives_an_oversized_source(monkeypatch, tmp_path):
    """Under --keep-going an oversized unit is reported and the rest still land."""
    small = _write_repo_graph(tmp_path, "a")
    big = tmp_path / "big.json"
    _graph_to_json(
        _make_graph([{"id": f"n{i}", "label": f"N{i}", "source_file": f"s/{i}.py"}
                     for i in range(400)]),
        big,
    )
    # The cap must sit above the small unit *and* above the global graph the batch
    # writes and re-reads, but below the oversized unit.
    cap = big.stat().st_size // 2
    assert small.stat().st_size < cap < big.stat().st_size

    global_dir = tmp_path / ".graphify"
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", cap)
    with _patch_global(global_dir):
        from graphify.global_graph import global_add_many, _load_global_graph
        batch = global_add_many([(big, "repoBig"), (small, "repoA")], on_error="skip")
        G = _load_global_graph()

    assert "exceeds" in batch["results"][0]["error"]
    assert batch["results"][1]["error"] is None
    assert "repoA::amod" in G.nodes
    assert not any(n.startswith("repoBig::") for n in G.nodes)
