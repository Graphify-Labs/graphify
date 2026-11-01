"""INC-QML-85/87: local QtTest proof composes without relaxing final Qt admission."""
from __future__ import annotations

import pytest

from graphify.build import build_from_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("field", ["", "struct Holder { int Owner::*data; };"])
def test_req_qml022_ac06_statement_repair_coexists_with_supported_member_pointer(tmp_path, field):
    """A local binder/branch assertion keeps source spans and member-pointer role in the same file."""
    source = "#include <QtTest>\nclass Owner{};" + field + "\nvoid run(bool ready){\n"
    source += "QFETCH(int,value); if(ready) QTRY_COMPARE(value,1);\n}"
    result = analysis(tmp_path, {"checks.cpp": source})
    assert len(sites(result, "test_data")) == len(sites(result, "test_assertion")) == 1
    for node in sites(result, "test_data") + sites(result, "test_assertion"):
        md = qt_metadata(node)
        span = md["span"]
        assert source.encode()[span["start_byte"]:span["end_byte"]].startswith(md["mechanism"].encode() + b"(")
    if field:
        pointer, = [n for n in result["nodes"] if n.get("metadata", {}).get("cpp_declarator", {}).get("member_pointer")]
        assert pointer["metadata"]["cpp_declarator"]["member_pointer"]["owner_status"] == "source_only"
        assert not pointer.get("_callable")
    graph = build_from_json(result, root=tmp_path)
    assert len([n for _, n in graph.nodes(data=True) if qt_metadata(n).get("kind") in {"test_data", "test_assertion"}]) == 2


@pytest.mark.parametrize("neighbor", ["struct Holder{ int Owner::*; };", "void broken( ;", "int value = ;"])
def test_req_qml022_ac06_local_statement_success_never_accepts_unrepaired_neighbor(tmp_path, neighbor):
    """Unknown malformed syntax still fails the final complete Qt overlay parser gate."""
    path = tmp_path / "checks.cpp"
    path.write_bytes(("#include <QtTest>\nclass Owner{};" + neighbor + "\nvoid run(){QFETCH(int,value);}").encode())
    with pytest.raises(QtCppError) as caught:
        read_cpp(path, tmp_path)
    assert caught.value.code == "QT_CPP_SYNTAX"
