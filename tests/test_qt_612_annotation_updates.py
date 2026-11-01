"""REQ-QML-022-AC03/06: actual source access governs durable QML bridge results."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.test_qt_final_incremental_parity import normalized


@pytest.mark.parametrize("later,expected", [("", "unavailable"), ("private:", "unavailable"),
                                             ("public:", "resolved")])
def test_actual_macro_access_survives_cold_warm_and_graph_reload(tmp_path, later, expected):
    """Real module membership cannot make an implicitly private member public."""
    sources = {
        "CMakeLists.txt": "qt_add_qml_module(app URI Audit.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.h)\n",
        "backend.h": ("#include <QObject>\nclass Backend : public QObject {\npublic:\n"
                      "void before();\nQ_OBJECT\nQML_NAMED_ELEMENT(Service)\n"
                      f"{later} Q_INVOKABLE int secret();\n}};\n"),
        "Main.qml": "import Audit.Tools 1.0 as Tools\nTools.Service { property int called: secret() }\n",
    }
    paths = []
    for name, source in sources.items():
        path = tmp_path / name
        path.write_bytes(source.encode())
        paths.append(path)
    graphs = []
    for phase in ("cold", "warm"):
        result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
        assert not result["failed_sources"] and not result.get("qml_failures")
        call = next(qml_metadata(n) for n in result["nodes"] if qml_metadata(n).get("kind") == "call")
        member = next(qt_metadata(n) for n in result["nodes"] if qt_metadata(n).get("raw_name") == "secret")
        assert member["access"] == ("public" if later == "public:" else "private")
        assert call["status"] == expected
        if expected == "unavailable":
            assert call["reason"] == "native_member_not_qml_visible" and not call.get("resolved_target_id")
        graph = build_from_json(result, root=tmp_path, directed=True)
        output = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(output), force=True)
        loaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        durable = next(qml_metadata(n) for _, n in loaded.nodes(data=True) if qml_metadata(n).get("kind") == "call")
        assert durable["status"] == expected
        graphs.append(normalized(loaded))
    assert graphs[0] == graphs[1]


def test_preprocessor_continuation_cannot_create_annotation_authority(tmp_path):
    """Definition bodies remain preprocessor data, including continued lines."""
    from graphify.extractors.qt_cpp_syntax import read_cpp

    raw = b"#define DECLARE \\\r\n Q_OBJECT \\\r\n QML_ELEMENT\r\nclass Ordinary {};\r\n"
    path = tmp_path / "ordinary.hpp"
    path.write_bytes(raw)
    unit = read_cpp(path, tmp_path)
    assert unit.macros == [] and unit.parsed_source == raw


@pytest.mark.parametrize("force", [False, True])
def test_invalid_annotation_scope_retains_products_and_recovers(tmp_path, force):
    """A new rejection boundary preserves the whole accepted Qt publication."""
    from graphify.qt_analysis_state import QT_STATE_FILE
    from graphify.watch import _rebuild_code

    path = tmp_path / "backend.hpp"
    source = b"class Backend { Q_OBJECT public: Q_INVOKABLE int value(); };\n"
    path.write_bytes(source)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Accepted annotation report\n")
    prior = {name: (out / name).read_bytes() for name in ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)}
    path.write_bytes(source.replace(b"int value();", b"int value(){ Q_OBJECT }"))
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in prior} == prior
    path.write_bytes(source)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == prior["graph.json"]
