"""INC-QML-87: actual callable substatements differ from nested expressions."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites
from tests.qt_cpp_test_helpers import collect


@pytest.mark.parametrize("body,count", [
    ("if (ready) QTRY_COMPARE(1,1);", 1),
    ("if(ready) while(ready) QTRY_VERIFY(ready); else QTRY_VERIFY(ready);", 2),
    ("for(auto value:values) QTRY_VERIFY(value);", 1),
    ("label: QTRY_VERIFY(ready);", 1),
    ("try{QTRY_VERIFY(ready);}catch(...){QTRY_VERIFY(ready);}", 2),
    ("#if FIRST\nQTRY_VERIFY(ready);\n#elif SECOND\nQTRY_VERIFY(ready);\n#else\nQTRY_VERIFY(ready);\n#endif", 3),
    ("auto callback=[](){QTRY_VERIFY(true);};", 1),
])
def test_req_qml022_ac03_typed_statement_paths_keep_actual_source_owner(tmp_path, body, count):
    """Each actual body/branch retains its original occurrence and source-only uncertainty."""
    source = "\ufeff// UTF-8: café 雪\r\n#include <QtTest>\r\nvoid run(bool ready){\r\n" + body + "\r\n}"
    result = analysis(tmp_path, {"checks.cpp": source})
    found = sites(result, "test_assertion")
    assert len(found) == count
    owners = {n["id"] for n in result["nodes"] if n.get("_callable")}
    for node in found:
        metadata = qt_metadata(node)
        assert metadata["owner_id"] in owners
        assert metadata["status"] == "source_only" and metadata["runtime_status"] == "unverified"
        assert metadata["evaluation_status"] == "unverified" and metadata["repeated_evaluation"] is True
        span = metadata["span"]
        assert source.encode()[span["start_byte"]:span["end_byte"]].startswith(metadata["mechanism"].encode() + b"(")
        scope = metadata["scope_span"]
        assert scope["start_byte"] < span["start_byte"] < span["end_byte"] < scope["end_byte"]


@pytest.mark.parametrize("source", [
    "QTRY_VERIFY(true);",
    "class Checks { QTRY_VERIFY(true); };",
    "void run(bool value=QTRY_VERIFY(true)){}",
    "void run(){int value=QTRY_VERIFY(true);}",
    "void run(){return QTRY_VERIFY(true);}",
    "void run(){consume(QTRY_VERIFY(true));}",
    "void run(){for(QTRY_VERIFY(true);;) {}}",
    "void run(){for(;QTRY_VERIFY(true);) {}}",
    "void run(){for(;;QTRY_VERIFY(true)) {}}",
    "void run(){if(QTRY_VERIFY(true)) {}}",
    "void run(){auto value=({QTRY_VERIFY(true);0;});}",
])
def test_req_qml022_ac06_nested_or_noncallable_expressions_cannot_borrow_statement_role(tmp_path, source):
    """Actual malformed/unsupported roles reject at the production boundary without Qt overlays."""
    path = tmp_path / "checks.cpp"
    path.write_bytes(("#include <QtTest>\n" + source).encode())
    with pytest.raises(QtCppError) as caught:
        read_cpp(path, tmp_path)
    assert caught.value.code == "QT_CPP_SYNTAX"
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert result.get("qml_failures") == [{"code": "QT_CPP_SYNTAX", "source_file": "checks.cpp"}]
    assert not sites(result, "test_data") and not sites(result, "test_assertion")


@pytest.mark.parametrize("body", [
    "if(ready) { QFETCH(QQmlApplicationEngine, engine); engine.load(\"Main.qml\"); }",
    "#if FEATURE\nQFETCH(QQmlApplicationEngine, engine); engine.load(\"Main.qml\");\n#endif",
])
def test_req_qml022_ac03_branch_test_columns_do_not_create_native_provider_types(tmp_path, body):
    """Conditional source binders stay opaque even when their original type names a Qt engine."""
    result = analysis(tmp_path, {"checks.cpp": "#include <QtTest>\nvoid run(bool ready){\n" + body + "\n}"})
    found, = sites(result, "test_data")
    assert qt_metadata(found)["status"] == "source_only"
    assert qt_metadata(found)["runtime_status"] == "unverified"
    assert not sites(result, "qml_load") and not sites(result, "context_exposure")


def test_req_qml022_ac06_direct_control_facts_keep_owner_scope_through_export_reload(tmp_path):
    """The actual direct overlay borrows unchanged canonical owners; transport preserves its proof."""
    source = "#include <QtTest>\nvoid run(bool ready){if(ready) QTRY_VERIFY(ready);}\n"
    result = collect(tmp_path, {"checks.cpp": source})
    assertion, = sites(result, "test_assertion")
    md = qt_metadata(assertion)
    owner = next(n for n in result["nodes"] if n["id"] == md["owner_id"])
    assert owner.get("_callable") and owner["label"] == "run()"
    graph = build_from_json(result, root=tmp_path, directed=True)
    destination = tmp_path / "proof.json"
    to_json(graph, {}, str(destination))
    loaded = load_node_link_graph(json.loads(destination.read_text()))
    assert qt_metadata(loaded.nodes[assertion["id"]]) == md


def test_req_qml022_ac03_conditional_opaque_column_shadows_global_callback(tmp_path):
    """A conditional source column cannot turn its uncertain local call into a global callback target."""
    source = ("#include <QtTest>\nusing Handler=void(*)(); void callback(){}\nvoid run(){\n"
              "#if FEATURE\nQFETCH(Handler,callback); callback();\n#endif\n}")
    result = analysis(tmp_path, {"checks.cpp": source})
    assert len(sites(result, "test_data")) == 1
    callback = next(n["id"] for n in result["nodes"] if n.get("_callable") and n["label"] == "callback()")
    assert not [e for e in result["edges"] if e.get("relation") == "calls" and e["target"] == callback]
