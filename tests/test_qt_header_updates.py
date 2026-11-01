"""REQ-QML-018-AC07/AC06: actual header dispatch update and durable failure."""
from __future__ import annotations

import os
import stat

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.test_qt_event_incremental_consumers import run
from tests.test_qt_final_incremental_parity import clean, normalized
from tests.test_qt_product_publication import reject, snapshot

CPP = "\ufeff// λ\r\nclass\r\nBackend : public QObject { Q_OBJECT };\r\n"
C = '/* class Ghost {}; :: namespace Fake {} */\nstruct Backend { int value; };\n'


def setup(root):
    """Generic retained sources prevent unrelated shrink policy from obscuring dispatch."""
    header = root / "backend.h"
    header.write_bytes(CPP.encode("utf-8"))
    (root / "keep.py").write_text("\n".join(f"def keep_{i}(): return {i}" for i in range(30)), encoding="utf-8")
    return header


def cpp_targets(graph):
    """Only an accepted canonical Qt class proves C++ header extraction occurred."""
    return [qt_metadata(node)["generic_target_id"] for _, node in graph.nodes(data=True)
            if node.get("source_file") == "backend.h" and qt_metadata(node).get("kind") == "class"
            and qt_metadata(node).get("status") == "resolved"]


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac07_header_dispatch_mutation_matches_cold_and_warm(tmp_path, monkeypatch, operation):
    """C++→C→C++ edits replace old authority without stale classes or cache aliases."""
    header = setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    original = run(tmp_path, monkeypatch, operation)
    old = cpp_targets(original)
    assert len(old) == 1 and old[0] in original
    header.write_bytes(C.encode())
    plain = run(tmp_path, monkeypatch, operation, [header])
    assert not cpp_targets(plain)
    assert not any(node.get("metadata", {}).get("cpp_class") for _, node in plain.nodes(data=True)
                   if node.get("source_file") == "backend.h")
    assert normalized(plain) == normalized(clean(tmp_path, tmp_path / ".clean-c"))
    header.write_bytes(CPP.encode("utf-8"))
    restored = run(tmp_path, monkeypatch, operation, [header])
    assert normalized(restored) == normalized(original)
    assert normalized(restored) == normalized(clean(tmp_path, tmp_path / ".clean-cpp"))
    accepted = snapshot(tmp_path / "graphify-out")
    assert normalized(run(tmp_path, monkeypatch, operation, [header])) == normalized(restored)
    assert snapshot(tmp_path / "graphify-out") == accepted


@pytest.mark.skipif(os.name != "nt", reason="Real Windows read-only publication boundary")
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac06_header_refresh_denial_preserves_then_recovers(tmp_path, monkeypatch, operation):
    """Actual final sidecar denial retains the accepted cohort after dispatch changed."""
    header = setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    header.write_bytes(C.encode())
    destination = output / "manifest.json"
    destination.chmod(stat.S_IREAD)
    try:
        reject(tmp_path, monkeypatch, operation, header)
        assert snapshot(output) == before
    finally:
        destination.chmod(stat.S_IWRITE)
    repaired = run(tmp_path, monkeypatch, operation, [header])
    assert not cpp_targets(repaired) and normalized(repaired) != normalized(initial)
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".clean-recovery"))
