"""INC-QML-80: actual callable parameters never come from a returned callback."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import read_cpp
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites
from tests.qt_adoption_fixture import NATIVE, sources as adoption_sources


def sources(pointee="void", own=""):
    """Return syntax is deliberately valid C++; no fixture code is executed."""
    return {"backend.hpp": f'''class Service:public QObject{{Q_OBJECT public:Q_INVOKABLE int count()const;}};
class Backend:public QObject{{Q_OBJECT public:Q_INVOKABLE {pointee} (*factory({own}))(int callbackValue);}};
''', "backend.cpp": f'''#include "backend.hpp"
{pointee} (*Backend::factory({own}))(int callbackValue){{return nullptr;}}
'''}


@pytest.mark.parametrize("pointee,own,parameters", [("void", "", []), ("Service *", "", []),
                                                   ("Service *", "double token", ["double"])])
def test_req_qml022_ac02_callback_return_header_definition_keep_actual_signature(tmp_path, pointee, own, parameters):
    """Both actual source occurrences preserve ownership, original spans and opaque returns."""
    fixtures = sources(pointee, own)
    result = analysis(tmp_path, fixtures)
    members = [node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "factory"]
    assert len(members) == 2
    for node in members:
        md = qt_metadata(node)
        assert md["parameter_types"] == parameters
        assert md["signature"] == "factory(" + ",".join(parameters) + ")"
        assert md["class_name"] == "Backend" and md["generic_target_id"]
        assert md["api_type_status"] == "unsupported" and not md.get("api_type_target_id")
        assert "(*" in md["api_type_spelling"] and "callbackValue" in md["api_type_spelling"]
        source = fixtures[node["source_file"]].encode()
        assert b"factory(" in source[md["span"]["start_byte"]:md["span"]["end_byte"]]
    source_path = tmp_path / "backend.cpp"
    direct = extract_cpp(source_path)
    assert not direct.get("parse_errors")
    mapping = map_cpp(read_cpp(source_path, tmp_path), result["nodes"], result["edges"], root=tmp_path)
    factory = [record for record in mapping.functions if record["name"] == "factory"]
    assert len(factory) == 1 and factory[0]["parameter_types"] == parameters
    assert factory[0]["body"] is not None
    graph = build_from_json(result, root=tmp_path, directed=True)
    destination = tmp_path / "roundtrip.json"
    to_json(graph, {}, str(destination))
    loaded = load_node_link_graph(json.loads(destination.read_text()))
    assert all(qt_metadata(loaded.nodes[node["id"]]) == qt_metadata(node) for node in members)


def test_req_qml022_ac03_pointer_returning_callback_is_not_qml_object_factory(tmp_path):
    """The callback's Service pointee cannot supply a declared native factory hop."""
    fixtures = sources("Service *")
    fixtures["backend.hpp"] = fixtures["backend.hpp"].replace("class Backend:public QObject{Q_OBJECT", "class Backend:public QObject{Q_OBJECT QML_NAMED_ELEMENT(Backend)")
    fixtures.update({"Main.qml": "import Public.Tools 1.0\nBackend { property int shown: factory().count() }",
                     "CMakeLists.txt": "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.hpp backend.cpp)"})
    result = analysis(tmp_path, fixtures)
    members = [qt_metadata(node) for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "factory"]
    assert len(members) == 2 and all(md["parameter_types"] == [] for md in members)
    assert all(md["api_type_status"] == "unsupported" and not md.get("api_type_target_id") for md in members)
    counts = {qt_metadata(node)["generic_target_id"] for node in sites(result, "member")
              if qt_metadata(node)["raw_name"] == "count"}
    assert not [edge for edge in result["edges"] if edge.get("relation") in {"calls", "uses"}
                and qt_metadata(edge).get("native_endpoint") and edge["target"] in counts]


@pytest.mark.parametrize("callback", [False, True])
def test_req_qml022_ac03_declared_provider_rejects_callback_pointee_with_ordinary_control(tmp_path, callback):
    """The real typed-provider consumer accepts an object pointer and rejects a callback."""
    native = NATIVE.replace("Backend *makeBackend()", "Backend *(*makeBackend())(int callbackValue)") if callback else NATIVE
    result = analysis(tmp_path, adoption_sources(tmp_path, native=native))
    bindings = sites(result, "context_binding")
    if callback:
        assert not bindings and not sites(result, "context_access")
        factory = next(qt_metadata(node) for node in sites(result, "member")
                       if qt_metadata(node)["raw_name"] == "makeBackend")
        assert factory["parameter_types"] == [] and factory["api_type_status"] == "unsupported"
    else:
        assert len(bindings) == 1 and qt_metadata(bindings[0])["provider_class_name"] == "Backend"
        assert sites(result, "context_access")


def test_req_qml022_ac06_callback_return_ranges_remain_original_bom_crlf_unicode_bytes(tmp_path):
    """Comments/newlines cannot shift either declaration or body source span."""
    fixtures = {name: '\ufeff// café 雪\r\n' + source.replace('\n', '\r\n') for name, source in sources("Service *").items()}
    result = analysis(tmp_path, fixtures)
    members = [node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "factory"]
    assert len(members) == 2
    for node in members:
        md, source = qt_metadata(node), fixtures[node["source_file"]].encode()
        span = md["span"]
        assert source[span["start_byte"]:span["end_byte"]].count(b"factory(") == 1
        prefix = source[:span["start_byte"]]
        assert prefix.count(b'\n') == span["start_row"]
        assert span["start_column"] == span["start_byte"] - prefix.rfind(b'\n') - 1
        assert md["parameter_types"] == []
