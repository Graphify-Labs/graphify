"""`affected` must traverse the cross-repo relations added by cluster links."""
import networkx as nx

from graphify.affected import DEFAULT_AFFECTED_RELATIONS, affected_nodes


def _cluster_shaped_graph():
    """A composed cluster graph in miniature: two repos + spec-declared links."""
    G = nx.Graph()
    G.add_node("web::client", label="cube-client.ts", repo="web",
               source_file="app/lib/cube/cube-client.ts")
    G.add_node("svc::server", label="cube.js", repo="svc", source_file="cube.js")
    G.add_node("web::payload", label="payload.ts", repo="web",
               source_file="src/types/payload.ts")
    G.add_node("svc::payload", label="payload.ts", repo="svc",
               source_file="src/payload.ts")
    # Stored orientation is (dependent, dependency), matching how
    # apply_spec_links adds from->to edges.
    G.add_edge("web::client", "svc::server", relation="calls_api",
               origin="cluster_spec", _src="web::client", _tgt="svc::server")
    G.add_edge("web::payload", "svc::payload", relation="mirrors",
               origin="cluster_spec", _src="web::payload", _tgt="svc::payload")
    return G


def test_default_relations_include_cluster_relations():
    assert "calls_api" in DEFAULT_AFFECTED_RELATIONS
    assert "mirrors" in DEFAULT_AFFECTED_RELATIONS
    # depends_on predates clusters and must stay out of the defaults (it would
    # change single-repo affected behavior through manifest dependency edges).
    assert "depends_on" not in DEFAULT_AFFECTED_RELATIONS


def test_affected_crosses_repo_boundary_via_calls_api():
    G = _cluster_shaped_graph()
    hits = affected_nodes(G, "svc::server", depth=2)
    assert any(h.node_id == "web::client" and h.via_relation == "calls_api" for h in hits)


def test_affected_crosses_repo_boundary_via_mirrors():
    G = _cluster_shaped_graph()
    hits = affected_nodes(G, "svc::payload", depth=2)
    assert any(h.node_id == "web::payload" and h.via_relation == "mirrors" for h in hits)
