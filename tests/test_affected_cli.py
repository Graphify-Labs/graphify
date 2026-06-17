from __future__ import annotations

import graphify.__main__ as mainmod

_NODES = [
    {"id": "target", "label": "Foo", "source_file": "pkg/foo.py", "source_location": "L1", "file_type": "code"},
    {"id": "caller", "label": "X()", "source_file": "app.py", "source_location": "L4", "file_type": "code"},
    {"id": "barrel", "label": "__init__.py", "source_file": "pkg/__init__.py", "file_type": "code"},
    {"id": "consumer", "label": "app.py", "source_file": "app.py", "file_type": "code"},
]
_LINKS = [
    {"source": "caller", "target": "target", "relation": "calls", "context": "call", "confidence": "EXTRACTED"},
    {"source": "barrel", "target": "target", "relation": "re_exports", "context": "export", "confidence": "EXTRACTED"},
    {"source": "consumer", "target": "target", "relation": "imports", "context": "import", "confidence": "EXTRACTED"},
]


def test_affected_cli_reverse_traverses_impact_edges(monkeypatch, tmp_path, capsys, seed_graph):
    seed_graph(tmp_path, _NODES, _LINKS)
    graph_path = tmp_path / "graph.json"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "affected", "Foo", "--graph", str(graph_path)],
    )

    mainmod.main()

    out = capsys.readouterr().out
    assert "Affected nodes for Foo" in out
    assert "X()" in out
    assert "calls" in out
    assert "__init__.py" in out
    assert "re_exports" in out
    assert "app.py" in out
    assert "imports" in out


def test_affected_cli_relation_filter_limits_reverse_traversal(monkeypatch, tmp_path, capsys, seed_graph):
    seed_graph(tmp_path, _NODES, _LINKS)
    graph_path = tmp_path / "graph.json"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "affected", "Foo", "--relation", "calls", "--graph", str(graph_path)],
    )

    mainmod.main()

    out = capsys.readouterr().out
    assert "Relations: calls" in out
    assert "X()" in out
    assert "__init__.py" not in out
