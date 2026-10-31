"""QML-016-AC04 event edit/removal parity through real update/watch persistence."""
from __future__ import annotations

from collections import Counter

import pytest

import graphify.__main__ as entrypoint
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, normalized, published
from tests.test_qt_signals_slots import SOURCE


NATIVE = SOURCE.replace(
    "private slots:", "public slots:\n void active(int value) {}\nprivate slots:"
).replace("\n}\n", "\n receiver->active(5);\n}\n")
UNCHANGED = '''class Heartbeat : public QObject { Q_OBJECT
signals: void beat();
public: void tick() { emit beat(); }
};
'''
EVENT_KINDS = {"emission", "connect", "disconnect"}


def project(root):
    sources = {
        "events.cpp": NATIVE,
        "unchanged.cpp": UNCHANGED,
        # Keep ordinary unrelated declarations and a real call dependency while
        # removing native events; a tiny-graph shrink guard is not the subject.
        "keep.py": "def helper(): return 7\n\ndef retained(): return helper()\n"
                   + "\n".join(f"def keep_{index}(): return {index}" for index in range(20)),
    }
    for name, text in sources.items():
        (root / name).write_text(text, encoding="utf-8", newline="")
    return root / "events.cpp"


def run(root, monkeypatch, operation, changes=None):
    if operation == "manual":
        # Production opt-out isolates installed-skill maintenance, without
        # replacing any CLI, update, parser, resolver or persistence function.
        monkeypatch.setenv("GRAPHIFY_NO_AUTO_REFRESH", "1")
        monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
        monkeypatch.setattr(entrypoint.sys, "argv", ["graphify", "update", str(root), "--no-cluster"])
        entrypoint.main()
    else:
        assert _rebuild_code(root, changed_paths=changes, no_cluster=True)
    return published(root)


def source_facts(graph, files):
    """Retain every public field and logical typed edge, including source spans."""
    nodes, edges = normalized(graph)
    ids = {identity for identity, data in graph.nodes(data=True) if data.get("source_file") in files}
    return ({identity: nodes[identity] for identity in ids},
            Counter({edge: count for edge, count in edges.items() if edge[0] in ids and edge[1] in ids}))


def event_sites(graph, file="events.cpp"):
    return {identity: metadata for identity, data in graph.nodes(data=True)
            if data.get("source_file") == file and (metadata := qt_metadata(data)).get("kind") in EVENT_KINDS}


def assert_distinct_mechanisms(graph, expected):
    sites = event_sites(graph)
    assert Counter(metadata["kind"] for metadata in sites.values()) == Counter(expected)
    assert all(metadata["status"] == "resolved" for metadata in sites.values())
    assert all(metadata["runtime_delivery"] == "unverified" for metadata in sites.values()
               if metadata["kind"] in {"connect", "disconnect"})
    # Event declarations reference source endpoints. They never manufacture a
    # signal-to-receiver call or replace the direct public-slot invocation.
    assert not any(data.get("_src", source) in sites and data.get("relation") == "calls"
                   for source, _, data in graph.edges(data=True))
    members = [metadata for _, data in graph.nodes(data=True)
               if data.get("source_file") == "events.cpp" and (metadata := qt_metadata(data)).get("kind") == "member"
               and metadata.get("raw_name") == "active"]
    assert len(members) == 1 and members[0]["roles"] == ["slot"]
    direct_target = members[0]["generic_target_id"]
    # Ordinary untyped calls in a default undirected graph have no serialized
    # logical-direction promise. Assert their actual canonical endpoint pair.
    direct = [(target if source == direct_target else source, data) for source, target, data in graph.edges(data=True)
              if direct_target in {source, target} and data.get("relation") == "calls"]
    assert len(direct) == 1 and direct[0][0] not in sites
    assert graph.nodes[direct[0][0]]["label"] == "wire()"
    assert direct[0][1]["source_file"] == "events.cpp"
    return sites


def compare_rebuild(graph, root, cache):
    cold = clean(root, cache)
    warm = clean(root, cache)
    assert normalized(graph) == normalized(cold) == normalized(warm)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_qml016_ac04_event_mutation_and_removal_match_clean_rebuild_without_delivery_calls(
    tmp_path, monkeypatch, operation
):
    """Success: changed source facts; state transition: no stale event endpoints.

    Acceptance covers complete cold/warm parity and persistence, unchanged Qt
    and Python source retention, and direct-slot/event relationship separation.
    """
    source = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    compare_rebuild(initial, tmp_path, tmp_path / ".initial-clean")
    initial_sites = assert_distinct_mechanisms(initial, {"emission": 3, "connect": 3, "disconnect": 1})
    untouched = source_facts(initial, {"unchanged.cpp", "keep.py"})
    assert untouched[0] and untouched[1] and len(event_sites(initial, "unchanged.cpp")) == 1

    edited_text = NATIVE.replace("emit changed(1);", "Q_EMIT changed(11);").replace(
        "Q_EMIT changed(2);", "changed(12);"
    ).replace("Qt::QueuedConnection", "Qt::DirectConnection")
    source.write_text(edited_text, encoding="utf-8", newline="")
    edited = run(tmp_path, monkeypatch, operation, [source])
    compare_rebuild(edited, tmp_path, tmp_path / ".edited-clean")
    edited_sites = assert_distinct_mechanisms(edited, {"emission": 3, "connect": 3, "disconnect": 1})
    assert sum(metadata["explicit_emit"] for metadata in edited_sites.values() if metadata["kind"] == "emission") == 1
    assert any(metadata.get("declared_type") == "DirectConnection" for metadata in edited_sites.values())
    assert not any(metadata.get("declared_type") == "QueuedConnection" for metadata in edited_sites.values())
    assert normalized(edited) != normalized(initial)
    assert source_facts(edited, {"unchanged.cpp", "keep.py"}) == untouched
    assert set(initial_sites) - set(edited_sites)
    assert all(identity not in edited for identity in set(initial_sites) - set(edited_sites))

    removed_text = edited_text.replace("Q_EMIT changed(11); changed(12); changed(3);", "")
    removed_text = "\n".join(line for line in removed_text.splitlines()
                             if "QObject::connect(" not in line and "QObject::disconnect(" not in line) + "\n"
    source.write_text(removed_text, encoding="utf-8", newline="")
    removed = run(tmp_path, monkeypatch, operation, [source])
    compare_rebuild(removed, tmp_path, tmp_path / ".removed-clean")
    assert_distinct_mechanisms(removed, {})
    assert all(identity not in removed for identity in edited_sites)
    assert not any(data.get("source_file") == "events.cpp" and qt_metadata(data).get("kind") == "event_endpoint"
                   for _, data in removed.nodes(data=True))
    assert not any(data.get("source_file") == "events.cpp" and data.get("context", "").startswith(
        ("qt_signal_emit", "qt_connect_", "qt_disconnect_")
    ) for _, _, data in removed.edges(data=True))
    assert source_facts(removed, {"unchanged.cpp", "keep.py"}) == untouched
    assert len(event_sites(removed, "unchanged.cpp")) == 1
