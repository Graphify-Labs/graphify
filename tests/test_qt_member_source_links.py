"""REQ-QML-008-AC02 links source occurrences without inventing class authority."""
import copy
import json
import re

import pytest

from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_html, to_json
from graphify.extractors.qt_cpp_exposure import enrich_qt_cpp, is_qt_cpp_source
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qt_qml_bridge import build_qt_qml_bridge
from tests.qt_analysis_helpers import analysis, sites


HEADER = "class Utility { public: void write(int value); };\n"
METHOD = "void Utility::write(int value) { Q_UNUSED(value) }"
LOCAL = "void collect(int value) { struct Row { int entry; }; Q_UNUSED(value) }"
HINT = "class Utility;\nclass Host : public QObject { Q_OBJECT };\n"


def utility(root, filename="utility.cpp", *, hint=False):
    sources = {"utility.hpp": HEADER, filename: '#include "utility.hpp"\n' + METHOD + "\n"}
    if hint:
        sources[filename] = sources[filename].replace("Q_UNUSED(value)", "(void)value;")
        sources["host.hpp"] = HINT
    result = analysis(root, sources)
    member = next(node for node in sites(result, "member")
                  if qt_metadata(node)["class_name"] == "Utility")
    return result, member


def occurrence(result, kind):
    values = sites(result, kind)
    if kind == "member":
        values = [node for node in values if qt_metadata(node)["class_name"] == "Utility"]
    assert len(values) == 1
    return values[0]


def accepted_generic(result):
    nodes = copy.deepcopy([node for node in result["nodes"] if not qt_metadata(node)])
    ids = {node["id"] for node in nodes}
    edges = copy.deepcopy([edge for edge in result["edges"]
                           if not qt_metadata(edge) and edge["source"] in ids and edge["target"] in ids])
    return nodes, edges


def assert_source_link(result, site, target, original):
    metadata = qt_metadata(site)
    assert metadata["owner_id"] == target
    assert metadata["class_id"] == ""
    span = metadata["span"]
    assert original[span["start_byte"]:span["end_byte"]] in (
        METHOD.encode(), METHOD.replace("Q_UNUSED(value)", "(void)value;").encode(), b"struct Row { int entry; }")
    links = [edge for edge in result["edges"] if edge["source"] == target and edge["target"] == site["id"]]
    assert len(links) == 1
    assert links[0]["relation"] == "contains" and links[0]["confidence"] == "EXTRACTED"
    assert links[0]["context"] == "qt_source_site"
    assert qt_metadata(links[0])["span"] == span


@pytest.mark.parametrize("filename,hint", [("utility.cpp", False), ("writer.cpp", False),
                                           ("writer.cpp", True)])
def test_req_qml008_ac02_plain_member_uses_exact_callable_without_native_class_claim(tmp_path, filename, hint):
    result, member = utility(tmp_path, filename, hint=hint)
    metadata = qt_metadata(member)
    target = metadata["generic_target_id"]
    declaration = next(node for node in result["nodes"] if node["id"] == target)
    assert metadata["status"] == "resolved"
    assert declaration.get("_callable") is True and not declaration.get("_callable_class")
    assert not metadata["roles"] and metadata["class_id"] == ""
    assert metadata["owner_id"] == target
    assert not is_qt_cpp_source(tmp_path / "utility.hpp")
    assert not [node for node in sites(result, "class") if qt_metadata(node).get("class_name") == "Utility"
                and qt_metadata(node).get("is_definition") is True]
    if hint:
        assert not is_qt_cpp_source(tmp_path / filename)
        assert is_qt_cpp_source(tmp_path / filename, class_names=["Utility"])
        forwards = [node for node in sites(result, "class") if qt_metadata(node)["class_name"] == "Utility"]
        assert len(forwards) == 1 and qt_metadata(forwards[0])["is_definition"] is False
    assert_source_link(result, member, target, (tmp_path / filename).read_bytes())
    index = build_qt_qml_bridge(result["nodes"], result["edges"], root=tmp_path)
    assert not index.provider_records and index.module_type("Demo", 1, 0, "Utility").status == "unavailable"


def test_req_qml008_ac02_source_link_survives_build_json_and_aggregate(tmp_path):
    result, member = utility(tmp_path)
    target = qt_metadata(member)["generic_target_id"]
    graph = build_from_json(result, root=tmp_path)
    assert graph.has_edge(target, member["id"]) and graph.degree(member["id"]) > 0
    groups = cluster(graph)
    community = next(values for values in groups.values() if member["id"] in values)
    assert target in community and len(community) > 1
    output = tmp_path / "graph.json"
    assert to_json(graph, groups, str(output))
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    edge = restored.edges[target, member["id"]]
    assert (edge["_src"], edge["_tgt"]) == (target, member["id"])
    assert edge["relation"] == "contains" and edge["context"] == "qt_source_site"
    assert qt_metadata(dict(restored.nodes[member["id"]])) == qt_metadata(member)
    html = tmp_path / "graph.html"
    assert to_html(restored, groups, str(html), node_limit=1)
    match = re.search(r"const RAW_NODES = (\[.*?\]);", html.read_text(encoding="utf-8"), re.S)
    assert match
    payload = json.loads(match[1])
    assert not [node for node in payload if node.get("member_count") == 1 and "Qt member" in node["label"]]


def test_req_qml008_ac02_local_class_links_to_enclosing_callable_without_type_authority(tmp_path):
    result = analysis(tmp_path, {"local.cpp": LOCAL + "\n"})
    local = occurrence(result, "class")
    function = next(node for node in result["nodes"] if node.get("_callable")
                    and node.get("source_file") == "local.cpp" and node["label"] == "collect()")
    metadata = qt_metadata(local)
    assert metadata["is_definition"] is True and metadata["status"] == "unavailable"
    assert metadata["generic_target_id"] == "" and metadata["class_id"] == ""
    assert not metadata["is_qobject"] and not metadata["source_q_object"]
    assert_source_link(result, local, function["id"], LOCAL.encode())
    assert not build_qt_qml_bridge(result["nodes"], result["edges"], root=tmp_path).provider_records


@pytest.mark.parametrize("kind", ["member", "class"])
def test_req_qml008_ac02_direct_collector_borrows_exact_callable_without_mutating_context(tmp_path, kind):
    if kind == "member":
        accepted, _ = utility(tmp_path, "writer.cpp")
        path = tmp_path / "writer.cpp"
        target = qt_metadata(occurrence(accepted, kind))["generic_target_id"]
    else:
        accepted = analysis(tmp_path, {"local.cpp": LOCAL + "\n"})
        path = tmp_path / "local.cpp"
        target = next(node["id"] for node in accepted["nodes"] if node.get("_callable")
                      and node["label"] == "collect()")
    nodes, edges = accepted_generic(accepted)
    before = copy.deepcopy((nodes, edges))
    fresh = {"nodes": [], "edges": []}
    enrich_qt_cpp([path], [fresh], root=tmp_path, accepted_nodes=nodes, accepted_edges=edges)
    assert (nodes, edges) == before
    assert not fresh.get("qml_failures")
    assert_source_link(fresh, occurrence(fresh, kind), target, path.read_bytes())


@pytest.mark.parametrize("kind", ["member", "class"])
@pytest.mark.parametrize("corruption", ["missing", "wrong_file", "wrong_line", "ambiguous",
                                         "not_callable", "class_like"])
def test_req_qml008_ac02_source_fallback_rejects_unproved_or_noncallable_context(tmp_path, kind, corruption):
    if kind == "member":
        accepted, _ = utility(tmp_path, "writer.cpp")
        path = tmp_path / "writer.cpp"
        target = qt_metadata(occurrence(accepted, kind))["generic_target_id"]
    else:
        accepted = analysis(tmp_path, {"local.cpp": LOCAL + "\n"})
        path = tmp_path / "local.cpp"
        target = next(node["id"] for node in accepted["nodes"] if node.get("_callable")
                      and node["label"] == "collect()")
    nodes, edges = accepted_generic(accepted)
    chosen = next(node for node in nodes if node["id"] == target)
    if corruption == "missing":
        nodes.remove(chosen)
    elif corruption == "wrong_file":
        chosen["source_file"] = "foreign.cpp"
    elif corruption == "wrong_line":
        chosen["source_location"] = "L100"
    elif corruption == "ambiguous":
        nodes.append({**copy.deepcopy(chosen), "id": target + "_different"})
    elif corruption == "not_callable":
        chosen["_callable"] = False
    elif corruption == "class_like":
        chosen["_callable_class"] = True
    before = copy.deepcopy((nodes, edges))
    fresh = {"nodes": [], "edges": []}
    enrich_qt_cpp([path], [fresh], root=tmp_path, accepted_nodes=nodes, accepted_edges=edges)
    assert (nodes, edges) == before
    assert not fresh.get("qml_failures")
    site = occurrence(fresh, kind)
    metadata = qt_metadata(site)
    assert metadata["owner_id"] == "" and metadata["class_id"] == ""
    if kind == "member" and corruption == "class_like":
        assert metadata["status"] == "resolved" and metadata["generic_target_id"] == target
    assert not [edge for edge in fresh["edges"] if edge["target"] == site["id"]
                and edge["context"] == "qt_source_site"]
