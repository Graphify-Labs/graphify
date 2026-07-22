"""Spec-declared cross-repo link resolution (selectors, hubs, on_missing)."""
import json

import pytest

from graphify.cluster_graph import (
    AmbiguousSelectorError,
    ClusterSpecError,
    build_cluster,
    load_spec,
    apply_spec_links,
    compose_members,
    resolve_selector,
)
from tests.test_cluster_build import make_member, write_cluster, _node, _load_out


@pytest.fixture()
def linked_cluster(tmp_path):
    """Two members shaped like a client/service pair plus a mirrored type file."""
    make_member(tmp_path, "web", [
        _node("lib_cube_client", label="cube-client.ts", source_file="app/lib/cube/cube-client.ts"),
        _node("lib_cube_client_getmeta", label="getMeta", source_file="app/lib/cube/cube-client.ts"),
        _node("types_payload", label="payload.ts", source_file="src/types/payload.ts"),
    ])
    make_member(tmp_path, "svc", [
        _node("cube", label="cube.js", source_file="cube.js"),
        _node("sync", label="pingSync", source_file="src/sync.ts"),
        _node("payload", label="payload.ts", source_file="src/payload.ts"),
    ])
    cluster = tmp_path / "cluster"
    return cluster


def _compose(cluster_dir):
    spec = load_spec(cluster_dir)
    from graphify.cluster_graph import load_local_config, resolve_all_members
    resolved, _w, errors = resolve_all_members(spec, cluster_dir, load_local_config(cluster_dir))
    assert not errors
    G, _stats = compose_members(spec, resolved)
    return G, spec


def test_api_call_link_by_file_selector(linked_cluster, tmp_path):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "api_call",
        "name": "cube-rest",
        "from": {"repo": "web", "file": "app/lib/cube/cube-client.ts"},
        "to": {"repo": "svc", "file": "cube.js"},
        "note": "JWT via env",
    }])
    build_cluster(linked_cluster)
    G = _load_out(linked_cluster)
    data = G.get_edge_data("web::lib_cube_client", "svc::cube")
    assert data is not None
    assert data["relation"] == "calls_api"
    assert data["confidence"] == "EXTRACTED"
    assert data["origin"] == "cluster_spec"
    assert data["link_name"] == "cube-rest"
    assert data["_src"] == "web::lib_cube_client"
    assert data["_tgt"] == "svc::cube"
    assert data["source_file"] == "cluster.json"


def test_file_selector_prefers_file_node(linked_cluster):
    # app/lib/cube/cube-client.ts contains both the file node and a symbol
    # node; the file selector must land on the file node.
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ])
    G, _spec = _compose(linked_cluster)
    nodes_by_repo = {}
    for n, d in G.nodes(data=True):
        nodes_by_repo.setdefault(d.get("repo", ""), []).append((n, d))
    node = resolve_selector(nodes_by_repo, {"repo": "web", "file": "app/lib/cube/cube-client.ts"})
    assert node == "web::lib_cube_client"
    # Suffix matching: a shorter repo-relative tail also resolves.
    node = resolve_selector(nodes_by_repo, {"repo": "web", "file": "cube/cube-client.ts"})
    assert node == "web::lib_cube_client"


def test_file_selector_prefers_file_node_in_llm_labeled_graph(tmp_path):
    """LLM extractions relabel file nodes descriptively ("PR Summary Generator"),
    so the basename-label heuristic fails; the file-node ID spec (#1504 —
    local_id == normalize_id(path minus extension)) must still disambiguate."""
    make_member(tmp_path, "plugin", [
        _node("scripts_generate_pr_summary", label="PR Summary Generator",
              source_file="scripts/generate-pr-summary.js"),
        _node("scripts_generate_pr_summary_buildprompt", label="buildPrompt",
              source_file="scripts/generate-pr-summary.js"),
        _node("scripts_generate_pr_summary_callclaudeapi", label="callClaudeApi",
              source_file="scripts/generate-pr-summary.js"),
    ])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "plugin", "path": "../plugin"}])
    G, _spec = _compose(cluster)
    nodes_by_repo = {}
    for n, d in G.nodes(data=True):
        nodes_by_repo.setdefault(d.get("repo", ""), []).append((n, d))
    node = resolve_selector(
        nodes_by_repo, {"repo": "plugin", "file": "scripts/generate-pr-summary.js"}
    )
    assert node == "plugin::scripts_generate_pr_summary"


def test_label_selector_exact_then_normalized(linked_cluster):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ])
    G, _spec = _compose(linked_cluster)
    nodes_by_repo = {}
    for n, d in G.nodes(data=True):
        nodes_by_repo.setdefault(d.get("repo", ""), []).append((n, d))
    assert resolve_selector(nodes_by_repo, {"repo": "svc", "label": "pingSync"}) == "svc::sync"
    # Normalized fallback: case-insensitive via normalize_id.
    assert resolve_selector(nodes_by_repo, {"repo": "svc", "label": "PingSync"}) == "svc::sync"


def test_id_selector_uses_local_id(linked_cluster):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ])
    G, _spec = _compose(linked_cluster)
    nodes_by_repo = {}
    for n, d in G.nodes(data=True):
        nodes_by_repo.setdefault(d.get("repo", ""), []).append((n, d))
    assert resolve_selector(nodes_by_repo, {"repo": "svc", "id": "cube"}) == "svc::cube"


def test_ambiguous_selector_lists_candidates(tmp_path):
    make_member(tmp_path, "twins", [
        _node("a_util", label="util", source_file="a/util.ts"),
        _node("b_util", label="util", source_file="b/util.ts"),
    ])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "twins", "path": "../twins"}])
    G, _spec = _compose(cluster)
    nodes_by_repo = {}
    for n, d in G.nodes(data=True):
        nodes_by_repo.setdefault(d.get("repo", ""), []).append((n, d))
    with pytest.raises(AmbiguousSelectorError) as exc:
        resolve_selector(nodes_by_repo, {"repo": "twins", "label": "util"})
    assert "a/util.ts" in str(exc.value) and "b/util.ts" in str(exc.value)


def test_shared_resource_creates_hub_with_uses_edges(linked_cluster):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "shared_resource",
        "kind": "supabase_table",
        "name": "cro.pings",
        "referents": [
            {"repo": "web", "file": "src/types/payload.ts"},
            {"repo": "svc", "label": "pingSync"},
        ],
    }])
    build_cluster(linked_cluster)
    G = _load_out(linked_cluster)
    hub = "cluster::supabase_table_cro_pings"
    assert hub in G
    assert G.nodes[hub]["file_type"] == "concept"
    assert G.nodes[hub]["label"] == "cro.pings"
    assert G.nodes[hub]["repo"] == "cluster"
    assert set(G.neighbors(hub)) == {"web::types_payload", "svc::sync"}
    for neighbor in G.neighbors(hub):
        assert G.get_edge_data(neighbor, hub)["relation"] == "uses"


def test_mirrored_file_link(linked_cluster):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "mirrored_file",
        "name": "payload",
        "from": {"repo": "web", "file": "src/types/payload.ts"},
        "to": {"repo": "svc", "file": "src/payload.ts"},
        "direction": "both",
    }])
    build_cluster(linked_cluster)
    G = _load_out(linked_cluster)
    data = G.get_edge_data("web::types_payload", "svc::payload")
    assert data["relation"] == "mirrors"
    assert data["direction"] == "both"


def test_on_missing_warn_skips(linked_cluster, capsys):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "api_call",
        "from": {"repo": "web", "label": "no-such-node"},
        "to": {"repo": "svc", "file": "cube.js"},
    }])
    summary = build_cluster(linked_cluster)
    assert summary["links"].edges_added == 0
    assert any("no node matches" in w for w in summary["links"].warnings)


def test_on_missing_create_makes_concept_node(linked_cluster):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "api_call",
        "on_missing": "create",
        "from": {"repo": "web", "label": "External Webhook"},
        "to": {"repo": "svc", "file": "cube.js"},
    }])
    build_cluster(linked_cluster)
    G = _load_out(linked_cluster)
    concept = "web::concept_external_webhook"
    assert concept in G
    assert G.nodes[concept]["file_type"] == "concept"
    assert G.nodes[concept]["origin"] == "cluster_spec"
    assert G.get_edge_data(concept, "svc::cube")["relation"] == "calls_api"


def test_on_missing_error_fails_build(linked_cluster):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "api_call",
        "on_missing": "error",
        "from": {"repo": "web", "label": "no-such-node"},
        "to": {"repo": "svc", "file": "cube.js"},
    }])
    with pytest.raises(ClusterSpecError, match="no node matches"):
        build_cluster(linked_cluster)


def test_dry_run_does_not_mutate(linked_cluster):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "api_call",
        "from": {"repo": "web", "file": "app/lib/cube/cube-client.ts"},
        "to": {"repo": "svc", "file": "cube.js"},
    }])
    G, spec = _compose(linked_cluster)
    before_nodes, before_edges = G.number_of_nodes(), G.number_of_edges()
    report = apply_spec_links(G, spec, dry_run=True)
    assert report.edges_added == 1
    assert (G.number_of_nodes(), G.number_of_edges()) == (before_nodes, before_edges)
