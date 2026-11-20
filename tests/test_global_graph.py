"""Tests for the global graph infrastructure (graphify/global_graph.py),
prefix/prune helpers in graphify/build.py, and the cross-repo guard in
graphify/dedup.py."""
from __future__ import annotations

import json
from pathlib import Path
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


def test_global_add_records_built_at_commit_and_basis(tmp_path):
    """Manifest must record built_at_commit and commit_basis='built_at_commit'
    when the source graph.json carries an explicit build commit stamp."""
    repo_dir = tmp_path / "repoA"
    out_dir = repo_dir / "graphify-out"
    out_dir.mkdir(parents=True)
    src_graph = out_dir / "graph.json"

    G = _make_graph([{"id": "a", "label": "A", "source_file": "a.py"}])
    _graph_to_json(G, src_graph)
    raw = json.loads(src_graph.read_text(encoding="utf-8"))
    raw["built_at_commit"] = "1111111deadbeef"
    src_graph.write_text(json.dumps(raw), encoding="utf-8")

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"), \
         patch("graphify.watch._git_head", return_value="2222222cafebabe"):
        from graphify.global_graph import global_add
        global_add(src_graph, "repoA")

    manifest = json.loads((global_dir / "global-manifest.json").read_text(encoding="utf-8"))
    entry = manifest["repos"]["repoA"]
    assert entry["built_at_commit"] == "1111111deadbeef"
    assert entry["head_at_merge"] == "2222222cafebabe"
    assert entry["commit_basis"] == "built_at_commit"


def test_global_add_falls_back_to_head_at_merge_when_graph_has_no_commit(tmp_path):
    """When graph.json carries no built_at_commit (e.g. --no-cluster raw output),
    manifest records head_at_merge with commit_basis='head_at_merge' rather than
    conflating git HEAD with extracted graph provenance."""
    repo_dir = tmp_path / "repoB"
    out_dir = repo_dir / "graphify-out"
    out_dir.mkdir(parents=True)
    src_graph = out_dir / "graph.json"

    G = _make_graph([{"id": "b", "label": "B", "source_file": "b.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"), \
         patch("graphify.watch._git_head", return_value="abcdef0123456789"):
        from graphify.global_graph import global_add
        global_add(src_graph, "repoB")

    manifest = json.loads((global_dir / "global-manifest.json").read_text(encoding="utf-8"))
    entry = manifest["repos"]["repoB"]
    assert entry["built_at_commit"] is None
    assert entry["head_at_merge"] == "abcdef0123456789"
    assert entry["commit_basis"] == "head_at_merge"


def test_settled_detects_in_flight_writes_and_converges(tmp_path, monkeypatch):
    """settled() must return False when file size/mtime keeps changing across the
    polling budget, and True once two consecutive samples match."""
    from graphify.global_graph import settled

    target = tmp_path / "graph.json"
    target.write_text("{}", encoding="utf-8")

    # Simulate a file that keeps changing on every stat() call
    counter = {"n": 0}
    orig_stat = Path.stat

    class _ChangingStat:
        def __init__(self, size: int, mtime: float, mtime_ns: int):
            self.st_size = size
            self.st_mtime = mtime
            self.st_mtime_ns = mtime_ns

    import time as _time
    now = _time.time()

    def _changing_stat(self, *args, **kwargs):
        if self == target:
            counter["n"] += 1
            return _ChangingStat(100 + counter["n"], now, int(now * 1e9) + counter["n"])
        return orig_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _changing_stat)
    monkeypatch.setattr("graphify.global_graph.time.sleep", lambda _s: None)
    assert settled(target, 0.5, quiet_s=10.0, poll_interval_s=0.2) is False

    # Now simulate a file that settles after 1 change
    seq = [
        _ChangingStat(100, now, 1000),
        _ChangingStat(120, now, 2000),
        _ChangingStat(120, now, 2000),
    ]
    idx = {"i": 0}

    def _settling_stat(self, *args, **kwargs):
        if self == target:
            val = seq[min(idx["i"], len(seq) - 1)]
            idx["i"] += 1
            return val
        return orig_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _settling_stat)
    assert settled(target, 1.0, quiet_s=10.0, poll_interval_s=0.2) is True


def test_global_add_skips_unsettled_file_without_touching_manifest(tmp_path):
    """When settle_s > 0 and the source graph is still being written by a
    background hook, global_add must skip and leave the manifest untouched."""
    src_graph = tmp_path / "graph.json"
    G = _make_graph([{"id": "a", "label": "A", "source_file": "a.py"}])
    _graph_to_json(G, src_graph)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"), \
         patch("graphify.global_graph.settled", return_value=False):
        from graphify.global_graph import global_add
        res = global_add(src_graph, "repoA", settle_s=1.5)

    assert res["skipped"] is True
    assert res["unsettled"] is True
    assert not (global_dir / "global-manifest.json").exists()


def test_global_status_detects_hash_drift_and_commit_lag(tmp_path):
    """global_status() must report in-sync initially, then flag stale when either
    the on-disk graph.json changes or git HEAD advances past the merged commit."""
    repo_dir = tmp_path / "repoA"
    out_dir = repo_dir / "graphify-out"
    out_dir.mkdir(parents=True)
    src_graph = out_dir / "graph.json"

    G = _make_graph([{"id": "a", "label": "A", "source_file": "a.py"}])
    _graph_to_json(G, src_graph)
    raw = json.loads(src_graph.read_text(encoding="utf-8"))
    raw["built_at_commit"] = "aaa1111"
    src_graph.write_text(json.dumps(raw), encoding="utf-8")

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"), \
         patch("graphify.watch._git_head", return_value="aaa1111"), \
         patch("graphify.global_graph._commits_between", return_value=0):
        from graphify.global_graph import global_add, global_status
        global_add(src_graph, "repoA")
        st_clean = global_status()

    assert st_clean["all_in_sync"] is True
    assert st_clean["repos"]["repoA"]["stale"] is False
    assert st_clean["repos"]["repoA"]["commits_behind"] == 0

    # Advance git HEAD by 3 commits without rebuilding/merging
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"), \
         patch("graphify.watch._git_head", return_value="bbb2222"), \
         patch("graphify.global_graph._commits_between", return_value=3):
        from graphify.global_graph import global_status
        st_lag = global_status()

    assert st_lag["all_in_sync"] is False
    assert st_lag["repos"]["repoA"]["stale"] is True
    assert st_lag["repos"]["repoA"]["commits_behind"] == 3

    # Modify graph.json on disk so hash drifts from manifest
    G2 = _make_graph([
        {"id": "a", "label": "A", "source_file": "a.py"},
        {"id": "b", "label": "B", "source_file": "b.py"},
    ])
    _graph_to_json(G2, src_graph)
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"), \
         patch("graphify.watch._git_head", return_value="aaa1111"), \
         patch("graphify.global_graph._commits_between", return_value=0):
        from graphify.global_graph import global_status
        st_hash = global_status()

    assert st_hash["all_in_sync"] is False
    assert st_hash["repos"]["repoA"]["hash_in_sync"] is False
    assert st_hash["repos"]["repoA"]["stale"] is True


def test_global_sync_remerges_modified_and_reports_missing(tmp_path):
    """global_sync() re-merges modified registered repos, skips unchanged ones,
    and reports registered repos whose source_path is missing."""
    g1 = tmp_path / "repo1" / "graphify-out" / "graph.json"
    g2 = tmp_path / "repo2" / "graphify-out" / "graph.json"
    g1.parent.mkdir(parents=True)
    g2.parent.mkdir(parents=True)

    _graph_to_json(_make_graph([{"id": "a", "label": "A", "source_file": "a.py"}]), g1)
    _graph_to_json(_make_graph([{"id": "b", "label": "B", "source_file": "b.py"}]), g2)

    global_dir = tmp_path / ".graphify"
    with patch("graphify.global_graph._GLOBAL_DIR", global_dir), \
         patch("graphify.global_graph._GLOBAL_GRAPH", global_dir / "global-graph.json"), \
         patch("graphify.global_graph._GLOBAL_MANIFEST", global_dir / "global-manifest.json"):
        from graphify.global_graph import global_add, global_sync
        global_add(g1, "repo1")
        global_add(g2, "repo2")

        # Update g1 on disk, leave g2 unchanged
        _graph_to_json(
            _make_graph([
                {"id": "a", "label": "A", "source_file": "a.py"},
                {"id": "a2", "label": "A2", "source_file": "a2.py"},
            ]),
            g1,
        )
        sync_res = global_sync()
        assert sync_res["updated"] == ["repo1"]
        assert sync_res["skipped"] == ["repo2"]
        assert sync_res["missing"] == []

        # Remove g2 on disk -> global_sync must report it in missing
        g2.unlink()
        sync_missing = global_sync()
        assert sync_missing["missing"] == ["repo2"]

