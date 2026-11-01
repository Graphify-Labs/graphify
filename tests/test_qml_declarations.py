"""QML-01 declarations, source evidence and rejection at the production boundary."""
from __future__ import annotations

from collections import Counter

import pytest

from graphify.extractors.qml import extract_qml
from graphify.validate import validate_extraction
from tests.qml_test_helpers import DECLARATIONS, DECLARATION_KINDS, assert_contains, assert_spans, by_kind, canonical, one, qml, write_qml


def test_qml003_ac01_exact_declarations_ownership_and_raw_types(tmp_path):
    """Members/imports belong to source owners; no body-derived guesses are emitted."""
    path = write_qml(tmp_path)
    result = extract_qml(path, root=tmp_path)
    assert not result.get("error")
    assert Counter(qml(node)["kind"] for node in result["nodes"] if qml(node)["kind"] in DECLARATION_KINDS) == {
        "file": 1, "component": 1, "object": 2, "property": 6,
        "signal": 1, "function": 1, "import": 4,
    }
    assert validate_extraction(result) == []
    file_node, component = one(result, "file"), one(result, "component")
    assert qml(component)["raw_name"] == "Main"
    objects = {qml(node)["object_id"]: node for node in by_kind(result, "object")}
    assert set(objects) == {"root", "editor"}
    assert qml(objects["root"])["type_name"] == "Item"
    assert qml(objects["editor"])["type_name"] == "Controls.TextField"
    assert_contains(result, file_node, component)
    assert_contains(result, component, objects["root"])
    assert_contains(result, objects["root"], objects["editor"])
    root_properties = {"count": "int", "title": "string", "doubled": "int", "extras": "list<QtObject>", "editorText": "alias"}
    for name, raw_type in root_properties.items():
        node = one(result, "property", name)
        assert qml(node)["raw_type"] == raw_type
        assert qml(node)["parent_scope_key"] == qml(objects["root"])["object_scope_key"]
        assert_contains(result, objects["root"], node)
    assert_contains(result, objects["editor"], one(result, "property", "caption"))
    for kind, name in (("signal", "activated"), ("function", "bump")):
        assert_contains(result, objects["root"], one(result, kind, name))
    for name, modifier in (("title", "required"), ("doubled", "readonly"), ("extras", "default")):
        assert modifier in qml(one(result, "property", name))["modifiers"]
    assert not result.get("raw_calls")
    # QML-03 may add independently tested semantic sites/edges; this QML-01 test
    # remains exact about declarations and their source-backed ownership.
    assert any(edge["relation"] == "contains" for edge in result["edges"])
    assert all(edge["confidence"] == "EXTRACTED" for edge in result["edges"] if edge["relation"] == "contains")
    assert all(qml(node)["contract_version"] == 1 for node in result["nodes"])
    assert_spans(result, path.read_bytes())


def test_qml01_import_facts_preserve_kind_value_qualifier_and_versions(tmp_path):
    """Raw import facts retain evidence without invented module/component targets."""
    result = extract_qml(write_qml(tmp_path), root=tmp_path)
    imports = by_kind(result, "import")
    expected = [("module", "QtQuick", None, None, None), ("module", "QtQuick.Controls", "Controls", 6, 5), ("directory", "widgets", "Local", None, None), ("script", "helpers.js", "Helpers", None, None)]
    actual = [tuple(qml(node).get(key) for key in ("import_kind", "value", "qualifier", "major", "minor")) for node in imports]
    assert actual == expected
    for node in imports:
        assert_contains(result, one(result, "file"), node)


def test_qml003_ac03_comments_literals_groups_and_js_inner_functions_are_not_objects(tmp_path):
    """Grouped properties have their own kind; fake and nested-JS declarations stay opaque."""
    source = '''import QtQuick
Item {
    property string example: "Rectangle { id: fake }"
    /* Button { id: phantom } */
    function calculate() { function inner() { return 3; } return inner(); }
    anchors { left: parent.left; topMargin: 4 }
    Text { id: label; font { pixelSize: 12; bold: true } }
}
'''
    result = extract_qml(write_qml(tmp_path, source=source), root=tmp_path)
    assert not result.get("error")
    assert [qml(node)["type_name"] for node in by_kind(result, "object")] == ["Item", "Text"]
    groups = by_kind(result, "property_group")
    assert [qml(node)["raw_name"] for node in groups] == ["anchors", "font"]
    assert all(qml(node)["raw_type"] == "" for node in groups)
    assert [qml(node)["raw_name"] for node in by_kind(result, "function")] == ["calculate"]
    assert len(by_kind(result, "property")) == 1
    assert not result.get("raw_calls")


def test_qml003_ac01_unicode_crlf_spans_and_original_names(tmp_path):
    """Production facts preserve original bytes and Unicode identifiers."""
    source = 'import QtQuick\r\nItem {\r\n    property string café: "雪😀"; property int après: 2\r\n}\r\n'
    path = write_qml(tmp_path, source=source)
    result = extract_qml(path, root=tmp_path)
    assert not result.get("error")
    assert [qml(node)["raw_name"] for node in by_kind(result, "property")] == ["café", "après"]
    assert_spans(result, path.read_bytes())
    span = qml(one(result, "property", "après"))["span"]
    prefix = source.encode("utf-8").split(b"\r\n")[2][:span["start_column"]]
    assert span["start_column"] == len(prefix) > len(prefix.decode("utf-8"))


def test_qml003_ac04_repeated_valid_extraction_is_identical(tmp_path):
    """Same production invocation retains node, edge, evidence and diagnostic facts."""
    path = write_qml(tmp_path)
    assert canonical(extract_qml(path, root=tmp_path)) == canonical(extract_qml(path, root=tmp_path))


@pytest.mark.parametrize("source", ['Item { property int kept: 1; function unfinished() {', 'Item { property int broken: @@@; property string kept: "safe" }'])
def test_qml012_ac01_malformed_or_partial_parse_has_no_authoritative_nodes(tmp_path, source):
    """Recovery cannot publish earlier declarations as a complete successful result."""
    result = extract_qml(write_qml(tmp_path, source=source), root=tmp_path)
    assert result.get("error")
    assert result["nodes"] == [] and result["edges"] == []
    assert result.get("diagnostics")
    assert all(str(tmp_path) not in str(diagnostic) for diagnostic in result["diagnostics"])


def test_qml001_ac04_empty_source_is_distinguishable_from_parse_failure(tmp_path):
    """Empty input retains its file fact and explicit informational coverage status."""
    result = extract_qml(write_qml(tmp_path, source=""), root=tmp_path)
    assert not result.get("error") and len(result["nodes"]) == 1
    file_node = one(result, "file")
    assert qml(file_node)["empty"] is True and result["edges"] == []
    assert any(diagnostic["code"] == "QML_EMPTY" for diagnostic in result["diagnostics"])
    assert qml(file_node)["span"]["start_byte"] == qml(file_node)["span"]["end_byte"] == 0


def test_qml003_ac01_source_slices_match_hand_checked_declarations(tmp_path):
    """Reported spans enclose the named declaration, not an unrelated member/body."""
    path = write_qml(tmp_path)
    result = extract_qml(path, root=tmp_path)
    source = DECLARATIONS.encode("utf-8")
    for kind, name, prefix in (("property", "count", b"property int count"), ("property", "title", b"required property string title"), ("signal", "activated", b"signal activated"), ("function", "bump", b"function bump")):
        span = qml(one(result, kind, name))["span"]
        assert source[span["start_byte"]:span["end_byte"]].startswith(prefix)
