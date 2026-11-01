"""Hand-checked production QML syntax, object ownership and template boundaries."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from graphify.extract import extract
from graphify.extractors.qml import extract_qml
from graphify.extractors.qml_facts import qml_metadata
from tests.qml_test_helpers import assert_contains, assert_spans, by_kind, canonical, one, write_qml

FIXTURES = Path(__file__).parent / "fixtures/qml/parser_probe"
PROFILE = {
    "Main.qml": {"component": 1, "object": 2, "property": 5, "signal": 2, "function": 1, "import": 4},
    "Grouped.qml": {"component": 1, "object": 1, "property_group": 2, "import": 1},
    "Imports.qml": {"component": 1, "object": 1, "import": 4},
    "Modern68.qml": {"component": 1, "inline_component": 1, "object": 3, "property": 3, "enum": 1, "import": 1},
    "Script.qml": {"component": 1, "object": 1, "property": 1, "function": 1, "import": 1},
    "UnicodeCRLF.qml": {"component": 1, "object": 1, "property": 2, "function": 1, "import": 1},
}
DECLARATIONS = {"component", "inline_component", "object", "property_group", "property", "signal", "function", "enum", "import"}


def literal(result, source, kind, name, expected):
    """A concrete original-source slice is independent of AST-to-fact conversion."""
    node = one(result, kind, name)
    span = qml_metadata(node)["span"]
    encoded = expected.encode("utf-8")
    assert span["start_byte"] == source.index(encoded)
    assert span["end_byte"] == span["start_byte"] + len(encoded)
    assert source[span["start_byte"]:span["end_byte"]] == encoded
    return qml_metadata(node)


@pytest.mark.parametrize("filename", PROFILE)
def test_qml001_ac02_handchecked_profile_uses_production_extractor_and_original_spans(tmp_path, filename):
    """The parser spike corpus now exercises shipping declarations, not parser smoke only."""
    source = (FIXTURES / filename).read_bytes()
    path = tmp_path / filename
    path.write_bytes(source)
    result = extract_qml(path, root=tmp_path)
    assert not result.get("error") and not result.get("qml_failures")
    counts = {kind: len(by_kind(result, kind)) for kind in DECLARATIONS if by_kind(result, kind)}
    assert counts == PROFILE[filename]
    assert_spans(result, source)
    assert canonical(result) == canonical(extract_qml(path, root=tmp_path))
    assert all(node["source_file"] == filename for node in result["nodes"])
    if filename == "Main.qml":
        assert literal(result, source, "property", "title", "required property string title")["modifiers"] == ["required"]
        assert literal(result, source, "property", "extras", "default property list<QtObject> extras")["raw_type"] == "list<QtObject>"
        assert literal(result, source, "signal", "changed", "signal changed(value: int)")["signature"] == "(value: int)"
        assert qml_metadata(one(result, "function", "bump"))["return_type"] == ": int"
    elif filename == "Grouped.qml":
        literal(result, source, "property_group", "anchors", "anchors { left: parent.left; topMargin: 4 }")
        assert [qml_metadata(node)["type_name"] for node in by_kind(result, "object")] == ["Text"]
    elif filename == "Imports.qml":
        imports = [qml_metadata(node) for node in by_kind(result, "import")]
        assert [(md["value"], md["major"], md["minor"], md["qualifier"]) for md in imports] == [
            ("QtQuick", 6, None, None), ("Example.Widgets", 1, 2, None),
            ("Example.Services", None, None, "Services"), ("./components", None, None, None)]
        literal(result, source, "import", "QtQuick", "import QtQuick 6")
    elif filename == "Modern68.qml":
        assert qml_metadata(one(result, "inline_component", "Tile"))["raw_name"] == "Tile"
        literal(result, source, "enum", "Mode", "enum Mode { Idle = 0, Active = 1 }")
        literal(result, source, "property", "ownValue", "property alias ownValue: tile.value")
    elif filename == "Script.qml":
        assert qml_metadata(one(result, "function", "evaluate"))["signature"] == "(input)"
        assert not by_kind(result, "signal")
        assert not any(qml_metadata(node).get("raw_name") in {"fake", "phantom", "Broken"} for node in result["nodes"])
    else:
        assert source.count(b"\r\n") == source.count(b"\n") > 0
        literal(result, source, "property", "après", "property int après: 2")
        literal(result, source, "function", "résumé", "function résumé(étape) { return café + étape; }")


def test_qml003_ac01_property_binding_and_array_objects_keep_exact_owners(tmp_path):
    """Each held instance has its own scope and its actual property/object owner."""
    source = """Item {
 id: root
 property QtObject held: QtObject { id: held; property int value: 1 }
 property list<QtObject> extras: [
  QtObject { id: firstProperty; property int value: 2 },
  QtObject { id: secondProperty; property int value: 3 }
 ]
 data: [
  QtObject { id: firstBinding; property int value: 4 },
  QtObject { id: secondBinding; property int value: 5 }
 ]
 property QtObject emptyFirst: QtObject {}
 property QtObject emptySecond: QtObject {}
}
"""
    result = extract_qml(write_qml(tmp_path, source=source), root=tmp_path)
    assert not result.get("error")
    objects = by_kind(result, "object")
    assert len(objects) == 8 and len({node["id"] for node in objects}) == 8
    assert len({qml_metadata(node)["object_scope_key"] for node in objects}) == 8
    assert len({qml_metadata(node)["component_key"] for node in objects}) == 1
    named = {qml_metadata(node)["object_id"]: node for node in objects if qml_metadata(node)["object_id"]}
    assert set(named) == {"root", "held", "firstProperty", "secondProperty", "firstBinding", "secondBinding"}
    assert_contains(result, one(result, "property", "held"), named["held"])
    for name in ("firstProperty", "secondProperty"):
        assert_contains(result, one(result, "property", "extras"), named[name])
    for name in ("firstBinding", "secondBinding"):
        assert_contains(result, named["root"], named[name])
    for property_name in ("emptyFirst", "emptySecond"):
        owner = one(result, "property", property_name)
        children = [edge["target"] for edge in result["edges"] if edge["source"] == owner["id"] and edge["relation"] == "contains"]
        assert len(children) == 1
        assert next(node for node in objects if node["id"] == children[0])["id"] != named["held"]["id"]
    assert_spans(result, source.encode())


@pytest.mark.parametrize("root_type,template", [
    ("Item", "property Component factory: Item { id: hidden; property int value: 1 }"),
    ("ListView", "delegate: Item { id: hidden; property int value: 1 }"),
    ("Loader", "sourceComponent: Item { id: hidden; property int value: 1 }"),
    ("Item", "Component { id: factory; Item { id: hidden; property int value: 1 } }"),
])
def test_qml003_ac02_template_bodies_do_not_leak_ids_to_enclosing_component(tmp_path, root_type, template):
    """Source-held templates get separate component scopes without assumed runtime context."""
    source = f"{root_type} {{\n id: outer\n {template}\n function read() {{ return hidden.value; }}\n}}"
    path = write_qml(tmp_path, source=source)
    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert not result.get("qml_failures")
    objects = {qml_metadata(node)["object_id"]: node for node in by_kind(result, "object")}
    assert qml_metadata(objects["hidden"])["component_key"] != qml_metadata(objects["outer"])["component_key"]
    sites = [node for node in by_kind(result, "read") if qml_metadata(node).get("reference") == "hidden.value"]
    assert len(sites) == 1 and qml_metadata(sites[0])["status"] != "resolved"
    assert not any(edge["source"] == sites[0]["id"] and edge["relation"] == "uses" for edge in result["edges"])


# Guard external boundaries in a fresh interpreter before loading Graphify. A
# production-parser success with no marker proves no corpus expression was run;
# the guards additionally reject Python network/process access during extraction.
OFFLINE_PRODUCTION = r'''
import json
from importlib.metadata import version
from pathlib import Path
import os
import socket
import subprocess
import sys

checkout, corpus = map(Path, sys.argv[1:])
sys.path.insert(0, str(checkout))

def forbidden(*args, **kwargs):
    raise RuntimeError("Production QML extraction attempted network or external execution")

socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
subprocess.Popen = forbidden
os.system = forbidden
from graphify.extractors.qml import extract_qml

counts = {}
for path in sorted(corpus.glob("*.qml")):
    result = extract_qml(path, root=corpus)
    assert not result.get("error"), result.get("diagnostics")
    counts[path.name] = len(result["nodes"])
print(json.dumps({"parser": version("tree-sitter-language-pack"), "files": counts}))
'''


def test_qml001_ac02_profile_runs_offline_in_fresh_production_process_without_corpus_execution(tmp_path):
    """All declared fixtures work with empty caches; embedded JS side effects stay inert."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for filename in PROFILE:
        (corpus / filename).write_bytes((FIXTURES / filename).read_bytes())
    marker = tmp_path / "must-not-exist"
    write_qml(corpus, "Dangerous.qml", 'QtObject { property var effect: require("fs").writeFileSync(' + json.dumps(marker.as_posix()) + ', "bad") }')
    clean_home, cwd = tmp_path / "clean-home", tmp_path / "empty-cwd"
    clean_home.mkdir()
    cwd.mkdir()
    env = dict(os.environ, HOME=str(clean_home), USERPROFILE=str(clean_home), XDG_CACHE_HOME=str(clean_home), PYTHONUTF8="1")
    child = subprocess.run([sys.executable, "-I", "-c", OFFLINE_PRODUCTION, str(Path(__file__).resolve().parent.parent), str(corpus)],
                           cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    assert result["parser"] == "0.11.0"
    assert set(result["files"]) == set(PROFILE) | {"Dangerous.qml"}
    assert all(count > 0 for count in result["files"].values())
    assert not marker.exists()
