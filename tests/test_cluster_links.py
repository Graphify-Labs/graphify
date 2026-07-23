"""Spec-declared cross-repo link resolution (selectors, hubs, on_missing)."""
import json

import networkx as nx
import pytest

from graphify.cluster_graph import (
    AmbiguousSelectorError,
    ClusterSpecError,
    ClusterSpec,
    build_cluster,
    check_cluster,
    load_spec,
    apply_spec_links,
    apply_auto_package_links,
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


def _package(nid, name, repo_key, dependencies=()):
    return _node(
        nid,
        label=name,
        source_file="pyproject.toml",
        type="package",
        ecosystem="python",
        package_key=repo_key,
        dependency_keys=list(dependencies),
    )


def test_auto_packages_links_unique_cross_repo_provider(tmp_path):
    make_member(tmp_path, "app", [
        _package("pkg_app", "app", "python:app", ["python:shared-lib"]),
    ])
    make_member(tmp_path, "lib", [
        _package("pkg_shared", "shared-lib", "python:shared-lib"),
    ])
    cluster = tmp_path / "cluster"
    write_cluster(
        cluster,
        [{"tag": "app", "path": "../app"}, {"tag": "lib", "path": "../lib"}],
        auto_links={"packages": True},
    )

    summary = build_cluster(cluster)
    graph = _load_out(cluster)
    edge = graph.get_edge_data("app::pkg_app", "lib::pkg_shared")
    assert edge["relation"] == "depends_on"
    assert edge["origin"] == "cluster_auto_package"
    assert summary["links"].auto_package_edges == 1


def test_auto_packages_skips_external_same_repo_and_ambiguous_providers(tmp_path):
    make_member(tmp_path, "app", [
        _package(
            "pkg_app", "app", "python:app",
            ["python:local", "python:external", "python:shared"],
        ),
        _package("pkg_local", "local", "python:local"),
    ])
    make_member(tmp_path, "lib1", [_package("pkg_shared1", "shared", "python:shared")])
    make_member(tmp_path, "lib2", [_package("pkg_shared2", "shared", "python:shared")])
    cluster = tmp_path / "cluster"
    write_cluster(
        cluster,
        [
            {"tag": "app", "path": "../app"},
            {"tag": "lib1", "path": "../lib1"},
            {"tag": "lib2", "path": "../lib2"},
        ],
        auto_links={"packages": True},
    )

    summary = build_cluster(cluster)
    assert summary["links"].auto_package_edges == 0
    assert any("2 cross-repo providers" in warning for warning in summary["links"].warnings)


def test_auto_packages_declared_link_takes_precedence(tmp_path):
    make_member(tmp_path, "app", [
        _package("pkg_app", "app", "python:app", ["python:shared"]),
    ])
    make_member(tmp_path, "lib", [_package("pkg_shared", "shared", "python:shared")])
    cluster = tmp_path / "cluster"
    write_cluster(
        cluster,
        [{"tag": "app", "path": "../app"}, {"tag": "lib", "path": "../lib"}],
        links=[{
            "type": "depends_on",
            "name": "declared",
            "from": {"repo": "app", "id": "pkg_app"},
            "to": {"repo": "lib", "id": "pkg_shared"},
        }],
        auto_links={"packages": True},
    )

    summary = build_cluster(cluster)
    edge = _load_out(cluster).get_edge_data("app::pkg_app", "lib::pkg_shared")
    assert edge["origin"] == "cluster_spec"
    assert summary["links"].auto_package_edges == 0
    assert any("already connected" in warning for warning in summary["links"].warnings)


def test_auto_packages_warns_for_stale_member_graph():
    graph = nx.Graph()
    graph.add_node(
        "app::pkg", type="package", repo="app", package_key="python:app"
    )
    report = apply_auto_package_links(
        graph, ClusterSpec(name="test", auto_packages=True)
    )
    assert any("re-run `graphify extract --force`" in warning for warning in report.warnings)


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
    assert data["source_file"] == "cluster.json"
    # Direction is topological (the graph is directed) and the _src/_tgt
    # persistence markers are popped at write time like export.to_json does.
    assert "_src" not in data and "_tgt" not in data
    assert G.get_edge_data("svc::cube", "web::lib_cube_client") is None


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
    # Referents depend on the resource, so `uses` edges point referent -> hub.
    referents = {"web::types_payload", "svc::sync"}
    assert set(G.predecessors(hub)) == referents
    for referent in referents:
        assert G.get_edge_data(referent, hub)["relation"] == "uses"


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
    # direction: "both" materializes a real reverse edge, not just metadata —
    # affected/query traverse topology, so both directions must exist.
    reverse = G.get_edge_data("svc::payload", "web::types_payload")
    assert reverse is not None
    assert reverse["relation"] == "mirrors"
    assert reverse["direction"] == "both"


def test_direction_both_traverses_from_either_endpoint(linked_cluster):
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
    from graphify.affected import affected_nodes

    G = _load_out(linked_cluster)
    from_web = {h.node_id for h in affected_nodes(G, "web::types_payload", relations=["mirrors"])}
    from_svc = {h.node_id for h in affected_nodes(G, "svc::payload", relations=["mirrors"])}
    assert "svc::payload" in from_web
    assert "web::types_payload" in from_svc


def test_direction_validation_rejects_unknown_values(linked_cluster):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "mirrored_file",
        "name": "payload",
        "from": {"repo": "web", "file": "src/types/payload.ts"},
        "to": {"repo": "svc", "file": "src/payload.ts"},
        "direction": "sideways",
    }])
    with pytest.raises(ClusterSpecError, match="direction"):
        load_spec(linked_cluster)


def test_direction_both_still_owns_the_pair(linked_cluster):
    # The declared link's own reverse edge is exempt from the
    # one-relation-per-pair guard; a separate reverse-declaring link is not.
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[
        {
            "type": "mirrored_file",
            "name": "payload",
            "from": {"repo": "web", "file": "src/types/payload.ts"},
            "to": {"repo": "svc", "file": "src/payload.ts"},
            "direction": "both",
        },
        {
            "type": "references",
            "name": "reverse-decl",
            "from": {"repo": "svc", "file": "src/payload.ts"},
            "to": {"repo": "web", "file": "src/types/payload.ts"},
        },
    ])
    with pytest.raises(ClusterSpecError, match="one relation per node pair"):
        build_cluster(linked_cluster)


def test_duplicate_direct_links_fail_check_and_build(linked_cluster):
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[
        {
            "type": "api_call",
            "name": "first-contract",
            "from": {"repo": "web", "file": "app/lib/cube/cube-client.ts"},
            "to": {"repo": "svc", "file": "cube.js"},
        },
        {
            "type": "references",
            "name": "second-contract",
            "from": {"repo": "web", "file": "app/lib/cube/cube-client.ts"},
            "to": {"repo": "svc", "file": "cube.js"},
        },
    ])

    report, errors = check_cluster(linked_cluster)
    assert report.edges_added == 1
    assert any("one relation per node pair" in error for error in errors)
    assert any("first-contract" in error and "second-contract" in error for error in errors)
    with pytest.raises(ClusterSpecError, match="one relation per node pair"):
        build_cluster(linked_cluster)


def test_repeated_shared_resource_referent_is_rejected(linked_cluster):
    selector = {"repo": "svc", "label": "pingSync"}
    write_cluster(linked_cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "shared_resource",
        "kind": "table",
        "name": "events",
        "referents": [selector, selector],
    }])

    with pytest.raises(ClusterSpecError, match="one relation per node pair"):
        build_cluster(linked_cluster)


def test_declared_link_cannot_overwrite_existing_edge(tmp_path):
    make_member(
        tmp_path,
        "web",
        [
            _node("client", label="client", source_file="client.py"),
            _node("server", label="server", source_file="server.py"),
        ],
        edges=[("client", "server", {"relation": "calls"})],
    )
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [{"tag": "web", "path": "../web"}], links=[{
        "type": "references",
        "from": {"repo": "web", "id": "client"},
        "to": {"repo": "web", "id": "server"},
    }])

    with pytest.raises(ClusterSpecError, match="existing relation 'calls'"):
        build_cluster(cluster)


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


def test_norm_source_file_keeps_leading_dots():
    from graphify.cluster_graph import _norm_source_file

    assert _norm_source_file(".env") == ".env"
    assert _norm_source_file(".github/workflows/ci.yml") == ".github/workflows/ci.yml"
    assert _norm_source_file("./src/app.py") == "src/app.py"
    assert _norm_source_file("/abs/src/app.py") == "abs/src/app.py"


def test_file_selector_matches_dotfile(tmp_path):
    make_member(tmp_path, "web", [
        _node("env", label=".env", source_file=".env"),
        _node("scripts_env", label="env", source_file="scripts/env"),
    ])
    make_member(tmp_path, "svc", [_node("sync", source_file="src/sync.ts")])
    cluster = tmp_path / "cluster"
    write_cluster(cluster, [
        {"tag": "web", "path": "../web"},
        {"tag": "svc", "path": "../svc"},
    ], links=[{
        "type": "references",
        "name": "env-contract",
        "from": {"repo": "svc", "file": "src/sync.ts"},
        "to": {"repo": "web", "file": ".env"},
    }])
    build_cluster(cluster)
    G = _load_out(cluster)
    # ".env" must match the dotfile node, not alias onto "scripts/env".
    assert G.get_edge_data("svc::sync", "web::env") is not None
    assert G.get_edge_data("svc::sync", "web::scripts_env") is None


def test_external_label_selector_is_member_order_independent(tmp_path):
    """Externals dedupe onto the FIRST member that references them; a selector
    naming any other referencing member must still resolve, in either order."""
    make_member(tmp_path, "alpha", [
        _node("app", source_file="src/app.ts"),
        _node("requests", label="requests"),  # external
    ], edges=[("app", "requests", {"relation": "imports"})])
    make_member(tmp_path, "beta", [
        _node("server", source_file="src/server.ts"),
        _node("requests", label="requests"),
    ], edges=[("server", "requests", {"relation": "imports"})])

    for member_order in (["alpha", "beta"], ["beta", "alpha"]):
        cluster = tmp_path / f"cluster-{'-'.join(member_order)}"
        # Distinct names: same-named clusters sharing a member are (correctly)
        # rejected by the marker conflict check.
        write_cluster(cluster, [
            {"tag": tag, "path": f"../{tag}"} for tag in member_order
        ], name=f"stack-{'-'.join(member_order)}", links=[{
            "type": "shared_resource",
            "kind": "library",
            "name": "requests-lib",
            "referents": [
                {"repo": "beta", "label": "requests"},
                {"repo": "alpha", "file": "src/app.ts"},
            ],
        }])
        build_cluster(cluster)
        G = _load_out(cluster)
        hub = "cluster::library_requests_lib"
        assert hub in G, f"hub missing for member order {member_order}"
        referents = set(G.predecessors(hub))
        assert any("requests" in r for r in referents), member_order
        assert "alpha::app" in referents, member_order
