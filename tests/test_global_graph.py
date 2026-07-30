"""Tests for the global graph infrastructure (graphify/global_graph.py),
prefix/prune helpers in graphify/build.py, and the cross-repo guard in
graphify/dedup.py. FalkorDB-backed."""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch


# ── build.py helpers ──────────────────────────────────────────────────────────

def test_prefix_graph_preserves_label(store, make_store):
    from graphify.build import prefix_graph_for_global
    store.add_node("userservice", label="UserService", source_file="src/user.py", file_type="code")
    target = make_store()
    H = prefix_graph_for_global(store, "repoA", target)
    assert "repoA::userservice" in H.nodes
    assert "userservice" not in H.nodes
    assert H.nodes["repoA::userservice"]["label"] == "UserService"


def test_prefix_graph_sets_repo_and_local_id(store, make_store):
    from graphify.build import prefix_graph_for_global
    store.add_node("userservice", label="UserService", file_type="code")
    target = make_store()
    H = prefix_graph_for_global(store, "repoA", target)
    data = H.nodes["repoA::userservice"]
    assert data["repo"] == "repoA"
    assert data["local_id"] == "userservice"


def test_prefix_graph_rewrites_edges(store, make_store):
    from graphify.build import prefix_graph_for_global
    store.add_nodes_from([("a", {"label": "A", "file_type": "code"}), ("b", {"label": "B", "file_type": "code"})])
    store.add_edge("a", "b", relation="calls")
    target = make_store()
    H = prefix_graph_for_global(store, "repo1", target)
    assert H.has_edge("repo1::a", "repo1::b")
    assert not H.has_edge("a", "b")


def test_prefix_graph_preserves_edge_direction(store, make_store):
    """#2261: prefixing must not lose the stored caller->callee orientation.

    v8 pins this via the _src/_tgt markers that undirected NetworkX storage
    needed to recover direction. Edges here are stored in their native
    source->target orientation, so the guarantee is asserted directly: after
    prefixing, the edge still runs rota -> collections and not the reverse.
    """
    from graphify.build import prefix_graph_for_global
    store.add_nodes_from([
        ("rota", {"label": "rota.js", "file_type": "code"}),
        ("collections", {"label": "collections.js", "file_type": "code"}),
    ])
    store.add_edge("rota", "collections", relation="imports_from")
    H = prefix_graph_for_global(store, "repoA", make_store())
    assert H.has_directed_edge("repoA::rota", "repoA::collections")
    assert not H.has_directed_edge("repoA::collections", "repoA::rota")


def test_prune_repo_removes_correct_nodes(store):
    from graphify.build import prune_repo_from_graph
    store.add_nodes_from([
        ("repoA::userservice", {"repo": "repoA", "label": "UserService", "file_type": "code"}),
        ("repoB::userservice", {"repo": "repoB", "label": "UserService", "file_type": "code"}),
        ("repoA::auth", {"repo": "repoA", "label": "Auth", "file_type": "code"}),
    ])
    removed = prune_repo_from_graph(store, "repoA")
    assert removed == 2
    assert "repoB::userservice" in store.nodes
    assert "repoA::userservice" not in store.nodes
    assert "repoA::auth" not in store.nodes


def test_prune_repo_returns_zero_if_not_present(store):
    from graphify.build import prune_repo_from_graph
    store.add_node("repoA::x", repo="repoA", file_type="code")
    removed = prune_repo_from_graph(store, "repoB")
    assert removed == 0
    assert store.number_of_nodes() == 1


# ── global_graph.py ───────────────────────────────────────────────────────────

@pytest.fixture()
def global_env(tmp_path, falkordb_uri):
    """Isolate the global graph to a unique FalkorDB name + temp manifest dir."""
    import os
    from graphify.store import GraphStore
    global_dir = tmp_path / ".graphify"
    name = f"pytest_global_{os.getpid()}_{id(tmp_path)}"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"), \
         patch("graphify.global_graph._GLOBAL_NAME", name):
        gs = GraphStore(graph_name=name, uri=falkordb_uri)
        gs.clear()
        try:
            yield global_dir
        finally:
            try:
                gs.clear()
            except Exception:
                pass


def test_global_add_creates_global_graph(tmp_path, seed_graph, global_env):
    seed_graph(tmp_path, [{"id": "userservice", "label": "UserService", "source_file": "src/user.py", "file_type": "code"}])
    from graphify.global_graph import global_add
    result = global_add(tmp_path / "graph.json", "repoA")

    assert result["skipped"] is False
    assert result["nodes_added"] > 0
    manifest = json.loads((global_env / "global-manifest.json").read_text())
    assert "repoA" in manifest["repos"]


def test_global_add_skip_on_unchanged_hash(tmp_path, seed_graph, global_env):
    seed_graph(tmp_path, [{"id": "userservice", "label": "UserService", "source_file": "src/user.py", "file_type": "code"}])
    from graphify.global_graph import global_add
    global_add(tmp_path / "graph.json", "repoA")
    result2 = global_add(tmp_path / "graph.json", "repoA")
    assert result2["skipped"] is True


def test_global_add_two_repos_no_collision(tmp_path, seed_graph, global_env):
    d1 = tmp_path / "r1"
    d2 = tmp_path / "r2"
    d1.mkdir(); d2.mkdir()
    seed_graph(d1, [{"id": "userservice", "label": "UserService", "source_file": "src/user.py", "file_type": "code"}])
    seed_graph(d2, [{"id": "userservice", "label": "UserService", "source_file": "src/user.py", "file_type": "code"}])
    from graphify.global_graph import global_add, _load_global_graph
    global_add(d1 / "graph.json", "repoA")
    global_add(d2 / "graph.json", "repoB")
    G = _load_global_graph()
    assert "repoA::userservice" in G.nodes
    assert "repoB::userservice" in G.nodes
    assert G.number_of_nodes() == 2  # no silent merge


def test_global_remove(tmp_path, seed_graph, global_env):
    seed_graph(tmp_path, [{"id": "userservice", "label": "UserService", "source_file": "src/user.py", "file_type": "code"}])
    from graphify.global_graph import global_add, global_remove, global_list
    global_add(tmp_path / "graph.json", "repoA")
    removed = global_remove("repoA")
    assert removed > 0
    assert "repoA" not in global_list()


def test_global_remove_unknown_tag_raises(tmp_path, global_env):
    from graphify.global_graph import global_remove
    with pytest.raises(KeyError):
        global_remove("nonexistent")


def test_global_add_collision_warning(tmp_path, seed_graph, global_env, capsys):
    d1 = tmp_path / "r1"
    d2 = tmp_path / "r2"
    d1.mkdir(); d2.mkdir()
    seed_graph(d1, [{"id": "x", "label": "X", "source_file": "x.py", "file_type": "code"}])
    seed_graph(d2, [{"id": "x", "label": "X", "source_file": "x.py", "file_type": "code"}])
    from graphify.global_graph import global_add
    global_add(d1 / "graph.json", "myrepo")
    global_add(d2 / "graph.json", "myrepo")  # different source path, same tag
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower() or "warning" in captured.out.lower()


# ── dedup guard (needs datasketch) ─────────────────────────────────────────────

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
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


def test_dedup_ok_with_no_repo_attr():
    from graphify.dedup import deduplicate_entities
    nodes = [
        {"id": "userservice", "label": "UserService"},
        {"id": "auth", "label": "Auth"},
    ]
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


# ── merge-graphs prefix (plain-dict node-link, no NetworkX) ────────────────────

def test_merge_graphs_prefixes_ids():
    """merge-graphs prefixes node IDs with repo name to avoid silent collision."""
    from graphify.graphjson import prefix_node_link, merge_node_link, node_count

    g1 = {"nodes": [{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}], "links": []}
    g2 = {"nodes": [{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}], "links": []}
    merged = merge_node_link([prefix_node_link(g1, "repo1"), prefix_node_link(g2, "repo2")])
    ids = {n["id"] for n in merged["nodes"]}
    assert "repo1::userservice" in ids
    assert "repo2::userservice" in ids
    assert node_count(merged) == 2  # no silent collapse
