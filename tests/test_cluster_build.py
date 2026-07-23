"""Composing member graphs into a cluster graph (`graphify cluster build`)."""
import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph as _jg

from graphify.cluster_graph import (
    ClusterSpecError,
    build_cluster,
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
    # The cluster graph is directed; import edges point importer -> external.
    importers = set(G.predecessors(react))
    assert {"alpha::app", "beta::server"} <= importers


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




def _write_member_json(base, name, graph):
    """Write a member graph.json exactly as a real export would persist it."""
    out = base / name / "graphify-out"
    out.mkdir(parents=True)
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    return base / name


def test_build_preserves_edge_direction_regardless_of_node_order(tmp_path):
    # Real member graphs say "directed": false but their source/target order IS
    # the caller->callee direction (export restores it from _src/_tgt and pops
    # the attrs). The callee node deliberately precedes the caller here — the
    # exact case where an undirected compose re-emits the edge flipped by node
    # insertion order (#760 class). The cluster graph must keep caller->callee.
    _write_member_json(tmp_path, "alpha", {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "callee", "label": "callee", "file_type": "code",
             "source_file": "src/callee.ts"},
            {"id": "caller", "label": "caller", "file_type": "code",
             "source_file": "src/caller.ts"},
        ],
        "links": [{"source": "caller", "target": "callee", "relation": "calls"}],
    })
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "alpha", "path": "../alpha"}])
    build_cluster(cluster)

    data = json.loads(
        (cluster / "graphify-out" / "graph.json").read_text(encoding="utf-8")
    )
    assert data["directed"] is True
    (link,) = [l for l in data["links"] if l.get("relation") == "calls"]
    assert link["source"] == "alpha::caller"
    assert link["target"] == "alpha::callee"

    # affected traverses in_edges on the loaded graph: changing the callee
    # must report the caller, never the reverse.
    from graphify.affected import affected_nodes, load_graph

    G = load_graph(cluster / "graphify-out" / "graph.json")
    from_callee = {h.node_id for h in affected_nodes(G, "alpha::callee", relations=["calls"])}
    from_caller = {h.node_id for h in affected_nodes(G, "alpha::caller", relations=["calls"])}
    assert "alpha::caller" in from_callee
    assert "alpha::callee" not in from_caller


def test_corrupt_member_graph_is_actionable(two_members):
    (two_members.parent / "alpha" / "graphify-out" / "graph.json").write_text(
        "{oops", encoding="utf-8"
    )
    with pytest.raises(ClusterSpecError) as exc:
        build_cluster(two_members)
    msg = str(exc.value)
    assert "alpha" in msg and "unreadable" in msg and "graphify extract" in msg

    from graphify.cluster_graph import check_cluster

    report, errors = check_cluster(two_members)
    assert any("unreadable" in e for e in errors)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"nodes": "bad", "links": []},
        {"nodes": [], "links": "bad"},
        {"nodes": [{"label": "missing id"}], "links": []},
        {"nodes": [{"id": "a"}], "links": [{"source": "a"}]},
    ],
    ids=[
        "non-mapping-root",
        "nodes-not-list",
        "links-not-list",
        "node-missing-id",
        "edge-missing-target",
    ],
)
def test_structurally_corrupt_member_graph_is_actionable(two_members, payload):
    graph_path = two_members.parent / "alpha" / "graphify-out" / "graph.json"
    graph_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ClusterSpecError, match="unreadable graph"):
        build_cluster(two_members)

    from graphify.cluster_graph import check_cluster

    report, errors = check_cluster(two_members)
    assert report.errors == errors
    assert any("unreadable graph" in error for error in errors)


def test_cluster_cannot_compose_itself(two_members):
    spec_path = two_members / "cluster.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["members"].append({"tag": "selfie", "path": "."})
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    (two_members / "graphify-out").mkdir(exist_ok=True)
    (two_members / "graphify-out" / "graph.json").write_text(
        json.dumps({"directed": False, "multigraph": False, "graph": {},
                    "nodes": [], "links": []}),
        encoding="utf-8",
    )
    with pytest.raises(ClusterSpecError, match="compose its own output"):
        build_cluster(two_members)

    from graphify.cluster_graph import check_cluster

    report, errors = check_cluster(two_members)
    assert any("compose its own output" in e for e in errors)


def test_member_communities_are_renumbered_per_member(tmp_path):
    # Both members number their communities from 0; composing verbatim would
    # merge unrelated "community 0" groups across repos.
    make_member(tmp_path, "alpha", [
        _node("a1", source_file="a1.ts", community=0, community_name="Community 0"),
        _node("a2", source_file="a2.ts", community=0, community_name="Community 0"),
    ])
    make_member(tmp_path, "beta", [
        _node("b1", source_file="b1.ts", community=0, community_name="Auth Layer"),
    ])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [
        {"tag": "alpha", "path": "../alpha"},
        {"tag": "beta", "path": "../beta"},
    ])
    build_cluster(cluster)
    G = _load_out(cluster)
    cids = {n: d.get("community") for n, d in G.nodes(data=True) if d.get("community") is not None}
    assert cids["alpha::a1"] == cids["alpha::a2"]
    assert cids["alpha::a1"] != cids["beta::b1"]
    # Placeholder names track the new id; real LLM names are preserved.
    assert G.nodes["alpha::a1"]["community_name"] == f"Community {cids['alpha::a1']}"
    assert G.nodes["beta::b1"]["community_name"] == "Auth Layer"


def test_empty_cluster_build_is_actionable(tmp_path):
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [])
    with pytest.raises(ClusterSpecError, match="no members"):
        build_cluster(cluster)
    assert not (cluster / "graphify-out").exists()

    from graphify.cluster_graph import check_cluster

    report, errors = check_cluster(cluster)
    assert any("no members" in e for e in errors)


def test_yaml_spec_still_loads(tmp_path):
    yaml = pytest.importorskip("yaml")
    make_member(tmp_path, "alpha", [_node("app", source_file="src/app.ts")])
    cluster = tmp_path / "cluster"
    cluster.mkdir()
    (cluster / "cluster.yaml").write_text(
        yaml.safe_dump({
            "schema_version": 1,
            "name": "yaml-cluster",
            "members": [{"tag": "alpha", "path": "../alpha"}],
        }),
        encoding="utf-8",
    )
    summary = build_cluster(cluster)
    assert summary["name"] == "yaml-cluster"
    assert "alpha::app" in _load_out(cluster)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("members", {}, "members must be a list"),
        ("links", {}, "links must be a list"),
        ("defaults", [], "defaults must be a mapping"),
        ("auto_links", [], "auto_links must be a mapping"),
        (
            "auto_links",
            {"externals": "false"},
            "auto_links.externals must be a boolean",
        ),
        (
            "auto_links",
            {"packages": 1},
            "auto_links.packages must be a boolean",
        ),
    ],
)
def test_invalid_cluster_spec_field_shapes_are_actionable(
    tmp_path, field, value, message
):
    from graphify.cluster_graph import load_spec

    cluster = tmp_path / "cluster"
    write_cluster(cluster, [])
    spec_path = cluster / "cluster.json"
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    data[field] = value
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ClusterSpecError, match=message):
        load_spec(cluster)


def test_invalid_json_cluster_spec_is_actionable(tmp_path):
    from graphify.cluster_graph import load_spec

    cluster = tmp_path / "cluster"
    cluster.mkdir()
    (cluster / "cluster.json").write_text("{oops", encoding="utf-8")
    with pytest.raises(ClusterSpecError, match="invalid JSON at line"):
        load_spec(cluster)


def test_invalid_yaml_cluster_spec_is_actionable(tmp_path):
    pytest.importorskip("yaml")
    from graphify.cluster_graph import load_spec

    cluster = tmp_path / "cluster"
    cluster.mkdir()
    (cluster / "cluster.yaml").write_text("members: [\n", encoding="utf-8")
    with pytest.raises(ClusterSpecError, match="invalid YAML"):
        load_spec(cluster)
