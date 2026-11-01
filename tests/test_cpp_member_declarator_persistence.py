"""REQ-QML-022-AC02/AC06: declarator facts survive real caches and durable graphs."""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.paths import load_node_link_graph
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


HEADER = "struct Value {}; class Owner { public: Owner(); ~Owner(); Value &borrowed; void (*callback)(int); };\n"


def fixture(root):
    """A C++-only edit must preserve both member provenance and another language."""
    path = root / "members.hpp"
    path.write_text(HEADER, encoding="utf-8")
    (root / "keep.py").write_text("def helper(): return 7\n\ndef retained(): return helper()\n", encoding="utf-8")
    return path


def declaration_nodes(graph):
    return {identity: data for identity, data in graph.nodes(data=True)
            if data.get("metadata", {}).get("cpp_declarator")}


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac02_cache_and_serialized_reload_preserve_exact_declarators(tmp_path, directed):
    """The actual facade cache, builder, sanitation, JSON writer and loader retain facts."""
    path = fixture(tmp_path)
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert result == extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    graph = build_from_json(result, root=tmp_path, directed=directed)
    expected = declaration_nodes(graph)
    assert {data["label"] for data in expected.values()} >= {"borrowed", "callback", ".~Owner()"}
    output = tmp_path / "result.json"
    assert to_json(graph, {}, str(output))
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    for identity, original in expected.items():
        assert restored.nodes[identity]["metadata"]["cpp_declarator"] == original["metadata"]["cpp_declarator"]
        if original["metadata"]["cpp_declarator"]["kind"] == "field":
            assert not restored.nodes[identity].get("_callable")
    assert not any(data.get("metadata", {}).get("qt_cpp") for data in expected.values())


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_actual_member_updates_remove_stale_facts_and_match_full_scan(tmp_path, monkeypatch, operation):
    """Real production updates remove renamed declarations and persist exactly the cold result."""
    path = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    old = {identity for identity, data in declaration_nodes(initial).items() if data["label"] == "borrowed"}
    assert len(old) == 1
    path.write_text(HEADER.replace("borrowed", "changed"), encoding="utf-8")
    updated = run(tmp_path, monkeypatch, operation, [path])
    assert old.isdisjoint(updated)
    assert any(data["label"] == "changed" for data in declaration_nodes(updated).values())
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".warm"))
    assert unrelated(initial) == unrelated(updated)
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(updated)
    assert products(tmp_path) == before


def test_req_qml022_ac06_failed_replacement_retains_prior_declarators_and_recovers(tmp_path, monkeypatch):
    """An injected OS replacement error follows real serialization/temp-file work and preserves prior bytes."""
    path = fixture(tmp_path)
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    before = output.read_bytes()
    assert any(data["label"] == "borrowed" for data in declaration_nodes(graph).values())
    path.write_text(HEADER.replace("borrowed", "changed"), encoding="utf-8")
    candidate = build_from_json(extract([path], root=tmp_path, cache_root=tmp_path, parallel=False), root=tmp_path)
    replace = os.replace

    def reject(source, destination):
        if Path(destination).resolve() == output.resolve():
            raise OSError(errno.EIO, "simulated device failure")
        return replace(source, destination)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "replace", reject)
        with pytest.raises(OSError, match="simulated device failure"):
            to_json(candidate, {}, str(output), force=True)
    assert output.read_bytes() == before
    assert not list(tmp_path.glob(".gfy-*.tmp"))
    assert to_json(candidate, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert any(data["label"] == "changed" for data in declaration_nodes(restored).values())
    assert not any(data["label"] == "borrowed" for data in declaration_nodes(restored).values())
