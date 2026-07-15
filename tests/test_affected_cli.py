from __future__ import annotations

import json

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    graph = nx.DiGraph()
    graph.add_node("target", label="Foo", source_file="pkg/foo.py", source_location="L1")
    graph.add_node("caller", label="X()", source_file="app.py", source_location="L4")
    graph.add_node("barrel", label="__init__.py", source_file="pkg/__init__.py", source_location=None)
    graph.add_node("consumer", label="app.py", source_file="app.py", source_location=None)
    graph.add_edge("caller", "target", relation="calls", context="call", confidence="EXTRACTED")
    graph.add_edge("barrel", "target", relation="re_exports", context="export", confidence="EXTRACTED")
    graph.add_edge("consumer", "target", relation="imports", context="import", confidence="EXTRACTED")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(graph, edges="links")), encoding="utf-8")
    return graph_path


def test_affected_cli_reverse_traverses_impact_edges(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
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


def test_affected_cli_relation_filter_limits_reverse_traversal(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
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


def test_affected_cli_forces_directed_on_undirected_graph(monkeypatch, tmp_path, capsys):
    """A graph persisted with directed=false must still recover caller->callee
    direction (#1174): affected on the callee returns the caller, not the callee
    or nothing. Without forcing directed=True, node_link_graph builds an
    undirected Graph, predecessors() collapses, and the reverse traversal breaks.
    """
    graph = nx.DiGraph()
    graph.add_node("A", label="caller_fn", source_file="a.py", source_location="L1")
    graph.add_node("B", label="callee_fn", source_file="b.py", source_location="L2")
    graph.add_edge("A", "B", relation="calls", context="call", confidence="EXTRACTED")

    data = json_graph.node_link_data(graph, edges="links")
    # Persist as undirected on disk to reproduce the bug condition.
    data["directed"] = False
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "affected", "B", "--relation", "calls", "--graph", str(graph_path)],
    )

    mainmod.main()

    out = capsys.readouterr().out
    # A (the caller) is affected by a change to B (the callee).
    assert "caller_fn" in out
    assert "calls" in out
    # B is the query node, not an affected node, and the result is not empty.
    assert "No affected nodes found." not in out


def test_affected_cli_loads_edges_keyed_graph(monkeypatch, tmp_path, capsys):
    """graphify's `extract` writes graph.json with an "edges" key (not networkx's
    default "links"). affected.load_graph must handle it; before the edges/links
    normalization it raised an uncaught KeyError: 'links' (same class as #1198)."""
    graph = nx.DiGraph()
    graph.add_node("target", label="Foo", source_file="pkg/foo.py", source_location="L1")
    graph.add_node("caller", label="X()", source_file="app.py", source_location="L4")
    graph.add_edge("caller", "target", relation="calls", context="call", confidence="EXTRACTED")

    # Emulate graphify extract output: top-level "edges" key instead of "links".
    data = json_graph.node_link_data(graph, edges="links")
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
    graph_path.write_text(json.dumps(json_graph.node_link_data(graph, edges="links")), encoding="utf-8")

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
