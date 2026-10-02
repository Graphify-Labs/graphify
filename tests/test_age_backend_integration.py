"""Tier-3 integration tests for graphify.age_backend (docs/AGE_PLAN.md
Phase 6, optional): fetching a graph from live AGE and handing it to the
exact same scoring/formatting code the file backend uses. The central
claim under test is "behavior stays identical to the file backend" --
these tests push the *same* graph to both a local graph.json and a live
AGE instance, run `graphify query`/`path`/`explain` against each, and
diff the output.

    docker run -d --name graphify-age -p 5432:5432 \\
        -e POSTGRES_PASSWORD=graphify_test \\
        apache/age@sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb
    uv run pytest tests/test_age_backend_integration.py -q

Host/port/db/user/password: AGE_HOST / AGE_PORT / AGE_DB / AGE_USER /
AGE_PASSWORD, matching the other AGE live-suite files' convention.
"""
from __future__ import annotations

import json
import os

import networkx as nx
import pytest
from networkx.readwrite import json_graph

psycopg = pytest.importorskip("psycopg")

import graphify.__main__ as mainmod  # noqa: E402
from graphify import age_backend as ab  # noqa: E402
from graphify.exporters.graphdb import push_to_age  # noqa: E402

HOST = os.environ.get("AGE_HOST", "localhost")
PORT = int(os.environ.get("AGE_PORT", "5432"))
DBNAME = os.environ.get("AGE_DB", "postgres")
USER = os.environ.get("AGE_USER", "postgres")
PASSWORD = os.environ.get("AGE_PASSWORD", "graphify_test")
GRAPH_NAME = "graphify_backend_test"


def _conninfo() -> str:
    return f"host={HOST} port={PORT} dbname={DBNAME} user={USER} password={PASSWORD}"


def _connect_or_skip():
    try:
        conn = psycopg.connect(_conninfo(), connect_timeout=5)
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
        conn.rollback()
    except Exception as e:  # pragma: no cover - depends on local environment
        pytest.skip(f"no AGE-enabled Postgres reachable at {HOST}:{PORT} ({e})")
    return conn


def _drop_graph_if_exists(conn, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s;", (name,))
        if cur.fetchone()[0]:
            cur.execute("SELECT drop_graph(%s, true);", (name,))
    conn.commit()


@pytest.fixture()
def conn():
    c = _connect_or_skip()
    _drop_graph_if_exists(c, GRAPH_NAME)
    yield c
    _drop_graph_if_exists(c, GRAPH_NAME)
    c.close()


def _build_graph() -> nx.Graph:
    """A small graph exercising labels, source locations, relations,
    confidence, and community -- enough surface for query/path/explain's
    scoring and formatting to have something to chew on."""
    G = nx.Graph()
    G.add_node("n_extract", label="extract", file_type="code",
               source_file="extract.py", source_location="L10", community=0)
    G.add_node("n_cluster", label="cluster", file_type="code",
               source_file="cluster.py", source_location="L5", community=0)
    G.add_node("n_build", label="build", file_type="code",
               source_file="build.py", source_location="L1", community=1)
    G.add_edge("n_extract", "n_cluster", relation="calls", confidence="EXTRACTED",
               _src="n_extract", _tgt="n_cluster")
    G.add_edge("n_cluster", "n_build", relation="imports", confidence="EXTRACTED",
               _src="n_cluster", _tgt="n_build")
    return G


def _write_graph_json(G: nx.Graph, path) -> None:
    path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))


def _push(G: nx.Graph) -> None:
    """--full-props, and the communities dict matching the "community"
    attrs _build_graph() already set: push_to_age() derives a node's
    community from the `communities` clustering result passed at push
    time (mirroring push_to_neo4j/push_to_falkordb), not from a
    pre-existing "community" node attribute, so a bare push_to_age(G, ...)
    would silently blank it out here. --full-props additionally includes
    file_type, which the lean schema omits by design (docs/AGE_SCHEMA.md)
    - both are pushed here so the file/AGE comparison below is apples to
    apples, not a rediscovery of the already-documented lean/full tradeoff.
    """
    communities = {
        cid: [n for n, d in G.nodes(data=True) if d.get("community") == cid]
        for cid in {d.get("community") for _, d in G.nodes(data=True)}
    }
    push_to_age(G, conninfo=_conninfo(), graph_name=GRAPH_NAME,
                communities=communities, full_props=True)


def _strip_graph_header(output: str) -> str:
    """The one line that's *supposed* to differ (file path vs. age://...)."""
    return "\n".join(
        line for line in output.splitlines() if not line.startswith("Graph:")
    )


def _run_cli(monkeypatch, capsys, argv: list[str]) -> str:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", *argv])
    mainmod.main()
    return capsys.readouterr().out


def test_fetch_graph_from_age_matches_pushed_graph(conn):
    G = _build_graph()
    _push(G)
    fetched = ab.fetch_graph_from_age(_conninfo(), GRAPH_NAME)

    assert set(fetched.nodes()) == set(G.nodes())
    for nid in G.nodes():
        assert fetched.nodes[nid]["label"] == G.nodes[nid]["label"]
        assert fetched.nodes[nid]["source_file"] == G.nodes[nid]["source_file"]

    fetched_edges = {
        (d["_src"], d["_tgt"], d["relation"]) for _, _, d in fetched.edges(data=True)
    }
    expected_edges = {
        (d["_src"], d["_tgt"], d["relation"]) for _, _, d in G.edges(data=True)
    }
    assert fetched_edges == expected_edges


def test_query_cli_age_backend_matches_file_backend(monkeypatch, tmp_path, capsys, conn):
    G = _build_graph()
    _push(G)
    graph_path = tmp_path / "graph.json"
    _write_graph_json(G, graph_path)

    file_out = _run_cli(monkeypatch, capsys, ["query", "who calls cluster", "--graph", str(graph_path)])
    age_out = _run_cli(monkeypatch, capsys, [
        "query", "who calls cluster", "--age", _conninfo(), "--graph-name", GRAPH_NAME,
    ])

    assert _strip_graph_header(file_out) == _strip_graph_header(age_out)
    assert "cluster" in file_out  # sanity: the query actually found something


def test_path_cli_age_backend_matches_file_backend(monkeypatch, tmp_path, capsys, conn):
    G = _build_graph()
    _push(G)
    graph_path = tmp_path / "graph.json"
    _write_graph_json(G, graph_path)

    file_out = _run_cli(monkeypatch, capsys, ["path", "extract", "build", "--graph", str(graph_path)])
    age_out = _run_cli(monkeypatch, capsys, [
        "path", "extract", "build", "--age", _conninfo(), "--graph-name", GRAPH_NAME,
    ])

    assert file_out == age_out  # `path` never prints a Graph: header to strip
    assert "Shortest path" in file_out


def test_explain_cli_age_backend_matches_file_backend(monkeypatch, tmp_path, capsys, conn):
    G = _build_graph()
    _push(G)
    graph_path = tmp_path / "graph.json"
    _write_graph_json(G, graph_path)

    file_out = _run_cli(monkeypatch, capsys, ["explain", "cluster", "--graph", str(graph_path)])
    age_out = _run_cli(monkeypatch, capsys, [
        "explain", "cluster", "--age", _conninfo(), "--graph-name", GRAPH_NAME,
    ])

    assert file_out == age_out
    assert "Node: cluster" in file_out
    assert "Connections" in file_out


def test_query_cli_age_backend_reports_clear_error_on_missing_graph(monkeypatch, capsys, conn):
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, capsys, [
            "query", "anything", "--age", _conninfo(), "--graph-name", "does_not_exist_graph",
        ])
    err = capsys.readouterr().err
    assert "could not fetch graph" in err
