"""Collapsed-edge provenance on the simple graph (#2311).

The graph is deliberately a simple Graph/DiGraph: parallel edges are not needed
for traversal. But repeated observations of the same node pair collapse onto one
edge, and before this every attribute but the last was lost — 1,112 collapses in
a real corpus left no trace of what produced them. The surviving edge must carry
deterministic evidence of everything that merged into it.
"""
import networkx as nx

from graphify.build import build_from_json


def _extraction(edges, nodes=None):
    node_ids = nodes or sorted({e["source"] for e in edges} | {e["target"] for e in edges})
    return {
        "nodes": [
            {"id": n, "label": n, "file_type": "code", "source_file": "App/Sample.swift"}
            for n in node_ids
        ],
        "edges": edges,
    }


def _edge(source, target, relation="references", location="L1",
          source_file="App/Sample.swift", confidence="EXTRACTED"):
    return {
        "source": source, "target": target, "relation": relation,
        "confidence": confidence, "source_file": source_file,
        "source_location": location, "weight": 1.0,
    }


def test_repeated_swift_references_keep_every_source_location():
    """A Swift type referencing another on 5 lines collapses to one edge."""
    edges = [_edge("Record", "Bool", location=f"L{n}") for n in (152, 153, 154, 155, 156)]
    G = build_from_json(_extraction(edges), directed=False)

    assert G.number_of_edges() == 1
    data = G.edges["Record", "Bool"]
    assert data["evidence_count"] == 5
    assert data["source_locations"] == ["L152", "L153", "L154", "L155", "L156"]
    assert data["relations"] == ["references"]
    # One direction only -> no `directions` noise on the edge.
    assert "directions" not in data


def test_differing_relations_are_all_preserved():
    edges = [
        _edge("View", "Protocol", relation="implements", location="L3"),
        _edge("View", "Protocol", relation="references", location="L34"),
        _edge("View", "Protocol", relation="references", location="L124"),
    ]
    G = build_from_json(_extraction(edges), directed=False)

    data = G.edges["View", "Protocol"]
    assert data["evidence_count"] == 3
    assert data["relations"] == ["implements", "references"]
    # Lexicographic, not numeric — the contract is determinism, not line order.
    assert data["source_locations"] == ["L124", "L3", "L34"]


def test_differing_source_files_are_preserved():
    edges = [
        _edge("Alpha", "Beta", location="L10", source_file="App/One.swift"),
        _edge("Alpha", "Beta", location="L20", source_file="App/Two.swift"),
    ]
    G = build_from_json(_extraction(edges), directed=False)

    data = G.edges["Alpha", "Beta"]
    assert data["source_files"] == ["App/One.swift", "App/Two.swift"]
    assert data["evidence_count"] == 2


def test_reciprocal_directions_are_recorded_not_silently_dropped():
    """a->b and b->a collapse on an undirected graph; both must stay visible."""
    edges = [
        _edge("Alpha", "Beta", relation="calls", location="L5"),
        _edge("Beta", "Alpha", relation="calls", location="L9"),
    ]
    G = build_from_json(_extraction(edges), directed=False)

    assert G.number_of_edges() == 1
    data = G.edges["Alpha", "Beta"]
    assert data["directions"] == ["Alpha->Beta", "Beta->Alpha"]
    assert data["evidence_count"] == 2
    assert data["source_locations"] == ["L5", "L9"]
    # First-seen direction still wins for the primary attributes (#1061).
    assert (data["_src"], data["_tgt"]) == ("Alpha", "Beta")


def test_single_direction_records_no_directions_field():
    edges = [_edge("Alpha", "Beta", location="L1"), _edge("Alpha", "Beta", location="L2")]
    G = build_from_json(_extraction(edges), directed=False)
    assert "directions" not in G.edges["Alpha", "Beta"]


def test_semantic_edge_provenance_survives_collapse():
    """Semantic (LLM) edges collapse too — 2 did in the real corpus."""
    nodes = [
        {"id": "concept_a", "label": "Concept A", "file_type": "document",
         "source_file": "docs/one.md"},
        {"id": "concept_b", "label": "Concept B", "file_type": "document",
         "source_file": "docs/two.md"},
    ]
    edges = [
        _edge("concept_a", "concept_b", relation="shares_data_with",
              location="L12", source_file="docs/one.md", confidence="INFERRED"),
        _edge("concept_a", "concept_b", relation="conceptually_related_to",
              location="L40", source_file="docs/two.md", confidence="INFERRED"),
    ]
    G = build_from_json({"nodes": nodes, "edges": edges}, directed=False)

    data = G.edges["concept_a", "concept_b"]
    assert data["evidence_count"] == 2
    assert data["relations"] == ["conceptually_related_to", "shares_data_with"]
    assert data["source_files"] == ["docs/one.md", "docs/two.md"]
    assert data["source_locations"] == ["L12", "L40"]


def test_provenance_is_deterministic_across_rebuilds():
    """Same extraction -> byte-identical provenance, regardless of input order."""
    edges = [
        _edge("Alpha", "Beta", relation="calls", location="L9"),
        _edge("Beta", "Alpha", relation="calls", location="L5"),
        _edge("Alpha", "Beta", relation="references", location="L1"),
        _edge("Alpha", "Gamma", location="L7"),
    ]

    def provenance(edge_list):
        G = build_from_json(_extraction(edge_list), directed=False)
        return {
            tuple(sorted((u, v))): (
                d.get("evidence_count"), tuple(d.get("relations", ())),
                tuple(d.get("source_files", ())), tuple(d.get("source_locations", ())),
                tuple(d.get("directions", ())),
            )
            for u, v, d in G.edges(data=True)
        }

    baseline = provenance(edges)
    assert provenance(edges) == baseline
    assert provenance(list(reversed(edges))) == baseline
    assert provenance([edges[2], edges[0], edges[3], edges[1]]) == baseline


def test_directed_graph_keeps_opposite_directions_apart():
    """A DiGraph does not collapse a->b with b->a, so each keeps its own count."""
    edges = [
        _edge("Alpha", "Beta", relation="calls", location="L1"),
        _edge("Alpha", "Beta", relation="calls", location="L2"),
        _edge("Beta", "Alpha", relation="calls", location="L3"),
    ]
    G = build_from_json(_extraction(edges), directed=True)

    assert isinstance(G, nx.DiGraph)
    assert G.number_of_edges() == 2
    assert G.edges["Alpha", "Beta"]["evidence_count"] == 2
    assert G.edges["Beta", "Alpha"]["evidence_count"] == 1


def test_uncollapsed_edge_still_reports_single_evidence():
    G = build_from_json(_extraction([_edge("Alpha", "Beta", location="L4")]), directed=False)
    data = G.edges["Alpha", "Beta"]
    assert data["evidence_count"] == 1
    assert data["relations"] == ["references"]
    assert data["source_locations"] == ["L4"]
