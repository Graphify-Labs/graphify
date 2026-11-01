"""INC-QML-60: allocated native roles preserve complete-body source proof."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import collect_files, extract, extract_cpp
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph


def _source_proof(result, name, source, header):
    """The declaration body and file retain distinct original-byte locations."""
    classes = [node for node in result["nodes"]
               if node.get("label") == name and node.get("_callable_class") is True]
    assert len(classes) == 1
    owner = classes[0]
    fact = class_fact(owner)
    assert fact and fact["is_definition"] is True and fact["ambiguous"] is False
    assert owner["source_location"] == "L4"
    span = fact["span"]
    assert span["start_byte"] == source.index(f"class {name} :".encode())
    assert source[span["start_byte"]:span["end_byte"]].endswith(b"}")
    assert span["start_row"] == 3
    # Build membership facts may display the same name but are owned by CMake.
    files = [node for node in result["nodes"] if node.get("label") == header.name
             and Path(node.get("source_file", "")).name == header.name]
    assert len(files) == 1 and files[0]["source_location"] == "L1"
    assert files[0]["id"] != owner["id"]
    return owner["id"]


@pytest.mark.parametrize("name,filename", [("Backend", "native.h"), ("Hpp", "native.hpp")])
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_req_qml003_ac02_ac04_qml018_ac04_forward_role_preserves_complete_body(
        tmp_path, name, filename, newline):
    """Forward reuse cannot need a late marker or overwrite a colliding file.

    Actual parser, facade cache and serialized native QML joins retain the body;
    BOM/Unicode and both newline profiles keep offsets tied to original bytes.
    """
    source = ("\ufeff// π source proof\n"
              f"class {name};\n\n"
              f"class {name} : public QObject {{ Q_OBJECT QML_NAMED_ELEMENT(Widget)\n"
              "public: Q_INVOKABLE void ping() {}\n};\n").replace("\n", newline).encode()
    header = tmp_path / filename
    header.write_bytes(source)
    (tmp_path / "CMakeLists.txt").write_text(
        f"qt_add_qml_module(app URI Public.Forward VERSION 1.0 QML_FILES Main.qml SOURCES {filename})\n",
        encoding="utf-8",
    )
    (tmp_path / "Main.qml").write_text(
        "import Public.Forward 1.0 as Tools\nTools.Widget { function run() { ping() } }\n",
        encoding="utf-8",
    )
    direct = extract_cpp(header)
    assert not direct.get("parse_errors")
    _source_proof(direct, name, source, header)

    paths = collect_files(tmp_path, root=tmp_path)
    facts = []
    for phase in ("cold", "warm"):
        result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
        assert not result.get("failed_sources") and not result.get("qml_failures")
        owner = _source_proof(result, name, source, header)
        calls = [edge for edge in result["edges"] if edge.get("context") == "qml_js_call"]
        assert len(calls) == 1
        proof = qt_metadata(calls[0])["native_endpoint"]
        assert proof["class_id"] == owner
        assert proof["canonical_target_id"] == calls[0]["target"]
        graph = build_from_json(result, root=tmp_path, directed=True)
        output = tmp_path / f"{phase}.json"
        assert to_json(graph, {}, str(output), force=True, built_at_commit="fixed")
        restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert restored.nodes[owner]["source_location"] == "L4"
        restored_calls = [data for _, _, data in restored.edges(data=True)
                          if data.get("context") == "qml_js_call"]
        assert len(restored_calls) == 1 and qt_metadata(restored_calls[0])["native_endpoint"] == proof
        facts.append((owner, proof))
    assert facts[0] == facts[1]
