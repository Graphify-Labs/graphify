"""REQ-QML-022-AC06: explicit validation contexts cannot cross graph revisions."""
import copy

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.build import build_from_json
from graphify.qt_metaobject import QtMetaobjectIndex
from graphify.qt_qml_projection import allows_qt_qml_edge
from tests.qt_metaobject_helpers import analyzed, bridge, facts, member_edges, sources
from tests.qt_analysis_helpers import analysis


@pytest.mark.parametrize("corruption", ["marker", "class"])
def test_metaobject_index_rejects_changed_source_after_prior_success(tmp_path, corruption):
    """An earlier lookup cannot cache authority across mutation of borrowed source proof."""
    result = analyzed(tmp_path)
    index = bridge(tmp_path, result)
    provider = index.module_type("Public.Probe", 1, 0, "Service")
    assert index.member(provider.target_id, "ownMethod").status == "resolved"
    if corruption == "marker":
        marker, = facts(result, "metaobject")
        update_qt(marker, owner_id="changed-source")
    else:
        owner, = facts(result, "class")
        identity = qt_metadata(owner)["class_id"]
        next(node for node in result["nodes"] if node["id"] == identity)["_callable_class"] = False
    with pytest.raises(ValueError, match="QT_METADATA"):
        index.member(provider.target_id, "ownMethod")


@pytest.mark.parametrize("change", ["foreign_nodes", "foreign_edges", "changed_marker", "replaced_class"])
def test_explicit_metaobject_context_is_bound_to_its_actual_source_snapshot(tmp_path, change):
    """Only the exact graph/immutable ownership snapshot may reuse its validated index."""
    result = analyzed(tmp_path)
    nodes = {node["id"]: node for node in result["nodes"]}
    edges = tuple(result["edges"])
    index = QtMetaobjectIndex(nodes, edges)
    edge = member_edges(result)[0]
    def accepted(view=nodes, ownership=edges):
        return allows_qt_qml_edge(view[edge["source"]], view[edge["target"]], edge,
            source_id=edge["source"], target_id=edge["target"], nodes=view, edges=ownership, metaobject_index=index)
    assert accepted()
    if change == "foreign_nodes":
        assert not accepted(copy.deepcopy(nodes))
    elif change == "foreign_edges":
        assert not accepted(ownership=tuple(copy.deepcopy(result["edges"])))
    elif change == "changed_marker":
        marker, = facts(result, "metaobject")
        update_qt(marker, conditional=True)
        assert not accepted()
    else:
        owner, = facts(result, "class")
        nodes[owner["id"]] = copy.deepcopy(owner)
        assert not accepted()


@pytest.mark.parametrize("absolute", [False, True])
def test_graph_context_uses_complete_ownership_after_endpoint_and_path_normalization(tmp_path, absolute):
    """Late-sorted class ownership and accepted absolute paths cannot depend on edge insertion order."""
    files = sources()
    files["zznative.hpp"] = files.pop("backend.hpp")
    files["CMakeLists.txt"] = files["CMakeLists.txt"].replace("backend.hpp", "zznative.hpp")
    result = analysis(tmp_path, files)
    if absolute:
        for item in result["nodes"] + result["edges"]:
            if item.get("source_file"):
                item["source_file"] = str(tmp_path / item["source_file"])
    graph = build_from_json(result, root=tmp_path, directed=True)
    assert len([d for _, _, d in graph.edges(data=True) if d.get("context") in {
        "qml_js_call", "qml_binding_read", "qml_signal_subscription"}]) == 3


@pytest.mark.parametrize("kind", ["class", "metaobject"])
def test_list_source_context_rejects_replaced_element_after_success(tmp_path, kind):
    """Indexed list positions detect replacement with bounded work, without rescanning the corpus."""
    result = analyzed(tmp_path)
    index = QtMetaobjectIndex(result["nodes"], tuple(result["edges"]))
    owner, = facts(result, "class")
    identity = qt_metadata(owner)["class_id"]
    assert index.resolve(identity).status == "resolved"
    selected, = facts(result, kind)
    position = result["nodes"].index(selected)
    result["nodes"][position] = copy.deepcopy(selected)
    with pytest.raises(ValueError, match="QT_METADATA"):
        index.resolve(identity)


@pytest.mark.parametrize("field,value", [("target", "foreign-marker"), ("context", "unrelated-owner")])
def test_ownership_context_revalidates_actual_target_and_role_after_success(tmp_path, field, value):
    """An indexed ownership row cannot keep authority after its actual endpoint or mechanism changes."""
    result = analyzed(tmp_path)
    edges = tuple(result["edges"])
    index = QtMetaobjectIndex(result["nodes"], edges)
    owner, = facts(result, "class")
    marker, = facts(result, "metaobject")
    identity = qt_metadata(owner)["class_id"]
    assert index.resolve(identity).status == "resolved"
    ownership = next(e for e in edges if e.get("target") == marker["id"])
    ownership[field] = value
    with pytest.raises(ValueError, match="QT_METADATA"):
        index.resolve(identity)
