"""QML-00 parser characterization; no Graphify language support is registered.

These independently authored fixtures exercise the pinned parser through the
Language/Parser primitives used by Graphify. They do not execute Qt or corpus JS,
resolve modules, validate qmldir semantics, or verify production requirements.
"""
from __future__ import annotations

import importlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest
from tree_sitter import LANGUAGE_VERSION, MIN_COMPATIBLE_LANGUAGE_VERSION, Language, Parser

from tests.qml_probe_helpers import OFFLINE_PROBE, field_text, nodes, point_at, text, walk

FIXTURES = Path(__file__).parent / "fixtures" / "qml" / "parser_probe"
VALID_QML = ("Main.qml", "Modern68.qml", "Grouped.qml", "Script.qml", "UnicodeCRLF.qml", "Imports.qml", "plugins.qmltypes")


@pytest.fixture(scope="module")
def pack() -> ModuleType:
    """Absence is explicit optional-parser coverage loss, never parser acceptance."""
    pytest.importorskip("tree_sitter_language_pack", reason="QML-00 needs the optional pinned language-pack candidate")
    return importlib.import_module("tree_sitter_language_pack")


def parse(pack: ModuleType, filename: str):
    source = (FIXTURES / filename).read_bytes()
    grammar = "qmldir" if filename.startswith("qmldir") else "qmljs"
    return source, pack.get_parser(grammar).parse(source).root_node


def test_qml00_candidate_distribution_fingerprint(pack):
    """Candidate version changes require a new recorded parser decision."""
    assert version("tree-sitter-language-pack") == "0.11.0"
    major, minor, patch = map(int, version("tree-sitter").split("."))
    assert (0, 25, 2) <= (major, minor, patch) < (0, 26, 0)


@pytest.mark.parametrize("grammar,source,root_type", [
    ("qmljs", b"import QtQuick\nItem {}\n", "program"),
    ("qmldir", b"module Example\nMain 1.0 Main.qml\n", "module_definition"),
])
def test_qml00_binding_uses_graphify_tree_sitter_api(pack, grammar, source, root_type):
    """Installed grammar capsules work with current Graphify API/ABI primitives."""
    language = Language(pack.get_binding(grammar))
    assert MIN_COMPATIBLE_LANGUAGE_VERSION <= language.abi_version <= LANGUAGE_VERSION
    root = Parser(language).parse(source).root_node
    assert root.type == root_type and not root.has_error
    assert root.end_byte == len(source)


@pytest.mark.parametrize("filename,counts", [
    ("Main.qml", {"ui_import": 4, "ui_object_definition": 2, "ui_property": 5, "ui_signal": 2, "function_declaration": 1}),
    ("Modern68.qml", {"ui_pragma": 1, "ui_inline_component": 1, "enum_declaration": 1, "arrow_function": 1}),
    ("Grouped.qml", {"ui_object_definition": 3}),
    ("Script.qml", {"function_declaration": 1, "arrow_function": 1, "ui_signal": 0, "ui_import": 1}),
    ("UnicodeCRLF.qml", {"ui_property": 2, "function_declaration": 1}),
    ("Imports.qml", {"ui_import": 4}),
    ("plugins.qmltypes", {"ui_object_definition": 6}),
])
def test_qml00_supported_syntax_corpus(pack, filename, counts):
    """Hand-counted declarations and syntax nodes survive representative inputs."""
    _, root = parse(pack, filename)
    assert root.type == "program" and not root.has_error
    for kind, expected in counts.items():
        assert len(nodes(root, kind)) == expected, (filename, kind)


@pytest.mark.parametrize("filename,expected", [
    ("Main.qml", [("QtQuick", None, None), ("QtQuick.Controls", "6.5", "Controls"), ('"./components"', None, "Local"), ('"helpers.js"', None, "Helpers")]),
    ("Imports.qml", [("QtQuick", "6", None), ("Example.Widgets", "1.2", None), ("Example.Services", None, "Services"), ('"./components"', None, None)]),
])
def test_qml00_import_source_version_alias_are_distinct_fields(pack, filename, expected):
    """Qualified and quoted sources retain their version/alias without resolution."""
    _, root = parse(pack, filename)
    actual = [tuple(field_text(node, name) for name in ("source", "version", "alias")) for node in nodes(root, "ui_import")]
    assert actual == expected


def test_qml00_properties_signals_methods_and_nested_object_ownership(pack):
    """Modifiers, aliases, typed signatures and nested IDs keep AST ownership."""
    _, root = parse(pack, "Main.qml")
    properties = {field_text(node, "name"): node for node in nodes(root, "ui_property")}
    assert {name: field_text(node, "type") for name, node in properties.items()} == {
        "title": "string", "doubled": "int", "extras": "list<QtObject>", "count": "int", "editorText": "alias",
    }
    for name, modifier in (("title", "required"), ("doubled", "readonly"), ("extras", "default")):
        assert [text(node) for node in nodes(properties[name], "ui_property_modifier")] == [modifier]
    assert field_text(properties["editorText"], "value") == "editor.text"
    parameters = nodes(root, "ui_signal_parameter")
    assert [(field_text(node, "name"), field_text(node, "type")) for node in parameters] == [("value", "int"), ("label", "string"), ("value", "int")]
    method = nodes(root, "function_declaration")[0]
    assert field_text(method, "name") == "bump" and field_text(method, "return_type") == ": int"
    owners = {}
    for obj in nodes(root, "ui_object_definition"):
        initializer = obj.child_by_field_name("initializer")
        assert initializer is not None
        owners[field_text(obj, "type_name")] = [field_text(node, "value") for node in initializer.named_children if node.type == "ui_binding" and field_text(node, "name") == "id"]
    assert owners == {"Item": ["root"], "Controls.TextField": ["editor"]}


def test_qml00_inline_component_keeps_local_definition_and_base_type(pack):
    """Inline type names and their own alias owner must not be flattened."""
    _, root = parse(pack, "Modern68.qml")
    component = nodes(root, "ui_inline_component")[0]
    assert field_text(component, "name") == "Tile"
    definition = component.child_by_field_name("component")
    assert definition is not None
    assert field_text(definition, "type_name") == "Rectangle"
    assert [field_text(node, "name") for node in nodes(definition, "ui_property")] == ["value", "ownValue"]
    assert field_text(nodes(definition, "ui_property")[1], "value") == "tile.value"
    binding_names = [field_text(node, "name") for node in nodes(root, "ui_binding")]
    assert all(name is not None for name in binding_names)
    assert [name for name in binding_names if name is not None and "." in name] == ["Component.onCompleted"]


def test_qml00_grouped_property_object_definition_pitfall_is_explicit(pack):
    """Pinned grammar treats grouped properties as objects; semantic handling is pending."""
    _, root = parse(pack, "Grouped.qml")
    definitions = nodes(root, "ui_object_definition")
    assert [field_text(node, "type_name") for node in definitions] == ["Text", "anchors", "font"]
    assert field_text(definitions[1], "initializer") == "{ left: parent.left; topMargin: 4 }"


def test_qml00_embedded_js_keeps_scopes_and_ignores_literal_declarations(pack):
    """Shadowed variables stay in separate blocks; strings/comments invent no signals."""
    _, root = parse(pack, "Script.qml")
    variables = [node for node in nodes(root, "variable_declarator") if field_text(node, "name") == "value"]
    assert len(variables) == 2
    blocks = []
    for variable in variables:
        assert variable.parent is not None
        block = variable.parent.parent
        assert block is not None and block.type == "statement_block"
        blocks.append(block)
    assert blocks[0] != blocks[1]
    assert [field_text(node, "function") for node in nodes(root, "call_expression")] == ["transform", "evaluate"]
    assert not nodes(root, "ui_signal")
    assert any("signal fake" in text(node) for node in nodes(root, "string"))


@pytest.mark.parametrize("filename", VALID_QML + ("Incomplete.qml", "Malformed.qml", "Empty.qml", "qmldir", "qmldir.modern"))
def test_qml00_source_ranges_use_original_utf8_bytes(pack, filename):
    """All node ranges/points remain bounded in the original, unnormalized source."""
    source, root = parse(pack, filename)
    assert root.end_byte == len(source)
    for node in walk(root):
        assert 0 <= node.start_byte <= node.end_byte <= len(source)
        assert tuple(node.start_point) == point_at(source, node.start_byte)
        assert tuple(node.end_point) == point_at(source, node.end_byte)
        source[node.start_byte:node.end_byte].decode("utf-8")


def test_qml00_unicode_crlf_columns_are_byte_offsets(pack):
    """A non-ASCII prefix changes byte columns without changing CRLF row counts."""
    source, root = parse(pack, "UnicodeCRLF.qml")
    assert source.count(b"\r\n") == source.count(b"\n") > 0
    properties = nodes(root, "ui_property")
    assert [field_text(node, "name") for node in properties] == ["café", "après"]
    second_name = properties[1].child_by_field_name("name")
    assert second_name is not None
    assert tuple(second_name.start_point)[0] == 4
    prefix = source.split(b"\r\n")[4][:second_name.start_point.column]
    assert second_name.start_point.column == len(prefix) > len(prefix.decode("utf-8"))
    assert text(nodes(root, "function_declaration")[0].child_by_field_name("name")) == "résumé"


@pytest.mark.parametrize("filename", ["Incomplete.qml", "Malformed.qml", "Empty.qml"])
def test_qml00_malformed_empty_partial_inputs_do_not_look_successful(pack, filename):
    """Error status survives recovery, including an ERROR root in an editor buffer."""
    source, root = parse(pack, filename)
    assert root.has_error
    assert any(node.is_error or node.is_missing for node in walk(root))
    if filename != "Empty.qml":
        retained = [node for node in nodes(root, "ui_property") if field_text(node, "name") == "retained"]
        assert len(retained) == 1
        assert source[retained[0].start_byte:retained[0].end_byte].startswith(b"property ")
    else:
        assert source == b"" and root.end_byte == 0


@pytest.mark.parametrize("filename,expected", [
    ("qmldir", ["module Example.Widgets", "Main 1.0 Main.qml", "singleton Theme 1.0 Theme.qml", "internal Helper Helper.qml", "typeinfo plugins.qmltypes", "plugin exampleplugin", "classname ExamplePlugin", "depends QtQuick.Controls 6.5"]),
    ("qmldir.modern", ["module Example.Widgets", "optional plugin exampleplugin", "import QtQuick auto", "prefer :/qt/qml/Example/Widgets/", "Main Main.qml"]),
])
def test_qml00_qmldir_preserves_basic_and_modern_command_tokens(pack, filename, expected):
    """Module-descriptor tokens remain available for a future directive validator."""
    _, root = parse(pack, filename)
    assert root.type == "module_definition" and not root.has_error
    # qmldir command spans include the line terminator; compare its raw contents
    # independently of checkout line endings, while range tests retain all bytes.
    assert [text(node).rstrip("\r\n") for node in nodes(root, "command")] == expected


@pytest.mark.parametrize("source", [b"module\n", b"Main wrong Main.qml\n", b"nonsense albatross unknown\n"])
def test_qml00_qmldir_missing_semantic_validation_is_explicit(pack, source):
    """Characterize rejected-by-contract metadata accepted by the generic grammar."""
    root = pack.get_parser("qmldir").parse(source).root_node
    assert not root.has_error
    assert len(nodes(root, "command")) == 1


def test_qml00_qmldir_invalid_tokens_report_error(pack):
    """Lexically invalid metadata is distinct from permissive directive syntax."""
    root = pack.get_parser("qmldir").parse(b"@@@\n").root_node
    assert root.has_error and nodes(root, "ERROR")


def test_qml00_unavailable_grammar_has_explicit_failure(pack):
    """Missing native grammar must raise a bounded library error, not empty success."""
    with pytest.raises(LookupError, match="Could not find language library"):
        pack.get_parser("qml_probe_missing_grammar")


def test_qml00_fresh_isolated_subprocess_needs_no_network_or_corpus_execution(pack, tmp_path):
    """Cold installed invocation works with no repository imports or download cache."""
    inherited = {key: value for key, value in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
    for key in ("HOME", "USERPROFILE", "XDG_CACHE_HOME", "APPDATA", "LOCALAPPDATA"):
        inherited[key] = str(tmp_path)
    child = subprocess.run([sys.executable, "-I", "-c", OFFLINE_PROBE, str(FIXTURES.resolve())], cwd=tmp_path, env=inherited, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    assert result["network_denied"] is True and result["unavailable"] == "LookupError"
    assert set(result["results"]) == {"qmljs", "qmldir"}
    for grammar in result["results"].values():
        assert grammar["has_error"] is False and grammar["end_byte"] == grammar["size"] > 0
