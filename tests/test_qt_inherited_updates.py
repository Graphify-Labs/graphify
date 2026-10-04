"""REQ-QML-016-AC04 inherited endpoint refresh, retention and recovery."""
from __future__ import annotations

import os
import stat

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.test_qt_event_incremental_consumers import run
from tests.test_qt_final_incremental_parity import clean, normalized, unrelated
from tests.test_qt_product_publication import reject, snapshot


HEADER = '''class Grand : public QObject { Q_OBJECT
signals: void changed(int value);
public slots: void accept(int value) {}
};
class Middle : public Grand { Q_OBJECT };
class Child : public Middle { Q_OBJECT public: void run(); };
'''
BODY = '''#include "events.h"
void Child::run() { emit changed(1); }
void wire(Child *sender, Child *receiver) {
 QObject::connect(sender, &Child::changed, receiver, &Child::accept);
 QObject::connect(sender, SIGNAL(changed(int)), receiver, SLOT(accept(int)));
}
'''


def fixture(root):
    """Header declarations own targets; unchanged implementation owns event sites."""
    (root / "events.h").write_bytes(HEADER.encode())
    (root / "events.cpp").write_bytes(BODY.encode())
    (root / "keep.py").write_text("def helper(): return 7\n\ndef retained(): return helper()\n"
                               + "\n".join(f"def keep_{index}(): return {index}" for index in range(20)), encoding="utf-8")
    return root / "events.h", root / "events.cpp"


def endpoints(graph, expected: str | None = "changed", event_count=3):
    """Connections and emissions preserve explicit roles and source declaring class."""
    events = {identity: qt_metadata(data) for identity, data in graph.nodes(data=True)
              if qt_metadata(data).get("kind") in {"connect", "emission"}}
    assert len(events) == event_count
    for identity, metadata in events.items():
        if expected is None:
            assert metadata["status"] != "resolved"
            assert not metadata.get("signal_target_id") and not metadata.get("target_id")
        else:
            assert metadata["status"] == "resolved"
            target = metadata.get("signal_target_id") or metadata.get("target_id")
            declaration = qt_metadata(graph.nodes[target])
            assert declaration["class_name"] == "Grand" and declaration["raw_name"] == expected
            assert graph.nodes[target]["source_file"] == "events.h"
        assert not any(data.get("relation") == "calls" for _, _, data in graph.edges(identity, data=True))
    return events


def parity(graph, root, key):
    """A fresh and a reused AST cache must produce the entire same public graph."""
    cache = root / (".clean-" + key)
    assert normalized(graph) == normalized(clean(root, cache)) == normalized(clean(root, cache))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml016_ac04_header_signal_base_and_site_edits_match_full_cold_warm(tmp_path, monkeypatch, operation):
    """Header-only edits rejoin existing sites; removal eliminates stale endpoint facts."""
    header, body = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    endpoints(initial)
    parity(initial, tmp_path, "initial")
    untouched = unrelated(initial)
    old_signal = next(md.get("signal_target_id") or md["target_id"] for md in endpoints(initial).values())

    header.write_bytes(HEADER.replace("changed", "revised").encode())
    changed = run(tmp_path, monkeypatch, operation, [header])
    # Current source admission removes an explicit emission whose name no
    # longer appears in the signal inventory; INC-QML-28 owns its correction.
    # The existing connection syntax remains observed and cannot retain targets.
    endpoints(changed, expected=None, event_count=2)
    parity(changed, tmp_path, "header")
    assert old_signal not in changed
    body.write_bytes(BODY.replace("changed", "revised").encode())
    repaired = run(tmp_path, monkeypatch, operation, [body])
    endpoints(repaired, expected="revised")
    parity(repaired, tmp_path, "repair")

    header.write_bytes(HEADER.replace("changed", "revised").replace("public Grand", "public Missing").encode())
    disconnected = run(tmp_path, monkeypatch, operation, [header])
    endpoints(disconnected, expected=None)
    parity(disconnected, tmp_path, "base")
    header.write_bytes(HEADER.replace("changed", "revised").encode())
    restored = run(tmp_path, monkeypatch, operation, [header])
    assert normalized(restored) == normalized(repaired)

    # Inheritance access is a source fact and header-only invalidation input.
    # Nonpublic bases reject external C++ pointers while legacy meta lookup
    # retains its independently admitted declaration identity.
    header.write_bytes(HEADER.replace("changed", "revised").replace("public Grand", "private Grand").encode())
    restricted = run(tmp_path, monkeypatch, operation, [header])
    connections = [qt_metadata(data) for _, data in restricted.nodes(data=True)
                   if qt_metadata(data).get("kind") == "connect"]
    modern = next(md for md in connections if md["signal"]["form"] == "member_pointer")
    legacy = next(md for md in connections if md["signal"]["form"] == "legacy")
    assert modern["status"] == "unavailable" and modern["signal_reason"] == "inheritance_access_unavailable"
    assert legacy["status"] == "resolved"
    parity(restricted, tmp_path, "access")
    header.write_bytes(HEADER.replace("changed", "revised").encode())
    assert normalized(run(tmp_path, monkeypatch, operation, [header])) == normalized(repaired)

    removed_text = BODY.replace("emit changed(1);", "")
    removed_text = "\n".join(line for line in removed_text.splitlines() if "QObject::connect" not in line)
    body.write_bytes(removed_text.encode())
    removed = run(tmp_path, monkeypatch, operation, [body])
    parity(removed, tmp_path, "removed")
    assert all(identity not in removed for identity in endpoints(restored, expected="revised"))
    assert not any(qt_metadata(data).get("kind") == "event_endpoint" for _, data in removed.nodes(data=True))
    assert unrelated(removed) == untouched
    current = snapshot(tmp_path / "graphify-out")
    assert normalized(run(tmp_path, monkeypatch, operation, [header, body])) == normalized(removed)
    assert snapshot(tmp_path / "graphify-out") == current


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml016_ac04_malformed_ancestor_preserves_products_then_retries(tmp_path, monkeypatch, operation):
    """Rejected native source cannot advance durable endpoint evidence or sidecars."""
    header, _ = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    endpoints(initial)
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    header.write_bytes(b"class Grand : public QObject { Q_OBJECT signals: void changed( ;\n")
    reject(tmp_path, monkeypatch, operation, header)
    assert snapshot(output) == before
    header.write_bytes(HEADER.encode())
    recovered = run(tmp_path, monkeypatch, operation, [header])
    assert normalized(recovered) == normalized(initial)
    parity(recovered, tmp_path, "syntax-retry")


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only publication boundary")
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml016_ac04_readonly_ancestor_refresh_preserves_cohort_and_retry(tmp_path, monkeypatch, operation):
    """A real late sidecar denial retains graph/root/manifest/Qt stamp before recovery."""
    header, _ = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out"
    before = snapshot(output)
    header.write_bytes(HEADER.replace("changed", "revised").encode())
    target = output / "manifest.json"
    target.chmod(stat.S_IREAD)
    try:
        reject(tmp_path, monkeypatch, operation, header)
        assert snapshot(output) == before
    finally:
        target.chmod(stat.S_IWRITE)
    recovered = run(tmp_path, monkeypatch, operation, [header])
    endpoints(recovered, expected=None, event_count=2)
    assert normalized(recovered) != normalized(initial)
    parity(recovered, tmp_path, "publication-retry")
    accepted = snapshot(output)
    assert normalized(run(tmp_path, monkeypatch, operation, [header])) == normalized(recovered)
    assert snapshot(output) == accepted
