"""Regression tests for `graphify explain` arrow direction (#853)."""
from __future__ import annotations
import json
import graphify.__main__ as mainmod


_NODES = [
    {"id": "validate", "label": "validateSanitySession()", "source_file": "server/sanity-validate-session.ts", "community": 0, "file_type": "code"},
    {"id": "create_patch", "label": "createPatchHandler()", "source_file": "server/create-patch-handler.ts", "community": 0, "file_type": "code"},
    {"id": "create_edit", "label": "createEditHandler()", "source_file": "server/create-edit-handler.ts", "community": 0, "file_type": "code"},
    {"id": "stable_stringify", "label": "stableStringify()", "source_file": "shared/stringify.ts", "community": 0, "file_type": "code"},
]
_LINKS = [
    {"source": "create_patch", "target": "validate", "relation": "calls", "confidence": "EXTRACTED"},
    {"source": "create_edit", "target": "validate", "relation": "calls", "confidence": "EXTRACTED"},
    {"source": "validate", "target": "stable_stringify", "relation": "calls", "confidence": "EXTRACTED"},
]


def _write_graph(tmp_path):
    """Seed the FalkorDB graph for tmp_path so `explain` (which loads from the
    store) finds it."""
    from graphify.store import open_store

    store = open_store(tmp_path, create=True)
    store.clear()
    store.add_nodes_from([(n["id"], {k: v for k, v in n.items() if k != "id"}) for n in _NODES])
    store.add_edges_from([
        (e["source"], e["target"], {k: v for k, v in e.items() if k not in ("source", "target")})
        for e in _LINKS
    ])
    p = tmp_path / "graph.json"
    p.write_text(json.dumps({"directed": True, "multigraph": False, "graph": {},
                             "nodes": _NODES, "links": _LINKS}))
    return p


def _run(monkeypatch, graph_path, label, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", label, "--graph", str(graph_path)])
    mainmod.main()
    return capsys.readouterr().out


def test_callee_shows_callers_as_inbound(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "<-- createPatchHandler() [calls]" in out
    assert "<-- createEditHandler() [calls]" in out
    assert "--> stableStringify() [calls]" in out
    assert "--> createPatchHandler() [calls]" not in out
    assert "--> createEditHandler() [calls]" not in out


def test_caller_shows_callee_as_outbound(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "createPatchHandler", capsys)
    assert "--> validateSanitySession() [calls]" in out
    assert "<-- " not in out
