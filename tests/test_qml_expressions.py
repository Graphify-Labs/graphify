"""QML-006-AC01..04 static source reads, aliases, rejection and lossless sites."""

import json

import networkx as nx

from graphify.build import build_from_json
from graphify.extractors.qml_facts import qml_metadata
from tests.qml_expression_helpers import extraction, nodes, single, target_edges


def test_binding_reads_and_nested_qualified_aliases(tmp_path):
    result = extraction(tmp_path, {"Main.qml": """QtObject {
 id: root
 property int total: child.value + child.value
 property alias selected: child
 property alias nested: root.selected.value
 property QtObject childObject: QtObject { id: child; property int value: 3 }
}"""})
    value = single(result, "property", "value")
    repeated = nodes(result, "read", "child.value")
    assert len(repeated) == 2
    assert len({node["id"] for node in repeated}) == 2
    for site in repeated:
        assert target_edges(result, site)[0]["target"] == value["id"]
        assert qml_metadata(site)["span"]["end_byte"] > qml_metadata(site)["span"]["start_byte"]
    nested = single(result, "alias", "nested")
    assert target_edges(result, nested, "qml_alias_target")[0]["target"] == value["id"]
    assert qml_metadata(nested)["evidence"]


def test_alias_cycles_missing_and_ambiguous_targets_never_guess(tmp_path):
    result = extraction(tmp_path, {"Main.qml": """QtObject {
 id: root
 property alias a: root.b
 property alias b: root.a
 property alias missing: unknown.value
 property alias duplicate: root.value
 property int value: 1
 property int value: 2
}"""})
    for name, status in [("a", "unsupported"), ("b", "unsupported"),
                         ("missing", "unavailable"), ("duplicate", "ambiguous")]:
        site = single(result, "alias", name)
        assert qml_metadata(site)["status"] == status
        assert qml_metadata(site)["reason"]
        assert not target_edges(result, site)


def test_component_and_object_scope_do_not_bind_hidden_identifiers(tmp_path):
    result = extraction(tmp_path, {"Main.qml": """QtObject {
 id: root
 property int value: 1
 property int total: child.value
 property QtObject childObject: QtObject { id: child; property int value: 2 }
 component Inner: QtObject { property int hidden: child.value }
}"""})
    reads = nodes(result, "read", "child.value")
    assert len(reads) == 2
    assert sorted(qml_metadata(site)["status"] for site in reads) == ["resolved", "unavailable"]
    resolved = [site for site in reads if qml_metadata(site)["status"] == "resolved"][0]
    assert target_edges(result, resolved)[0]["target"] in {n["id"] for n in nodes(result, "property", "value")}
    hidden = [site for site in reads if qml_metadata(site)["status"] != "resolved"][0]
    assert not target_edges(result, hidden)


def test_dynamic_reads_and_executable_source_are_only_analyzed(tmp_path):
    marker = tmp_path / "must-not-exist"
    result = extraction(tmp_path, {"Main.qml": f"""QtObject {{
 property int value: provider()[key]
 function provider() {{ return {{}}; }}
 function dangerous() {{ require('fs').writeFileSync('{marker.as_posix()}', 'bad'); }}
}}"""})
    dynamic = [site for site in nodes(result, "read") if qml_metadata(site)["status"] == "dynamic"]
    assert dynamic and all(not target_edges(result, site) for site in dynamic)
    assert nodes(result, "call", "provider")
    assert not marker.exists()


def test_repeated_sites_survive_actual_directed_build_and_json(tmp_path):
    result = extraction(tmp_path, {"Main.qml": "QtObject { id: root; property int value: 1; property int sum: value + value }"})
    sites = nodes(result, "read", "value")
    graph = build_from_json(result, directed=True, root=tmp_path)
    assert isinstance(graph, nx.DiGraph)
    value = single(result, "property", "value")
    for site in sites:
        assert graph.has_edge(site["id"], value["id"])
    portable = nx.node_link_graph(json.loads(json.dumps(nx.node_link_data(graph))))
    assert len(sites) == 2
    for site in sites:
        assert portable.has_edge(site["id"], value["id"])
        assert qml_metadata(portable.nodes[site["id"]])["span"] == qml_metadata(site)["span"]
