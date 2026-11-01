"""REQ-QML-008/016/017: changed qualified ownership survives real updates."""
import base64

import pytest

from graphify.affected import affected_nodes, load_graph
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


HEADER = '''class Base : public QWidget { Q_OBJECT };
namespace Public { class Base : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Service)
public: Q_INVOKABLE int fetch(); void run(); signals: void changed(); }; }
'''
IMPLEMENTATION = '#include "backend.h"\nint Public::Base::fetch() { return 2; }\nvoid Public::Base::run() { emit changed(); }\n'


def fixture(root):
    sources = {
        "backend.h": HEADER, "backend.cpp": IMPLEMENTATION,
        "Main.qml": 'import Public.Tools 1.0\nService { function refresh() { fetch() } }',
        "CMakeLists.txt": 'qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.h backend.cpp)',
        "keep.py": 'def helper(): return 7\n\ndef retained(): return helper()\n',
    }
    for name, source in sources.items():
        (root / name).write_text(source, encoding="utf-8", newline="")


def owners(graph):
    return {base64.b64decode(data["metadata"]["cpp_class"]["qualified_name_b64"]).decode(): identity
            for identity, data in graph.nodes(data=True) if data.get("metadata", {}).get("cpp_class")}


def evidence(graph):
    emissions = [(identity, qt_metadata(data)) for identity, data in graph.nodes(data=True)
                 if qt_metadata(data).get("kind") == "emission"]
    assert len(emissions) == 1 and emissions[0][1]["status"] == "resolved"
    identity, metadata = emissions[0]
    assert metadata["owner_id"] in graph
    assert any(data.get("_src", source) == identity and data.get("context") == "qt_signal_emit"
               for source, _, data in graph.edges(data=True))
    calls = [(source, target, data) for source, target, data in graph.edges(data=True)
             if data.get("relation") == "calls" and qt_metadata(data).get("native_endpoint")]
    assert calls
    return identity, metadata


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml017_ac04_qualified_owner_edits_match_cold_warm_updates_and_consumers(tmp_path, monkeypatch, operation):
    fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    before = owners(initial)
    assert set(before) == {"Base", "Public::Base"}
    evidence(initial)
    assert normalized(initial) == normalized(clean(tmp_path, tmp_path / ".cold"))
    (tmp_path / "backend.h").write_text(HEADER.replace("namespace Public", "namespace PUBLIC"), encoding="utf-8")
    (tmp_path / "backend.cpp").write_text(IMPLEMENTATION.replace("Public::", "PUBLIC::"), encoding="utf-8")
    updated = run(tmp_path, monkeypatch, operation, [tmp_path / "backend.h", tmp_path / "backend.cpp"])
    after = owners(updated)
    assert set(after) == {"Base", "PUBLIC::Base"}
    assert after["Base"] == before["Base"] and after["PUBLIC::Base"] != before["Public::Base"]
    assert before["Public::Base"] not in updated
    identity, metadata = evidence(updated)
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".changed"))
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".changed"))
    assert unrelated(initial) == unrelated(updated)
    consumer = load_graph(tmp_path / "graphify-out/graph.json")
    assert identity in {hit.node_id for hit in affected_nodes(consumer, metadata["target_id"], relations=["uses"], depth=1)}
    unchanged = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(updated)
    assert products(tmp_path) == unchanged
