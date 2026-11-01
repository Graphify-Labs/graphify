"""INC-QML-15: distinct constructor bodies own durable native relationships."""
from __future__ import annotations

import json

import pytest

from graphify.affected import affected_nodes
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.serve import _query_graph_text
from tests.qt_analysis_helpers import analysis, sites
from tests.test_cpp_overload_identity import constructors


def body(parameter="", signal="changed"):
    """Literal loader handles and an emission belong to one exact constructor."""
    return (f"Backend({parameter}) {{ QQmlApplicationEngine engine; engine.load(\"qrc:/App/Main.qml\"); "
            "QObject *root = engine.rootObjects().first(); root->setProperty(\"value\", 2); "
            f"emit {signal}(); }}")


def fixture(root, *, inline=False, same_line=False, unicode=False):
    """Public Qt source is analyzed as data; no engine/component or project hook executes."""
    if inline:
        header = ("class Backend : public QObject { Q_OBJECT public:\n " + body() + "\n " + body("int value", "otherChanged") +
                  "\nsignals: void changed(); void otherChanged(); };\n")
        implementation = "int unrelated(){return 7;}\n"
    else:
        header = ("class Backend : public QObject { Q_OBJECT public:\n Backend(); Backend(int value);\n"
                  "signals: void changed(); void otherChanged(); };\n")
        separator = " " if same_line else "\n"
        implementation = '#include "backend.hpp"\n' + body().replace("Backend(", "Backend::Backend(", 1)
        implementation += separator + body("int renamed", "otherChanged").replace("Backend(", "Backend::Backend(", 1) + "\n"
    if unicode:
        header = ("\ufeff// caf\u00e9 \u96ea\n" + header).replace("\n", "\r\n")
        implementation = ("\ufeff// caf\u00e9 \u96ea\n" + implementation).replace("\n", "\r\n")
    return analysis(root, {"backend.hpp": header, "backend.cpp": implementation,
        "Main.qml": "import QtQml\nQtObject { property int value: 1 }",
        "app.qrc": '<RCC><qresource prefix="/App"><file>Main.qml</file></qresource></RCC>'})


@pytest.mark.parametrize("inline,same_line,unicode", [(False, False, False), (False, True, False),
                                                     (True, False, False), (False, False, True), (True, False, True)])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml008_ac02_and_qml011_ac01_exact_overload_native_consumers(tmp_path, inline, same_line, unicode, directed):
    """Canonical constructor IDs survive assembly/export/reload with exact body-owned native sites."""
    result = fixture(tmp_path, inline=inline, same_line=same_line, unicode=unicode)
    found = constructors(result)
    assert len(found) == 2 and len({node["id"] for node in found}) == 2
    owned = sites(result, "emission") + sites(result, "qml_access") + sites(result, "qml_load") + sites(result, "qml_root")
    assert len(owned) == 8
    assert all(qt_metadata(node)["status"] == "resolved" for node in owned)
    assert {qt_metadata(node)["owner_id"] for node in owned} == {node["id"] for node in found}
    for node in found:
        scope = node["metadata"]["cpp_constructor"]
        filename = node.get("definition_file") or node["source_file"]
        span = scope.get("definition_span") or scope["span"]
        for site in owned:
            md = qt_metadata(site)
            if md["owner_id"] != node["id"]:
                continue
            assert site["source_file"] == filename
            assert span["start_byte"] <= md["span"]["start_byte"] < md["span"]["end_byte"] <= span["end_byte"]
            if md["kind"] == "emission":
                assert md["target_id"]
    graph = build_from_json(result, root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    reloaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    for site in sites(result, "emission"):
        md = qt_metadata(site)
        assert reloaded.has_edge(md["owner_id"], site["id"])
        assert md["owner_id"] in {hit.node_id for hit in affected_nodes(reloaded, md["target_id"], depth=3)}
        assert not any(data.get("relation") == "calls" for _, _, data in reloaded.edges(site["id"], data=True))
    answer = _query_graph_text(reloaded, "Backend changed otherChanged", token_budget=8000)
    assert "changed" in answer and "otherChanged" in answer and "backend.hpp" in answer


def test_req_qml008_ac03_unknown_overload_signature_cannot_borrow_known_native_class(tmp_path):
    """Unsupported alias constructor facts remain source-visible without guessed native endpoints."""
    result = analysis(tmp_path, {
        "backend.hpp": "class Backend: public QObject { Q_OBJECT public: Backend(int); Backend(Alias); signals: void changed(); };",
        "backend.cpp": '#include "backend.hpp"\nBackend::Backend(Alias value) { emit changed(); }',
    })
    emission = qt_metadata(sites(result, "emission")[0])
    assert emission["status"] != "resolved" and emission["target_id"] == ""
    assert constructors(result)


def test_req_qml008_ac03_duplicate_inline_signature_cannot_authorize_emission(tmp_path):
    """Contradictory source bodies do not become one accepted inline constructor owner."""
    result = analysis(tmp_path, {"backend.hpp": "class Backend: public QObject { Q_OBJECT public: "
                       "Backend(int value) { emit changed(); } Backend(const int other) { emit changed(); } "
                       "signals: void changed(); };"})
    emissions = sites(result, "emission")
    assert len(emissions) == 2
    assert all(qt_metadata(node)["status"] != "resolved" and qt_metadata(node)["target_id"] == "" for node in emissions)
