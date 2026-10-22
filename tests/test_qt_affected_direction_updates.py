"""INC-QML-30: affected direction across real cold/manual/watch publication."""
from __future__ import annotations

import pytest

from graphify.affected import affected_nodes
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_adoption_fixture import sources
from tests.qt_analysis_helpers import analysis
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated


def native_dependency(graph):
    """The accepted provider function, occurrence and call-site location form one consumer contract."""
    candidates = [(identity, data) for identity, data in graph.nodes(data=True)
                  if qt_metadata(data).get("kind") == "context_access"
                  and qt_metadata(data).get("endpoint_proof", {}).get("kind") == "function"]
    assert len(candidates) == 1
    identity, data = candidates[0]
    target = qt_metadata(data)["endpoint_proof"]["canonical_target_id"]
    hits = {hit.node_id: hit for hit in affected_nodes(graph, target, relations=["calls"], depth=1)}
    assert identity in hits and hits[identity].depth == 1
    assert (hits[identity].via_file, hits[identity].via_location) == ("Main.qml", data["source_location"])
    return identity, target


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("expression", ["factory->makeBackend()", "backend"])
def test_native_affected_direction_cold_warm_update_removal_recovery_and_repeat(tmp_path, monkeypatch,
                                                                            operation, expression):
    """A real QML edit retires its incoming access; repair restores cold-equivalent affected results."""
    corpus = sources(tmp_path, expression)
    corpus["keep.py"] = "def helper(): return 7\n\ndef retained(): return helper()\n"
    analysis(tmp_path, corpus)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cold = clean(tmp_path, tmp_path / ".cold-cache")
    assert normalized(clean(tmp_path, tmp_path / ".cold-cache")) == normalized(cold)
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(cold)
    access, target = native_dependency(initial)
    assert native_dependency(cold) == (access, target)
    kept = unrelated(initial)

    # Keep the native declaration while removing this actual QML member use.
    # The consumer must not report an access whose old source occurrence retired.
    qml = tmp_path / "Main.qml"
    original = qml.read_bytes()
    qml.write_bytes(original.replace(b"backend.service.refresh()", b"backend.service.missing()"))
    removed = run(tmp_path, monkeypatch, operation, [qml])
    assert target in removed and access not in removed
    assert not affected_nodes(removed, target, relations=["calls"], depth=1)
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    assert unrelated(removed) == kept

    # Recovery and a no-change update exercise the durable production cohort;
    # querying affected nodes itself must never rewrite the published graph.
    qml.write_bytes(original)
    repaired = run(tmp_path, monkeypatch, operation, [qml])
    assert native_dependency(repaired) == (access, target)
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".repaired-cache"))
    output = tmp_path / "graphify-out/graph.json"
    before = output.read_bytes()
    repeated = run(tmp_path, monkeypatch, operation, [])
    assert native_dependency(repeated) == (access, target)
    assert output.read_bytes() == before and unrelated(repeated) == kept
