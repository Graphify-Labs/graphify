"""Tests for the global graph infrastructure (graphify/global_graph.py),
prefix/prune helpers in graphify/build.py, and the cross-repo guard in
graphify/dedup.py."""
from __future__ import annotations

import json
import os
import pytest
import networkx as nx
from pathlib import Path
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


# ── #3100: community offset and shared type linking parity with merge-graphs ──

def test_global_add_offsets_community_ids_across_repos(tmp_path):
    """merge-graphs already offsets each input's community ids into a shared
    id space (#3014); global_add builds the same kind of store with the same
    prefixer but kept the default (no) offset, so two repos both numbering
    their own communities from 0 collided in the merged store -- worst of
    all at id 0, which every repo starts numbering from."""
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    G1 = _make_graph([
        {"id": "a", "label": "A", "source_file": "a.py", "community": 0},
        {"id": "b", "label": "B", "source_file": "b.py", "community": 1},
    ])
    G2 = _make_graph([
        {"id": "c", "label": "C", "source_file": "c.py", "community": 0},
        {"id": "d", "label": "D", "source_file": "d.py", "community": 1},
    ])
    _graph_to_json(G1, g1)
    _graph_to_json(G2, g2)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add, _load_global_graph
        global_add(g1, "repoA")
        global_add(g2, "repoB")
        G = _load_global_graph()

    by_repo: dict[str, set[int]] = {}
    for _, data in G.nodes(data=True):
        by_repo.setdefault(data["repo"], set()).add(data["community"])
    assert by_repo["repoA"].isdisjoint(by_repo["repoB"]), (
        f"community ids collide across repos: {by_repo}"
    )


def test_global_add_links_shared_type_declarations(tmp_path):
    """merge-graphs already links identically declared types across repos so
    a traversal can cross the repo boundary (#3007); global_add never called
    that pass, so an incrementally built store held zero same_type_as edges
    no matter how many repos actually shared a type."""
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    shared = {
        "id": "contracttype", "label": "ContractType", "source_file": "models.cs",
        "_callable_class": True, "metadata": {"namespace": "Acme.Contracts"},
    }
    G1 = _make_graph([shared])
    G2 = _make_graph([shared])
    _graph_to_json(G1, g1)
    _graph_to_json(G2, g2)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add, _load_global_graph
        first = global_add(g1, "repoA")
        second = global_add(g2, "repoB")
        G = _load_global_graph()

    assert first["shared_type_links"] == 0  # nothing to link against yet
    assert second["shared_type_links"] == 1
    assert G.has_edge("repoA::contracttype", "repoB::contracttype")
    assert G["repoA::contracttype"]["repoB::contracttype"]["relation"] == "same_type_as"


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


def test_global_add_updates_manifest_path_after_a_same_content_repoint(tmp_path, capsys):
    """Review finding: a repo tag re-pointed at a new path with identical
    content took the hash-match skip return before the manifest entry's
    source_path (and mtime/size/ctime/indexed_at) were ever refreshed to the
    new location. Left unfixed, that stale source_path can never match the
    resolved path again, so the fast stat path is permanently defeated for
    this tag (every future add re-reads and re-hashes), and the "previously
    pointed to" warning reprints on every subsequent call forever instead of
    the single time it is meant to."""
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "x.py"}])
    _graph_to_json(G, g1)
    _graph_to_json(G, g2)  # identical content, different path

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add, _load_manifest
        global_add(g1, "myrepo")
        global_add(g2, "myrepo")  # repoint, same content -> hash-match skip
        capsys.readouterr()  # clear the repoint warning

        manifest = _load_manifest()
        assert manifest["repos"]["myrepo"]["source_path"] == str(g2.resolve())

        global_add(g2, "myrepo")  # same tag, same path again

    captured = capsys.readouterr()
    assert "warning" not in captured.err.lower(), (
        "the repoint warning must not reprint once the manifest reflects "
        "the current path"
    )


def test_global_add_rejects_a_file_grown_past_the_cap_after_the_stat_check(tmp_path, monkeypatch):
    """Review finding: the pre-read size cap check is stat-based, so a file
    replaced with a larger one between that check and the actual read()
    just below it is never re-confirmed against the cap. A post-read length
    check closes that window before the much more expensive JSON parse and
    graph merge run on an oversized payload."""
    import pytest

    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "src/x.py"}])
    _graph_to_json(G, src_graph)
    actual_size = src_graph.stat().st_size

    global_dir = tmp_path / ".graphify"
    # Simulate the TOCTOU: the pre-read stat check is bypassed entirely (as
    # if it had passed against a smaller file that was then swapped out),
    # while the real cap stays below the file's actual size.
    monkeypatch.setattr("graphify.security.check_graph_file_size_cap", lambda p: None)
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", actual_size - 1)
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        with pytest.raises(ValueError, match="exceeds"):
            global_add(src_graph, "repoA")


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


def test_global_add_skip_on_unchanged_hash_survives_a_later_size_cap_drop(tmp_path, monkeypatch):
    """Review finding: reordering the size cap check ahead of the unchanged
    hash skip check (to consolidate hashing and parsing into a single read)
    made an already tracked, unchanged graph start erroring on every later
    call once the file (or a lowered GRAPHIFY_MAX_GRAPH_BYTES) crossed the
    cap, instead of continuing to skip -- the cap was never reached at all
    on that path before. Skip must still win when nothing changed, even if
    the file would now fail the cap on its own."""
    import pytest

    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "src/x.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add

        # First add succeeds while the file is well under the cap.
        result1 = global_add(src_graph, "repoA")
        assert result1["skipped"] is False

        # The cap drops below the (unchanged) file's size -- a later call
        # for the SAME, untouched file must still skip, not raise.
        monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)
        result2 = global_add(src_graph, "repoA")
        assert result2["skipped"] is True

        # A genuinely different (still oversized) file for the same repo
        # must still be rejected -- the cap is not bypassed entirely.
        _graph_to_json(
            _make_graph([{"id": "y", "label": "Y", "source_file": "src/y.py"}]), src_graph
        )
        with pytest.raises(ValueError, match="exceeds"):
            global_add(src_graph, "repoA")


def test_global_add_never_reads_a_new_oversized_file_into_memory(tmp_path, monkeypatch):
    """Review finding: the size cap exists to fail fast before a multi-GiB
    file is read into memory, but hashing source_path (to check the
    unchanged skip) read its full bytes before the cap ever ran, defeating
    it for exactly the case that matters most -- a new or genuinely changed
    oversized file, which has no prior manifest entry to skip via. The cap
    must be checked, and must reject, before a single byte of such a file
    is read."""
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "src/x.py"}])
    _graph_to_json(G, src_graph)

    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)

    reads = []
    orig_read_bytes = Path.read_bytes

    def counting_read_bytes(self, *a, **kw):
        if self == src_graph:
            reads.append("bytes")
        return orig_read_bytes(self, *a, **kw)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        with pytest.raises(ValueError, match="exceeds"):
            global_add(src_graph, "repoA")

    assert reads == [], (
        f"an oversized, never-before-tracked source file must be rejected "
        f"by the cap before any read of its bytes, got {reads}"
    )


def test_global_add_skips_a_legacy_manifest_entry_that_becomes_oversized(tmp_path, monkeypatch):
    """Review finding: a manifest entry written before the mtime/size fields
    existed (every manifest from before this fix) has no stat baseline for
    the fast path, so it fell straight through to the size cap and errored
    on an unchanged file that merely became oversized -- exactly the
    regression the fast path exists to prevent, just for the subset of
    manifests that predate it. A streaming hash (bounded memory regardless
    of size) must still recognize the file as unchanged and skip."""
    import hashlib

    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "src/x.py"}])
    _graph_to_json(G, src_graph)
    content = src_graph.read_bytes()
    legacy_hash = hashlib.sha256(content).hexdigest()[:16]

    global_dir = tmp_path / ".graphify"
    global_dir.mkdir()
    (global_dir / "global-manifest.json").write_text(json.dumps({
        "version": 1,
        "repos": {
            "repoA": {
                "added_at": "2020-01-01T00:00:00+00:00",
                "source_path": str(src_graph.resolve()),
                "node_count": 1,
                "edge_count": 0,
                "source_hash": legacy_hash,
                # No source_mtime_ns/source_size: predates this fix.
            }
        },
    }))

    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)

    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        result = global_add(src_graph, "repoA")

    assert result["skipped"] is True, (
        "an unchanged file tracked by a legacy (pre-stat-fields) manifest "
        "entry must still skip, not error, once it becomes oversized"
    )


def test_global_add_rejects_a_legacy_manifest_entry_with_changed_oversized_content(
    tmp_path, monkeypatch
):
    """Companion to the finding above: a legacy manifest entry whose file
    genuinely changed (not just became oversized) must still be rejected by
    the cap -- the streaming-hash fallback only rescues a truly unchanged
    file, it does not bypass the cap for new content."""
    import hashlib

    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "src/x.py"}])
    _graph_to_json(G, src_graph)
    stale_hash = hashlib.sha256(b"not the current content").hexdigest()[:16]

    global_dir = tmp_path / ".graphify"
    global_dir.mkdir()
    (global_dir / "global-manifest.json").write_text(json.dumps({
        "version": 1,
        "repos": {
            "repoA": {
                "added_at": "2020-01-01T00:00:00+00:00",
                "source_path": str(src_graph.resolve()),
                "node_count": 1,
                "edge_count": 0,
                "source_hash": stale_hash,
            }
        },
    }))

    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)

    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        with pytest.raises(ValueError, match="exceeds"):
            global_add(src_graph, "repoA")


def test_global_add_does_not_skip_a_different_file_with_matching_stat(tmp_path):
    """Review finding: the mtime/size fast path checked only the stat pair,
    never the source path itself. A repo_tag re-pointed at a genuinely
    different file that happens to share the old file's mtime and size (a
    real possibility with cp -p/rsync -a/checkout-preserved timestamps) must
    never fast-skip on stat coincidence alone, or the store silently keeps
    stale data with no warning."""
    src_a = tmp_path / "a.json"
    src_b = tmp_path / "b.json"
    G_a = _make_graph([{"id": "old", "label": "Old", "source_file": "old.py"}])
    G_b = _make_graph([{"id": "new", "label": "New", "source_file": "new.py"}])
    _graph_to_json(G_a, src_a)
    _graph_to_json(G_b, src_b)

    # Force identical size (pad the shorter payload with trailing whitespace
    # -- valid outside a JSON document) and identical mtime, so only a path
    # comparison can tell the two apart.
    text_a = src_a.read_text(encoding="utf-8")
    text_b = src_b.read_text(encoding="utf-8")
    pad = abs(len(text_a) - len(text_b))
    if len(text_a) < len(text_b):
        src_a.write_text(text_a + " " * pad, encoding="utf-8")
    else:
        src_b.write_text(text_b + " " * pad, encoding="utf-8")
    assert src_a.stat().st_size == src_b.stat().st_size
    # os.utime's float-seconds form loses nanosecond precision (rounding can
    # differ between the two calls); the ns= form sets it exactly.
    common_mtime_ns = src_a.stat().st_mtime_ns
    os.utime(src_b, ns=(common_mtime_ns, common_mtime_ns))
    assert src_a.stat().st_mtime_ns == src_b.stat().st_mtime_ns

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add

        result_a = global_add(src_a, "repoX")
        assert result_a["skipped"] is False

        result_b = global_add(src_b, "repoX")
        assert result_b["skipped"] is False, (
            "a different file with a matching mtime/size must not fast-skip"
        )

        manifest = json.loads((global_dir / "global-manifest.json").read_text())
        assert manifest["repos"]["repoX"]["source_path"] == str(src_b.resolve())

        graph = json.loads((global_dir / "global-graph.json").read_text())
        ids = {n["id"] for n in graph["nodes"]}
        assert "repoX::new" in ids, "the new file's content must actually be imported"
        assert "repoX::old" not in ids, "the stale file's content must not survive"


def test_global_add_stat_fast_path_serves_a_settled_unchanged_file_without_reading(tmp_path, monkeypatch):
    """Review finding (bot, PR #3578): the mtime/size fast path is meant to
    serve a genuinely unchanged file with no read at all. This is the
    positive-case companion to the oversized-file test above -- confirms the
    fast path still actually fires (zero reads) for the ordinary case.

    The racily-clean granularity guard is disabled here (matching its own
    documented GRAPHIFY_MTIME_GRANULARITY_MS=0 override) rather than settled
    by backdating mtime via os.utime(): that call always bumps ctime too
    (see the new ctime check added in this same round), which would make
    the file look changed for a reason that has nothing to do with this
    test."""
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "src/x.py"}])
    _graph_to_json(G, src_graph)

    monkeypatch.setattr("graphify.cache._mtime_granularity_ns", lambda: 0)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        assert global_add(src_graph, "repoA")["skipped"] is False

        reads = []
        orig_read_bytes = Path.read_bytes

        def counting_read_bytes(self, *a, **kw):
            if self == src_graph:
                reads.append("bytes")
            return orig_read_bytes(self, *a, **kw)

        monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

        result = global_add(src_graph, "repoA")

    assert result["skipped"] is True
    assert reads == [], (
        f"a settled, genuinely unchanged file must skip via the stat only "
        f"fast path, not fall through to a hash based read; got {reads}"
    )


def test_global_add_does_not_skip_content_changed_with_preserved_mtime_and_size(tmp_path, monkeypatch):
    """Review finding (bot, PR #3578): the mtime/size fast path checked only
    those two fields, so a file edited in place and then restored to its
    OLD mtime and size (a real possibility with cp -p/rsync -a against an
    unrelated same-length source, or a build step that pins timestamps for
    reproducibility) would silently skip re-import even though its content
    genuinely changed.

    mtime and size are both directly settable by the caller and so cannot
    rule this out by themselves; ctime (inode change time on POSIX) cannot
    be forged the same way -- writing new content, or the utime() call that
    restores mtime, both bump it to the real current time regardless of
    what mtime is set to afterward. The racily-clean granularity guard is
    disabled here so this test isolates the ctime defense specifically --
    without disabling it, a fast-running test would already force a real
    read on its own, for an unrelated reason (not enough wall-clock time
    has passed), masking whether ctime is doing anything at all."""
    monkeypatch.setattr("graphify.cache._mtime_granularity_ns", lambda: 0)

    src_graph = tmp_path / "graph.json"
    G_old = _make_graph([{"id": "old", "label": "Old", "source_file": "old.py"}])
    _graph_to_json(G_old, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        assert global_add(src_graph, "repoA")["skipped"] is False

        # Baseline captured right after the add that recorded it, matching
        # exactly what landed in the manifest -- settling first (backdating
        # mtime) would itself change ctime and diverge from that baseline.
        original_mtime_ns = src_graph.stat().st_mtime_ns
        original_size = src_graph.stat().st_size

        # Genuinely different content, forced to the exact same byte length,
        # then mtime restored to its original value -- the shape a same-size
        # cp -p/rsync -a copy or a timestamp-pinning build step produces.
        G_new = _make_graph([{"id": "new", "label": "New", "source_file": "new.py"}])
        _graph_to_json(G_new, src_graph)
        new_text = src_graph.read_text(encoding="utf-8")
        pad = original_size - len(new_text.encode("utf-8"))
        assert pad >= 0, "test fixture: the new payload must not be longer than the old one"
        src_graph.write_text(new_text + " " * pad, encoding="utf-8")
        os.utime(src_graph, ns=(original_mtime_ns, original_mtime_ns))
        assert src_graph.stat().st_mtime_ns == original_mtime_ns
        assert src_graph.stat().st_size == original_size

        result = global_add(src_graph, "repoA")

    assert result["skipped"] is False, (
        "a genuine content change must not silently skip just because "
        "mtime and size were restored to their old values"
    )
    graph = json.loads((global_dir / "global-graph.json").read_text())
    ids = {n["id"] for n in graph["nodes"]}
    assert "repoA::new" in ids, "the changed file's new content must actually be imported"
    assert "repoA::old" not in ids, "the stale content must not survive"


def test_global_store_lock_serializes_concurrent_critical_sections(tmp_path):
    """Review finding: global_add/global_remove each load-mutate-save the
    shared store with no locking, so two concurrent calls read the same
    pre-write snapshot, compute conflicting results, and the second save
    silently discards the first's work entirely. The lock added to close
    this must actually provide mutual exclusion -- verified directly by
    running several threads through the critical section and confirming
    at most one is ever inside it at once, rather than through global_add
    itself (racing its real logic reliably, without deadlocking a test
    that also needs to pass once the lock works, is far harder to get
    right than testing the lock's own guarantee in isolation)."""
    import threading
    import time
    from graphify import global_graph as gg_mod

    global_dir = tmp_path / ".graphify"
    active = {"count": 0}
    max_active = {"value": 0}
    counter_lock = threading.Lock()

    def worker():
        with gg_mod._global_store_lock():
            with counter_lock:
                active["count"] += 1
                max_active["value"] = max(max_active["value"], active["count"])
            time.sleep(0.05)
            with counter_lock:
                active["count"] -= 1

    with patch("graphify.global_graph._GLOBAL_DIR", global_dir):
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive(), "a thread did not finish within the timeout (deadlock?)"

    assert max_active["value"] == 1, (
        f"the lock let {max_active['value']} threads into the critical section at once"
    )


def test_global_add_concurrent_calls_both_survive(tmp_path):
    """End-to-end: two different repos added via genuinely concurrent
    global_add calls must both still be present afterward -- the lock
    from the finding above must be held across the real load/mutate/save
    cycle, not just demonstrated in isolation."""
    import threading
    from graphify import global_graph as gg_mod

    src_a = tmp_path / "a.json"
    src_b = tmp_path / "b.json"
    _graph_to_json(
        _make_graph([{"id": "a1", "label": "A1", "source_file": "a.py"}]), src_a
    )
    _graph_to_json(
        _make_graph([{"id": "b1", "label": "B1", "source_file": "b.py"}]), src_b
    )

    global_dir = tmp_path / ".graphify"
    errors: list[Exception] = []

    def add(src, tag):
        try:
            gg_mod.global_add(src, tag)
        except Exception as exc:  # pragma: no cover - surfaced via assertion below
            errors.append(exc)

    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        t1 = threading.Thread(target=add, args=(src_a, "repoA"))
        t2 = threading.Thread(target=add, args=(src_b, "repoB"))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        assert not t1.is_alive() and not t2.is_alive(), (
            "a thread did not finish within the timeout (deadlock?)"
        )

    assert not errors, errors
    manifest = json.loads((global_dir / "global-manifest.json").read_text())
    assert set(manifest["repos"]) == {"repoA", "repoB"}, (
        f"a concurrent add lost the other's update, got {set(manifest['repos'])}"
    )


def test_global_add_hashes_and_parses_a_single_read(tmp_path, monkeypatch):
    """Review finding: source_path used to be read twice at two different
    times -- once by a standalone hashing helper before the lock, once for
    the actual JSON parse after it -- so a concurrent writer to source_path
    between those two reads could make the recorded manifest hash describe
    different bytes than what was actually imported into the global graph.
    Hashing and parsing must now share a single read of the file."""
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "x", "label": "X", "source_file": "x.py"}])
    _graph_to_json(G, src_graph)

    reads = []
    orig_read_bytes = Path.read_bytes
    orig_read_text = Path.read_text

    def counting_read_bytes(self, *a, **kw):
        if self == src_graph:
            reads.append("bytes")
        return orig_read_bytes(self, *a, **kw)

    def counting_read_text(self, *a, **kw):
        if self == src_graph:
            reads.append("text")
        return orig_read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    monkeypatch.setattr(Path, "read_text", counting_read_text)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add
        global_add(src_graph, "repoA")

    assert reads == ["bytes"], (
        f"source_path must be read exactly once, for both hashing and "
        f"parsing, so the recorded hash always matches what was actually "
        f"imported -- got {reads}"
    )
