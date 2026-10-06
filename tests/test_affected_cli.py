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
    gp.write_text(json.dumps(json_graph.node_link_data(g, edges="links")), encoding="utf-8")
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
    gp.write_text(json.dumps(json_graph.node_link_data(g, edges="links")), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "affected", "target", "--graph", str(gp)])
    mainmod.main()
    assert "a.py:L90" in capsys.readouterr().out


def test_affected_resolves_equivalent_path_forms(tmp_path, monkeypatch):
    """`./x.py`, an absolute path and `x.py` name one file and must resolve alike.

    The graph stores repo-relative `source_file`, and `resolve_seed` compared the
    query to it as a plain string. `./pkg/foo.py` and `/abs/repo/pkg/foo.py`
    therefore matched nothing, `affected` printed an empty list and exited 0 — a
    blast-radius tool reporting "nothing depends on this" about a file with three
    dependents, and indistinguishable both from a genuine zero and from a typo.
    """
    from graphify.affected import resolve_seed

    graph = nx.DiGraph()
    graph.add_node("target", label="Foo", source_file="pkg/foo.py", source_location="L1")
    graph.add_node("caller", label="X()", source_file="app.py", source_location="L4")
    graph.add_edge("caller", "target", relation="calls")

    monkeypatch.chdir(tmp_path)
    for query in (
        "pkg/foo.py",
        "./pkg/foo.py",
        str(tmp_path / "pkg" / "foo.py"),
    ):
        assert resolve_seed(graph, query) == "target", query


def test_affected_absolute_seed_resolves_via_graph_root_off_cwd(tmp_path, monkeypatch, capsys):
    """An absolute-path seed resolves off the graph's location, not the cwd (#2706).

    The shipped `./`/absolute fix only matched when the working directory already
    was the analysed repo root. Editors and scripts pass an absolute path from
    anywhere, so `affected` kept answering "nothing depends on this" — the
    maintainer's noted follow-up. The root is now derived from the graph's own
    location (`<root>/graphify-out/graph.json`).
    """
    from graphify.paths import GRAPHIFY_OUT_NAME

    repo_root = tmp_path / "repo"
    out_dir = repo_root / GRAPHIFY_OUT_NAME
    out_dir.mkdir(parents=True)
    g = nx.DiGraph()
    g.add_node("target", label="Foo", source_file="pkg/foo.py", source_location="L1")
    g.add_node("caller", label="X()", source_file="app.py", source_location="L4")
    g.add_edge("caller", "target", relation="calls")
    gp = out_dir / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(g, edges="links")), encoding="utf-8")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # NOT the repo root — mimics an editor/script caller
    abs_seed = str(repo_root / "pkg" / "foo.py")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "affected", abs_seed, "--graph", str(gp)])
    mainmod.main()

    out = capsys.readouterr().out
    assert "Affected nodes for Foo" in out
    assert "X()" in out


def test_affected_absolute_seed_outside_root_misses_cleanly(tmp_path, monkeypatch, capsys):
    """An absolute seed that is NOT under the derived repo root must report a clean
    no-match, not silently traverse from a wrong/guessed node (#2706)."""
    from graphify.paths import GRAPHIFY_OUT_NAME

    repo_root = tmp_path / "repo"
    out_dir = repo_root / GRAPHIFY_OUT_NAME
    out_dir.mkdir(parents=True)
    g = nx.DiGraph()
    g.add_node("target", label="Foo", source_file="pkg/foo.py", source_location="L1")
    g.add_node("caller", label="X()", source_file="app.py", source_location="L4")
    g.add_edge("caller", "target", relation="calls")
    gp = out_dir / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(g, edges="links")), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    outside_seed = str(tmp_path / "other-repo" / "pkg" / "foo.py")  # same basename, different tree
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
                        ["graphify", "affected", outside_seed, "--graph", str(gp)])
    # A miss exits nonzero on stderr, so a script cannot read it as "no dependents".
    import pytest
    with pytest.raises(SystemExit) as exc:
        mainmod.main()

    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert "Affected nodes for Foo" not in captured.out  # must NOT resolve to the in-root Foo
    assert f"No unique node match for {outside_seed}" in captured.err


def test_affected_absolute_seed_with_graph_not_under_out_dir(tmp_path, monkeypatch, capsys):
    """Fallback layout: when --graph points at a graph.json NOT under the
    graphify-out dir, the root is the graph's own parent (`else gp.parent`)."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    g = nx.DiGraph()
    g.add_node("target", label="Foo", source_file="pkg/foo.py", source_location="L1")
    g.add_node("caller", label="X()", source_file="app.py", source_location="L4")
    g.add_edge("caller", "target", relation="calls")
    gp = repo_root / "graph.json"  # directly under repo_root, not graphify-out/
    gp.write_text(json.dumps(json_graph.node_link_data(g, edges="links")), encoding="utf-8")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    abs_seed = str(repo_root / "pkg" / "foo.py")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
                        ["graphify", "affected", abs_seed, "--graph", str(gp)])
    mainmod.main()

    out = capsys.readouterr().out
    assert "Affected nodes for Foo" in out
    assert "X()" in out


# ── Qualified seeds, stub preference, and nonzero exit on a miss/ambiguity ──

def _two_send_graph():
    """httpx-shaped graph: `Client.send` and `AsyncClient.send` share the label
    `.send()` in one file, a nested `send()` lives in another, and a parameter
    annotation left a sourceless `Send` stub whose id is the bare name `send`."""
    g = nx.DiGraph()
    g.add_node("client_py", label="_client.py", source_file="pkg/_client.py", source_location="L1")
    g.add_node("client", label="Client", source_file="pkg/_client.py", source_location="L10")
    g.add_node("client_send", label=".send()", source_file="pkg/_client.py", source_location="L20")
    g.add_node("async_client", label="AsyncClient", source_file="pkg/_client.py", source_location="L50")
    g.add_node("async_send", label=".send()", source_file="pkg/_client.py", source_location="L60")
    g.add_node("handle", label="handle()", source_file="pkg/asgi.py", source_location="L5")
    g.add_node("handle_send", label="send()", source_file="pkg/asgi.py", source_location="L8")
    g.add_node("helper", label="helper()", source_file="pkg/util.py", source_location="L3")
    g.add_node("helper_other", label="helper()", source_file="pkg/other.py", source_location="L3")
    g.add_node("send", label="Send", source_file="", source_location="")
    g.add_node("caller", label="caller()", source_file="app.py", source_location="L4")
    g.add_node("async_caller", label="async_caller()", source_file="app.py", source_location="L9")
    g.add_edge("client_py", "client", relation="contains")
    g.add_edge("client_py", "async_client", relation="contains")
    g.add_edge("client", "client_send", relation="method")
    g.add_edge("async_client", "async_send", relation="method")
    g.add_edge("handle", "handle_send", relation="contains")
    g.add_edge("caller", "client_send", relation="calls", source_file="app.py", source_location="L5")
    g.add_edge("async_caller", "async_send", relation="calls", source_file="app.py", source_location="L10")
    g.add_edge("caller", "send", relation="references")
    return g


def test_resolve_seed_class_dot_method_uses_owning_class():
    from graphify.affected import resolve_seed

    g = _two_send_graph()
    assert resolve_seed(g, "Client.send") == "client_send"
    assert resolve_seed(g, "AsyncClient.send") == "async_send"
    assert resolve_seed(g, "Client.send()") == "client_send"
    # A nested function is reachable through its `contains` owner too.
    assert resolve_seed(g, "handle.send") == "handle_send"
    # The owner must really own the member: no label-text guess.
    assert resolve_seed(g, "Client.helper") is None


def test_resolve_seed_path_scoped_forms(tmp_path):
    from graphify.affected import resolve_seed

    g = _two_send_graph()
    assert resolve_seed(g, "pkg/_client.py::Client.send") == "client_send"
    assert resolve_seed(g, "pkg/_client.py::AsyncClient.send") == "async_send"
    assert resolve_seed(g, "./pkg/_client.py::Client.send") == "client_send"
    assert resolve_seed(g, str(tmp_path / "pkg" / "_client.py") + "::Client.send", tmp_path) == "client_send"
    assert resolve_seed(g, "pkg/_client.py::Client") == "client"
    assert resolve_seed(g, "pkg/util.py::helper") == "helper"
    assert resolve_seed(g, "pkg/other.py::helper()") == "helper_other"
    # Both `.send()` methods live in this file: the path alone cannot pick one.
    assert resolve_seed(g, "pkg/_client.py::send") is None
    # The path must be the member's own file, not a guess from the label.
    assert resolve_seed(g, "pkg/asgi.py::Client.send") is None


def test_resolve_seed_bare_name_does_not_pick_sourceless_stub():
    from graphify.affected import resolve_seed

    g = _two_send_graph()
    # `send` is the stub's id and `Send` its label, but three real definitions
    # carry that name: ambiguous, not the stub.
    assert resolve_seed(g, "send") is None
    assert resolve_seed(g, "Send") is None

    g.remove_nodes_from(["client_send", "async_send"])
    # One real definition left: it wins over the stub.
    assert resolve_seed(g, "send") == "handle_send"
    assert resolve_seed(g, "Send") == "handle_send"

    g.remove_node("handle_send")
    # No real namesake: the stub is the only answer and stays reachable.
    assert resolve_seed(g, "send") == "send"


def test_resolve_seed_substring_does_not_break_a_name_tie():
    """Two `Config` classes tie on the name; the substring pass must not then
    hand back the one `load_config()` that happens to contain `config()`."""
    from graphify.affected import resolve_seed

    g = nx.DiGraph()
    g.add_node("a", label="Config", source_file="pkg/a.py", source_location="L1")
    g.add_node("b", label="Config", source_file="pkg/b.py", source_location="L1")
    g.add_node("c", label="load_config()", source_file="pkg/c.py", source_location="L1")

    assert resolve_seed(g, "Config()") is None


def test_resolve_seed_qualified_miss_does_not_fall_back_to_substring():
    """A qualified query that matches nothing is a miss, even when some label
    (here a docs heading) happens to contain the whole query text."""
    from graphify.affected import resolve_seed

    g = _two_send_graph()
    g.add_node("doc", label="Using pkg/missing.py::Client.send safely", source_file="guide.md")
    g.add_node("doc2", label="Why Client.nope was removed", source_file="guide.md")
    assert resolve_seed(g, "pkg/missing.py::Client.send") is None
    assert resolve_seed(g, "Client.nope") is None

    # A left half that names a file in the graph is a path even without an
    # extension (`Makefile::all`), so a root file named `Invoice` scopes
    # `Invoice::Line` to itself and the miss is final, even though a Ruby
    # label `Billing::Invoice::Line` contains the query.
    g.add_node("line", label="Billing::Invoice::Line", source_file="billing.rb", source_location="L3")
    g.add_node("invoice_file", label="Invoice", source_file="Invoice", source_location="L1")
    assert resolve_seed(g, "Invoice::Line") is None


def test_resolve_seed_unqualified_dotted_and_namespace_queries_keep_substring_match():
    """Boundary of the rule above, unchanged from before: a `::` whose left half
    is a namespace rather than a path (Ruby's `Billing::Invoice::Line`), and a
    dotted name whose owner part names nothing that owns members, still reach
    the substring tier, even next to an unrelated `index()` function."""
    from graphify.affected import resolve_seed

    g = nx.DiGraph()
    g.add_node("line", label="Billing::Invoice::Line", source_file="billing.rb", source_location="L3")
    g.add_node("index", label="web/index.ts", source_file="web/index.ts", source_location="L1")
    assert resolve_seed(g, "Invoice::Line") == "line"
    assert resolve_seed(g, "index.ts") == "index"

    g.add_node("index_fn", label="index()", source_file="views.py", source_location="L4")
    assert resolve_seed(g, "index.ts") == "index"

    # A file named after a heading that owns sections is still found by its
    # exact label, and a docstring label containing `::` is prose, not a path.
    g.add_node("changelog_file", label="CHANGELOG.md", source_file="CHANGELOG.md", source_location="L1")
    g.add_node("changelog", label="Changelog", source_file="CHANGELOG.md", source_location="L1")
    g.add_node("unreleased", label="Unreleased", source_file="CHANGELOG.md", source_location="L3")
    g.add_edge("changelog", "unreleased", relation="contains")
    prose = "Registers a function. .. versionadded:: 0.11"
    g.add_node("rationale", label=prose, source_file="app.py", source_location="L9")
    assert resolve_seed(g, "CHANGELOG.md") == "changelog_file"
    assert resolve_seed(g, prose) == "rationale"


def test_resolve_seed_reads_ownership_from_direction_markers_on_undirected_graph():
    """`build_from_json` returns an undirected graph by default, which keeps
    edge direction only in `_src`/`_tgt`. Ownership must follow those markers
    whichever endpoint was inserted first, never the reverse."""
    from graphify.affected import resolve_seed
    from graphify.build import build_from_json

    outer = {"id": "outer", "label": "Outer", "source_file": "pkg.py", "source_location": "L1"}
    inner = {"id": "inner", "label": "Inner", "source_file": "pkg.py", "source_location": "L2"}
    edge = {"source": "outer", "target": "inner", "relation": "contains",
            "confidence": "EXTRACTED", "source_file": "pkg.py", "source_location": "L2"}
    for nodes in ([outer, inner], [inner, outer]):
        g = build_from_json({"nodes": nodes, "edges": [edge]})
        assert not g.is_directed()
        assert resolve_seed(g, "Outer.Inner") == "inner", [n["id"] for n in nodes]
        assert resolve_seed(g, "Inner.Outer") is None, [n["id"] for n in nodes]


def test_resolve_seed_owner_prefers_real_definition_over_stub(tmp_path):
    """Extracted fixture: `handler: Handle` leaves a sourceless stub labeled
    `Handle`, which matches the owner `handle` exactly. The real `handle()`
    (matched by bare name) must still be the owner of its nested `send()`."""
    import pytest

    from graphify.affected import resolve_seed
    from graphify.build import build_from_json
    from graphify.extract import extract

    (tmp_path / "pkg.py").write_text(
        "def handle():\n    def send():\n        pass\n    send()\n", encoding="utf-8"
    )
    (tmp_path / "server.py").write_text(
        "def unrelated(handler: Handle):\n    pass\n", encoding="utf-8"
    )
    extraction = extract(
        [tmp_path / "pkg.py", tmp_path / "server.py"], root=tmp_path, cache_root=tmp_path
    )
    for directed in (True, False):
        g = build_from_json(extraction, directed=directed)
        stubs = [n for n, d in g.nodes(data=True) if d.get("label") == "Handle"]
        if not stubs or g.nodes[stubs[0]].get("source_file"):
            pytest.fail(f"fixture no longer yields a sourceless Handle stub: {stubs}")
        nested = [
            n for n, d in g.nodes(data=True)
            if d.get("label") == "send()" and d.get("source_file") == "pkg.py"
        ]
        assert len(nested) == 1, nested
        assert resolve_seed(g, "handle.send") == nested[0], directed
        assert resolve_seed(g, "pkg.py::handle.send") == nested[0], directed

    # A source-backed `class Handle` elsewhere matches `handle` exactly too.
    # It owns no `send`, so it is not an eligible owner for this query.
    (tmp_path / "other.py").write_text(
        "class Handle:\n    def unrelated(self):\n        pass\n", encoding="utf-8"
    )
    extraction = extract(
        [tmp_path / "pkg.py", tmp_path / "other.py"], root=tmp_path, cache_root=tmp_path
    )
    for directed in (True, False):
        g = build_from_json(extraction, directed=directed)
        classes = [
            n for n, d in g.nodes(data=True)
            if d.get("label") == "Handle" and d.get("source_file") == "other.py"
        ]
        assert classes, "fixture no longer yields the source-backed class Handle"
        nested = [
            n for n, d in g.nodes(data=True)
            if d.get("label") == "send()" and d.get("source_file") == "pkg.py"
        ]
        assert len(nested) == 1, nested
        assert resolve_seed(g, "pkg.py::handle.send") == nested[0], directed
        assert resolve_seed(g, "handle.send") == nested[0], directed
        assert resolve_seed(g, "pkg.py::Handle.unrelated") is None, directed
        assert resolve_seed(g, "Handle.unrelated") is not None, directed


def test_resolve_seed_path_scope_keeps_case_distinct_files_apart():
    """On a case-sensitive filesystem `a.py` and `A.py` are two files, so a path
    only scopes to its exact-case file. A wrong-case path still resolves when
    a single file matches it case-insensitively (Windows, macOS)."""
    from graphify.affected import resolve_seed

    g = nx.DiGraph()
    g.add_node("lower_foo", label="Foo", source_file="a.py", source_location="L1")
    g.add_node("upper_bar", label="Bar", source_file="A.py", source_location="L1")
    assert resolve_seed(g, "a.py::Bar") is None
    assert resolve_seed(g, "A.py::Foo") is None
    assert resolve_seed(g, "a.py::Foo") == "lower_foo"
    assert resolve_seed(g, "A.py::Bar") == "upper_bar"
    # Neither file is spelled `A.PY`, and two match it case-insensitively.
    assert resolve_seed(g, "A.PY::Bar") is None

    g.remove_node("lower_foo")
    assert resolve_seed(g, "a.py::Bar") == "upper_bar"

    # Composed and decomposed spellings are two files on Linux too.
    composed, decomposed = "caf\u00e9.py", "cafe\u0301.py"
    g = nx.DiGraph()
    g.add_node("composed_foo", label="Foo", source_file=composed, source_location="L1")
    g.add_node("decomposed_bar", label="Bar", source_file=decomposed, source_location="L1")
    assert resolve_seed(g, f"{composed}::Bar") is None
    assert resolve_seed(g, f"{decomposed}::Foo") is None
    assert resolve_seed(g, f"{composed}::Foo") == "composed_foo"
    assert resolve_seed(g, f"{decomposed}::Bar") == "decomposed_bar"
    g.remove_node("composed_foo")
    assert resolve_seed(g, f"{composed}::Bar") == "decomposed_bar"

    # The path is not trimmed: ` a.py` and `a.py` are two files too.
    g = nx.DiGraph()
    g.add_node("spaced_run", label="run()", source_file=" a.py", source_location="L1")
    g.add_node("plain_run", label="run()", source_file="a.py", source_location="L1")
    assert resolve_seed(g, " a.py::run") == "spaced_run"
    assert resolve_seed(g, "a.py::run") == "plain_run"
    assert resolve_seed(g, "./ a.py::run") == "spaced_run"


def test_resolve_seed_path_matching_several_files_is_a_reported_tie():
    """A path that matches several files only after case folding keeps its
    path scope (spaces or no extension notwithstanding): a heading whose text
    is the query must not answer it. The tie is listed when the symbol is in
    both files, and a miss names the files when it is in only one."""
    import pytest

    from graphify.affected import resolve_seed

    for lower, upper, owner, member, query in (
        ("my client.py", "My Client.py", "Client", ".send()", "MY CLIENT.PY::Client.send"),
        ("makefile", "Makefile", "", "all", "MAKEFILE::all"),
    ):
        g = nx.DiGraph()
        for key, source in (("lower", lower), ("upper", upper)):
            g.add_node(f"{key}_file", label=source, source_file=source, source_location="L1")
            if owner:
                g.add_node(f"{key}_owner", label=owner, source_file=source, source_location="L1")
                g.add_edge(f"{key}_owner", f"{key}_member", relation="method")
            g.add_node(f"{key}_member", label=member, source_file=source, source_location="L2")
        g.add_node("heading", label=query, source_file="guide.md", source_location="L1")

        assert resolve_seed(g, query) is None, query
        assert resolve_seed(g, f"{lower}::{query.split('::')[1]}") == "lower_member", query
        assert resolve_seed(g, f"{upper}::{query.split('::')[1]}") == "upper_member", query
        from graphify.affected import SeedResolutionError, format_affected, resolve_seed_candidates

        assert resolve_seed_candidates(g, query) == ["lower_member", "upper_member"], query
        with pytest.raises(SeedResolutionError) as exc:
            format_affected(g, query)
        assert "2 nodes match" in str(exc.value) and "heading" not in str(exc.value), query

        # Symbol in one file only: still no guess at which file was meant.
        g.remove_node("upper_member")
        assert resolve_seed(g, query) is None, query
        with pytest.raises(SeedResolutionError) as exc:
            format_affected(g, query)
        message = str(exc.value)
        assert f"No unique node match for {query}" in message, message
        assert f"The path matches 2 files: {upper!r}, {lower!r}" in message, message


def test_affected_refuses_nested_owner_chain_instead_of_guessing():
    """`Outer.Inner.run` names an owner of an owner. Only one level is
    supported, so it must miss with a hint, not fall through to the docs node
    whose text contains it."""
    import pytest

    from graphify.affected import resolve_seed

    g = nx.DiGraph()
    g.add_node("outer", label="Outer", source_file="pkg.py", source_location="L1")
    g.add_node("inner", label="Inner", source_file="pkg.py", source_location="L2")
    g.add_node("run", label=".run()", source_file="pkg.py", source_location="L3")
    g.add_edge("outer", "inner", relation="contains")
    g.add_edge("inner", "run", relation="method")
    g.add_node("doc", label="Using Outer.Inner.run safely", source_file="guide.md")

    assert resolve_seed(g, "Outer.Inner.run") is None
    from graphify.affected import SeedResolutionError, format_affected

    with pytest.raises(SeedResolutionError) as exc:
        format_affected(g, "Outer.Inner.run")
    message = str(exc.value)
    assert "No unique node match for Outer.Inner.run" in message
    assert "Only one owner level is supported" in message
    assert "Inner.run" in message.splitlines()[1]
    assert resolve_seed(g, "Inner.run") == "run"
    assert resolve_seed(g, "pkg.py::Inner.run") == "run"

    # An owner whose own label is dotted is one level, not a chain.
    g = nx.DiGraph()
    g.add_node("owner", label="Outer.Inner", source_file="pkg.py", source_location="L1")
    g.add_node("member", label=".run()", source_file="pkg.py", source_location="L2")
    g.add_edge("owner", "member", relation="method")
    assert resolve_seed(g, "Outer.Inner.run") == "member"


def test_affected_refuses_nested_owner_chain_over_exact_and_bare_headings(tmp_path):
    """Extracted fixture: a heading whose text is exactly the chain, or the
    chain with `()`, must not answer it. The refusal comes before the label
    tiers. A heading `# Outer.Inner` does not lift it either, alone or owning
    an unrelated section: only an `Outer.Inner` node that owns `run` would."""
    import pytest

    from graphify.affected import resolve_seed
    from graphify.build import build_from_json
    from graphify.extract import extract

    (tmp_path / "nested.py").write_text(
        "class Outer:\n    class Inner:\n        def run(self):\n            pass\n",
        encoding="utf-8",
    )
    guides = (
        ("Outer.Inner.run", "# Outer.Inner.run\n"),
        ("Outer.Inner.run()", "# Outer.Inner.run()\n"),
        ("Outer.Inner.run", "# Outer.Inner\n\n# Outer.Inner.run\n"),
        ("Outer.Inner.run", "# Outer.Inner\n\n## Details\n\n# Outer.Inner.run\n"),
    )
    for heading, guide in guides:
        (tmp_path / "guide.md").write_text(guide, encoding="utf-8")
        extraction = extract(
            [tmp_path / "nested.py", tmp_path / "guide.md"], root=tmp_path, cache_root=tmp_path
        )
        for directed in (True, False):
            g = build_from_json(extraction, directed=directed)
            labels = {d.get("label") for _, d in g.nodes(data=True)}
            assert heading in labels, labels
            assert resolve_seed(g, "Outer.Inner.run") is None, (guide, directed)
            from graphify.affected import SeedResolutionError, format_affected

            with pytest.raises(SeedResolutionError) as exc:
                format_affected(g, "Outer.Inner.run")
            assert "Only one owner level is supported" in str(exc.value), (guide, directed)
            run = [n for n, d in g.nodes(data=True) if d.get("label") == ".run()"]
            assert resolve_seed(g, "Inner.run") == run[0], (guide, directed)


def test_resolve_seed_path_with_spaces_keeps_its_scope(tmp_path):
    """Extracted fixture: paths with spaces, relative and absolute, existing
    and missing, each next to a heading whose text is exactly the query. A
    `::` left half with a separator, or one that names a file in the graph,
    is a path even with spaces in it."""
    from graphify.affected import resolve_seed
    from graphify.build import build_from_json
    from graphify.extract import extract

    (tmp_path / "my pkg").mkdir()
    (tmp_path / "my pkg" / "client.py").write_text(
        "class Client:\n    def send(self):\n        pass\n", encoding="utf-8"
    )
    (tmp_path / "my client.py").write_text(
        "class Other:\n    def ping(self):\n        pass\n", encoding="utf-8"
    )
    absolute = (tmp_path / "my pkg").as_posix()
    queries = [
        "my pkg/client.py::Client.send",
        "my pkg/missing.py::Client.send",
        "my client.py::Other.ping",
        f"{absolute}/client.py::Client.send",
        f"{absolute}/missing.py::Client.send",
    ]
    (tmp_path / "guide.md").write_text(
        "".join(f"# {query}\n\n" for query in queries), encoding="utf-8"
    )
    extraction = extract(
        [tmp_path / "my pkg" / "client.py", tmp_path / "my client.py", tmp_path / "guide.md"],
        root=tmp_path, cache_root=tmp_path,
    )
    for directed in (True, False):
        g = build_from_json(extraction, directed=directed)
        headings = {d.get("label") for _, d in g.nodes(data=True) if d.get("source_file") == "guide.md"}
        assert set(queries) <= headings, headings
        send = [n for n, d in g.nodes(data=True) if d.get("label") == ".send()"]
        ping = [n for n, d in g.nodes(data=True) if d.get("label") == ".ping()"]
        assert resolve_seed(g, queries[0], tmp_path) == send[0], directed
        assert resolve_seed(g, queries[1], tmp_path) is None, directed
        assert resolve_seed(g, queries[2], tmp_path) == ping[0], directed
        assert resolve_seed(g, queries[3], tmp_path) == send[0], directed
        assert resolve_seed(g, queries[4], tmp_path) is None, directed


def test_affected_nodes_member_seeding_unchanged_from_v8():
    """Qualified resolution reads ownership direction from `_src`/`_tgt`, but
    `affected_nodes` keeps v8's own member seeding. On an undirected graph
    v8 reads arc order, and so does its reverse walk; reading direction in
    only one of the two reported `callee` as affected by `Svc`, which it
    calls, not the other way round."""
    from graphify.affected import affected_nodes
    from graphify.build import build_from_json

    def edge(source, target, relation, loc):
        return {"source": source, "target": target, "relation": relation,
                "confidence": "EXTRACTED", "source_file": "pkg.py", "source_location": loc}

    nodes = [
        {"id": "callee", "label": "callee()", "source_file": "pkg.py", "source_location": "L1"},
        {"id": "method", "label": ".run()", "source_file": "pkg.py", "source_location": "L5"},
        {"id": "owner", "label": "Svc", "source_file": "pkg.py", "source_location": "L4"},
    ]
    edges = [edge("owner", "method", "method", "L5"), edge("method", "callee", "calls", "L6")]
    for directed in (False, True):
        g = build_from_json({"nodes": nodes, "edges": edges}, directed=directed)
        assert [h.node_id for h in affected_nodes(g, "owner")] == [], directed

    # Directed: a caller of the method is still reached through member seeding.
    nodes.append({"id": "caller", "label": "caller()", "source_file": "app.py", "source_location": "L2"})
    edges.append(edge("caller", "method", "calls", "L3"))
    g = build_from_json({"nodes": nodes, "edges": edges}, directed=True)
    assert [h.node_id for h in affected_nodes(g, "owner")] == ["caller"]


def test_resolve_seed_qualified_scope_beats_exact_heading_labels(tmp_path):
    """Extracted fixture: Markdown headings whose text is exactly the query.
    A qualified query is answered from the scope it names first, so the
    `# Client.send` heading cannot stand in for the method, and a heading
    cannot answer a `path::` query for a file that does not exist."""
    import pytest

    from graphify.affected import resolve_seed
    from graphify.build import build_from_json
    from graphify.extract import extract

    (tmp_path / "pkg.py").write_text(
        "class Client:\n    def send(self):\n        pass\n", encoding="utf-8"
    )
    (tmp_path / "guide.md").write_text(
        "# Client.send\n\n# pkg.py::Client.send\n\n# missing.py::Client.send\n",
        encoding="utf-8",
    )
    extraction = extract(
        [tmp_path / "pkg.py", tmp_path / "guide.md"], root=tmp_path, cache_root=tmp_path
    )
    for directed in (True, False):
        g = build_from_json(extraction, directed=directed)
        headings = {
            d.get("label") for _, d in g.nodes(data=True) if d.get("source_file") == "guide.md"
        }
        assert {"Client.send", "pkg.py::Client.send", "missing.py::Client.send"} <= headings
        method = [
            n for n, d in g.nodes(data=True)
            if d.get("label") == ".send()" and d.get("source_file") == "pkg.py"
        ]
        assert len(method) == 1, method
        assert resolve_seed(g, "Client.send") == method[0], directed
        assert resolve_seed(g, "pkg.py::Client.send") == method[0], directed
        assert resolve_seed(g, "missing.py::Client.send") is None, directed
        from graphify.affected import SeedResolutionError, format_affected

        with pytest.raises(SeedResolutionError):
            format_affected(g, "missing.py::Client.send")


def test_affected_ties_a_heading_tree_with_the_method_it_names(tmp_path):
    """Extracted fixture: `# Client` with a `## send` section is a second
    `Client` owning a `send` member. Neither owner outranks the other by
    member-label decoration (`send` vs `.send()`), and graphify's seed lookups
    have no code-over-document rule, so `Client.send` is a tie listed on
    stderr. Before, the heading won and hid the method's real caller. The
    path form picks the method, and its caller is reported."""
    import pytest

    from graphify.affected import resolve_seed
    from graphify.build import build_from_json
    from graphify.extract import extract

    (tmp_path / "pkg.py").write_text(
        "class Client:\n    def send(self):\n        pass\n"
        "    def request(self):\n        self.send()\n",
        encoding="utf-8",
    )
    (tmp_path / "guide.md").write_text("# Client\n\n## send\n", encoding="utf-8")
    extraction = extract(
        [tmp_path / "pkg.py", tmp_path / "guide.md"], root=tmp_path, cache_root=tmp_path
    )
    for directed in (True, False):
        g = build_from_json(extraction, directed=directed)
        method = [n for n, d in g.nodes(data=True) if d.get("label") == ".send()"]
        heading = [
            n for n, d in g.nodes(data=True)
            if d.get("label") == "send" and d.get("source_file") == "guide.md"
        ]
        assert len(method) == 1 and len(heading) == 1, (method, heading)
        assert resolve_seed(g, "pkg.py::Client.send") == method[0], directed
        assert resolve_seed(g, "guide.md::Client.send") == heading[0], directed
        assert resolve_seed(g, "Client.send") is None, directed
        from graphify.affected import resolve_seed_candidates

        assert set(resolve_seed_candidates(g, "Client.send", tmp_path)) == {method[0], heading[0]}

    g = build_from_json(extraction, directed=True)
    from graphify.affected import SeedResolutionError, format_affected

    with pytest.raises(SeedResolutionError) as exc:
        format_affected(g, "Client.send")
    assert "pkg.py:L2" in str(exc.value) and "guide.md:L3" in str(exc.value)
    report = format_affected(g, "pkg.py::Client.send")
    assert "- .request() [calls] pkg.py:L5" in report


def test_qualified_resolution_looks_up_owners_once_per_member(monkeypatch):
    """With N classes all labeled `Client`, each owning `.send()`, owner
    lookups grow with N, not N squared: matching members are grouped by owner
    once. Checking every owner against every member took 19 s at 2,000."""
    from graphify import affected

    calls = []
    original_owners, original_members = affected._Ownership.owners, affected._Ownership.members

    def owners(self, node_id):
        calls.append(node_id)
        return original_owners(self, node_id)

    def members(self, node_id):
        calls.append(node_id)
        return original_members(self, node_id)

    monkeypatch.setattr(affected._Ownership, "owners", owners)
    monkeypatch.setattr(affected._Ownership, "members", members)
    n = 500
    for graph_class in (nx.DiGraph, nx.Graph):
        g = graph_class()
        for i in range(n):
            g.add_node(f"c{i}", label="Client", source_file=f"m{i}.py", source_location="L1")
            g.add_node(f"s{i}", label=".send()", source_file=f"m{i}.py", source_location="L2")
            g.add_edge(f"c{i}", f"s{i}", relation="method", _src=f"c{i}", _tgt=f"s{i}")
        calls.clear()
        assert len(affected.resolve_seed_candidates(g, "Client.send")) == n
        assert len(calls) <= 3 * n, f"{len(calls)} ownership lookups for {n} owners"


def test_qualified_resolution_reads_undirected_edges_once():
    """On an undirected graph ownership is indexed from one whole-graph edge
    pass per resolution. Rescanning every edge per lookup made `C0.run` on
    4,000 classes take 17 s."""
    from graphify.affected import resolve_seed

    g = nx.Graph()
    for i in range(300):
        g.add_node(f"c{i}", label=f"C{i}", source_file="pkg.py", source_location=f"L{i}")
        g.add_node(f"m{i}", label=".run()", source_file="pkg.py", source_location=f"L{i}")
        g.add_edge(f"c{i}", f"m{i}", relation="method", _src=f"c{i}", _tgt=f"m{i}")
    view = g.edges
    scans = []

    class _CountingEdges:
        def __call__(self, nbunch=None, data=False, default=None):
            if nbunch is None:
                scans.append(1)
            return view(nbunch, data=data, default=default)

        def __iter__(self):
            scans.append(1)
            return iter(view)

        def __getattr__(self, name):
            return getattr(view, name)

    # `Graph.edges` is a cached_property, so the instance dict holds the view.
    g.__dict__["edges"] = _CountingEdges()
    assert resolve_seed(g, "C0.run") == "m0"
    assert resolve_seed(g, "pkg.py::C7.run") == "m7"
    assert len(scans) <= 2, f"{len(scans)} whole-graph edge scans for two lookups"


def test_resolve_seed_keeps_dotfile_names_intact():
    """Only a method label (".name()") answers to its name without the dot.
    `Config()` resolved to the class before; a `.config` dotfile must not tie it."""
    from graphify.affected import resolve_seed

    g = nx.DiGraph()
    g.add_node("config_class", label="Config", source_file="config.py", source_location="L1")
    g.add_node("dotconfig", label=".config", source_file=".config", source_location="L1")
    assert resolve_seed(g, "Config()") == "config_class"
    assert resolve_seed(g, "Config") == "config_class"
    assert resolve_seed(g, ".config") == "dotconfig"


def _run_affected(monkeypatch, tmp_path, seed):
    import pytest

    gp = tmp_path / "graph.json"
    gp.write_text(
        json.dumps(json_graph.node_link_data(_two_send_graph(), edges="links")), encoding="utf-8"
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "affected", seed, "--graph", str(gp)])
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    return exc.value.code


def test_affected_cli_qualified_seed_reports_its_own_callers(monkeypatch, tmp_path, capsys):
    gp = tmp_path / "graph.json"
    gp.write_text(
        json.dumps(json_graph.node_link_data(_two_send_graph(), edges="links")), encoding="utf-8"
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    for seed, caller, other in (
        ("Client.send", "caller()", "async_caller()"),
        ("pkg/_client.py::AsyncClient.send", "async_caller()", "caller()"),
    ):
        monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "affected", seed, "--graph", str(gp)])
        mainmod.main()
        out = capsys.readouterr().out
        assert "Affected nodes for .send()" in out, seed
        assert f"- {caller} [calls] app.py:" in out, seed
        assert f"- {other} " not in out, seed


def test_affected_cli_ambiguous_seed_lists_candidates_and_fails(monkeypatch, tmp_path, capsys):
    for seed in ("send", ".send()", "pkg/_client.py::send"):
        code = _run_affected(monkeypatch, tmp_path, seed)
        captured = capsys.readouterr()
        assert code not in (0, None), seed
        assert captured.out == "", seed
        assert "pkg/_client.py:L20" in captured.err, seed
        assert "pkg/_client.py:L60" in captured.err, seed
        assert "client_send" in captured.err and "async_send" in captured.err, seed
        assert "Affected nodes for" not in captured.err, seed
    # The bare name also lists the nested function, and never the stub.
    _run_affected(monkeypatch, tmp_path, "send")
    err = capsys.readouterr().err
    assert "pkg/asgi.py:L8" in err
    assert "(id: send)" not in err


def test_affected_cli_missing_seed_fails(monkeypatch, tmp_path, capsys):
    for seed in ("no_such_symbol", "Client.nope", "pkg/missing.py::Client.send"):
        code = _run_affected(monkeypatch, tmp_path, seed)
        captured = capsys.readouterr()
        assert code not in (0, None), seed
        assert captured.out == "", seed
        assert f"No unique node match for {seed}" in captured.err, seed
