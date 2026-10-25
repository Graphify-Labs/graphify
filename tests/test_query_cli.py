"""Tests for graphify query CLI context filtering."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build", source_file="build.py", source_location="L1", community=1)
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", context="call")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED", context="import")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return graph_path


def test_query_cli_explicit_context_filter(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--context", "call", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "Context: call (explicit)" in out
    assert "cluster" in out
    assert "build" not in out


def test_query_cli_heuristic_context_filter(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "who calls extract", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "Context: call (heuristic)" in out
    assert "cluster" in out
    assert "build" not in out


def _write_calls_graph(tmp_path):
    """A single directed `calls` edge on an (on-disk) undirected graph.json,

    the standard `graphify extract`/`update` output shape (`"directed":
    false`, direction implied only by each link's source/target).
    """
    G = nx.Graph()
    G.add_node("caller", label="caller_fn", source_file="a.py", source_location="L1", community=0)
    G.add_node("callee", label="callee_fn", source_file="b.py", source_location="L1", community=1)
    G.add_edge("caller", "callee", relation="calls", confidence="EXTRACTED", context="call")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return graph_path


def test_query_cli_preserves_calls_direction_when_seeded_on_callee(monkeypatch, tmp_path, capsys):
    """`graphify query` must render `calls` edges caller->callee regardless of
    which endpoint the query term matches first.

    The graph `query` loads is undirected (so BFS/DFS can explore both
    callers and callees of the seed), so `G.neighbors()` returns `caller_fn`
    as a neighbor of `callee_fn` with no direction of its own. Before the
    fix, the renderer assumed the BFS/DFS visit order (u, v) was the edge's
    (source, target), so seeding on the callee printed the edge backwards:
    "callee_fn --calls--> caller_fn". graph.json's `source`/`target` for this
    edge stay correct on disk either way; only the query rendering was wrong.
    """
    graph_path = _write_calls_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "callee_fn", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "caller_fn --calls" in out
    assert "callee_fn --calls" not in out


def test_query_cli_preserves_calls_direction_when_seeded_on_caller(monkeypatch, tmp_path, capsys):
    """Same edge, seeded from the caller side — must stay correct too."""
    graph_path = _write_calls_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "caller_fn", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "caller_fn --calls" in out
    assert "callee_fn --calls" not in out


def test_query_cli_rejects_oversized_graph(monkeypatch, tmp_path, capsys):
    """#F4: query CLI must refuse to parse a graph.json that exceeds the cap."""
    import pytest

    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 16)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--graph", str(graph_path)],
    )
    with pytest.raises(SystemExit):
        mainmod.main()
    err = capsys.readouterr().err
    assert "exceeds" in err
    assert "byte cap" in err


# Project query defaults share the selected graph's identity, not process CWD.
def _capture_query_settings(monkeypatch, graph_path, flags):
    captured = {}

    def query(_graph, _question, **kwargs):
        captured["execution"] = kwargs
        return "captured query result"

    def log(**kwargs):
        captured["log"] = kwargs

    monkeypatch.setattr("graphify.serve._query_graph_text", query)
    monkeypatch.setattr("graphify.querylog.log_query", log)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify", "query", "extract", "--graph", str(graph_path), *flags,
    ])
    mainmod.main()
    return captured


@pytest.mark.parametrize("settings, flags, expected", [
    ("", [], (2000, 2)),
    ("query_budget=4000\n", [], (4000, 2)),
    ("query_depth=4\n", [], (2000, 4)),
    ("query_budget=4000\nquery_depth=4\n", [], (4000, 4)),
    ("query_budget=4000\nquery_depth=4\n", ["--budget", "5000"], (5000, 4)),
    ("query_budget=4000\nquery_depth=4\n", ["--depth=6"], (4000, 6)),
    ("query_budget=4000\nquery_depth=4\n", ["--budget=5000", "--depth", "1"], (5000, 1)),
    ("query_budget=4000\n", ["--budget=0"], (0, 2)),
    ("query_budget=4000\n", ["--budget", "-2"], (-2, 2)),
    ("query_budget=4000\n", ["--budget"], (4000, 2)),
    ("", ["--budget", "3000", "--budget=5000", "--depth=3", "--depth", "5"], (5000, 5)),
])
def test_query_settings_precedence_and_execution_log_agree(monkeypatch, tmp_path, settings, flags, expected):
    project = tmp_path / "project"
    out = project / "graphify-out"
    out.mkdir(parents=True)
    graph_path = _write_graph(out)
    if settings:
        (project / ".graphifyrc").write_text(settings, encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    (other / ".graphifyrc").write_text("query_budget=9999\nquery_depth=6\n", encoding="utf-8")
    monkeypatch.chdir(other)
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", "graphify-out")
    captured = _capture_query_settings(monkeypatch, graph_path, flags)
    for consumer in ["execution", "log"]:
        assert (captured[consumer]["token_budget"], captured[consumer]["depth"]) == expected
    assert captured["execution"]["seed_root"] == project


@pytest.mark.parametrize("flags", [
    ["--depth"], ["--depth="], ["--depth", "no"], ["--depth=0"],
    ["--depth=-1"], ["--depth=7"], ["--depth", "1.5"],
])
def test_query_rejects_invalid_explicit_depth(monkeypatch, tmp_path, capsys, flags):
    with pytest.raises(SystemExit) as error:
        _capture_query_settings(monkeypatch, _write_graph(tmp_path), flags)
    assert error.value.code == 1
    assert "--depth" in capsys.readouterr().err


@pytest.mark.parametrize("settings, flags, expected", [
    ("query_budget=4000\nquery_depth=7\n", [], (2000, 2)),
    ("query_depth=4\nviz_node_limit=-1\n", ["--budget=5000"], (5000, 2)),
    ("query_budget=4000\nmalformed\n", ["--depth=3"], (2000, 3)),
    ("query_budget=4000\nquery_depth=no\n", ["--budget=5000", "--depth=3"], (5000, 3)),
])
def test_bad_project_settings_warn_once_and_discard_all_defaults(monkeypatch, tmp_path, capsys, settings, flags, expected):
    (tmp_path / ".graphifyrc").write_text(settings, encoding="utf-8")
    captured = _capture_query_settings(monkeypatch, _write_graph(tmp_path), flags)
    for consumer in ["execution", "log"]:
        assert (captured[consumer]["token_budget"], captured[consumer]["depth"]) == expected
    error = capsys.readouterr().err
    assert error.count("warning:") == 1
    assert str(tmp_path / ".graphifyrc") in error
    assert "Invalid" in error


def test_query_settings_read_error_preserves_explicit_values(monkeypatch, tmp_path, capsys):
    def unreadable(root):
        assert root == tmp_path
        raise OSError("unreadable project settings")

    monkeypatch.setattr("graphify.rcfile.load_graphifyrc", unreadable)
    captured = _capture_query_settings(monkeypatch, _write_graph(tmp_path), ["--budget=5000", "--depth=3"])
    assert captured["execution"]["token_budget"] == captured["log"]["token_budget"] == 5000
    assert captured["execution"]["depth"] == captured["log"]["depth"] == 3
    assert "unreadable project settings" in capsys.readouterr().err


def test_query_settings_unexpected_error_is_not_hidden(monkeypatch, tmp_path):
    def unexpected(_root):
        raise RuntimeError("unexpected loader failure")

    monkeypatch.setattr("graphify.rcfile.load_graphifyrc", unexpected)
    with pytest.raises(RuntimeError, match="unexpected loader failure"):
        _capture_query_settings(monkeypatch, _write_graph(tmp_path), [])


@pytest.mark.parametrize("graph_error", ["missing", "invalid-json"])
def test_graph_errors_precede_settings_loading(monkeypatch, tmp_path, capsys, graph_error):
    (tmp_path / ".graphifyrc").write_text("query_depth=bad\n", encoding="utf-8")
    graph_path = tmp_path / "graph.json"
    if graph_error == "invalid-json":
        graph_path.write_text("{broken", encoding="utf-8")

    def should_not_load(_root):
        pytest.fail("settings loaded before graph validation")

    monkeypatch.setattr("graphify.rcfile.load_graphifyrc", should_not_load)
    with pytest.raises(SystemExit) as error:
        _capture_query_settings(monkeypatch, graph_path, [])
    assert error.value.code == 1
    assert "warning:" not in capsys.readouterr().err


@pytest.mark.parametrize("configured, graph_dir, expected_root", [
    ("graphify-out", "project/graphify-out", "project"),
    ("cache/graphs", "project/cache/graphs", "project"),
    ("", "project/graphify-out", "project/graphify-out"),
    (".", "project/graphify-out", "project/graphify-out"),
    ("..", "project/graphify-out", "project/graphify-out"),
    ("../graphs", "project/graphs", "project/graphs"),
    ("cache/../graphs", "project/graphs", "project/graphs"),
    ("cache/..", "project/cache", "project/cache"),
    ("cache/graphs/..", "project/cache", "project/cache"),
    ("elsewhere", "project/graphify-out", "project/graphify-out"),
    ("ABSOLUTE", "project/graphify-out", "project/graphify-out"),
])
def test_query_root_suffix_is_native_lexical_and_cwd_independent(monkeypatch, tmp_path, configured, graph_dir, expected_root):
    from graphify.cli import _graph_root_for

    if configured == "ABSOLUTE":
        configured = str(tmp_path / "project" / "graphify-out")
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", configured)
    directory = tmp_path / graph_dir
    directory.mkdir(parents=True)
    gp = directory / "graph.json"
    for cwd in [tmp_path, directory]:
        monkeypatch.chdir(cwd)
        assert _graph_root_for(gp) == tmp_path / expected_root


@pytest.mark.parametrize("marker_kind", ["missing", "empty", "dot", "parent", "relative", "file", "nul", "bom-absolute"])
def test_query_root_marker_is_absolute_directory_or_falls_back(monkeypatch, tmp_path, marker_kind):
    from graphify.cli import _graph_root_for

    project = tmp_path / "selected"
    project.mkdir()
    directory = tmp_path / "shared" / "custom"
    directory.mkdir(parents=True)
    gp = directory / "graph.json"
    not_dir = tmp_path / "plain-file"
    not_dir.write_text("file", encoding="utf-8")
    values = {"empty": " \n", "dot": ".", "parent": "..", "relative": "selected",
              "file": str(not_dir), "nul": "\0", "bom-absolute": "\ufeff  " + str(project) + " \n"}
    if marker_kind != "missing":
        (directory / ".graphify_root").write_text(values[marker_kind], encoding="utf-8")
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", "graphify-out")
    for cwd in [tmp_path, directory]:
        monkeypatch.chdir(cwd)
        expected = project if marker_kind == "bom-absolute" else directory
        assert _graph_root_for(gp) == expected


@pytest.mark.parametrize("failure", [OSError("unreadable"), UnicodeError("bad encoding"), ValueError("invalid path")])
def test_query_root_expected_marker_failures_fall_back(monkeypatch, tmp_path, failure):
    from graphify.cli import _graph_root_for

    directory = tmp_path / "graphify-out"
    directory.mkdir()
    marker = directory / ".graphify_root"
    original = Path.read_text

    def fail_marker(path, *args, **kwargs):
        if path == marker:
            raise failure
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_marker)
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", "graphify-out")
    assert _graph_root_for(directory / "graph.json") == tmp_path


def test_query_root_unexpected_marker_error_propagates(monkeypatch, tmp_path):
    from graphify.cli import _graph_root_for

    def unexpected(*_args, **_kwargs):
        raise TypeError("unexpected marker failure")

    monkeypatch.setattr(Path, "read_text", unexpected)
    with pytest.raises(TypeError, match="unexpected marker failure"):
        _graph_root_for(tmp_path / "graph.json")


def test_query_root_absolute_symlink_marker_resolves_to_project(monkeypatch, tmp_path):
    from graphify.cli import _graph_root_for

    project = tmp_path / "project"
    project.mkdir()
    link = tmp_path / "project-link"
    try:
        link.symlink_to(project, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable")
    directory = tmp_path / "output"
    directory.mkdir()
    (directory / ".graphify_root").write_text(str(link), encoding="utf-8")
    assert _graph_root_for(directory / "graph.json") == project


@pytest.mark.parametrize("operation, failure", [
    ("resolve", OSError("resolve denied")),
    ("resolve", ValueError("invalid marker path")),
    ("resolve", RuntimeError("symlink loop")),
    ("is_dir", OSError("stat denied")),
])
def test_query_root_path_operation_failures_fall_back(monkeypatch, tmp_path, operation, failure):
    from graphify.cli import _graph_root_for

    directory = tmp_path / "graphify-out"
    directory.mkdir()
    target = tmp_path / "selected"
    target.mkdir()
    (directory / ".graphify_root").write_text(str(target), encoding="utf-8")
    original = getattr(Path, operation)

    def fail_target(path, *args, **kwargs):
        if path == target:
            raise failure
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, fail_target)
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", "graphify-out")
    assert _graph_root_for(directory / "graph.json") == tmp_path


@pytest.mark.parametrize("layout", ["absolute-marker", "nested-relative-output"])
def test_query_reads_custom_output_selected_project_settings(monkeypatch, tmp_path, layout):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".graphifyrc").write_text("query_budget=4000\nquery_depth=4\n", encoding="utf-8")
    if layout == "absolute-marker":
        directory = tmp_path / "shared-output"
        directory.mkdir()
        (directory / ".graphify_root").write_text(str(project), encoding="utf-8")
        monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", str(directory))
    else:
        directory = project / "cache" / "graphs"
        directory.mkdir(parents=True)
        monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", "cache/graphs")
    graph_path = _write_graph(directory)
    monkeypatch.chdir(tmp_path)
    captured = _capture_query_settings(monkeypatch, graph_path, [])
    for consumer in ["execution", "log"]:
        assert (captured[consumer]["token_budget"], captured[consumer]["depth"]) == (4000, 4)
    assert captured["execution"]["seed_root"] == project


@pytest.mark.parametrize("operation", ["read_text", "is_dir"])
def test_query_root_unexpected_runtime_error_propagates(monkeypatch, tmp_path, operation):
    from graphify.cli import _graph_root_for

    directory = tmp_path / "graphify-out"
    directory.mkdir()
    target = tmp_path / "project"
    target.mkdir()
    marker = directory / ".graphify_root"
    marker.write_text(str(target), encoding="utf-8")
    original = getattr(Path, operation)

    def unexpected(path, *args, **kwargs):
        if path == (marker if operation == "read_text" else target):
            raise RuntimeError("unexpected marker operation")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, unexpected)
    with pytest.raises(RuntimeError, match="unexpected marker operation"):
        _graph_root_for(directory / "graph.json")
