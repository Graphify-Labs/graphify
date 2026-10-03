"""QML-004/009 metadata boundary: literal records, safe failures and provenance."""

import json

import pytest

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_metadata import MAX_METADATA_BYTES, extract_qmldir, parse_qmldir
from graphify.security import sanitize_metadata


def test_qmldir_literal_records_and_utf8_offsets():
    """Supported metadata retains independent records beyond sanitizer's list cap."""
    source = "# α\nmodule Public.Tools\n" + "".join(f"Widget{i} 1.0 Widget{i}.qml\n" for i in range(60))
    source += "singleton State 1.1 State.qml\ninternal Hidden Hidden.qml\n"
    source += "import Public.Base auto\ndepends Public.Runtime 1.0\noptional plugin tools\n"
    source += "typeinfo tools.qmltypes\nclassname ToolsPlugin\ndesignersupported\n"
    result = parse_qmldir(source, relative_file="Public/Tools/qmldir")
    assert not result.get("error")
    assert len([node for node in result["nodes"] if qml_metadata(node).get("kind") == "export"]) == 62
    module = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "module")
    md = qml_metadata(module)
    assert source.encode()[md["span"]["start_byte"]:md["span"]["end_byte"]] == b"module Public.Tools"
    assert md["span"]["start_row"] == 1
    assert all(edge["confidence"] == "EXTRACTED" for edge in result["edges"])
    payload = json.loads(json.dumps(result))
    for node in payload["nodes"]:
        node["metadata"] = sanitize_metadata(node["metadata"])
    assert [qml_metadata(node).get("raw_name") for node in payload["nodes"]] == [
        qml_metadata(node).get("raw_name") for node in result["nodes"]]


@pytest.mark.parametrize("source,reason", [
    ("Widget 1.0 Widget.qml\nmodule Bad.Order", "invalid_module_declaration"),
    ("module Public.Tools\nmodule Public.Tools", "invalid_module_declaration"),
    ("module Public.Tools\nWidget 1.0 A.qml\nWidget 1.0 B.qml", "duplicate_export"),
    ("module Public.Tools\ninternal Hidden 1.0 Hidden.qml", "unsupported_or_malformed_directive"),
    ("module Public.Tools\nimport Public.Base mystery", "invalid_module_version"),
    ("module Public.Tools\nplugin " + "a" * 400, "metadata_value_limit"),
    ("module Public.Tools\nunknown executable --args", "unsupported_or_malformed_directive"),
    ("module Public.Tools\nimport", "invalid_module_dependency"),
    ("module Public.Tools\noptional broken", "unsupported_or_malformed_directive"),
])
def test_qmldir_partial_failure_is_explicit(source, reason):
    """Malformed/unsupported input must not be reported as complete coverage."""
    result = parse_qmldir(source)
    assert result["partial"] is True
    assert result["error"].startswith("QML-META-001")
    assert reason in {item["reason"] for item in result["parse_errors"]}
    assert result["diagnostics"][0]["severity"] == "error"


def test_qmldir_read_containment_and_size_limits(tmp_path):
    """Declarations never authorize following target files, plugins or host paths."""
    root = tmp_path / "accepted"
    root.mkdir()
    outside = tmp_path / "qmldir"
    outside.write_text("module Outside\n")
    assert extract_qmldir(outside, root=root)["error"].startswith("QML-META-002")
    path = root / "qmldir"
    path.write_bytes(b"x" * (MAX_METADATA_BYTES + 1))
    assert extract_qmldir(path, root=root)["nodes"] == []
    path.write_bytes(b"\xff")
    assert extract_qmldir(path, root=root)["error"].startswith("QML-META-002")
    path.write_text("module Public.Tools\nWidget 1.0 ../../host.qml\nplugin arbitrary\n")
    result = extract_qmldir(path, root=root)
    assert not result.get("error")
    assert all(node["source_file"] == "qmldir" for node in result["nodes"])


def test_qmldir_ids_are_portable_and_exact_case_sensitive():
    """Case-colliding names and harmless line shifts preserve declaration identity."""
    source = "module Public.Tools\nWidget 1.0 Widget.qml\nwidget 1.0 widget.qml"
    before = parse_qmldir(source)
    after = parse_qmldir("# editor comment\n" + source)
    assert [node["id"] for node in before["nodes"]] == [node["id"] for node in after["nodes"]]
    assert len({node["id"] for node in before["nodes"]}) == len(before["nodes"])


def test_qmldir_record_limit_is_reported(monkeypatch):
    """Work rejection retains a diagnostic and never claims complete coverage."""
    monkeypatch.setattr("graphify.extractors.qml_metadata.MAX_METADATA_RECORDS", 2)
    result = parse_qmldir("module Public.Tools\nA 1.0 A.qml\nB 1.0 B.qml")
    assert result["parse_errors"][-1]["reason"] == "metadata_record_limit"
    result = parse_qmldir("x" * (MAX_METADATA_BYTES + 1))
    assert result["parse_errors"][-1]["reason"] == "metadata_size_limit"
