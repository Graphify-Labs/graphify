"""Regression tests for `graphify path` arrow direction (#849)."""
from __future__ import annotations
import graphify.__main__ as mainmod

_NODES = [
    {"id": "create_patch", "label": "createPatchHandler()",
     "source_file": "server/create-patch-handler.ts", "community": 0, "file_type": "code"},
    {"id": "validate", "label": "validateSanitySession()",
     "source_file": "server/sanity-validate-session.ts", "community": 0, "file_type": "code"},
]
_LINKS = [
    {"source": "create_patch", "target": "validate", "relation": "calls", "confidence": "EXTRACTED"},
]


def _run(monkeypatch, graph_path, src, tgt, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "path", src, tgt, "--graph", str(graph_path)])
    mainmod.main()
    return capsys.readouterr().out


def test_forward_arrow(monkeypatch, tmp_path, capsys, seed_graph):
    seed_graph(tmp_path, _NODES, _LINKS)
    p = tmp_path / "graph.json"
    out = _run(monkeypatch, p, "createPatchHandler", "validateSanitySession", capsys)
    assert "Shortest path (1 hops):" in out
    assert "createPatchHandler() --calls [EXTRACTED]--> validateSanitySession()" in out


def test_reverse_arrow(monkeypatch, tmp_path, capsys, seed_graph):
    seed_graph(tmp_path, _NODES, _LINKS)
    p = tmp_path / "graph.json"
    out = _run(monkeypatch, p, "validateSanitySession", "createPatchHandler", capsys)
    assert "Shortest path (1 hops):" in out
    assert "validateSanitySession() <--calls [EXTRACTED]-- createPatchHandler()" in out
    assert "validateSanitySession() --calls [EXTRACTED]--> createPatchHandler()" not in out
