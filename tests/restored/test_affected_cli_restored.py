from __future__ import annotations

import graphify.__main__ as mainmod
from tests.native_helpers import make_loaded


def _write_graph(tmp_path):
    return make_loaded(
        tmp_path,
        kind="digraph",
        nodes=[
            {"id": "target", "label": "Foo", "source_file": "pkg/foo.py", "source_location": "L1"},
            {"id": "caller", "label": "X()", "source_file": "app.py", "source_location": "L4"},
            {"id": "barrel", "label": "__init__.py", "source_file": "pkg/__init__.py"},
            {"id": "consumer", "label": "app.py", "source_file": "app.py"},
        ],
        edges=[
            {"source": "caller", "target": "target", "relation": "calls", "context": "call", "confidence": "EXTRACTED"},
            {"source": "barrel", "target": "target", "relation": "re_exports", "context": "export", "confidence": "EXTRACTED"},
            {"source": "consumer", "target": "target", "relation": "imports", "context": "import", "confidence": "EXTRACTED"},
        ],
    ).store_path


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
    graph_path = make_loaded(
        tmp_path,
        kind="graph",
        nodes=[
            {"id": "A", "label": "caller_fn", "source_file": "a.py", "source_location": "L1"},
            {"id": "B", "label": "callee_fn", "source_file": "b.py", "source_location": "L2"},
        ],
        edges=[{"source": "A", "target": "B", "relation": "calls", "context": "call", "confidence": "EXTRACTED"}],
    ).store_path

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


def test_resolve_seed_bare_name_matches_callable_label():
    from graphify.affected import resolve_seed

    loaded = make_loaded(nodes=[
        {"id": "a", "label": "classifyProperty()", "source_file": "pkg/entity.py"},
        {"id": "b", "label": "classifyPropertySafe()", "source_file": "app/context.py"},
    ], kind="digraph")

    assert resolve_seed(loaded.graph, "classifyProperty", node_query=loaded.query) == "a"
    assert resolve_seed(loaded.graph, "classifyPropertySafe", node_query=loaded.query) == "b"


def test_resolve_seed_decorated_query_matches_bare_label():
    from graphify.affected import resolve_seed

    loaded = make_loaded(nodes=[
        {"id": "a", "label": "Foo", "source_file": "pkg/foo.py"},
        {"id": "b", "label": "FooBar", "source_file": "pkg/foobar.py"},
    ], kind="digraph")

    assert resolve_seed(loaded.graph, "Foo()", node_query=loaded.query) == "a"


def test_resolve_seed_matches_unicode_normalized_label():
    import unicodedata

    from graphify.affected import resolve_seed

    loaded = make_loaded(nodes=[{"id": "a", "label": "Auditoría", "source_file": "pkg/auditoria.py"}], kind="digraph")

    assert resolve_seed(loaded.graph, unicodedata.normalize("NFD", "Auditoría"), node_query=loaded.query) == "a"


def test_resolve_seed_preserves_distinct_accents():
    from graphify.affected import resolve_seed

    loaded = make_loaded(nodes=[
        {"id": "a", "label": "resume", "source_file": "pkg/resume.py"},
        {"id": "b", "label": "résumé", "source_file": "pkg/resume_accented.py"},
    ], kind="digraph")

    assert resolve_seed(loaded.graph, "resume", node_query=loaded.query) == "a"


def test_resolve_seed_bare_name_tie_still_returns_none():
    from graphify.affected import resolve_seed

    loaded = make_loaded(nodes=[
        {"id": "a", "label": "dup()", "source_file": "pkg/one.py"},
        {"id": "b", "label": "dup()", "source_file": "pkg/two.py"},
    ], kind="digraph")

    assert resolve_seed(loaded.graph, "dup", node_query=loaded.query) is None


def test_resolve_seed_source_file_path_prefers_file_level_node():
    from graphify.affected import resolve_seed

    source_file = "app/api/example/route.ts"
    loaded = make_loaded(nodes=[
        {"id": "example_route_get", "label": "GET()", "source_file": source_file, "source_location": "L42"},
        {"id": "example_route", "label": "route.ts", "source_file": source_file, "source_location": "L1"},
    ], kind="digraph")

    assert resolve_seed(loaded.graph, source_file, node_query=loaded.query) == "example_route"


def test_resolve_seed_source_file_trailing_slash_parity():
    """A trailing path separator must not change the match (parity with explain's
    _find_node, which tokenizes the path and drops the slash)."""
    from graphify.affected import resolve_seed

    source_file = "app/api/example/route.ts"
    loaded = make_loaded(nodes=[
        {"id": "get", "label": "GET()", "source_file": source_file, "source_location": "L42"},
        {"id": "file", "label": "route.ts", "source_file": source_file, "source_location": "L1"},
    ], kind="digraph")

    assert resolve_seed(loaded.graph, source_file + "/", node_query=loaded.query) == "file"


def test_resolve_seed_source_file_ambiguous_no_file_node_returns_none():
    """Several nodes share a source_file but none is the L1 file node and none's
    basename matches the path — must not guess; return None."""
    from graphify.affected import resolve_seed

    source_file = "pkg/handlers.py"
    loaded = make_loaded(nodes=[
        {"id": "a", "label": "handle_a()", "source_file": source_file, "source_location": "L10"},
        {"id": "b", "label": "handle_b()", "source_file": source_file, "source_location": "L20"},
    ], kind="digraph")

    assert resolve_seed(loaded.graph, source_file, node_query=loaded.query) is None


def test_affected_cli_source_file_path_uses_file_level_node(monkeypatch, tmp_path, capsys):
    source_file = "app/api/example/route.ts"
    graph_path = make_loaded(
        tmp_path,
        kind="digraph",
        nodes=[
            {"id": "example_route_get", "label": "GET()", "source_file": source_file, "source_location": "L42"},
            {"id": "example_route", "label": "route.ts", "source_file": source_file, "source_location": "L1"},
            {"id": "consumer", "label": "consumer.ts", "source_file": "app/consumer.ts", "source_location": "L1"},
        ],
        edges=[{"source": "consumer", "target": "example_route", "relation": "imports_from", "context": "import", "confidence": "EXTRACTED"}],
    ).store_path

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
