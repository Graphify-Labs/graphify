"""Unit tests for the streaming DB push (graph.json -> UNWIND, no NetworkX).

The --push paths used to json.loads the whole graph.json and rebuild a
NetworkX graph before pushing; on a 1.87GB graph.json the pusher peaked at
~5.3GB RSS and was OOM-killed on a 7.6GB box during loading. The streaming
twins (stream_push_to_neo4j / stream_push_to_falkordb) read the file
incrementally and feed the same batched UNWIND writers, so peak memory is
batch-scale. These tests pin:

- end-state parity with the in-memory push: identical Cypher text, identical
  rows in identical per-label/per-relation order, identical counts (batch
  interleaving ACROSS labels may differ; MERGE makes that irrelevant);
- the ordering guarantee: every node batch is sent before any edge batch,
  even when the "links" array physically precedes "nodes" in the file;
- a memory-shaped assertion: tracemalloc peak on a 50k-node file stays at
  batch scale, nowhere near file size;
- the malformed-file error tone.

Fake drivers come from test_batched_push - no server, no network.
"""
from __future__ import annotations

import json
import sys
import tracemalloc

import pytest
from networkx.readwrite import json_graph

from tests.test_batched_push import _fake_falkordb_module, _fake_neo4j_module


# ---------------------------------------------------------------------------
# Synthetic node-link corpus
# ---------------------------------------------------------------------------

def _synthetic_raw(n_nodes: int = 12, *, edge_key: str = "links") -> dict:
    """A node-link dict with several labels/relations and filterable attrs."""
    nodes = []
    for i in range(n_nodes):
        nodes.append({
            "id": f"n-{i}",
            "file_type": ["python", "markdown", "x) DETACH DELETE n //"][i % 3],
            "label": f"Node {i}",
            "community": i % 4,
            "degree": i,
            "score": i / 10,
            "flagged": i % 2 == 0,
            "tags": ["a", "b"],       # non-scalar: must not reach props
            "meta": {"x": 1},         # non-scalar: must not reach props
            "_private": "hidden",     # underscore: must not reach props
        })
    edges = []
    for i in range(n_nodes - 1):
        edges.append({
            "source": f"n-{i}",
            "target": f"n-{i + 1}",
            "key": 0,
            "relation": ["calls", "imports", "reads-from"][i % 3],
            "confidence": "INFERRED",
            "weights": [1, 2],        # non-scalar: must not reach props
            "_shadow": "x",           # underscore: must not reach props
        })
    return {
        "directed": True,
        "multigraph": True,
        "graph": {"name": "synthetic"},
        "nodes": nodes,
        edge_key: edges,
    }


def _write(tmp_path, raw: dict):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _build_graph(raw: dict):
    """Load the dict exactly the way the old CLI push path did."""
    data = raw if "links" in raw or "edges" not in raw else dict(raw, links=raw["edges"])
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return json_graph.node_link_graph(data)


# ---------------------------------------------------------------------------
# Capture helpers - both fakes record (cypher, {"rows": batch}) pairs.
# ---------------------------------------------------------------------------

def _split(recorded):
    node_q = [(c, p) for c, p in recorded if "MERGE (n:" in c]
    edge_q = [(c, p) for c, p in recorded if "MATCH (a {id: row.src})" in c]
    return node_q, edge_q


def _node_group(cypher: str) -> str:
    return cypher.split("MERGE (n:")[1].split(" ")[0]


def _edge_group(cypher: str) -> str:
    return cypher.split("MERGE (a)-[r:")[1].split("]")[0]


def _grouped(queries, group_of):
    """{group: (concatenated rows, chunk-size sequence)} for parity checks."""
    rows: dict[str, list] = {}
    chunks: dict[str, list[int]] = {}
    for cypher, params in queries:
        g = group_of(cypher)
        batch = params["rows"]
        rows.setdefault(g, []).extend(batch)
        chunks.setdefault(g, []).append(len(batch))
    return rows, chunks


def _assert_same_wire(old, new):
    """Same groups, same rows in the same per-group order, same chunking."""
    for group_of, kind in ((_node_group, "node"), (_edge_group, "edge")):
        old_q, new_q = old[kind], new[kind]
        old_rows, old_chunks = _grouped(old_q, group_of)
        new_rows, new_chunks = _grouped(new_q, group_of)
        assert new_rows == old_rows
        assert new_chunks == old_chunks
    # Identical Cypher text (as a set - only cross-group interleaving differs).
    assert {c for c, _ in new["node"] + new["edge"]} == \
           {c for c, _ in old["node"] + old["edge"]}


# ---------------------------------------------------------------------------
# End-state parity vs the in-memory push
# ---------------------------------------------------------------------------

def test_falkordb_stream_matches_in_memory_push(tmp_path, monkeypatch):
    raw = _synthetic_raw()
    path = _write(tmp_path, raw)
    communities = {7: ["n-1"], 9: ["n-5"]}

    recorded_old: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded_old))
    from graphify.export import push_to_falkordb, stream_push_to_falkordb
    result_old = push_to_falkordb(_build_graph(raw), uri="localhost:6379",
                                  communities=communities, batch_size=3)

    recorded_new: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded_new))
    result_new = stream_push_to_falkordb(path, uri="localhost:6379",
                                         communities=communities, batch_size=3)

    assert result_new == result_old == {"nodes": 12, "edges": 11}
    old_n, old_e = _split(recorded_old)
    new_n, new_e = _split(recorded_new)
    _assert_same_wire({"node": old_n, "edge": old_e},
                      {"node": new_n, "edge": new_e})
    # The communities sidecar override lands identically.
    for queries in (old_n, new_n):
        by_id = {r["id"]: r["props"] for _, p in queries for r in p["rows"]}
        assert by_id["n-1"]["community"] == 7
        assert by_id["n-5"]["community"] == 9
        assert by_id["n-0"]["community"] == 0  # from the node's own attribute
        # Attr filtering is byte-for-byte the old shape.
        assert "tags" not in by_id["n-0"] and "_private" not in by_id["n-0"]


def test_neo4j_stream_matches_in_memory_push(tmp_path, monkeypatch):
    raw = _synthetic_raw()
    path = _write(tmp_path, raw)

    recorded_old: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module(recorded_old))
    from graphify.export import push_to_neo4j, stream_push_to_neo4j
    result_old = push_to_neo4j(_build_graph(raw), uri="bolt://x", user="neo4j",
                               password="pw", batch_size=4)

    recorded_new: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module(recorded_new))
    result_new = stream_push_to_neo4j(path, uri="bolt://x", user="neo4j",
                                      password="pw", batch_size=4)

    assert result_new == result_old == {"nodes": 12, "edges": 11}
    old_n, old_e = _split(recorded_old)
    new_n, new_e = _split(recorded_new)
    _assert_same_wire({"node": old_n, "edge": old_e},
                      {"node": new_n, "edge": new_e})
    # Multigraph edge "key" is a NetworkX edge key, not a property - the
    # in-memory path never sent it and the streaming path must not either.
    for _, p in new_e:
        for row in p["rows"]:
            assert "key" not in row["props"]
            assert row["props"].get("confidence") == "INFERRED"


def test_stream_reads_legacy_edges_key(tmp_path, monkeypatch):
    raw = _synthetic_raw(edge_key="edges")
    path = _write(tmp_path, raw)

    recorded_old: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded_old))
    from graphify.export import push_to_falkordb, stream_push_to_falkordb
    result_old = push_to_falkordb(_build_graph(raw), uri="localhost:6379",
                                  batch_size=100)

    recorded_new: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded_new))
    result_new = stream_push_to_falkordb(path, uri="localhost:6379", batch_size=100)

    assert result_new == result_old == {"nodes": 12, "edges": 11}
    old_n, old_e = _split(recorded_old)
    new_n, new_e = _split(recorded_new)
    _assert_same_wire({"node": old_n, "edge": old_e},
                      {"node": new_n, "edge": new_e})


def test_stream_empty_graph_object(tmp_path, monkeypatch):
    path = tmp_path / "graph.json"
    path.write_text('{"directed": true, "multigraph": false, "graph": {}, '
                    '"nodes": [], "links": []}', encoding="utf-8")
    recorded: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded))
    from graphify.export import stream_push_to_falkordb
    assert stream_push_to_falkordb(path, uri="localhost:6379") == {"nodes": 0, "edges": 0}
    assert recorded == []


# ---------------------------------------------------------------------------
# Ordering guarantee: nodes fully precede edges
# ---------------------------------------------------------------------------

def test_nodes_fully_precede_edges_even_when_links_come_first(tmp_path, monkeypatch):
    raw = _synthetic_raw()
    reordered = {"links": raw["links"], "directed": True, "multigraph": True,
                 "graph": {}, "nodes": raw["nodes"]}
    path = _write(tmp_path, reordered)

    recorded: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded))
    from graphify.export import stream_push_to_falkordb
    result = stream_push_to_falkordb(path, uri="localhost:6379", batch_size=3)

    assert result == {"nodes": 12, "edges": 11}
    kinds = ["node" if "MERGE (n:" in c else "edge" for c, _ in recorded]
    first_edge = kinds.index("edge")
    assert all(k == "node" for k in kinds[:first_edge])
    assert all(k == "edge" for k in kinds[first_edge:])


# ---------------------------------------------------------------------------
# Memory: batch-scale, nowhere near file size
# ---------------------------------------------------------------------------

def _discarding_falkordb_module():
    """A falkordb stand-in that drops every batch - recording them would keep
    the whole graph alive in the test and mask the very leak being measured."""
    import types

    class _Graph:
        def query(self, cypher, params):
            pass

    class FalkorDB:
        def __init__(self, host, port, username=None, password=None):
            pass

        def select_graph(self, name):
            return _Graph()

    mod = types.ModuleType("falkordb")
    mod.FalkorDB = FalkorDB
    return mod


def test_stream_push_memory_stays_at_batch_scale(tmp_path, monkeypatch):
    n = 50_000
    path = tmp_path / "graph.json"
    pad = "x" * 400  # bulk per node so 50k nodes make a tens-of-MB file
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"directed": true, "multigraph": false, "graph": {}, "nodes": [')
        for i in range(n):
            if i:
                fh.write(", ")
            fh.write(json.dumps({"id": f"n-{i}", "file_type": "python",
                                 "label": f"Node {i}", "description": pad}))
        fh.write('], "links": [')
        for i in range(n - 1):
            if i:
                fh.write(", ")
            fh.write(json.dumps({"source": f"n-{i}", "target": f"n-{i + 1}",
                                 "relation": "calls", "note": pad[:80]}))
        fh.write(']}')
    file_size = path.stat().st_size
    assert file_size > 25 * 1024 * 1024  # the wall being simulated is real

    monkeypatch.setitem(sys.modules, "falkordb", _discarding_falkordb_module())
    from graphify.export import stream_push_to_falkordb

    tracemalloc.start()
    try:
        result = stream_push_to_falkordb(path, uri="localhost:6379", batch_size=500)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert result == {"nodes": n, "edges": n - 1}
    # Batch scale: 500 rows of ~500B plus the fixed 64KiB read buffer is
    # well under 1MB of live data; 8MB leaves headroom for allocator noise
    # while staying an order of magnitude below the file itself. The old
    # path held the whole json.loads tree + a NetworkX graph (measured
    # ~5.3GB peak for a 1.87GB file in production).
    assert peak < 8 * 1024 * 1024, f"peak {peak} bytes is not batch-scale"
    assert peak < file_size // 4


# ---------------------------------------------------------------------------
# Malformed files: house error tone
# ---------------------------------------------------------------------------

def test_truncated_file_raises_house_style_valueerror(tmp_path, monkeypatch):
    raw = json.dumps(_synthetic_raw())
    path = tmp_path / "graph.json"
    path.write_text(raw[: len(raw) // 2], encoding="utf-8")
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module([]))
    from graphify.export import stream_push_to_falkordb

    with pytest.raises(ValueError, match=r"not valid node-link JSON near byte \d+"):
        stream_push_to_falkordb(path, uri="localhost:6379")


def test_non_object_top_level_raises_house_style_valueerror(tmp_path, monkeypatch):
    path = tmp_path / "graph.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module([]))
    from graphify.export import stream_push_to_falkordb

    with pytest.raises(ValueError) as exc:
        stream_push_to_falkordb(path, uri="localhost:6379")
    msg = str(exc.value)
    assert msg.startswith(str(path))  # names the file the user must open
    assert "expected a top-level JSON object" in msg


def test_non_dict_node_entry_raises_house_style_valueerror(tmp_path, monkeypatch):
    path = tmp_path / "graph.json"
    path.write_text('{"nodes": [42], "links": []}', encoding="utf-8")
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module([]))
    from graphify.export import stream_push_to_falkordb

    with pytest.raises(ValueError, match=r'every "nodes" entry must be an object'):
        stream_push_to_falkordb(path, uri="localhost:6379")


# ---------------------------------------------------------------------------
# CLI wiring: --push streams; the NetworkX loader is never touched
# ---------------------------------------------------------------------------

def _run_export_in_process(monkeypatch, argv: list[str]):
    from graphify import cli
    monkeypatch.setattr(sys, "argv", ["graphify"] + argv)
    with pytest.raises(SystemExit) as exc:
        cli.dispatch_command("export")
    return exc.value.code


def test_cli_push_streams_without_building_networkx(tmp_path, monkeypatch, capsys):
    path = _write(tmp_path, _synthetic_raw())
    monkeypatch.chdir(tmp_path)
    recorded: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded))

    # If the CLI ever rebuilds the in-memory graph on a --push, that IS the
    # 5.3GB memory wall coming back - fail loudly.
    def _wall(*a, **k):
        raise AssertionError("push must not build a NetworkX graph")
    monkeypatch.setattr(json_graph, "node_link_graph", _wall)

    code = _run_export_in_process(
        monkeypatch,
        ["export", "falkordb", "--push", "localhost:6379", "--graph", str(path)],
    )

    assert code == 0
    assert "Pushed to FalkorDB: 12 nodes, 11 edges" in capsys.readouterr().out
    assert recorded  # batches actually went to the (fake) driver


def test_cli_push_reports_malformed_graph_in_house_tone(tmp_path, monkeypatch, capsys):
    path = tmp_path / "graph.json"
    path.write_text('{"nodes": [{"id": "a"', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module([]))

    code = _run_export_in_process(
        monkeypatch,
        ["export", "falkordb", "--push", "localhost:6379", "--graph", str(path)],
    )

    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("error: ")
    assert "not valid node-link JSON" in err


def test_cli_neo4j_push_still_requires_password(tmp_path, monkeypatch, capsys):
    path = _write(tmp_path, _synthetic_raw())
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module([]))

    code = _run_export_in_process(
        monkeypatch,
        ["export", "neo4j", "--push", "bolt://x", "--graph", str(path)],
    )

    assert code == 1
    assert "error: --password required for --push" in capsys.readouterr().err
