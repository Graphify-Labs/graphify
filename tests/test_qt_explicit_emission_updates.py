"""REQ-QML-016-AC04 explicit observations survive native declaration transitions."""
from __future__ import annotations

import os
import stat

import pytest

import graphify.watch as watch
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.test_qt_event_incremental_consumers import run
from tests.test_qt_final_incremental_parity import clean, normalized, unrelated
from tests.test_qt_product_publication import reject, snapshot


HEADER = '''class Backend : public QObject { Q_OBJECT
public: void run();
signals: void missing(int value);
};
'''
BODY = '''#include "events.h"
void Backend::run() {
 QObject *admission_only;
 emit missing(1); Q_EMIT missing(2); missing(3);
}
'''


def fixture(root):
    """Separate declaration and event owners make header-only invalidation observable."""
    (root / "events.h").write_bytes(HEADER.encode())
    (root / "events.cpp").write_bytes(BODY.encode())
    (root / "keep.py").write_text("def helper(): return 7\n\ndef retained(): return helper()\n"
                               + "\n".join(f"def keep_{index}(): return {index}" for index in range(30)), encoding="utf-8")
    return root / "events.h", root / "events.cpp"


def events(graph, *, resolved=True, count=None):
    """Explicit observations retain exact identity; undeclared bare calls remain generic."""
    selected = {identity: qt_metadata(data) for identity, data in graph.nodes(data=True)
                if qt_metadata(data).get("kind") == "emission"}
    assert len(selected) == (count if count is not None else 3 if resolved else 2)
    assert sum(md["explicit_emit"] for md in selected.values()) == (2 if count is None else count)
    for identity, metadata in selected.items():
        assert metadata["owner_id"] in graph and graph.has_edge(metadata["owner_id"], identity)
        assert metadata["status"] == ("resolved" if resolved else "unavailable")
        if resolved:
            assert metadata["target_id"] in graph
            assert qt_metadata(graph.nodes[metadata["target_id"]])["raw_name"] == "missing"
        else:
            assert not metadata["target_id"]
        assert not any(data.get("relation") == "calls" for _, _, data in graph.edges(identity, data=True))
    return selected


def parity(graph, root, name):
    """Cold and warm production facades compare the complete public durable graph."""
    cache = root / (".clean-" + name)
    assert normalized(graph) == normalized(clean(root, cache)) == normalized(clean(root, cache))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml016_ac04_header_rename_remove_restore_and_marker_edits_preserve_observations(tmp_path, monkeypatch, operation):
    """Header-only role removal retains explicit facts and removes their stale edges."""
    header, body = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    before = events(initial)
    explicit = {identity for identity, md in before.items() if md["explicit_emit"]}
    old_target = next(md["target_id"] for md in before.values())
    untouched = unrelated(initial)
    parity(initial, tmp_path, "initial")
    header.write_bytes(HEADER.replace("missing", "revised").encode())
    renamed = run(tmp_path, monkeypatch, operation, [header])
    assert set(events(renamed, resolved=False)) == explicit
    assert old_target not in renamed
    parity(renamed, tmp_path, "rename")

    removed_header = HEADER.replace("signals: void missing(int value);", "")
    header.write_bytes(removed_header.encode())
    removed = run(tmp_path, monkeypatch, operation, [header])
    assert set(events(removed, resolved=False)) == explicit
    parity(removed, tmp_path, "remove")
    header.write_bytes(HEADER.encode())
    restored = run(tmp_path, monkeypatch, operation, [header])
    assert normalized(restored) == normalized(initial)
    assert set(events(restored)) == set(before)

    header.write_bytes(removed_header.encode())
    run(tmp_path, monkeypatch, operation, [header])
    body.write_bytes(BODY.replace("emit missing(1);", "missing(1);").encode())
    one = run(tmp_path, monkeypatch, operation, [body])
    events(one, resolved=False, count=1)
    parity(one, tmp_path, "one")
    body.write_bytes(BODY.replace("emit ", "").replace("Q_EMIT ", "").encode())
    none = run(tmp_path, monkeypatch, operation, [body])
    events(none, resolved=False, count=0)
    assert all(identity not in none for identity in explicit)
    parity(none, tmp_path, "none")
    assert unrelated(none) == untouched
    accepted = snapshot(tmp_path / "graphify-out")
    assert normalized(run(tmp_path, monkeypatch, operation, [header, body])) == normalized(none)
    assert snapshot(tmp_path / "graphify-out") == accepted


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure", ["syntax", "publication"])
def test_req_qml016_ac04_failed_explicit_refresh_retains_products_and_retries(tmp_path, monkeypatch, operation, failure):
    """Actual extraction or late publication failure retains the accepted cohort."""
    header, _ = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    explicit = {identity for identity, md in events(initial).items() if md["explicit_emit"]}
    output = tmp_path / "graphify-out"
    accepted = snapshot(output)
    if failure == "syntax":
        header.write_bytes(b"class Backend { Q_OBJECT signals: void missing( ;\n")
        reject(tmp_path, monkeypatch, operation, header)
    else:
        header.write_bytes(HEADER.replace("missing", "revised").encode())
        replace = watch.os_replace_with_fallback

        def fail_late(source, destination):
            if destination.name == "manifest.json":
                raise OSError("public fixture publication fault")
            return replace(source, destination)

        with monkeypatch.context() as fault:
            fault.setattr(watch, "os_replace_with_fallback", fail_late)
            reject(tmp_path, fault, operation, header)
    assert snapshot(output) == accepted
    header.write_bytes(HEADER.replace("missing", "revised").encode())
    recovered = run(tmp_path, monkeypatch, operation, [header])
    assert set(events(recovered, resolved=False)) == explicit
    parity(recovered, tmp_path, "recovered")
    current = snapshot(output)
    assert normalized(run(tmp_path, monkeypatch, operation, [header])) == normalized(recovered)
    assert snapshot(output) == current


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only publication boundary")
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml016_ac04_readonly_declaration_removal_preserves_graph_and_explicit_retry(tmp_path, monkeypatch, operation):
    """A real OS denial leaves prior evidence until a corrected repeat publication."""
    header, _ = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    explicit = {identity for identity, md in events(initial).items() if md["explicit_emit"]}
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    header.write_bytes(HEADER.replace("signals: void missing(int value);", "").encode())
    target = output / "manifest.json"
    target.chmod(stat.S_IREAD)
    try:
        reject(tmp_path, monkeypatch, operation, header)
        assert snapshot(output) == before
    finally:
        target.chmod(stat.S_IWRITE)
    recovered = run(tmp_path, monkeypatch, operation, [header])
    assert set(events(recovered, resolved=False)) == explicit
    parity(recovered, tmp_path, "readonly-retry")
