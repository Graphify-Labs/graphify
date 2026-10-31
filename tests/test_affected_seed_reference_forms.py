"""#4792 — `affected` and `query --seed` rejected the reference forms `explain`
already resolved, and `affected` exited 0 on an ambiguous or unmatched seed.

`explain` resolves a `path::Symbol` reference (#3485) and a dotted Python name
(`pkg.mod.func`, #4366) to a single node. `affected` and `query --seed` answered
"No unique node match" for the very same string, so following the README's own
advice ("use the precise ID returned by the graph") forced a caller through
`explain` first merely to obtain an id. `affected` also exited 0 when the query
was ambiguous or matched nothing, so a script could not branch on the outcome
the README documents (3 = ambiguous, 4 = no match).

Regression shape: every assertion below fails on v8, where `resolve_seed`
returns None for the qualified forms and the CLI always exits 0.
"""
from __future__ import annotations

import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.affected import resolve_seed, resolve_seed_outcome


def _two_same_named_functions() -> nx.DiGraph:
    """Two `state` functions in different modules, plus one caller.

    The layout from the issue: a path-qualified seed must single one out, while
    the bare name is genuinely ambiguous and must stay unresolved.
    """
    g = nx.DiGraph()
    g.add_node("pkg", label="pkg", source_file="pkg/__init__.py", source_location="L1")
    g.add_node(
        "pkg_auth_mfa_state",
        label="state()",
        norm_label="state()",
        source_file="pkg/auth/mfa.py",
        source_location="L1",
    )
    g.add_node(
        "pkg_other_flow_state",
        label="state()",
        norm_label="state()",
        source_file="pkg/other/flow.py",
        source_location="L1",
    )
    g.add_node(
        "pkg_user_use",
        label="use()",
        norm_label="use()",
        source_file="pkg/user.py",
        source_location="L3",
    )
    g.add_edge("pkg_user_use", "pkg_auth_mfa_state", relation="calls",
               source_file="pkg/user.py", source_location="L4")
    return g


def test_resolve_seed_accepts_path_scoped_symbol():
    """`path::Symbol` resolves as it does in `explain` (#3485)."""
    g = _two_same_named_functions()
    assert resolve_seed(g, "pkg/auth/mfa.py::state") == "pkg_auth_mfa_state"


def test_resolve_seed_accepts_dotted_python_name():
    """`pkg.mod.func` resolves as it does in `explain` (#4366)."""
    g = _two_same_named_functions()
    assert resolve_seed(g, "pkg.auth.mfa.state") == "pkg_auth_mfa_state"


def test_resolve_seed_bare_ambiguous_name_still_returns_none():
    """A bare name shared by two modules stays unresolved — it must not guess."""
    g = _two_same_named_functions()
    assert resolve_seed(g, "state") is None


def test_resolve_seed_outcome_reports_rivals_for_ambiguous_name():
    """The ambiguity is reported so the CLI can exit 3 rather than 0."""
    g = _two_same_named_functions()
    seed, rivals = resolve_seed_outcome(g, "state")
    assert seed is None
    assert set(rivals) == {"pkg_auth_mfa_state", "pkg_other_flow_state"}


def test_resolve_seed_outcome_reports_no_rivals_for_a_miss():
    """A query that matches nothing is a miss (exit 4), not an ambiguity (exit 3)."""
    g = _two_same_named_functions()
    seed, rivals = resolve_seed_outcome(g, "nothing_like_this")
    assert seed is None
    assert rivals == []


def _write_graph(tmp_path, graph: nx.Graph) -> str:
    from graphify.paths import GRAPHIFY_OUT_NAME

    out_dir = tmp_path / "repo" / GRAPHIFY_OUT_NAME
    out_dir.mkdir(parents=True)
    gp = out_dir / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(graph, edges="links")), encoding="utf-8")
    return str(gp)


def _run_affected(monkeypatch, graph_path: str, query: str) -> int:
    """Run `graphify affected <query>` and return its exit code (0 when it returns)."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "affected", query, "--graph", graph_path]
    )
    try:
        mainmod.main()
    except SystemExit as exc:  # only the failure paths exit explicitly
        return int(exc.code or 0)
    return 0


def test_affected_cli_resolves_path_scoped_symbol(tmp_path, monkeypatch, capsys):
    """The exact repro from the issue: affected now resolves what explain resolves."""
    graph_path = _write_graph(tmp_path, _two_same_named_functions())

    code = _run_affected(monkeypatch, graph_path, "pkg/auth/mfa.py::state")

    out = capsys.readouterr().out
    assert code == 0
    assert "Affected nodes for state()" in out
    assert "use()" in out


def test_affected_cli_exits_3_on_ambiguous_seed(tmp_path, monkeypatch, capsys):
    """README documents exit 3 for an ambiguous name; affected used to exit 0."""
    from graphify.cli import EXIT_AMBIGUOUS

    graph_path = _write_graph(tmp_path, _two_same_named_functions())

    code = _run_affected(monkeypatch, graph_path, "state")

    err = capsys.readouterr().err
    assert code == EXIT_AMBIGUOUS
    assert err.startswith("Ambiguous:")
    # Both candidates must be named so the caller can pick one.
    assert "pkg/auth/mfa.py" in err
    assert "pkg/other/flow.py" in err


def test_affected_cli_exits_4_on_unmatched_seed(tmp_path, monkeypatch, capsys):
    """README documents exit 4 for no matching node; affected used to exit 0."""
    from graphify.cli import EXIT_NOT_FOUND

    graph_path = _write_graph(tmp_path, _two_same_named_functions())

    code = _run_affected(monkeypatch, graph_path, "nothing_like_this")

    err = capsys.readouterr().err
    assert code == EXIT_NOT_FOUND
    assert "No unique node match" in err
