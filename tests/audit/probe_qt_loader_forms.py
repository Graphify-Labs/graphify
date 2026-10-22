"""Opt-in INC-QML-20 audit of literal loader provenance, not runtime execution.

Invoke explicitly with pytest: normal discovery excludes ``probe_*.py``. These
strict assertions expose coverage omissions under REQ-QML-017-AC01/AC04; missing
facts remain unresolved rather than linking a guessed component or property.
"""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("loader", ["engine_load", "engine_url_constructor", "component_load_url"])
def test_req_qml017_ac01_literal_loader_keeps_component_and_property_provenance(tmp_path, loader):
    """Equivalent literal loaders must preserve exact source and persisted joins."""
    url = (tmp_path / "Main.qml").as_uri()
    loader_expressions = {
        "engine_load": f'engine.load(QUrl("{url}"))',
        "engine_url_constructor": f'QQmlApplicationEngine engine(QUrl("{url}"))',
        "component_load_url": f'component.loadUrl(QUrl("{url}"))',
    }
    expression = loader_expressions[loader]
    forms = {
        "engine_load": f'QQmlApplicationEngine engine; {expression}; auto root = engine.rootObjects().first();',
        "engine_url_constructor": f'{expression}; auto root = engine.rootObjects().first();',
        "component_load_url": f'QQmlEngine engine; QQmlComponent component(&engine); {expression}; auto root = component.create();',
    }
    source = 'void use() { ' + forms[loader] + ' root->property("value"); }'
    result = analysis(tmp_path, {
        "access.cpp": source,
        "Main.qml": 'import QtQml\nQtObject { property int value: 1 }',
    })
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "proof.json"
    assert to_json(graph, {}, str(output), force=True)
    reloaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))

    # Check the source-owning loader occurrence, not a URL-less constructor or
    # a generic C++ call that lacks special component provenance.
    original = source.encode()
    loaders = [node for node in sites(result, "qml_load")
               if original[qt_metadata(node)["span"]["start_byte"]:
                           qt_metadata(node)["span"]["end_byte"]] == expression.encode()]
    assert len(loaders) == 1, {
        "loader": loader,
        "recognized_operations": [qt_metadata(node)["operation"] for node in sites(result, "qml_load")],
    }
    metadata = qt_metadata(loaders[0])
    assert metadata["status"] == "resolved"
    assert metadata["target_id"] in reloaded
    assert reloaded.has_edge(loaders[0]["id"], metadata["target_id"])
    assert reloaded.edges[loaders[0]["id"], metadata["target_id"]]["context"] == "qt_cpp_qml_load"

    access = sites(result, "qml_access", "property")[0]
    metadata = qt_metadata(access)
    assert metadata["status"] == "resolved"
    assert original[metadata["span"]["start_byte"]:metadata["span"]["end_byte"]] == b'root->property("value")'
    assert reloaded.has_edge(access["id"], metadata["target_id"])
    assert reloaded.edges[access["id"], metadata["target_id"]]["context"] == "qt_cpp_qml_property_read"
