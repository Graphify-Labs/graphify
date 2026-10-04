"""REQ-QML-008-AC02 retain source context without guessing native owners."""
import copy
import json
from collections import Counter

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_source_containment import attach_qt_file_sites
from tests.qt_analysis_helpers import analysis, sites


HEADER = """class Backend : public QObject {
 Q_OBJECT
public:
 Backend();
 Backend(int count);
signals:
 void ready();
};
"""
CPP = '#include "backend.hpp"\nBackend::Backend() : Backend(0) { emit ready(); }\n'


def corpus(root):
    """Duplicate equivalent constructor bodies cannot prove one source callable owner."""
    cpp = CPP + CPP.split('\n', 1)[1]
    result = analysis(root, {"backend.hpp": HEADER, "backend.cpp": cpp})
    unknown = [node for node in sites(result, "member") + sites(result, "emission")
               if not qt_metadata(node)["owner_id"]]
    assert unknown
    return result, unknown


def test_req_qml008_ac02_unknown_native_owner_keeps_actual_file_context_after_reload(tmp_path):
    """The production facade/build/writer retain truthful source context and unknown roles."""
    # Equivalent duplicate definitions remain ambiguous after exact overload
    # admission; a source file link cannot turn them into accepted native owners.
    cpp = CPP + CPP.split('\n', 1)[1]
    result = analysis(tmp_path, {"backend.hpp": HEADER, "backend.cpp": cpp})
    unknown = [node for node in sites(result, "member") + sites(result, "emission")
               if not qt_metadata(node)["owner_id"]]
    assert unknown
    for site in unknown:
        assert any(edge["target"] == site["id"] and edge["context"] == "qt_source_file"
                   and edge["confidence"] == "EXTRACTED" for edge in result["edges"])
        assert qt_metadata(site)["owner_id"] == ""
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    reloaded = build_from_json(json.loads(output.read_text(encoding="utf-8")), root=tmp_path)
    assert all(reloaded.degree(site["id"]) for site in unknown)
    assert all(qt_metadata(reloaded.nodes[site["id"]])["owner_id"] == "" for site in unknown)
    assert all(qt_metadata(site)["status"] != "resolved" for site in unknown
               if qt_metadata(site)["kind"] == "emission")


@pytest.mark.parametrize("corruption", [None, "missing", "foreign", "outside_root", "duplicate", "callable", "class", "non_ast", "unmarked", "fresh_unmarked"])
def test_req_qml008_ac02_file_context_requires_unique_actual_file_role(tmp_path, corruption):
    """Borrowed file identities cannot be guessed from a label or fabricated path ID."""
    result, unknown = corpus(tmp_path)
    nodes = copy.deepcopy(result["nodes"])
    file = next(node for node in nodes if node.get("label") == "backend.cpp")
    if corruption == "missing":
        nodes.remove(file)
    elif corruption == "foreign":
        file["source_file"] = "outside.cpp"
    elif corruption == "outside_root":
        file["source_file"] = "../backend.cpp"
    elif corruption == "duplicate":
        nodes.append({**file, "id": file["id"] + "_competing"})
    elif corruption == "callable":
        file["_callable"] = True
    elif corruption == "class":
        file["_callable_class"] = True
    elif corruption == "non_ast":
        file["_origin"] = "llm"
    elif corruption in {"unmarked", "fresh_unmarked"}:
        file.pop("_origin", None)
    before = copy.deepcopy(nodes)
    fresh = {"nodes": copy.deepcopy(unknown), "edges": []}
    metadata = copy.deepcopy(fresh["nodes"])
    fresh_ids = {file["id"]} if corruption == "fresh_unmarked" else ()
    added = attach_qt_file_sites({tmp_path / "backend.cpp": fresh}, nodes, [], root=tmp_path,
                                fresh_ast_ids=fresh_ids)
    assert nodes == before and fresh["nodes"] == metadata
    assert bool(added) == (corruption in {None, "fresh_unmarked"})
    assert not attach_qt_file_sites({tmp_path / "backend.cpp": fresh}, nodes, added, root=tmp_path)
    for edge in added:
        assert edge["source"] == file["id"] and edge["context"] == "qt_source_file"
        assert edge["_src"] == edge["source"] and edge["_tgt"] == edge["target"]


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac04_unowned_file_sites_refresh_and_remove_stale_links(tmp_path, monkeypatch, operation):
    """Actual full/warm/update paths preserve Qt file links and evict removed sites.

    Equivalent duplicate definitions keep visible source occurrences without a
    guessed callable. Compare all nodes and every native edge; exact accepted
    overload tests separately establish complete generic graph parity.
    """
    from tests.test_qt_final_incremental_parity import clean, endpoints, normalized, run, semantic

    def native_snapshot(graph):
        nodes, _ = normalized(graph)
        native = Counter((*endpoints(graph, source, target, data),
                          json.dumps(semantic(data), sort_keys=True, ensure_ascii=False))
                         for source, target, data in graph.edges(data=True) if qt_metadata(data))
        return nodes, native

    corpus(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cold = clean(tmp_path, tmp_path / ".cold-cache")
    assert native_snapshot(clean(tmp_path, tmp_path / ".cold-cache")) == native_snapshot(cold)
    initial = run(tmp_path, monkeypatch, operation)
    assert native_snapshot(initial) == native_snapshot(cold)
    retained = {identity for identity, data in initial.nodes(data=True)
                if qt_metadata(data).get("kind") == "emission" and not qt_metadata(data)["owner_id"]}
    assert retained and all(initial.degree(identity) for identity in retained)
    path = tmp_path / "backend.cpp"
    path.write_bytes(path.read_bytes().replace(b"emit ready();", b""))
    changed = run(tmp_path, monkeypatch, operation, [path])
    assert not retained.intersection(changed)
    assert native_snapshot(changed) == native_snapshot(clean(tmp_path, tmp_path / ".changed-cache"))
    assert native_snapshot(run(tmp_path, monkeypatch, operation, [])) == native_snapshot(changed)
