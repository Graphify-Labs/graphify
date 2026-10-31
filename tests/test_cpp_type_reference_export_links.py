"""INC-QML-114: supplied raw links cannot erase a known accepted restriction."""
from __future__ import annotations

import base64
from copy import deepcopy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from tests.cpp_type_reference_helpers import produce, unavailable


def project(root, *, directed=False):
    """Two actual fields share an arc; ordinary simple storage retains one proof."""
    raw = (b"namespace Left{using Count=int;}\nnamespace Right{class Holder{\n"
           b"Count first;\nCount second;\n};}\n")
    result = produce(root, raw, "direct")
    assert len(unavailable(result)) == 2
    graph = build_from_json(result, root=root, directed=directed)
    retained = [edge for _, _, edge in graph.edges(data=True) if "cpp_type_reference_version" in edge]
    assert len(retained) == 1
    return graph, result["edges"], retained[0]["metadata"]["cpp_type_reference"]


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("damage", ["strip_both", "empty", "drop_known", "fact", "location", "relation"])
def test_req_qml014_ac03_supplied_links_cannot_erase_known_graph_context(tmp_path, directed, force, damage):
    """Real source promises must survive an overriding link collection before state or disk changes."""
    graph, links, retained = project(tmp_path, directed=directed)
    output = tmp_path / "accepted.json"
    assert to_json(graph, {}, str(output), force=True, original_links=links)
    accepted = output.read_bytes()
    supplied = deepcopy(links)
    known = next(edge for edge in unavailable({"edges": supplied})
                 if edge["metadata"]["cpp_type_reference"] == retained)
    if damage == "strip_both":
        for edge in unavailable({"edges": supplied}):
            edge.pop("cpp_type_reference_version")
            edge["metadata"].pop("cpp_type_reference")
    elif damage == "empty":
        supplied.clear()
    elif damage == "drop_known":
        supplied.remove(known)
    elif damage == "fact":
        known["metadata"]["cpp_type_reference"]["lookup_b64"] = base64.b64encode(b"Alternate").decode()
    elif damage == "location":
        known["source_location"] = "L1"
    else:
        known["relation"] = "inherits"
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = deepcopy((graph.graph, list(graph.nodes(data=True)), list(graph.edges(data=True)), supplied))
    assert to_json(graph, {}, str(output), force=force, original_links=supplied) is False
    assert output.read_bytes() == accepted
    assert (graph.graph, list(graph.nodes(data=True)), list(graph.edges(data=True)), supplied) == before


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml014_ac03_supplied_extra_actual_parallel_evidence_is_preserved(tmp_path, directed):
    """Known proof inclusion allows real raw observations that simple Graph folded."""
    graph, links, retained = project(tmp_path, directed=directed)
    output = tmp_path / "parallel.json"
    before = deepcopy(links)
    assert to_json(graph, {}, str(output), force=True, original_links=links)
    payload = json.loads(output.read_text(encoding="utf-8"))
    marked = unavailable({"edges": payload["links"]})
    assert len(marked) == 2 and any(edge["metadata"]["cpp_type_reference"] == retained for edge in marked)
    assert len({edge["metadata"]["cpp_type_reference"]["type_span"]["start_byte"] for edge in marked}) == 2
    restored = load_node_link_graph(payload)
    restored_edges = [edge for _, _, edge in restored.edges(data=True) if "cpp_type_reference_version" in edge]
    assert sorted(edge["metadata"]["cpp_type_reference"]["type_span"]["start_byte"] for edge in restored_edges) == sorted(
        edge["metadata"]["cpp_type_reference"]["type_span"]["start_byte"] for edge in marked)
    assert len(restored_edges) == 2
    for left, right, edge in restored.edges(data=True):
        if "cpp_type_reference_version" in edge:
            target = edge.get("_tgt", right)
            assert target in {left, right} and not restored.nodes[target]["source_file"]
    assert links == before
    # None still means derive output from the accepted graph, without a raw override.
    assert to_json(graph, {}, str(output), force=True, original_links=None)


def test_req_qml014_ac03_legacy_original_links_remain_an_independent_supported_view(tmp_path):
    """Absent C++ restrictions do not introduce graph/list equality or a new mode."""
    import networkx as nx
    graph = nx.Graph()
    graph.add_nodes_from(("first", "second"))
    graph.add_edge("first", "second", relation="references")
    output = tmp_path / "legacy.json"
    assert to_json(graph, {}, str(output), force=True, original_links=[])
    assert json.loads(output.read_text(encoding="utf-8"))["links"] == []
