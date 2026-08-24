"""--graph option parsing across query / affected / path / explain.

The four commands each grew their own copy of the option loop, in two different
parse styles, and only `affected` ever handled the `--graph=PATH` form — the
others silently dropped the token, so an explicitly selected graph was ignored
and the user queried the default graph with no warning. A trailing valueless
`--graph` was silently dropped by all four, same bug class. One shared
pre-pass (`cli._parse_graph_option`) keeps the four surfaces honest.

The `--graph PATH` cases are characterization: they passed before the shared
parser and must keep passing after it. The `--graph=PATH` and valueless cases
pin the fix.
"""
from __future__ import annotations

import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    """A graph distinctive enough that output proves WHICH graph was loaded:
    the default graphify-out/graph.json does not exist in tmp cwd, so loading
    the explicit graph is the only way these labels can appear."""
    graph = nx.DiGraph()
    graph.add_node("alpha", label="AlphaFn", source_file="alpha.py", source_location="L1")
    graph.add_node("beta", label="BetaFn", source_file="beta.py", source_location="L2")
    graph.add_edge("alpha", "beta", relation="calls", context="call", confidence="EXTRACTED")
    graph_path = tmp_path / "somewhere" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(
        json.dumps(json_graph.node_link_data(graph, edges="links")), encoding="utf-8"
    )
    return graph_path


# argv builders: (name, positionals-before-options)
_COMMANDS = {
    "query": ["query", "AlphaFn"],
    "affected": ["affected", "BetaFn"],
    "path": ["path", "AlphaFn", "BetaFn"],
    "explain": ["explain", "AlphaFn"],
}

# A string that only appears when the explicit graph actually loaded.
_PROOF = {
    "query": "AlphaFn",
    "affected": "AlphaFn",  # affected BetaFn reports the caller AlphaFn
    "path": "AlphaFn",
    "explain": "AlphaFn",
}


def _run(monkeypatch, tmp_path, argv):
    monkeypatch.chdir(tmp_path)  # default graphify-out/graph.json cannot exist
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", *argv])
    mainmod.main()


@pytest.mark.parametrize("command", sorted(_COMMANDS))
def test_graph_space_form_honored(command, monkeypatch, tmp_path, capsys):
    """Characterization: the space-separated form worked before the shared
    parser and must keep working after it."""
    graph_path = _write_graph(tmp_path)
    _run(monkeypatch, tmp_path, [*_COMMANDS[command], "--graph", str(graph_path)])
    out = capsys.readouterr().out
    assert _PROOF[command] in out


@pytest.mark.parametrize("command", sorted(_COMMANDS))
def test_graph_equals_form_honored(command, monkeypatch, tmp_path, capsys):
    """The `=` form was silently swallowed by query/path/explain (only
    affected parsed it), leaving the user on the default graph unannounced."""
    graph_path = _write_graph(tmp_path)
    _run(monkeypatch, tmp_path, [*_COMMANDS[command], f"--graph={graph_path}"])
    out = capsys.readouterr().out
    assert _PROOF[command] in out


@pytest.mark.parametrize("command", sorted(_COMMANDS))
def test_trailing_valueless_graph_errors(command, monkeypatch, tmp_path, capsys):
    """A trailing `--graph` with no value used to be silently dropped — the
    same silent-selection-loss class as the `=` form. Now exit 2 with an
    actionable message."""
    _write_graph(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        _run(monkeypatch, tmp_path, [*_COMMANDS[command], "--graph"])
    assert excinfo.value.code == 2
    assert "--graph requires a path" in capsys.readouterr().err


@pytest.mark.parametrize("command", sorted(_COMMANDS))
def test_graph_equals_empty_errors(command, monkeypatch, tmp_path, capsys):
    """`--graph=` (empty value) gets the same rejection as a valueless
    `--graph`. An empty path resolves to the cwd — a directory — which only
    two of the four commands guard with a .json suffix check; path/explain
    would crash reading it. Rejecting at parse time keeps all four uniform."""
    _write_graph(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        _run(monkeypatch, tmp_path, [*_COMMANDS[command], "--graph="])
    assert excinfo.value.code == 2
    assert "--graph requires a path" in capsys.readouterr().err


def test_own_flags_still_parsed_after_pre_pass(monkeypatch, tmp_path, capsys):
    """The pre-pass strips only graph tokens; each command's own flag loop
    still sees its flags (query --budget here as the representative)."""
    graph_path = _write_graph(tmp_path)
    _run(
        monkeypatch,
        tmp_path,
        ["query", "AlphaFn", "--budget", "50", f"--graph={graph_path}"],
    )
    out = capsys.readouterr().out
    assert "AlphaFn" in out
