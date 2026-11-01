"""INC-QML-73: namespace-owned callables never acquire native class identity."""
from __future__ import annotations

from graphify.extract import extract_cpp
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import read_cpp
from tests.qt_analysis_helpers import analysis, sites


def test_req_qml022_ac06_namespace_free_definition_keeps_sdk_body_without_native_member(tmp_path):
    """An actual namespace body retains engine calls while class ownership stays empty."""
    result = analysis(tmp_path, {"main.cpp": '''#include <QQmlApplicationEngine>
namespace N { void boot(){QQmlApplicationEngine engine; engine.load("Main.qml");} }
'''})
    assert not sites(result, "member")
    assert len(sites(result, "qml_load")) == 1
    path = tmp_path / "main.cpp"
    direct = extract_cpp(path)
    mapping = map_cpp(read_cpp(path, tmp_path), direct["nodes"], direct["edges"], root=tmp_path)
    record = next(item for item in mapping.functions if item["name"] == "boot")
    assert record["body"] is not None and record["node_id"]
    assert record["class_name"] == record["class_id"] == ""


def test_req_qml022_ac06_unrelated_free_provenance_cannot_clear_member_owner(tmp_path):
    """A valid neighboring source fact cannot suppress a real class method."""
    path = tmp_path / "main.cpp"
    path.write_text("namespace N { void free(){} } class Native { public: void run(){} };", encoding="utf-8")
    direct = extract_cpp(path)
    free = next(node for node in direct["nodes"] if node["label"] == "free()")
    member = next(node for node in direct["nodes"] if node["label"] == ".run()")
    member.setdefault("metadata", {})["cpp_function"] = free["metadata"]["cpp_function"]
    mapping = map_cpp(read_cpp(path, tmp_path), direct["nodes"], direct["edges"], root=tmp_path)
    record = next(item for item in mapping.functions if item["name"] == "run")
    assert record["class_name"] == "Native" and record["class_id"]
