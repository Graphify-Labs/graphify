"""REQ-QML-018-AC02/AC03 reference factories retain production refresh and recovery."""
from __future__ import annotations

import os
import stat

import pytest

import graphify.watch as watch
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_adoption_fixture import NATIVE, sources
from tests.test_qt_event_incremental_consumers import run
from tests.test_qt_final_incremental_parity import clean, normalized, unrelated
from tests.test_qt_product_publication import reject, snapshot


REFERENCE = NATIVE.replace("Backend *makeBackend()", "Backend &makeBackend()")


def fixture(root):
    """Only native signature source changes; engine scope and QML clients stay fixed."""
    inputs = sources(root, native=REFERENCE)
    inputs["keep.py"] = "def helper(): return 7\n\ndef retained(): return helper()\n" + "\n".join(
        f"def keep_{index}(): return {index}" for index in range(30))
    for name, content in inputs.items():
        (root / name).write_bytes(content.encode())
    return root / "native.h"


def callable_and_provider(graph, *, accepted=True):
    """Canonical factory remains a source callable independently of supported provider shape."""
    members = [(identity, qt_metadata(data)) for identity, data in graph.nodes(data=True)
               if qt_metadata(data).get("kind") == "member" and qt_metadata(data).get("raw_name") == "makeBackend"]
    assert len(members) == 1 and members[0][1]["generic_target_id"] in graph
    target = members[0][1]["generic_target_id"]
    assert graph.nodes[target]["_callable"] and graph.nodes[target]["label"] == ".makeBackend()"
    bindings = {identity for identity, data in graph.nodes(data=True) if qt_metadata(data).get("kind") == "context_binding"}
    accesses = {identity for identity, data in graph.nodes(data=True) if qt_metadata(data).get("kind") == "context_access"}
    subscriptions = {identity for identity, data in graph.nodes(data=True) if qt_metadata(data).get("kind") == "context_subscription"}
    if accepted:
        assert len(bindings) == 1 and accesses and len(subscriptions) == 2
        assert all(qt_metadata(graph.nodes[identity])["status"] == "resolved" for identity in accesses | subscriptions)
        assert all(qt_metadata(graph.nodes[identity])["provider_class_name"] == "Backend" for identity in bindings)
    else:
        assert not bindings and not accesses and not subscriptions
    return target, bindings | accesses | subscriptions


def parity(graph, root, name):
    """Entire durable source facts and typed edge metadata match cold and reused caches."""
    cache = root / (".clean-" + name)
    assert normalized(graph) == normalized(clean(root, cache)) == normalized(clean(root, cache))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac02_ac03_reference_factory_edits_keep_identity_and_drop_stale_provider_edges(tmp_path, monkeypatch, operation):
    """C++-only pointer/ref edits retain generic identity; unavailable return removes exposure."""
    header = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    target, original_sites = callable_and_provider(initial)
    parity(initial, tmp_path, "initial")
    untouched = unrelated(initial)
    header.write_bytes(NATIVE.encode())
    pointer = run(tmp_path, monkeypatch, operation, [header])
    assert callable_and_provider(pointer)[0] == target
    parity(pointer, tmp_path, "pointer")
    header.write_bytes(REFERENCE.replace("Backend &makeBackend()", "Unknown &makeBackend()").encode())
    removed = run(tmp_path, monkeypatch, operation, [header])
    assert callable_and_provider(removed, accepted=False)[0] == target
    assert all(identity not in removed for identity in original_sites)
    assert not any(data.get("context") in {"qt_context_member", "qt_context_subscription"}
                   for _, _, data in removed.edges(data=True))
    parity(removed, tmp_path, "unavailable")
    header.write_bytes(REFERENCE.encode())
    restored = run(tmp_path, monkeypatch, operation, [header])
    assert normalized(restored) == normalized(initial)
    assert callable_and_provider(restored)[0] == target
    assert unrelated(restored) == untouched
    current = snapshot(tmp_path / "graphify-out")
    assert normalized(run(tmp_path, monkeypatch, operation, [header])) == normalized(restored)
    assert snapshot(tmp_path / "graphify-out") == current


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure", ["syntax", "publication"])
def test_req_qml018_ac02_ac03_reference_admission_failure_preserves_and_repairs(tmp_path, monkeypatch, operation, failure):
    """Malformed reference source or real late publication fault cannot replace prior acceptance."""
    header = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    callable_and_provider(initial)
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    if failure == "syntax":
        header.write_bytes(REFERENCE.replace("Backend &makeBackend()", "Backend &makeBackend( {").encode())
        reject(tmp_path, monkeypatch, operation, header)
    else:
        header.write_bytes(NATIVE.encode())
        replace = watch.os_replace_with_fallback

        def fail_late(source, destination):
            if destination.name == "manifest.json":
                raise OSError("public fixture reference publication failure")
            return replace(source, destination)

        with monkeypatch.context() as fault:
            fault.setattr(watch, "os_replace_with_fallback", fail_late)
            reject(tmp_path, fault, operation, header)
    assert snapshot(output) == before
    header.write_bytes(REFERENCE.encode())
    repaired = run(tmp_path, monkeypatch, operation, [header])
    assert normalized(repaired) == normalized(initial)
    parity(repaired, tmp_path, "repaired")
    accepted = snapshot(output)
    assert normalized(run(tmp_path, monkeypatch, operation, [header])) == normalized(repaired)
    assert snapshot(output) == accepted


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only publication boundary")
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac02_ac03_readonly_reference_edit_retains_products_and_retries(tmp_path, monkeypatch, operation):
    """A genuine OS refusal retains prior graph and sidecars until repaired publication."""
    header = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    target, _ = callable_and_provider(initial)
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    header.write_bytes(NATIVE.encode())
    destination = output / "manifest.json"
    destination.chmod(stat.S_IREAD)
    try:
        reject(tmp_path, monkeypatch, operation, header)
        assert snapshot(output) == before
    finally:
        destination.chmod(stat.S_IWRITE)
    repaired = run(tmp_path, monkeypatch, operation, [header])
    assert callable_and_provider(repaired)[0] == target
    parity(repaired, tmp_path, "readonly-retry")
