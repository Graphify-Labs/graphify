"""REQ-QML-008/016/017: constructor ownership reaches durable Qt consumers."""
import json

import pytest

from graphify.affected import affected_nodes
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.serve import _query_graph_text
from tests.qt_analysis_helpers import analysis, sites


HEADER = '''class Backend : public QObject {
 Q_OBJECT
public:
 explicit Backend(QObject *parent = nullptr);
signals:
 void changed();
};
'''
BODY = '''#include "backend.hpp"
Backend::Backend(QObject *parent) : QObject(parent) {
 QQmlApplicationEngine engine;
 engine.load("qrc:/App/Main.qml");
 QObject *root = engine.rootObjects().first();
 root->setProperty("value", 2);
 emit changed();
}
'''


def fixture(root, header=HEADER, body=BODY):
    """An accepted literal resource supplies reverse-QML targets without executing Qt."""
    return analysis(root, {"backend.hpp": header, "backend.cpp": body,
        "Main.qml": "import QtQml\nQtObject { property int value: 1 }",
        "app.qrc": '<RCC><qresource prefix="/App"><file>Main.qml</file></qresource></RCC>'})


def constructor(result):
    candidates = [node for node in result["nodes"] if node.get("_callable") and not node.get("_callable_class")
                  and (node.get("definition_file") == "backend.cpp" or node.get("source_file") == "backend.cpp")]
    assert len(candidates) == 1
    return candidates[0]


@pytest.mark.parametrize("namespace", [False, True])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml016_ac01_and_qml017_ac02_constructor_owns_emission_and_write_after_json_reload(tmp_path, namespace, directed):
    """Original constructor identity owns every site through assembly, publication and real consumers."""
    header = f"namespace Shared {{\n{HEADER}}}\n" if namespace else HEADER
    body = BODY.replace("Backend::Backend", "Shared::Backend::Backend") if namespace else BODY
    result = fixture(tmp_path, header, body)
    method = constructor(result)
    owned = sites(result, "qml_load") + sites(result, "qml_root") + sites(result, "qml_access") + sites(result, "emission")
    assert len(owned) == 4
    assert all(qt_metadata(node)["owner_id"] == method["id"] and qt_metadata(node)["status"] == "resolved" for node in owned)
    emission = sites(result, "emission")[0]
    signal = qt_metadata(emission)["target_id"]
    original = (tmp_path / "backend.cpp").read_bytes()
    span = qt_metadata(emission)["span"]
    assert original[span["start_byte"]:span["end_byte"]] == b"changed()"
    graph = build_from_json(result, root=tmp_path, directed=directed)
    path = tmp_path / "graph.json"
    assert to_json(graph, cluster(graph), str(path))
    reloaded = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    assert all(reloaded.has_edge(method["id"], node["id"]) for node in owned)
    assert all(qt_metadata(reloaded.nodes[node["id"]])["owner_id"] == method["id"] for node in owned)
    assert not any(data.get("relation") == "calls" for _, _, data in reloaded.edges(emission["id"], data=True))
    assert method["id"] in {hit.node_id for hit in affected_nodes(reloaded, signal, depth=3)}
    answer = _query_graph_text(reloaded, "Backend changed", token_budget=4000)
    assert "backend.cpp" in answer and "Qt emission: changed" in answer


def test_req_qml008_ac02_constructor_spans_use_original_bom_crlf_unicode_bytes(tmp_path):
    """No normalized-newline or display-string offset may replace producer byte positions."""
    body = ("\ufeff// caf\u00e9 \u96ea\n" + BODY).replace("\n", "\r\n")
    result = fixture(tmp_path, body=body)
    method = constructor(result)
    assert method["definition_file"] == "backend.cpp" and method["definition_location"] == "L3"
    original = (tmp_path / "backend.cpp").read_bytes()
    assert original == body.encode("utf-8")
    for node in sites(result, "emission") + sites(result, "qml_access"):
        metadata = qt_metadata(node)
        assert metadata["owner_id"] == method["id"]
        span = metadata["span"]
        expected = b"changed()" if metadata["kind"] == "emission" else b'root->setProperty("value", 2)'
        assert original[span["start_byte"]:span["end_byte"]] == expected


@pytest.mark.parametrize("control", ["duplicate_body", "foreign_namespace", "overloaded_delegation"])
def test_req_qml016_ac04_constructor_conflicts_cannot_invent_a_canonical_owner(tmp_path, control):
    """A genuine duplicate class or collapsed overload remains a visible unresolved source site."""
    header, body = HEADER, BODY
    if control == "foreign_namespace":
        header = f"namespace Other {{\n{HEADER}}}\n"
        body = BODY.replace("Backend::Backend", "Foreign::Backend::Backend")
    elif control == "overloaded_delegation":
        header = HEADER.replace(" explicit Backend", " Backend();\n explicit Backend")
        body = BODY.replace("Backend::Backend(QObject *parent) : QObject(parent)", "Backend::Backend() : Backend(nullptr)")
    sources = {"backend.hpp": header, "backend.cpp": body}
    if control == "duplicate_body":
        sources["duplicate.hpp"] = header
    sources.update({"Main.qml": "import QtQml\nQtObject { property int value: 1 }",
        "app.qrc": '<RCC><qresource prefix="/App"><file>Main.qml</file></qresource></RCC>'})
    result = analysis(tmp_path, sources)
    method = constructor(result)
    implementation = next(node for node in sites(result, "member") if node["source_file"] == "backend.cpp")
    assert qt_metadata(implementation)["class_id"] == ""
    assert not any(edge["target"] == method["id"] and edge["relation"] == "method" for edge in result["edges"])
    emission = qt_metadata(sites(result, "emission")[0])
    assert emission["owner_id"] == method["id"] and emission["status"] != "resolved" and emission["target_id"] == ""
    # Independently proved source callables and literal resource handles do not
    # need native class authority to own a QML write in the same body.
    access = qt_metadata(sites(result, "qml_access")[0])
    assert access["owner_id"] == method["id"] and access["status"] == "resolved"


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml016_ac04_and_qml017_ac04_constructor_updates_remove_stale_sites_and_preserve_failures(tmp_path, monkeypatch, operation):
    """Real cold/warm, CLI/watch, edit/removal and failed publication keep exact source ownership."""
    from tests.test_qt_final_incremental_parity import clean, normalized, run

    fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cache = tmp_path / ".comparison-cache"
    cold = clean(tmp_path, cache)
    assert normalized(clean(tmp_path, cache)) == normalized(cold)
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(cold)
    paths = [tmp_path / "backend.hpp", tmp_path / "backend.cpp"]
    for path in paths:
        path.write_text(path.read_text(encoding="utf-8").replace("parent", "owner"), encoding="utf-8", newline="")
    changed = run(tmp_path, monkeypatch, operation, paths)
    assert normalized(changed) == normalized(clean(tmp_path, tmp_path / ".edited-cache"))
    emissions = [identity for identity, data in changed.nodes(data=True) if qt_metadata(data).get("kind") == "emission"]
    assert len(emissions) == 1 and qt_metadata(changed.nodes[emissions[0]])["owner_id"]
    cpp = paths[1]
    cpp.write_text(cpp.read_text(encoding="utf-8").replace(" emit changed();\n", ""), encoding="utf-8", newline="")
    removed = run(tmp_path, monkeypatch, operation, [cpp])
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    assert not any(qt_metadata(data).get("kind") == "emission" for _, data in removed.nodes(data=True))
    output = tmp_path / "graphify-out"
    retained = {name: (output / name).read_bytes() for name in ("graph.json", "manifest.json", ".qt_analysis.json")}
    valid = cpp.read_bytes()
    cpp.write_bytes(valid + b"\nvoid damaged( {\n")
    if operation == "manual":
        with pytest.raises(SystemExit) as failure:
            run(tmp_path, monkeypatch, operation, [cpp])
        assert failure.value.code == 1
    else:
        from graphify.watch import _rebuild_code
        assert not _rebuild_code(tmp_path, changed_paths=[cpp], no_cluster=True)
    assert retained == {name: (output / name).read_bytes() for name in retained}
    cpp.write_bytes(valid)
    corrected = run(tmp_path, monkeypatch, operation, [cpp])
    assert normalized(corrected) == normalized(removed)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(corrected)
