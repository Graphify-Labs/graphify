"""INC-QML-49: upstream qualified endpoint identity retains real Qt/QML paths."""
from __future__ import annotations

import json

import pytest

import graphify.__main__ as mainmod
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.test_qt_qml_integration import corpus


def native_path(root, directed=False):
    """Actual registered C++ source supplies a native target and typed QML call."""
    result = corpus(root)
    call = next(edge for edge in result["edges"] if edge.get("context") == "qml_js_call")
    source, target = call["source"], call["target"]
    assert qt_metadata(call)["native_endpoint"]["canonical_target_id"] == target
    graph = build_from_json(result, root=root, directed=directed)
    source_query = f'{graph.nodes[source]["source_file"]}::{graph.nodes[source]["label"]}'
    target_query = f'{graph.nodes[target]["source_file"]}::{graph.nodes[target]["label"]}'
    # A same-named declaration in another file may never steal the explicit
    # native query or add a route unrelated to the accepted registration.
    graph.add_node("decoy", label=graph.nodes[target]["label"], source_file="other.hpp", file_type="code")
    path = root / "graph.json"
    assert to_json(graph, {}, str(path), built_at_commit="fixed")
    return path, source, target, source_query, target_query


def run_path(monkeypatch, path, source, target, capsys, *flags):
    """Exercise the public CLI; only its unrelated version notification is isolated."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "path", source, target, "--graph", str(path), *flags])
    try:
        mainmod.main()
    except SystemExit as ended:
        code = ended.code
    else:
        code = 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml_010_ac03_qualified_native_path_preserves_direction(tmp_path, monkeypatch, capsys, directed):
    """Qualified source names select the real QML-to-C++ edge through either graph mode."""
    path, source, target, source_query, target_query = native_path(tmp_path, directed)
    accepted = path.read_bytes()
    code, output, error = run_path(monkeypatch, path, source_query, target_query, capsys)
    assert code == 0 and not error
    assert "Shortest path (1 hops):" in output and "--calls [INFERRED]-->" in output
    assert "qml_js_call" in output and "backend.hpp" in output
    code, output, error = run_path(monkeypatch, path, target_query, source_query, capsys)
    assert code == 0 and not error and "No directed path found" in output
    code, output, error = run_path(monkeypatch, path, target_query, source_query, capsys, "--undirected")
    assert code == 0 and not error and "<--calls [INFERRED]--" in output
    code, output, error = run_path(monkeypatch, path, source, target, capsys)
    assert code == 0 and not error and "Shortest path (1 hops):" in output
    assert path.read_bytes() == accepted


def test_req_qml_018_ac04_duplicate_qualified_target_refuses_guess(tmp_path, monkeypatch, capsys):
    """Two declarations in the same qualified file reject selection; exact ID still works."""
    path, source, target, source_query, target_query = native_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    original = next(node for node in payload["nodes"] if node["id"] == target)
    payload["nodes"].append({**original, "id": "same_file_duplicate"})
    path.write_text(json.dumps(payload), encoding="utf-8")
    accepted = path.read_bytes()
    code, output, error = run_path(monkeypatch, path, source_query, target_query, capsys)
    assert code == 1 and not output and "ambiguous" in error.lower()
    assert target in error and "same_file_duplicate" in error
    code, output, error = run_path(monkeypatch, path, source, target, capsys)
    assert code == 0 and not error and "Shortest path (1 hops):" in output
    assert path.read_bytes() == accepted
