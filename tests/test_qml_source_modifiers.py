"""INC-QML-66: Qt6.12 declaration modifiers retain source-only syntax evidence."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml import extract_qml
from graphify.extractors.qml_facts import qml_metadata
from graphify.paths import load_node_link_graph
from tests.qml_expression_helpers import extraction, nodes, single


@pytest.mark.parametrize("modifier", ["virtual", "override", "final"])
def test_req_qml022_ac04_source_property_modifiers_keep_original_spans(tmp_path, modifier):
    """Grammar compatibility retains original bytes; it asserts no engine semantics."""
    source = f'\ufeffQtObject {{\r\n // café\r\n {modifier} /* keep */ property int amount: 1\r\n}}\r\n'.encode()
    path = tmp_path / "Main.qml"
    path.write_bytes(source)
    direct = extract_qml(path, root=tmp_path)
    assert not direct.get("error"), direct
    prop = single(direct, "property", "amount")
    md = qml_metadata(prop)
    assert md["modifiers"] == [modifier]
    assert md["modifier_status"] == "source_only"
    assert md["modifier_reason"] == "override_semantics_require_engine"
    span = md["span"]
    assert source[span["start_byte"]:span["end_byte"]] == f'{modifier} /* keep */ property int amount: 1'.encode()
    result = extraction(tmp_path, {"Base.qml": "QtObject { virtual property int amount: 1 }",
        "Main.qml": f"Base {{ {modifier} property int amount: 2; property int shown: amount }}"})
    prop = single(result, "property", "amount", "Main.qml")
    read = single(result, "read", "amount", "Main.qml")
    assert qml_metadata(read)["resolved_target_id"] == prop["id"]
    graph = build_from_json(result, root=tmp_path, directed=True)
    output = tmp_path / "graph.json"
    to_json(graph, {}, str(output))
    loaded = load_node_link_graph(json.loads(output.read_text()))
    assert qml_metadata(loaded.nodes[prop["id"]])["modifiers"] == [modifier]
    assert loaded.has_edge(read["id"], prop["id"])


@pytest.mark.parametrize("modifiers", ["virtual override", "virtual final", "override final",
                                        "virtual virtual", "override override", "final final"])
def test_req_qml022_ac04_conflicting_source_modifiers_reject(tmp_path, modifiers):
    """Documented parser errors must not be normalized into plausible properties."""
    path = tmp_path / "Main.qml"
    path.write_bytes(f"QtObject {{ {modifiers} property int amount: 1 }}".encode())
    result = extract_qml(path, root=tmp_path)
    assert result["nodes"] == [] and result["edges"] == []
    assert result["qml_failures"] == [{"code": "QML_SYNTAX", "source_file": "Main.qml"}]


def test_req_qml022_ac04_source_modifier_recovery_preserves_ordinary_identifiers(tmp_path):
    """A real modifier alongside JS names/string/comment spellings grants no rewrite."""
    source = '''QtObject {
 virtual readonly property int amount: 1
 property string virtual: "override property int fake: 2"
 property int override: 3
 // virtual property int phantom: 4
 function check(virtual, override) { return virtual + override }
}'''
    result = extraction(tmp_path, {"Main.qml": source})
    assert {qml_metadata(node)["raw_name"] for node in nodes(result, "property")} == {"amount", "virtual", "override"}
    assert qml_metadata(single(result, "property", "amount"))["modifiers"] == ["virtual", "readonly"]
    for reference in ["virtual", "override"]:
        site = single(result, "read", reference)
        assert qml_metadata(site)["status"] == "dynamic"
        assert qml_metadata(site)["reason"] == "javascript_lexical_binding"


@pytest.mark.parametrize("source", [
    "QtObject { virtual function check() {} }",
    "QtObject { override amount: 1 }",
    "QtObject { abstract property int amount: 1 }",
    "QtObject { virtual property int amount: @@@ }",
    'QtObject { property string text: "virtual property int amount: 1 }',
])
def test_req_qml022_ac04_unknown_or_malformed_modifier_contexts_remain_failed(tmp_path, source):
    """Compatibility repairs only property modifier tokens, never arbitrary errors."""
    path = tmp_path / "Main.qml"
    path.write_bytes(source.encode())
    result = extract_qml(path, root=tmp_path)
    assert result.get("error") and not result["nodes"]


@pytest.mark.parametrize("limit", ["depth", "nodes"])
def test_req_qml022_ac06_ast_bounds_precede_modifier_compatibility_walks(tmp_path, monkeypatch, limit):
    """Oversized/deep real ASTs stop at QML_LIMIT before any recovery traversal."""
    import graphify.extractors.qml_source_modifiers as modifiers

    path = tmp_path / "Main.qml"
    if limit == "depth":
        source = "QtObject { " * 260 + "virtual property int amount: 1" + " }" * 260
    else:
        source = "QtObject { virtual property int amount: 1\n" + "\n".join(f"property int p{n}: 0" for n in range(20000)) + "\n}"
    path.write_bytes(source.encode())

    def forbidden_walk(_):
        raise AssertionError("compatibility traversed an over-budget raw AST")

    monkeypatch.setattr(modifiers, "_walk", forbidden_walk)
    result = extract_qml(path, root=tmp_path)
    assert not result["nodes"]
    assert result["qml_failures"] == [{"code": "QML_LIMIT", "source_file": "Main.qml"}]
