"""Composing member graphs into a cluster graph (`graphify cluster build`)."""
import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph as _jg

from graphify.cluster_graph import (
    ClusterSpecError,
    build_cluster,
    strip_cluster_artifacts,
)


def make_member(base, name, nodes, edges=(), url=""):
    """Write a mini member repo: <base>/<name>/graphify-out/graph.json."""
    repo = base / name
    out = repo / "graphify-out"
    out.mkdir(parents=True)
    G = nx.Graph()
    for node in nodes:
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for u, v, attrs in edges:
        G.add_edge(u, v, **attrs)
    (out / "graph.json").write_text(
        json.dumps(_jg.node_link_data(G, edges="links")), encoding="utf-8"
    )
    return repo


def _node(nid, label=None, source_file=None, **extra):
    d = {"id": nid, "label": label or nid, "file_type": "code"}
    if source_file is not None:
        d["source_file"] = source_file
    d.update(extra)
    return d


def write_cluster(cluster_dir, members, links=(), **extra):
    cluster_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "name": "test-cluster",
        "members": members,
        "links": list(links),
    }
    data.update(extra)
    (cluster_dir / "cluster.json").write_text(json.dumps(data), encoding="utf-8")


def _load_out(cluster_dir):
    data = json.loads((cluster_dir / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    return _jg.node_link_graph(data, edges="links")


@pytest.fixture()
def two_members(tmp_path):
    make_member(tmp_path, "alpha", [
        _node("app", source_file="src/app.ts"),
        _node("react", label="react"),  # external: no source_file
    ], edges=[("app", "react", {"relation": "imports"})])
    make_member(tmp_path, "beta", [
        _node("server", source_file="src/server.ts"),
        _node("react", label="react"),
    ], edges=[("server", "react", {"relation": "imports"})])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [
        {"tag": "alpha", "path": "../alpha"},
        {"tag": "beta", "path": "../beta"},
    ])
    return cluster


def test_build_composes_with_repo_prefixes(two_members):
    summary = build_cluster(two_members)
    assert not summary["skipped"]
    G = _load_out(two_members)
    assert "alpha::app" in G and "beta::server" in G
    assert G.nodes["alpha::app"]["repo"] == "alpha"
    assert G.nodes["alpha::app"]["local_id"] == "app"


def test_build_merges_externals_by_label(two_members):
    build_cluster(two_members)
    G = _load_out(two_members)
    # One shared `react` node, not one per member — and both import edges
    # were rewired onto it, connecting the repos through the shared external.
    react_nodes = [n for n, d in G.nodes(data=True) if d.get("label") == "react"]
    assert len(react_nodes) == 1
    (react,) = react_nodes
    neighbors = set(G.neighbors(react))
    assert {"alpha::app", "beta::server"} <= neighbors


def test_build_without_externals_merge(tmp_path, two_members):
    spec = json.loads((two_members / "cluster.json").read_text(encoding="utf-8"))
    spec["auto_links"] = {"externals": False}
    (two_members / "cluster.json").write_text(json.dumps(spec), encoding="utf-8")
    build_cluster(two_members)
    G = _load_out(two_members)
    react_nodes = [n for n, d in G.nodes(data=True) if d.get("label") == "react"]
    assert len(react_nodes) == 2


def test_rebuild_skips_when_unchanged_and_force_rebuilds(two_members):
    first = build_cluster(two_members)
    assert not first["skipped"]
    second = build_cluster(two_members)
    assert second["skipped"]
    assert second["nodes"] == first["nodes"]
    forced = build_cluster(two_members, force=True)
    assert not forced["skipped"]


def test_rebuild_when_link_mode_changes(two_members):
    spec_path = two_members / "cluster.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["links"] = [{
        "type": "api_call",
        "from": {"repo": "alpha", "file": "src/app.ts"},
        "to": {"repo": "beta", "file": "src/server.ts"},
    }]
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    linked = build_cluster(two_members)
    assert not linked["skipped"]
    assert any(
        data.get("origin") == "cluster_spec"
        for _u, _v, data in _load_out(two_members).edges(data=True)
    )

    unlinked = build_cluster(two_members, no_links=True)
    assert not unlinked["skipped"]
    assert not any(
        data.get("origin") == "cluster_spec"
        for _u, _v, data in _load_out(two_members).edges(data=True)
    )
    assert build_cluster(two_members, no_links=True)["skipped"]

    relinked = build_cluster(two_members)
    assert not relinked["skipped"]
    assert any(
        data.get("origin") == "cluster_spec"
        for _u, _v, data in _load_out(two_members).edges(data=True)
    )


def test_legacy_manifest_without_link_mode_rebuilds(two_members):
    build_cluster(two_members)
    manifest_path = two_members / "graphify-out" / "cluster-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["links_enabled"] is True
    del manifest["links_enabled"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert not build_cluster(two_members)["skipped"]


def test_rebuild_after_member_change_is_idempotent(tmp_path, two_members):
    first = build_cluster(two_members)
    # Change a member graph: rebuild must pick it up and not duplicate anything.
    make_member(tmp_path, "gamma", [_node("extra", source_file="x.ts")])
    gp = tmp_path / "alpha" / "graphify-out" / "graph.json"
    data = json.loads(gp.read_text(encoding="utf-8"))
    data["nodes"].append({"id": "helper", "label": "helper", "file_type": "code",
                          "source_file": "src/helper.ts"})
    gp.write_text(json.dumps(data), encoding="utf-8")

    second = build_cluster(two_members)
    assert not second["skipped"]
    assert second["nodes"] == first["nodes"] + 1
    third = build_cluster(two_members, force=True)
    assert third["nodes"] == second["nodes"]


def test_missing_member_graph_is_actionable(tmp_path):
    (tmp_path / "empty-repo").mkdir()
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "empty", "path": "../empty-repo"}])
    with pytest.raises(ClusterSpecError, match="graphify extract"):
        build_cluster(cluster)


def test_unresolvable_member_is_actionable(tmp_path):
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "ghost", "url": "https://github.com/org/ghost"}])
    with pytest.raises(ClusterSpecError, match="cluster locate"):
        build_cluster(cluster)


def test_build_writes_manifest_and_report(two_members):
    build_cluster(two_members)
    out = two_members / "graphify-out"
    manifest = json.loads((out / "cluster-manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["members"]) == {"alpha", "beta"}
    assert manifest["members"]["alpha"]["source_hash"]
    assert manifest["links_enabled"] is True
    report = (out / "CLUSTER_REPORT.md").read_text(encoding="utf-8")
    assert "test-cluster" in report and "alpha" in report


def test_strip_cluster_artifacts():
    G = nx.Graph()
    G.add_node("a::x", repo="a")
    G.add_node("b::y", repo="b")
    G.add_node("cluster::table_pings", repo="cluster", origin="cluster_spec")
    G.add_edge("a::x", "b::y", relation="calls_api", origin="cluster_spec")
    G.add_edge("a::x", "cluster::table_pings", relation="uses", origin="cluster_spec")
    edges_removed, nodes_removed = strip_cluster_artifacts(G)
    assert edges_removed >= 1 and nodes_removed == 1
    assert "cluster::table_pings" not in G
    assert not G.edges()
    assert "a::x" in G and "b::y" in G
