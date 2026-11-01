"""REQ-QML-022-AC03/AC06: real callable statements retain source-flow uncertainty."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import read_cpp
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("statement", [
    "if (ready) QTRY_VERIFY(ready);",
    "if (ready) {} else QTRY_VERIFY(ready);",
    "while (ready) QTRY_VERIFY(ready);",
    "do QTRY_VERIFY(ready); while (ready);",
    "for (int i=0; i<2; ++i) QTRY_VERIFY(ready);",
    "switch (ready) { case true: QTRY_VERIFY(ready); break; default: break; }",
])
def test_req_qml022_ac03_retry_is_a_standalone_statement_under_actual_flow(tmp_path, statement):
    """A legal substatement keeps the actual function owner without asserting execution/count."""
    source = "#include <QtTest>\nvoid run(bool ready) { " + statement + " }\n"
    result = analysis(tmp_path, {"checks.cpp": source})
    found = sites(result, "test_assertion")
    assert len(found) == 1
    metadata = qt_metadata(found[0])
    assert metadata["status"] == "source_only" and metadata["runtime_status"] == "unverified"
    assert metadata["repeated_evaluation"] is True
    span = metadata["span"]
    assert source.encode()[span["start_byte"]:span["end_byte"]] == b"QTRY_VERIFY(ready)"
    owner = next(node["id"] for node in result["nodes"] if node.get("_callable") and node["label"] == "run()")
    assert metadata["owner_id"] == owner


def test_req_qml022_ac03_conditional_data_keeps_occurrence_without_native_type(tmp_path):
    """An unknown feature condition does not erase a source column or prove its SDK type."""
    source = ("#include <QtTest>\nvoid run() {\n#if FEATURE\n"
              "QFETCH(QQmlEngine *, engine);\n#endif\n}\n")
    path = tmp_path / "checks.cpp"
    path.write_bytes(source.encode())
    unit = read_cpp(path, tmp_path)
    assert len(unit.qt_test_macros) == 1
    result = analysis(tmp_path, {"checks.cpp": source})
    found = sites(result, "test_data")
    assert len(found) == 1 and qt_metadata(found[0])["status"] == "source_only"
    assert not sites(result, "qml_load") and not sites(result, "context_exposure")


def test_req_qml022_ac06_expression_in_a_for_initializer_is_not_a_statement_macro(tmp_path):
    """A nested expression cannot borrow standalone-statement recovery."""
    source = "#include <QtTest>\nvoid run(bool ready){for(QTRY_VERIFY(ready); ready;) {}}\n"
    path = tmp_path / "checks.cpp"
    path.write_bytes(source.encode())
    from graphify.extractors.qt_cpp_syntax import QtCppError
    with pytest.raises(QtCppError):
        read_cpp(path, tmp_path)
