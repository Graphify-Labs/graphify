"""QML-01 rejection and optional/native parser boundaries without unsafe facts."""
from __future__ import annotations

import builtins
import json

import pytest
import tree_sitter_language_pack

from graphify.extract import extract_python
from graphify.extractors.qml import extract_qml
from tests.qml_test_helpers import assert_no_machine_paths, write_qml


def assert_rejected(result, code, root):
    """Rejected source cannot masquerade as a cacheable authoritative extraction."""
    assert result.get("error")
    assert result["nodes"] == [] and result["edges"] == []
    assert any(diagnostic["code"] == code for diagnostic in result["diagnostics"])
    assert_no_machine_paths(result, root)


def test_qml001_ac03_missing_optional_import_is_safe_and_does_not_break_python(tmp_path, monkeypatch):
    """Actual optional import rejection produces QML diagnostics; unrelated parsing works."""
    original_import = builtins.__import__

    def without_qml_parser(name, *args, **kwargs):
        if name == "tree_sitter_language_pack":
            raise ModuleNotFoundError("Synthetic unavailable optional parser")
        return original_import(name, *args, **kwargs)

    path = write_qml(tmp_path)
    python_path = tmp_path / "safe.py"
    python_path.write_text("def safe():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(builtins, "__import__", without_qml_parser)
    result = extract_qml(path, root=tmp_path)
    assert_rejected(result, "QML_PARSER_MISSING", tmp_path)
    assert any(node["label"] == "safe()" for node in extract_python(python_path, root=tmp_path)["nodes"])


def test_qml001_ac03_incompatible_parser_load_is_bounded_failure(tmp_path, monkeypatch):
    """Binding/ABI load failures are rejected with safe diagnostics, not backend details."""
    def incompatible(_grammar):
        raise RuntimeError("synthetic-backend-detail must not escape")

    monkeypatch.setattr(tree_sitter_language_pack, "get_parser", incompatible)
    result = extract_qml(write_qml(tmp_path), root=tmp_path)
    assert_rejected(result, "QML_PARSER_LOAD", tmp_path)
    assert "synthetic-backend-detail" not in json.dumps(result)


def test_qml001_ac04_unsupported_annotated_root_is_not_file_only_success(tmp_path):
    """A grammar-recognized shape outside the adapter profile needs explicit rejection."""
    path = write_qml(tmp_path, source="@Unknown {} Item { property int retained: 1 }\n")
    # The grammar accepts this shape; the declaration adapter must own its coverage
    # decision instead of publishing a successful file with all declarations lost.
    assert not tree_sitter_language_pack.get_parser("qmljs").parse(path.read_bytes()).root_node.has_error
    result = extract_qml(path, root=tmp_path)
    assert result.get("error") and result.get("diagnostics")
    assert result["nodes"] == [] and result["edges"] == []


def test_qml012_ac01_native_parse_exception_is_explicit_safe_failure(tmp_path, monkeypatch):
    """A failing external parser cannot escape or publish private backend exception text."""
    class FailingParser:
        def parse(self, _source):
            raise RuntimeError("synthetic-backend-detail must not escape")

    monkeypatch.setattr(tree_sitter_language_pack, "get_parser", lambda _grammar: FailingParser())
    result = extract_qml(write_qml(tmp_path), root=tmp_path)
    assert result.get("error") and result.get("diagnostics")
    assert result["nodes"] == [] and result["edges"] == []
    assert "synthetic-backend-detail" not in json.dumps(result)


@pytest.mark.parametrize("source", [b"Item { property string value: '\xff' }", b"//" + b"a" * 5_000_001], ids=["invalid-utf8", "oversized"])
def test_qml012_ac04_unreadable_or_oversized_source_has_safe_failure(tmp_path, source):
    """Decode/size limits reject input before publishing any partial declarations."""
    path = tmp_path / "Main.qml"
    path.write_bytes(source)
    result = extract_qml(path, root=tmp_path)
    assert_rejected(result, "QML_READ" if b"\xff" in source else "QML_LIMIT", tmp_path)


def test_qml012_ac04_deep_source_terminates_at_supported_bound(tmp_path):
    """Deep but grammar-valid objects do not recurse through unbounded extraction."""
    result = extract_qml(write_qml(tmp_path, source="Item {" * 270 + "}" * 270), root=tmp_path)
    assert_rejected(result, "QML_LIMIT", tmp_path)


def test_qml012_ac04_explicit_root_rejection_does_not_expose_absolute_paths(tmp_path):
    """An out-of-corpus file is rejected without serializing a machine-specific path."""
    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    result = extract_qml(write_qml(outside), root=allowed)
    assert result.get("error") and result["nodes"] == []
    assert_no_machine_paths(result, outside)
    assert_no_machine_paths(result, allowed)
