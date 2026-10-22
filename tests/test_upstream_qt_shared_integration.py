"""INC-QML-49: upstream C++ union ownership coexists with Qt native facts."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import collect_files, extract, extract_cpp
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.test_qt_final_incremental_parity import clean, normalized, run


HEADER = """#include <QObject>
union Value { int integer; float real; int fetch() { return integer; } };
struct Point { int x; };
typedef union { int anonymous; } Hidden;
class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Service)
 Q_PROPERTY(int value READ value)
public: int value() const { return 1; }
 Q_INVOKABLE int fetch() { return 2; }
};
"""
BUILDS = [
    ("CMakeLists.txt", "qt_add_qml_module(app URI Public.Tools VERSION 1.0 "
     "QML_FILES Main.qml SOURCES backend.h)\n"),
    ("app.pro", "CONFIG += qmltypes\nQML_IMPORT_NAME = Public.Tools\n"
     "QML_IMPORT_MAJOR_VERSION = 1\nHEADERS += backend.h\nDISTFILES += Main.qml\n"),
]


def project(root, build_name, build):
    """A same-named union method is a real non-provider collision control."""
    sources = {
        build_name: build,
        "backend.h": HEADER,
        "Main.qml": "import Public.Tools 1.0 as Tools\n"
                    "Tools.Service { property int displayed: value; "
                    "property int called: fetch() }\n",
    }
    for name, text in sources.items():
        (root / name).write_text(text, encoding="utf-8", newline="")
    return root / "backend.h"


def declaration(graph, label):
    matches = [(identity, data) for identity, data in graph.nodes(data=True)
               if data.get("source_file") == "backend.h" and data.get("label") == label]
    assert len(matches) == 1, (label, matches)
    return matches[0]


def method(graph, owner):
    """Generic display labels omit the class; stored ownership selects identity."""
    matches = [target for _, target, data in graph.edges(owner, data=True)
               if graph.nodes[target].get("label") == ".fetch()" and
               data.get("relation") == "method"]
    assert len(matches) == 1
    return matches[0]


def assert_joint_facts(graph, member="integer"):
    """Check source-owned generic relationships and exact Qt endpoint identity."""
    union, union_data = declaration(graph, "Value")
    field, field_data = declaration(graph, member)
    backend, _ = declaration(graph, "Backend")
    union_fetch, backend_fetch = method(graph, union), method(graph, backend)
    assert union_data["source_location"] == field_data["source_location"] == "L2"
    assert declaration(graph, "Point")[1]["source_location"] == "L3"
    assert any(target == field and data.get("relation") == "defines"
               for _, target, data in graph.edges(union, data=True))
    assert graph.nodes[union_fetch]["source_location"] == "L2"
    assert graph.nodes[backend_fetch]["source_location"] == "L8"
    assert not any(data.get("label") in {"Hidden", "anonymous"}
                   for _, data in graph.nodes(data=True))
    calls = [(source, target, data) for source, target, data in graph.edges(data=True)
             if data.get("context") == "qml_js_call"]
    assert len(calls) == 1
    source, target, call = calls[0]
    proof = qt_metadata(call)["native_endpoint"]
    assert (call.get("_src", source), call.get("_tgt", target))[1] == backend_fetch
    assert proof["canonical_target_id"] == backend_fetch != union_fetch
    assert graph.nodes[proof["class_id"]]["label"] == "Backend"
    assert any(qml_metadata(graph.nodes[item]).get("kind") == "qt_module"
               for item in proof["evidence"])
    assert any(data.get("context") == "qml_binding_read" and
               qt_metadata(data).get("native_endpoint")
               for _, _, data in graph.edges(data=True))
    assert all(graph.nodes[endpoint].get("source_file")
               for endpoint in (union, field, union_fetch, backend_fetch))
    return union, field, union_fetch, backend_fetch


@pytest.mark.parametrize("build_name,build", BUILDS)
def test_req_qml003_ac01_ac02_ac04_union_and_qt_native_cold_warm_reload(
        tmp_path, monkeypatch, build_name, build):
    """Real direct/facade parsing and warm replay retain both owners and spans."""
    source = project(tmp_path, build_name, build)
    raw = extract_cpp(source)
    assert not raw.get("parse_errors")
    raw_labels = {node["label"] for node in raw["nodes"]}
    assert {"Value", "integer", "real", ".fetch()"} <= raw_labels
    assert sum(node["label"] == ".fetch()" for node in raw["nodes"]) == 2
    paths = collect_files(tmp_path, root=tmp_path)
    cold = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not cold["failed_sources"] and not cold["qml_failures"]
    # The facade's generic C++ producer must really warm-hit; Qt's accepted
    # overlay may still reparse the same source for its run-owned metadata.
    import graphify.extract as extraction
    observed, real_extract = [], extraction._safe_extract_with_xaml_root

    def observe(path, *args, **kwargs):
        observed.append(path)
        return real_extract(path, *args, **kwargs)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    warm = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert source not in observed
    assert not warm["failed_sources"] and not warm["qml_failures"]
    graphs = []
    for name, facts in (("cold", cold), ("warm", warm)):
        graph = build_from_json(facts, root=tmp_path, directed=True)
        assert_joint_facts(graph)
        output = tmp_path / f"{name}.json"
        assert to_json(graph, {}, str(output), force=True)
        restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert_joint_facts(restored)
        graphs.append(restored)
    assert normalized(graphs[0]) == normalized(graphs[1])


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac01_ac04_union_edit_removes_stale_member_keeps_native_endpoint(
        tmp_path, monkeypatch, operation):
    """A real generic union edit replaces only its member through both updates."""
    source = project(tmp_path, *BUILDS[0])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    union, old_field, union_fetch, backend_fetch = assert_joint_facts(initial)
    source.write_text(HEADER.replace("integer", "whole"), encoding="utf-8", newline="")
    edited = run(tmp_path, monkeypatch, operation, [source])
    current_union, new_field, current_union_fetch, current_backend_fetch = assert_joint_facts(edited, "whole")
    assert (current_union, current_union_fetch, current_backend_fetch) == (union, union_fetch, backend_fetch)
    assert new_field != old_field and old_field not in edited
    assert not any(old_field in (start, end) for start, end in edited.edges())
    fresh = clean(tmp_path, tmp_path / ".comparison-cache")
    assert_joint_facts(fresh, "whole")
    assert normalized(edited) == normalized(fresh)
    accepted = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(edited)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == accepted
