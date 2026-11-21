"""Exercise cache creation, use, and recovery through graphify query."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

import networkx as nx
from networkx.readwrite import json_graph
import pytest

from graphify import __main__ as mainmod, paths, query_snapshot
from graphify.cli import EXIT_AMBIGUOUS, EXIT_NOT_FOUND


@pytest.fixture
def query_cli(monkeypatch, tmp_path, capsys):
    cache = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setenv("LOCALAPPDATA", str(cache))
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG_DISABLE", "1")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    def run(path, question, *args):
        monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "query", question, "--graph", str(path), *args])
        status = 0
        try:
            mainmod.main()
        except SystemExit as exc:
            status = exc.code
        out, err = capsys.readouterr()
        return status, out, err

    return run, cache


def _write(path: Path, graph: nx.Graph) -> None:
    path.write_text(json.dumps(json_graph.node_link_data(graph, edges="links")), encoding="utf-8")


def _fixture():
    graph = nx.Graph()
    graph.add_node("one", label="ParseNóde()", source_file="src/one.py", source_location="L1")
    graph.add_node("two", label="ParseNóde()", source_file="src/two.py", source_location="L9")
    graph.add_node("서울", label="서울()", source_file="src/three.py", source_location="L17")
    graph.add_node("driver", label="driver()", source_file="src/one.py", rationale="bounded retry")
    graph.add_node("literal", label="Alpha.Beta", attributes={"request": {"mode": "delta literal"}})
    graph.add_node("id", label="ID", source_file="src/id.py")
    graph.add_edge("one", "driver", relation="calls", _src="driver", _tgt="one")
    graph.add_edge("two", "driver", relation="inherits", context="type")
    graph.add_edge("one", "서울", relation="references", context="return_type")
    graph.add_edge("two", "two", relation="calls", context="call")
    return graph


def _deny_json(_path):
    pytest.fail("a snapshot cache hit read graph.json")


def test_warm_snapshot_matches_normal_query_without_loading_json(query_cli, monkeypatch, tmp_path):
    run, cache = query_cli
    path = tmp_path / "graph.json"
    _write(path, _fixture())
    cases = [
        ("what calls the parser", ("--seed", "one", "--context", "call")),
        ("why bounded retry", ("--depth", "1")),
        ("src/one.py::ParseNóde", ("--dfs", "--budget", "100")),
        ("서울", ("--context", "return")),
        ("ID", ("--no-doc-demotion",)),
        ("delta literal", ()),
        ("ParseNóde", ()),
        ("zzzz-missing", ()),
    ]
    expected = [run(path, question, *args) for question, args in cases]
    assert [status for status, _, _ in expected][-2:] == [EXIT_AMBIGUOUS, EXIT_NOT_FOUND]
    assert "driver() --calls" in expected[0][1]
    assert run(path, cases[0][0], *cases[0][1], "--snapshot") == expected[0]
    assert len(list(cache.rglob("*.sqlite3"))) == 1
    monkeypatch.setattr(paths, "read_graph_json", _deny_json)
    assert [run(path, question, *args, "--snapshot") for question, args in cases] == expected


def test_snapshot_rebuilds_when_unicode_data_changes(query_cli, monkeypatch, tmp_path):
    run, cache = query_cli
    path = tmp_path / "graph.json"
    _write(path, _fixture())
    expected = run(path, "bounded retry")
    assert run(path, "bounded retry", "--snapshot") == expected
    (first,) = cache.rglob("*.sqlite3")

    monkeypatch.setattr(query_snapshot, "unidata_version", "0.0.0")
    assert run(path, "bounded retry", "--snapshot") == expected
    assert len(set(cache.rglob("*.sqlite3")) - {first}) == 1
    monkeypatch.setattr(paths, "read_graph_json", _deny_json)
    assert run(path, "bounded retry", "--snapshot") == expected


def test_snapshot_recovers_from_same_size_replacement_and_broken_table(query_cli, monkeypatch, tmp_path):
    run, cache = query_cli
    path = tmp_path / "graph.json"
    graph = _fixture()
    _write(path, graph)
    assert run(path, "bounded retry", "--snapshot")[0] == 0
    first_generation = set(cache.rglob("*.sqlite3"))
    assert len(first_generation) == 1

    previous_stat = path.stat()
    replacement = tmp_path / "replacement.json"
    graph.nodes["driver"]["rationale"] = "digital token"
    _write(replacement, graph)
    assert replacement.stat().st_size == previous_stat.st_size
    os.utime(replacement, ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns))
    replacement.replace(path)
    expected = run(path, "digital token")
    assert expected[0] == 0 and "driver()" in expected[1]
    assert run(path, "digital token", "--snapshot") == expected
    assert run(path, "bounded retry", "--snapshot")[0] == EXIT_NOT_FOUND

    # Leave the metadata intact so opening the cache succeeds, then fail in
    # the middle of query evaluation and verify the canonical path repairs it.
    current_generation = set(cache.rglob("*.sqlite3")) - first_generation
    assert len(current_generation) == 1
    index, = current_generation
    with closing(sqlite3.connect(index)) as db:
        with db:
            db.execute("DROP TABLE search")
    assert run(path, "digital token", "--snapshot") == expected
    monkeypatch.setattr(paths, "read_graph_json", _deny_json)
    assert run(path, "digital token", "--snapshot") == expected


def test_unavailable_snapshot_directory_preserves_query_answer(query_cli, monkeypatch, tmp_path):
    run, _ = query_cli
    path = tmp_path / "graph.json"
    _write(path, _fixture())
    expected = run(path, "bounded retry")
    assert expected[0] == 0

    def unavailable_cache(_path, _identity):
        raise RuntimeError("cannot resolve cache directory")

    monkeypatch.setattr(query_snapshot, "_cache_file", unavailable_cache)
    assert run(path, "bounded retry", "--snapshot") == expected


def test_snapshot_build_failure_preserves_seeded_answer(query_cli, tmp_path):
    run, cache = query_cli
    path = tmp_path / "graph.json"
    graph = _fixture()
    # A seeded query can render its neighborhood without reading every node's
    # search text. Bad data on an unrelated node only affects the optional build.
    graph.add_node("unrelated", source_file=3)
    _write(path, graph)
    expected = run(path, "parser", "--seed", "one")
    assert expected[0] == 0
    assert run(path, "parser", "--seed", "one", "--snapshot") == expected
    assert not list(cache.rglob("*.sqlite3"))


@pytest.mark.parametrize(("field", "value"), [("nodes", "bad"), ("signatures", None)])
def test_malformed_projection_metadata_recovers_through_json(query_cli, monkeypatch, tmp_path, field, value):
    run, cache = query_cli
    path = tmp_path / "graph.json"
    _write(path, _fixture())
    args = ("--context", "call")
    expected = run(path, "bounded retry", *args)
    assert expected[0] == 0
    assert run(path, "bounded retry", *args, "--snapshot") == expected

    index, = cache.rglob("*.sqlite3")
    with closing(sqlite3.connect(index)) as db, db:
        metadata = json.loads(db.execute("SELECT value FROM metadata").fetchone()[0])
        metadata[field] = value
        db.execute("UPDATE metadata SET value = ?", (json.dumps(metadata),))

    assert run(path, "bounded retry", *args, "--snapshot") == expected
    monkeypatch.setattr(paths, "read_graph_json", _deny_json)
    assert run(path, "bounded retry", *args, "--snapshot") == expected


def test_case_variant_normalized_label_keeps_json_scoring(query_cli, tmp_path):
    run, cache = query_cli
    path = tmp_path / "graph.json"
    graph = nx.Graph()
    graph.add_node("opaque", label="different", norm_label="OwnerToken")
    _write(path, graph)

    expected = run(path, "token")
    assert expected[0] == 0
    assert run(path, "token", "--snapshot") == expected
    assert run(path, "token", "--snapshot") == expected
    assert not list(cache.rglob("*.sqlite3"))


@pytest.mark.parametrize(("question", "args"), [
    ("find bounded retry \udc80", ()),
    ("what calls the parser", ("--seed", "one\udc80", "--seed", "one")),
])
def test_unencodable_input_keeps_json_query_behavior(query_cli, tmp_path, question, args):
    run, cache = query_cli
    path = tmp_path / "graph.json"
    _write(path, _fixture())
    assert run(path, "bounded retry", "--snapshot")[0] == 0
    index, = cache.rglob("*.sqlite3")
    written = index.stat().st_mtime_ns

    expected = run(path, question, *args)
    assert expected[0] == 0
    assert run(path, question, *args, "--snapshot") == expected
    assert index.stat().st_mtime_ns == written


@pytest.mark.parametrize("constructor", [nx.DiGraph, nx.MultiGraph])
def test_unsupported_graph_shapes_use_existing_cli(query_cli, tmp_path, constructor):
    run, cache = query_cli
    path = tmp_path / "graph.json"
    _write(path, constructor(_fixture()))
    assert run(path, "bounded retry", "--snapshot") == run(path, "bounded retry")
    assert not list(cache.rglob("*.sqlite3"))
