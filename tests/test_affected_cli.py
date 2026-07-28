from __future__ import annotations

import json

import pytest

from tests import nxcompat as nx
from tests.nxcompat import node_link_data

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


def test_affected_cli_unbuilt_graph_exits_with_build_hint(monkeypatch, tmp_path):
    """On a never-built graph, `affected` must exit non-zero (telling the user to
    build) rather than silently reporting an empty result. Guards the
    connect_graph empty-graph check (parity with query/path/explain)."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "affected", "Foo", "--graph", str(tmp_path / "graph.json")],
    )
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code != 0


def test_affected_cli_loads_edges_keyed_graph(monkeypatch, tmp_path, capsys):
    """graphify's `extract` writes graph.json with an "edges" key (not networkx's
    default "links"). affected.load_graph must handle it; before the edges/links
    normalization it raised an uncaught KeyError: 'links' (same class as #1198)."""
    graph = nx.DiGraph()
    graph.add_node("target", label="Foo", source_file="pkg/foo.py", source_location="L1")
    graph.add_node("caller", label="X()", source_file="app.py", source_location="L4")
    graph.add_edge("caller", "target", relation="calls", context="call", confidence="EXTRACTED")

    # Emulate graphify extract output: top-level "edges" key instead of "links".
    data = node_link_data(graph, edges="links")
    data["edges"] = data.pop("links")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(data), encoding="utf-8")

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


def test_resolve_seed_bare_name_matches_callable_label():
    from graphify.affected import resolve_seed

    graph = nx.DiGraph()
    graph.add_node("a", label="classifyProperty()", source_file="pkg/entity.py")
    graph.add_node("b", label="classifyPropertySafe()", source_file="app/context.py")

    assert resolve_seed(graph, "classifyProperty") == "a"
    assert resolve_seed(graph, "classifyPropertySafe") == "b"


def test_resolve_seed_decorated_query_matches_bare_label():
    from graphify.affected import resolve_seed

    graph = nx.DiGraph()
    graph.add_node("a", label="Foo", source_file="pkg/foo.py")
    graph.add_node("b", label="FooBar", source_file="pkg/foobar.py")

    assert resolve_seed(graph, "Foo()") == "a"


def test_resolve_seed_matches_unicode_normalized_label():
    import unicodedata

    from graphify.affected import resolve_seed

    graph = nx.DiGraph()
    graph.add_node("a", label="Auditoría", source_file="pkg/auditoria.py")

    assert resolve_seed(graph, unicodedata.normalize("NFD", "Auditoría")) == "a"


def test_resolve_seed_preserves_distinct_accents():
    from graphify.affected import resolve_seed

    graph = nx.DiGraph()
    graph.add_node("a", label="resume", source_file="pkg/resume.py")
    graph.add_node("b", label="résumé", source_file="pkg/resume_accented.py")

    assert resolve_seed(graph, "resume") == "a"


def test_resolve_seed_bare_name_tie_still_returns_none():
    from graphify.affected import resolve_seed

    graph = nx.DiGraph()
    graph.add_node("a", label="dup()", source_file="pkg/one.py")
    graph.add_node("b", label="dup()", source_file="pkg/two.py")

    assert resolve_seed(graph, "dup") is None


def test_resolve_seed_source_file_path_prefers_file_level_node():
    from graphify.affected import resolve_seed

    graph = nx.DiGraph()
    source_file = "app/api/example/route.ts"
    graph.add_node(
        "example_route_get",
        label="GET()",
        source_file=source_file,
        source_location="L42",
    )
    graph.add_node(
        "example_route",
        label="route.ts",
        source_file=source_file,
        source_location="L1",
    )

    assert resolve_seed(graph, source_file) == "example_route"


def test_resolve_seed_source_file_trailing_slash_parity():
    """A trailing path separator must not change the match (parity with explain's
    _find_node, which tokenizes the path and drops the slash)."""
    from graphify.affected import resolve_seed

    graph = nx.DiGraph()
    source_file = "app/api/example/route.ts"
    graph.add_node("get", label="GET()", source_file=source_file, source_location="L42")
    graph.add_node("file", label="route.ts", source_file=source_file, source_location="L1")

    assert resolve_seed(graph, source_file + "/") == "file"


def test_resolve_seed_source_file_ambiguous_no_file_node_returns_none():
    """Several nodes share a source_file but none is the L1 file node and none's
    basename matches the path — must not guess; return None."""
    from graphify.affected import resolve_seed

    graph = nx.DiGraph()
    source_file = "pkg/handlers.py"
    graph.add_node("a", label="handle_a()", source_file=source_file, source_location="L10")
    graph.add_node("b", label="handle_b()", source_file=source_file, source_location="L20")

    assert resolve_seed(graph, source_file) is None


def test_affected_cli_source_file_path_uses_file_level_node(monkeypatch, tmp_path, capsys):
    graph = nx.DiGraph()
    source_file = "app/api/example/route.ts"
    graph.add_node(
        "example_route_get",
        label="GET()",
        source_file=source_file,
        source_location="L42",
    )
    graph.add_node(
        "example_route",
        label="route.ts",
        source_file=source_file,
        source_location="L1",
    )
    graph.add_node(
        "consumer",
        label="consumer.ts",
        source_file="app/consumer.ts",
        source_location="L1",
    )
    graph.add_edge(
        "consumer",
        "example_route",
        relation="imports_from",
        context="import",
        confidence="EXTRACTED",
    )
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(node_link_data(graph, edges="links")), encoding="utf-8")

    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "affected", source_file, "--graph", str(graph_path)],
    )

    mainmod.main()

    out = capsys.readouterr().out
    assert "Affected nodes for route.ts" in out
    assert "consumer.ts" in out
    assert "imports_from" in out
    assert "No unique node matched" not in out


# ── BUG1: caller lists must show the call-SITE line, not the caller def line ──

def _write_callsite_graph(tmp_path):
    """A caller whose call site (L158) differs from its own def line (L90)."""
    g = nx.DiGraph()
    g.add_node("loader", label="_load_apollo_app_state()",
               source_file="apollo_pipeline_status.py", source_location="L90")
    g.add_node("transition", label="transition_state()",
               source_file="state.py", source_location="L56")
    # The call happens at line 158 inside the caller's file.
    g.add_edge("loader", "transition", relation="calls", context="call",
               confidence="EXTRACTED", source_file="apollo_pipeline_status.py",
               source_location="L158")
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(node_link_data(g, edges="links")), encoding="utf-8")
    return gp


def test_affected_reports_call_site_line_not_def_line(monkeypatch, tmp_path, capsys):
    gp = _write_callsite_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
                        ["graphify", "affected", "transition_state", "--graph", str(gp)])
    mainmod.main()
    out = capsys.readouterr().out
    assert "apollo_pipeline_status.py:L158" in out, "must report the call SITE line (BUG1)"
    assert "apollo_pipeline_status.py:L90" not in out, "must NOT report the caller's def line"


def test_affected_falls_back_to_def_line_when_edge_has_no_location(monkeypatch, tmp_path, capsys):
    """An edge with no stored location honestly falls back to the node's def line."""
    g = nx.DiGraph()
    g.add_node("loader", label="load()", source_file="a.py", source_location="L90")
    g.add_node("t", label="target()", source_file="b.py", source_location="L5")
    g.add_edge("loader", "t", relation="calls", confidence="INFERRED")  # no source_location
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(node_link_data(g, edges="links")), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "affected", "target", "--graph", str(gp)])
    mainmod.main()
    assert "a.py:L90" in capsys.readouterr().out
