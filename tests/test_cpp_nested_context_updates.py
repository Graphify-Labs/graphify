"""INC-QML-109: QML/build-only updates retain source-owned nested C++ lookup."""
from __future__ import annotations

from collections import Counter

import pytest

from tests.cpp_nested_helpers import nested_source
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_nested_class_updates import calls
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def cpp_facts(graph):
    """Keep complete node/relationship attributes under the actual published identity profile."""
    nodes, edges = full_fields(graph)
    identities = {identity for identity, data in graph.nodes(data=True) if data.get("source_file") == "nested.cpp"}
    return ({identity: nodes[identity] for identity in identities},
            Counter({edge: count for edge, count in edges.items() if edge[0] in identities and edge[1] in identities}))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_qml_and_metadata_only_updates_keep_nested_cpp_proof(tmp_path, monkeypatch, operation):
    """Actual shared context owners refresh QML and metadata without losing a nested source call.

    Compare every persisted field against the same-owner cold full rebuild;
    legacy undirected iteration order supplies no new relationship direction.
    """
    cpp = tmp_path / "nested.cpp"
    cpp.write_bytes(nested_source(namespace="Public"))
    qml = tmp_path / "Main.qml"
    qml.write_bytes(b"import QtQuick\nItem {}\n")
    cmake = tmp_path / "CMakeLists.txt"
    cmake.write_bytes(b"qt_add_qml_module(app URI Public.Nested VERSION 1.0 QML_FILES Main.qml SOURCES nested.cpp)\n")
    (tmp_path / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    source_bytes, source_time = cpp.read_bytes(), cpp.stat().st_mtime_ns
    initial = run(tmp_path, monkeypatch, operation)
    assert len(calls(initial)) == 1
    witnesses = [data["metadata"]["cpp_class"]["lexical_scope_proof"]
                 for _, data in initial.nodes(data=True) if data.get("metadata", {}).get("cpp_class")]
    assert len(witnesses) == 2 and all(value["complete"] and not value["conditional"] for value in witnesses)
    expected = cpp_facts(initial)

    # Only QML changes first; only literal module metadata changes next. The
    # C++ facts, source witnesses, source bytes and file time must remain exact.
    qml.write_bytes(b"import QtQuick\nItem {property int revision: 1}\n")
    qml_only = run(tmp_path, monkeypatch, operation, [qml])
    assert len(calls(qml_only)) == 1 and cpp_facts(qml_only) == expected
    assert full_fields(qml_only) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    cmake.write_bytes(cmake.read_bytes().replace(b"VERSION 1.0", b"VERSION 1.1"))
    metadata_only = run(tmp_path, monkeypatch, operation, [cmake])
    assert len(calls(metadata_only)) == 1 and cpp_facts(metadata_only) == expected
    assert full_fields(metadata_only) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(initial) == unrelated(qml_only) == unrelated(metadata_only)
    assert (cpp.read_bytes(), cpp.stat().st_mtime_ns) == (source_bytes, source_time)
    accepted = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [qml, cmake])
    assert products(tmp_path) == accepted
