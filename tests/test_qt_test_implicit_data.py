"""INC-QML-88: implicit-body columns are source-only inert statements."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("body", [
    "if(ready) QFETCH(int,value);",
    "if(ready) {} else QFETCH(int,value);",
    "while(ready) QFETCH(int,value);",
    "do QFETCH(int,value); while(ready);",
    "for(int i=0;i<2;++i) QFETCH(int,value);",
    "for(auto item:items) QFETCH(int,value);",
])
def test_req_qml022_ac03_unbraced_data_keeps_exact_implicit_lifetime_without_declaration(tmp_path, body):
    """Actual direct body ownership admits an inert view, preserving only the original column facts."""
    source = "\ufeff// UTF-8: café 雪\r\n#include <QtTest>\r\nvoid run(bool ready){" + body + "}\r\n"
    result = analysis(tmp_path, {"checks.cpp": source})
    path = tmp_path / "checks.cpp"
    unit = read_cpp(path, tmp_path)
    record, = unit.qt_test_macros
    assert record["parsed_role"] == "opaque_statement"
    assert len(unit.source) == len(unit.parsed_source)
    view = unit.parsed_source[record["start"]:record["semicolon"] + 1]
    assert view.strip() == b"0" + b" " * (len(view.strip()) - 2) + b";"
    found, = sites(result, "test_data")
    md = qt_metadata(found)
    assert md["parsed_role"] == "opaque_statement"
    assert md["status"] == "source_only" and md["runtime_status"] == "unverified"
    assert md["scope_span"] == {"start_byte": record["start"], "end_byte": record["semicolon"] + 1}
    assert source.encode()[md["span"]["start_byte"]:md["span"]["end_byte"]] == b"QFETCH(int,value)"
    assert not [n for n in result["nodes"] if not qt_metadata(n) and n.get("label") == "value"]
    graph = build_from_json(result, root=tmp_path)
    destination = tmp_path / "proof.json"
    to_json(graph, {}, str(destination))
    loaded = load_node_link_graph(json.loads(destination.read_text()))
    assert qt_metadata(loaded.nodes[found["id"]]) == md


@pytest.mark.parametrize("statement", [
    "{QFETCH(int,value);}", "#if FEATURE\nQFETCH(int,value);\n#endif",
    "switch(ready){case true: QFETCH(int,value); break;}", "label: QFETCH(int,value);",
])
def test_req_qml022_ac03_existing_scoped_data_preserves_the_real_opaque_binder(tmp_path, statement):
    """Block/preprocessor/case/label declarations keep their established shadowing parse view."""
    source = "#include <QtTest>\nvoid run(bool ready){\n" + statement + "\n}"
    result = analysis(tmp_path, {"checks.cpp": source})
    unit = read_cpp(tmp_path / "checks.cpp", tmp_path)
    record, = unit.qt_test_macros
    assert record.get("parsed_role") != "opaque_statement"
    assert unit.parsed_source[record["start"]:record["start"] + 3] == b"int"
    assert qt_metadata(sites(result, "test_data")[0]).get("parsed_role") != "opaque_statement"


def test_req_qml022_ac03_implicit_column_cannot_shadow_outer_engine_or_callback_after_branch(tmp_path):
    """The original implicit body lifetime ends at its semicolon; later outer references stay valid."""
    source = ("#include <QtTest>\nusing Handler=void(*)(); void callback(){}\n"
              "void run(bool ready){QQmlApplicationEngine engine;"
              "if(ready) QFETCH(QQmlApplicationEngine,engine); engine.load(\"Main.qml\");"
              "if(ready) QFETCH(Handler,callback); callback();}")
    result = analysis(tmp_path, {"checks.cpp": source})
    assert len(sites(result, "test_data")) == 2
    assert len(sites(result, "qml_load")) == 1
    target = next(n["id"] for n in result["nodes"] if n.get("_callable") and n["label"] == "callback()")
    assert len([e for e in result["edges"] if e.get("relation") == "calls" and e["target"] == target]) == 1


@pytest.mark.parametrize("braced", [False, True])
def test_req_qml022_ac03_data_type_payload_never_becomes_a_generic_or_native_call(tmp_path, braced):
    """Even decltype payloads stay opaque; a real following SDK occurrence is retained independently."""
    statement = "QFETCH(decltype(engine.rootObjects()),value);"
    source = "#include <QtTest>\nvoid run(bool ready){QQmlApplicationEngine engine;if(ready)"
    source += "{" + statement + "}" if braced else statement
    source += "engine.rootObjects();}"
    result = analysis(tmp_path, {"checks.cpp": source})
    assert len(sites(result, "test_data")) == 1
    root, = sites(result, "qml_root")
    span = qt_metadata(root)["span"]
    assert span["start_byte"] == source.rindex("engine.rootObjects()")


@pytest.mark.parametrize("body", [
    "for(QFETCH(int,value);;){}", "if(QFETCH(int,value)){}",
    "int value=QFETCH(int,fetched);", "consume(QFETCH(int,value));",
])
def test_req_qml022_ac06_implicit_data_view_cannot_borrow_initializer_or_condition_role(tmp_path, body):
    """The fallback must prove a typed control body, not merely reside inside a callable."""
    path = tmp_path / "checks.cpp"
    path.write_text("#include <QtTest>\nvoid run(){" + body + "}", encoding="utf-8")
    with pytest.raises(QtCppError) as caught:
        read_cpp(path, tmp_path)
    assert caught.value.code == "QT_CPP_SYNTAX"
