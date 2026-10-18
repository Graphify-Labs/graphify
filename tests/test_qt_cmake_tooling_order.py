"""INC-QML-53 / REQ-QML-009: tooling flags belong to one source token only."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.extract import collect_files, extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from graphify.qml_resolution_types import qml_metadata


@pytest.mark.parametrize("order", [
    ("notes.h", "backend.h", "worker.cpp"),
    ("backend.h", "notes.h", "worker.cpp"),
    ("backend.h", "worker.cpp", "notes.h"),
], ids=["tooling_first", "tooling_middle", "tooling_last"])
@pytest.mark.parametrize("header_only", [True, False], ids=["header_only", "compiled"])
def test_req_qml009_ac01_mixed_source_order_preserves_native_membership_after_reload(tmp_path, order, header_only):
    """A native file's compile flag cannot alter its own or its siblings' membership.

    The real producer joins a native property to QML and publishes/reloads the
    graph. Assertions check each declaration and membership's role and exact
    accepted file endpoint, including both values and all placement boundaries.
    HEADER_FILE_ONLY controls object compilation, not AUTOMOC header scanning.
    """
    sources = {
        "Main.qml": "import Public.Tools 1.0\nService { property int shown: status }\n",
        "notes.h": "struct DocumentationOnly {};\n",
        "backend.h": "#include <QObject>\nclass Backend : public QObject { Q_OBJECT "
                     "QML_NAMED_ELEMENT(Service) Q_PROPERTY(int status READ status) "
                     "public: int status() const { return 1; } };\n",
        "worker.cpp": "int calculate() { return 1; }\n",
        "CMakeLists.txt": "set_source_files_properties(notes.h PROPERTIES HEADER_FILE_ONLY "
                          + ("TRUE" if header_only else "FALSE") + ")\n"
                          "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES "
                          + " ".join(order) + ")\n",
    }
    for name, text in sources.items():
        (tmp_path / name).write_bytes(text.encode())
    paths = collect_files(tmp_path, root=tmp_path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    assert not result.get("failed_sources") and not result.get("qml_failures") and not result.get("qt_failures")
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), force=True)
    reloaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    declarations = {qml_metadata(node)["value"]: (identity, qml_metadata(node))
                    for identity, node in reloaded.nodes(data=True)
                    if qml_metadata(node).get("kind") in {"qt_source", "qt_tooling_source"}}
    memberships = {qml_metadata(node)["declaration_id"]: (identity, qml_metadata(node))
                   for identity, node in reloaded.nodes(data=True)
                   if qml_metadata(node).get("kind") == "membership_resolution"}
    for path in order:
        identity, metadata = declarations[path]
        assert metadata["kind"] == "qt_source" and metadata["source_kind"] == "cpp"
        if path == "notes.h":
            assert metadata["header_file_only"] == header_only
        site, membership = memberships[identity]
        assert membership["source_kind"] == "cpp" and membership["status"] == "resolved"
        target = membership["target_id"]
        assert reloaded.nodes[target]["source_file"] == path
        assert reloaded.has_edge(site, target)
    reads = [edge for _, _, edge in reloaded.edges(data=True)
             if edge.get("context") == "qml_binding_read" and qt_metadata(edge).get("native_endpoint")]
    assert len(reads) == 1
    assert qt_metadata(reads[0])["native_endpoint"]
