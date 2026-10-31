"""INC-QML-89 shared-type composition retains independent source mechanisms."""
from __future__ import annotations

from graphify.build import add_source_relationship, build_from_json, prefix_graph_for_global
from graphify.cross_repo_types import link_shared_type_declarations
from graphify.extract import extract
from graphify.source_relationships import make_source_graph


def test_req_qml022_ac06_shared_type_fact_does_not_displace_or_hide_existing_reference(tmp_path):
    """Actual same-named sourced types retain a preexisting reference and one shared-type fact."""
    inputs = []
    for repo in ("first", "second"):
        root = tmp_path / repo
        root.mkdir()
        path = root / "Data.cs"
        path.write_text("namespace App{class Shared{void Use(){void Local(){} Local();}}}")
        inputs.append(prefix_graph_for_global(build_from_json(extract([path], root=root, cache_root=root, parallel=False), root=root), repo))
    graph = make_source_graph([node for source in inputs for node in source.nodes(data=True)], graph_metadata=inputs[0].graph)
    for source in inputs:
        graph.add_nodes_from(source.nodes(data=True))
        for u, v, data in source.edges(data=True):
            add_source_relationship(graph, u, v, data)
    left, right = [next(identity for identity, node in source.nodes(data=True) if node.get("_callable_class")) for source in inputs]
    add_source_relationship(graph, left, right, {"relation": "references", "confidence": "EXTRACTED"})
    assert link_shared_type_declarations(graph) == 1
    assert {data["relation"] for u, v, data in graph.edges(data=True) if {u, v} == {left, right}} == {"references", "same_type_as"}
    before = graph.number_of_edges()
    assert link_shared_type_declarations(graph) == 0 and graph.number_of_edges() == before
